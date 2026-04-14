"""Integration smoke tests — real Redis, MySQL, Qdrant, and OpenAI.

Run::

    export FINANCEHUB_INTEGRATION_TESTS=1
    cd backend && python -m pytest tests/test_smoke.py -v

Prerequisites: see ``tests/integration_support.py``. Ensure the Qdrant chat
collection exists (``python -m scripts.seed_chat_messages_collection``).

Market overview / indices / stocks use a **fake** upstream in-process to avoid
flaky DoltHub/IndexData network calls; all other paths hit real infra.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any

import pytest
from starlette.testclient import TestClient

import integration_support
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


@pytest.fixture
def registered_user(integration_client: TestClient) -> Generator[dict[str, Any], None, None]:
    email = f"integ_smoke_{uuid.uuid4().hex[:12]}@example.com"
    password = "integration-smoke-9"
    reg = integration_client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert reg.status_code == 200, reg.text
    body = reg.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    info = {
        "client": integration_client,
        "headers": headers,
        "email": email,
        "user_id": body["user"]["id"],
    }
    try:
        yield info
    finally:
        integration_support.delete_mysql_user_by_email(email)


def test_app_has_expected_routes() -> None:
    route_paths = {route.path for route in app.routes}
    for expected in (
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/me",
        "/api/market-overview",
        "/api/recommendations/generate",
        "/api/chat/sessions",
    ):
        assert expected in route_paths


def test_auth_register_login_me(registered_user: dict[str, Any]) -> None:
    client = registered_user["client"]
    email = registered_user["email"]
    password = "integration-smoke-9"

    login = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email.strip().lower()


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("GET", "/api/market-overview", {}),
        ("POST", "/api/recommendations/generate", {"json": {}}),
        ("POST", "/api/chat/sessions", {}),
    ],
)
def test_protected_endpoints_401_without_auth(
    integration_client: TestClient, method: str, path: str, kwargs: dict[str, Any]
) -> None:
    response = integration_client.request(method, path, **kwargs)
    assert response.status_code == 401


def test_market_overview_with_auth(registered_user: dict[str, Any]) -> None:
    r = registered_user["client"].get(
        "/api/market-overview", headers=registered_user["headers"]
    )
    assert r.status_code == 200
    assert r.json()["asOfDate"] == "2026-04-13"


def test_chat_redis_roundtrip(registered_user: dict[str, Any]) -> None:
    client, headers = registered_user["client"], registered_user["headers"]
    created = client.post("/api/chat/sessions", headers=headers)
    assert created.status_code == 200
    session_id = created.json()["id"]

    listed = client.get("/api/chat/sessions", headers=headers)
    assert listed.status_code == 200
    assert any(s["id"] == session_id for s in listed.json()["sessions"])

    deleted = client.delete(f"/api/chat/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 200


def test_chat_stream_reaches_openai(registered_user: dict[str, Any]) -> None:
    """Consume SSE until bytes arrive (real ChatAgent + OpenAI)."""
    client, headers = registered_user["client"], registered_user["headers"]
    session_id = client.post("/api/chat/sessions", headers=headers).json()["id"]
    try:
        with client.stream(
            "POST",
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "用一句话说你好。"},
            headers=headers,
        ) as response:
            assert response.status_code == 200
            raw = b""
            for chunk in response.iter_bytes():
                raw += chunk
                if len(raw) > 64:
                    break
            assert b"event:" in raw or len(raw) > 0
    finally:
        client.delete(f"/api/chat/sessions/{session_id}", headers=headers)
        integration_support.delete_redis_chat_keys_for_session(
            session_id, registered_user["user_id"]
        )


def test_recommendation_generate_real_agents(registered_user: dict[str, Any]) -> None:
    """Full LangGraph + live OpenAI agents (may take several minutes)."""
    client, headers = registered_user["client"], registered_user["headers"]
    payload = {
        "userIntentText": "我想要稳健投资，请给一句简要建议。",
        "historicalHoldings": [],
        "historicalTransactions": [],
        "includeAggressiveOption": False,
        "questionnaireAnswers": [],
        "conversationMessages": [],
        "riskAssessmentResult": {
            "baseProfile": "balanced",
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
            "finalProfile": "balanced",
            "totalScore": 60,
        },
    }
    resp = client.post(
        "/api/recommendations/generate", json=payload, headers=headers, timeout=600.0
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["executionMode"] == "agent_assisted"
    assert body["recommendationStatus"] in ("ready", "limited", "blocked")
    assert body.get("agentTrace")
