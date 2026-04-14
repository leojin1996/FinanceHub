"""Integration end-to-end tests — real Redis, MySQL, Qdrant, OpenAI.

Run::

    export FINANCEHUB_INTEGRATION_TESTS=1
    cd backend && python -m pytest tests/test_e2e.py -v

See ``tests/integration_support.py`` for environment variables.

Market data endpoints are stubbed in-process to avoid external market API flakiness.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from starlette.testclient import TestClient

import integration_support
from financehub_market_api.chat.recall_service import build_chat_history_recall_service_from_env
from financehub_market_api.main import app, get_market_data_service
from financehub_market_api.models import (
    IndicesResponse,
    MarketOverviewResponse,
    MetricCard,
    StocksResponse,
    TrendPoint,
)


def _integration_skip_reason() -> str | None:
    if not integration_support.integration_enabled():
        return "Set FINANCEHUB_INTEGRATION_TESTS=1 (see tests/integration_support.py)"
    errs = integration_support.collect_integration_prerequisite_errors()
    if errs:
        return " | ".join(errs)
    try:
        integration_support.ensure_chat_messages_qdrant_collection()
    except Exception as exc:
        return (
            f"Could not ensure Qdrant chat_messages collection: {exc}. "
            "Run: python -m scripts.seed_chat_messages_collection"
        )
    integration_support.clear_app_lru_caches()
    return None


_INTEGRATION_SKIP_REASON = _integration_skip_reason()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        _INTEGRATION_SKIP_REASON is not None,
        reason=_INTEGRATION_SKIP_REASON or "integration unavailable",
    ),
]


class _FakeMarketDataService:
    def get_market_overview(self) -> MarketOverviewResponse:
        return MarketOverviewResponse(
            asOfDate="2026-04-13",
            stale=False,
            metrics=[
                MetricCard(
                    label="上证指数",
                    value="3,250",
                    delta="+0.1%",
                    changeValue=3.2,
                    changePercent=0.1,
                    tone="positive",
                )
            ],
            chartLabel="上证指数",
            trendSeries=[TrendPoint(date="2026-04-13", value=3250.0)],
            topGainers=[],
            topLosers=[],
        )

    def get_indices(self) -> IndicesResponse:
        return IndicesResponse(asOfDate="2026-04-13", stale=False, cards=[])

    def get_stocks(self, *, query: str | None = None) -> StocksResponse:
        return StocksResponse(asOfDate="2026-04-13", stale=False, rows=[])


@pytest.fixture
def integration_client() -> Generator[TestClient, None, None]:
    integration_support.clear_app_lru_caches()
    app.dependency_overrides[get_market_data_service] = lambda: _FakeMarketDataService()
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.clear()
        integration_support.clear_app_lru_caches()


def _register(
    client: TestClient, suffix: str | None = None
) -> dict[str, Any]:
    token = suffix or uuid.uuid4().hex[:10]
    email = f"integ_e2e_{token}@example.com"
    password = "integration-e2e-9"
    reg = client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert reg.status_code == 200, reg.text
    body = reg.json()
    return {
        "client": client,
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
        "email": email,
        "user_id": body["user"]["id"],
        "password": password,
    }


@pytest.fixture
def user_a(integration_client: TestClient) -> Generator[dict[str, Any], None, None]:
    info = _register(integration_client, "a_" + uuid.uuid4().hex[:8])
    try:
        yield info
    finally:
        integration_support.delete_mysql_user_by_email(info["email"])


@pytest.fixture
def user_b(integration_client: TestClient) -> Generator[dict[str, Any], None, None]:
    info = _register(integration_client, "b_" + uuid.uuid4().hex[:8])
    try:
        yield info
    finally:
        integration_support.delete_mysql_user_by_email(info["email"])


def _consume_chat_stream(
    client: TestClient, session_id: str, headers: dict[str, str], content: str
) -> bytes:
    with client.stream(
        "POST",
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": content},
        headers=headers,
    ) as response:
        assert response.status_code == 200, response.text
        raw = b""
        for chunk in response.iter_bytes():
            raw += chunk
            if len(raw) > 256 * 1024:
                break
        return raw


def test_full_auth_chat_conversation_with_openai(user_a: dict[str, Any]) -> None:
    client, headers = user_a["client"], user_a["headers"]
    session_id = client.post("/api/chat/sessions", headers=headers).json()["id"]
    try:
        raw = _consume_chat_stream(
            client, session_id, headers, "用一句话介绍你自己。"
        )
        assert len(raw) > 0

        raw2 = _consume_chat_stream(
            client, session_id, headers, "谢谢，再见。"
        )
        assert len(raw2) > 0

        messages = client.get(
            f"/api/chat/sessions/{session_id}/messages", headers=headers
        ).json()["messages"]
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) >= 2
    finally:
        client.delete(f"/api/chat/sessions/{session_id}", headers=headers)
        integration_support.delete_redis_chat_keys_for_session(
            session_id, user_a["user_id"]
        )


def test_chat_message_indexed_to_qdrant_then_recalled(user_a: dict[str, Any]) -> None:
    """Background indexing writes to Qdrant; recall returns the distinctive phrase."""
    client, headers, user_id = (
        user_a["client"],
        user_a["headers"],
        user_a["user_id"],
    )
    marker = f"integration_marker_{uuid.uuid4().hex}"
    session_id = client.post("/api/chat/sessions", headers=headers).json()["id"]
    try:
        _consume_chat_stream(
            client,
            session_id,
            headers,
            f"请记住我的偏好关键词：{marker}，用于投资风格记录。",
        )
        recall = build_chat_history_recall_service_from_env()
        assert recall is not None
        snippets: list[str] = []
        for _ in range(15):
            snippets = recall.recall(
                user_id=user_id,
                risk_profile="balanced",
                user_intent_text=f"偏好关键词 {marker}",
                latest_user_message=f"查询关键词 {marker}",
                limit=10,
            )
            if any(marker in s for s in snippets):
                break
            time.sleep(1.0)
        else:
            pytest.fail(
                f"Qdrant recall did not return marker {marker!r} within 15s; "
                f"last snippets={snippets!r}"
            )
    finally:
        client.delete(f"/api/chat/sessions/{session_id}", headers=headers)
        integration_support.delete_redis_chat_keys_for_session(session_id, user_id)


def test_recommendation_with_user_id_and_conversation_context(user_a: dict[str, Any]) -> None:
    """Authenticated recommendation run; real agents + optional chat recall path."""
    client, headers = user_a["client"], user_a["headers"]
    payload = {
        "userIntentText": "我希望稳健配置，关注流动性。",
        "historicalHoldings": [],
        "historicalTransactions": [],
        "includeAggressiveOption": False,
        "questionnaireAnswers": [],
        "conversationMessages": [
            {
                "role": "user",
                "content": "我最多能接受小幅回撤。",
                "occurredAt": "2026-04-13T12:00:00Z",
            }
        ],
        "riskAssessmentResult": {
            "baseProfile": "stable",
            "dimensionLevels": {
                "capitalStability": "medium",
                "investmentExperience": "medium",
                "investmentHorizon": "medium",
                "returnObjective": "medium",
                "riskTolerance": "medium",
            },
            "dimensionScores": {
                "capitalStability": 12,
                "investmentExperience": 12,
                "investmentHorizon": 12,
                "returnObjective": 12,
                "riskTolerance": 12,
            },
            "finalProfile": "stable",
            "totalScore": 60,
        },
    }
    resp = client.post(
        "/api/recommendations/generate",
        json=payload,
        headers=headers,
        timeout=600.0,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["executionMode"] == "agent_assisted"
    assert body["recommendationStatus"] in ("ready", "limited", "blocked")


def test_multi_user_chat_session_isolation(
    integration_client: TestClient, user_a: dict[str, Any], user_b: dict[str, Any]
) -> None:
    ca, ha = user_a["client"], user_a["headers"]
    cb, hb = user_b["client"], user_b["headers"]

    sa = ca.post("/api/chat/sessions", headers=ha).json()["id"]
    sb = cb.post("/api/chat/sessions", headers=hb).json()["id"]
    try:
        ids_a = {s["id"] for s in ca.get("/api/chat/sessions", headers=ha).json()["sessions"]}
        ids_b = {s["id"] for s in cb.get("/api/chat/sessions", headers=hb).json()["sessions"]}
        assert sa in ids_a and sa not in ids_b
        assert sb in ids_b and sb not in ids_a
    finally:
        ca.delete(f"/api/chat/sessions/{sa}", headers=ha)
        cb.delete(f"/api/chat/sessions/{sb}", headers=hb)
        integration_support.delete_redis_chat_keys_for_session(sa, user_a["user_id"])
        integration_support.delete_redis_chat_keys_for_session(sb, user_b["user_id"])
