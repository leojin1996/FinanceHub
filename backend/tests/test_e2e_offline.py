"""Offline E2E-style tests — faked Redis/MySQL/Qdrant/OpenAI.

For real-stack flows see ``tests/test_e2e.py`` with
``FINANCEHUB_INTEGRATION_TESTS=1``.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from financehub_market_api.auth.database import Base, get_db
from financehub_market_api.auth.models import User  # noqa: F401
from financehub_market_api.chat.router import (
    get_chat_agent,
    get_chat_history_recall_service,
    get_chat_session_store,
)
from financehub_market_api.chat.store import ChatSessionStore
from financehub_market_api.main import (
    app,
    get_market_data_service,
    get_recommendation_service,
)
from financehub_market_api.models import (
    IndicesResponse,
    MarketOverviewResponse,
    MetricCard,
    RecommendationGenerationRequest,
    RecommendationResponse,
    StocksResponse,
    TrendPoint,
)
from financehub_market_api.recommendation.graph.runtime import (
    GraphServices,
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendations import RecommendationService


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


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


class _FakeChatRedis:
    def __init__(self) -> None:
        self._hashes: dict[str, dict[bytes, bytes]] = {}
        self._lists: dict[str, list[bytes]] = {}
        self._zsets: dict[str, dict[str, float]] = {}

    def hset(self, key: str, mapping: dict[bytes, bytes]) -> int:
        existing = self._hashes.setdefault(key, {})
        existing.update(mapping)
        return len(mapping)

    def hgetall(self, key: str) -> dict[bytes, bytes]:
        return dict(self._hashes.get(key, {}))

    def delete(self, key: str) -> int:
        removed = 0
        if self._hashes.pop(key, None) is not None:
            removed = 1
        if self._lists.pop(key, None) is not None:
            removed = 1
        return removed

    def rpush(self, key: str, *values: bytes) -> int:
        lst = self._lists.setdefault(key, [])
        lst.extend(values)
        return len(lst)

    def lrange(self, key: str, start: int, stop: int) -> list[bytes]:
        lst = self._lists.get(key, [])
        return list(lst[start:]) if stop == -1 else list(lst[start : stop + 1])

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        zset = self._zsets.setdefault(key, {})
        added = sum(1 for m in mapping if m not in zset)
        zset.update(mapping)
        return added

    def zrevrange(self, key: str, start: int, stop: int) -> list[bytes]:
        zset = self._zsets.get(key, {})
        sorted_members = sorted(zset, key=lambda m: zset[m], reverse=True)
        return [m.encode("utf-8") for m in sorted_members[start : stop + 1]]

    def zrem(self, key: str, *members: str) -> int:
        zset = self._zsets.get(key, {})
        return sum(1 for m in members if zset.pop(m, None) is not None)


class _FakeChatAgent:
    def stream(self, messages: list[dict[str, Any]]) -> Generator[Any, None, None]:
        yield from ()


class _FakeChatHistoryRecallService:
    """Records all index and recall calls for assertion."""

    def __init__(self, recall_snippets: list[str] | None = None) -> None:
        self.index_calls: list[dict[str, str]] = []
        self.recall_calls: list[dict[str, object]] = []
        self._snippets = recall_snippets or []

    def index_user_message(
        self,
        *,
        user_id: str,
        session_id: str,
        message_id: str,
        content: str,
        created_at: str,
    ) -> None:
        self.index_calls.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "message_id": message_id,
                "content": content,
                "created_at": created_at,
            }
        )

    def recall(
        self,
        *,
        user_id: str,
        risk_profile: str,
        user_intent_text: str | None,
        latest_user_message: str | None,
        limit: int = 10,
    ) -> list[str]:
        self.recall_calls.append(
            {
                "user_id": user_id,
                "risk_profile": risk_profile,
                "user_intent_text": user_intent_text,
                "latest_user_message": latest_user_message,
                "limit": limit,
            }
        )
        return list(self._snippets)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    from financehub_market_api.chat import recall_service as recall_mod
    from financehub_market_api.recommendation.compliance_knowledge import (
        service as compliance_mod,
    )
    from financehub_market_api.recommendation.product_knowledge import (
        service as product_mod,
    )

    for key in (
        "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_URL",
        "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_URL",
        "FINANCEHUB_CHAT_RECALL_QDRANT_URL",
        "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(product_mod, "_iter_env_file_candidates", lambda: [])
    monkeypatch.setattr(compliance_mod, "_iter_env_file_candidates", lambda: [])
    monkeypatch.setattr(recall_mod, "_iter_env_file_candidates", lambda: [])
    get_recommendation_service.cache_clear()
    yield
    get_recommendation_service.cache_clear()


@pytest.fixture(autouse=True)
def _setup_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def _override() -> Session:  # type: ignore[type-arg]
        db = TestSession()
        try:
            yield db  # type: ignore[misc]
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _auth_header(client: TestClient, email: str, password: str = "test1234") -> dict[str, str]:
    """Register + return Authorization header."""
    reg = client.post("/api/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _recommendation_payload(
    risk_profile: str = "balanced",
    user_intent: str = "我想要稳健投资",
    conversation_messages: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "userIntentText": user_intent,
        "historicalHoldings": [],
        "historicalTransactions": [],
        "includeAggressiveOption": True,
        "questionnaireAnswers": [],
        "conversationMessages": conversation_messages or [],
        "riskAssessmentResult": {
            "baseProfile": risk_profile,
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
            "finalProfile": risk_profile,
            "totalScore": 60,
        },
    }


# ===================================================================
# E2E: Auth → Chat conversation flow
# ===================================================================


def test_auth_chat_full_conversation_flow() -> None:
    """Register → login → create session → send messages → verify history."""
    store = ChatSessionStore(_FakeChatRedis())
    recall_service = _FakeChatHistoryRecallService()
    app.dependency_overrides[get_chat_session_store] = lambda: store
    app.dependency_overrides[get_chat_agent] = _FakeChatAgent
    app.dependency_overrides[get_chat_history_recall_service] = lambda: recall_service
    app.dependency_overrides[get_market_data_service] = _FakeMarketDataService

    try:
        client = TestClient(app)
        headers = _auth_header(client, "chatuser@example.com")

        session = client.post("/api/chat/sessions", headers=headers).json()
        session_id = session["id"]
        assert session["title"] == "New Chat"

        resp1 = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "帮我分析一下最近的市场行情"},
            headers=headers,
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "我更关注低风险产品"},
            headers=headers,
        )
        assert resp2.status_code == 200

        messages = client.get(
            f"/api/chat/sessions/{session_id}/messages", headers=headers
        ).json()["messages"]
        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) == 2
        assert user_messages[0]["content"] == "帮我分析一下最近的市场行情"
        assert user_messages[1]["content"] == "我更关注低风险产品"

        assert len(recall_service.index_calls) == 2
        assert recall_service.index_calls[0]["content"] == "帮我分析一下最近的市场行情"
        assert recall_service.index_calls[1]["content"] == "我更关注低风险产品"
    finally:
        app.dependency_overrides.clear()


# ===================================================================
# E2E: Auth → Recommendation with user_id threading
# ===================================================================


def test_auth_recommendation_threads_user_id() -> None:
    """Register → generate recommendation → verify user_id propagated."""
    recall_service = _FakeChatHistoryRecallService(["用户之前提过要保本"])
    runtime = RecommendationGraphRuntime.with_deterministic_services()
    runtime_with_recall = RecommendationGraphRuntime(
        replace(runtime._services, chat_history_recall=recall_service)
    )
    service = RecommendationService(graph_runtime=runtime_with_recall)

    app.dependency_overrides[get_market_data_service] = _FakeMarketDataService
    app.dependency_overrides[get_recommendation_service] = lambda: service

    try:
        client = TestClient(app)
        headers = _auth_header(client, "recuser@example.com")

        resp = client.post(
            "/api/recommendations/generate",
            json=_recommendation_payload(
                conversation_messages=[
                    {
                        "role": "user",
                        "content": "最近市场波动很大",
                        "occurredAt": "2026-04-13T10:00:00Z",
                    }
                ],
            ),
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["recommendationStatus"] in ("ready", "limited", "blocked")
        assert body["agentTrace"]

        assert len(recall_service.recall_calls) == 1
        assert recall_service.recall_calls[0]["risk_profile"] == "balanced"
        assert recall_service.recall_calls[0]["latest_user_message"] == "最近市场波动很大"
        assert recall_service.recall_calls[0]["user_id"]
    finally:
        app.dependency_overrides.clear()


# ===================================================================
# E2E: Chat indexing → Recommendation recall full pipeline
# ===================================================================


def test_chat_index_then_recommendation_recall_pipeline() -> None:
    """
    Step 1: User chats → messages indexed via recall service
    Step 2: User requests recommendation → recall service queried with user_id
    Verifies the full data flow from chat to recommendation.
    """
    recall_service = _FakeChatHistoryRecallService(
        recall_snippets=["我更看重流动性", "三到五年持有期"]
    )
    store = ChatSessionStore(_FakeChatRedis())
    runtime = RecommendationGraphRuntime.with_deterministic_services()
    runtime_with_recall = RecommendationGraphRuntime(
        replace(runtime._services, chat_history_recall=recall_service)
    )
    rec_service = RecommendationService(graph_runtime=runtime_with_recall)

    app.dependency_overrides[get_chat_session_store] = lambda: store
    app.dependency_overrides[get_chat_agent] = _FakeChatAgent
    app.dependency_overrides[get_chat_history_recall_service] = lambda: recall_service
    app.dependency_overrides[get_market_data_service] = _FakeMarketDataService
    app.dependency_overrides[get_recommendation_service] = lambda: rec_service

    try:
        client = TestClient(app)
        headers = _auth_header(client, "pipeline@example.com")

        # --- Step 1: Chat ---
        session = client.post("/api/chat/sessions", headers=headers).json()
        client.post(
            f"/api/chat/sessions/{session['id']}/messages",
            json={"content": "我更看重流动性"},
            headers=headers,
        )
        client.post(
            f"/api/chat/sessions/{session['id']}/messages",
            json={"content": "我的持有期大概三到五年"},
            headers=headers,
        )
        assert len(recall_service.index_calls) == 2

        # --- Step 2: Recommendation ---
        resp = client.post(
            "/api/recommendations/generate",
            json=_recommendation_payload(
                user_intent="我想要稳健投资，关注流动性",
                conversation_messages=[
                    {
                        "role": "user",
                        "content": "帮我推荐适合的产品",
                        "occurredAt": "2026-04-13T11:00:00Z",
                    }
                ],
            ),
            headers=headers,
        )
        assert resp.status_code == 200

        assert len(recall_service.recall_calls) == 1
        recall_call = recall_service.recall_calls[0]
        assert recall_call["user_id"]
        assert recall_call["risk_profile"] == "balanced"
        assert recall_call["user_intent_text"] == "我想要稳健投资，关注流动性"
        assert recall_call["latest_user_message"] == "帮我推荐适合的产品"

        body = resp.json()
        assert body["recommendationStatus"] in ("ready", "limited", "blocked")
        assert body["agentTrace"]
    finally:
        app.dependency_overrides.clear()


# ===================================================================
# E2E: Multi-user isolation
# ===================================================================


def test_multi_user_chat_isolation() -> None:
    """Two users register, create sessions — each sees only their own."""
    store = ChatSessionStore(_FakeChatRedis())
    app.dependency_overrides[get_chat_session_store] = lambda: store
    app.dependency_overrides[get_chat_agent] = _FakeChatAgent
    app.dependency_overrides[get_chat_history_recall_service] = lambda: None
    app.dependency_overrides[get_market_data_service] = _FakeMarketDataService

    try:
        client = TestClient(app)
        headers_a = _auth_header(client, "alice@example.com")
        headers_b = _auth_header(client, "bob@example.com")

        sa1 = client.post("/api/chat/sessions", headers=headers_a).json()
        sa2 = client.post("/api/chat/sessions", headers=headers_a).json()
        sb1 = client.post("/api/chat/sessions", headers=headers_b).json()

        alice_sessions = client.get("/api/chat/sessions", headers=headers_a).json()["sessions"]
        bob_sessions = client.get("/api/chat/sessions", headers=headers_b).json()["sessions"]

        alice_ids = {s["id"] for s in alice_sessions}
        bob_ids = {s["id"] for s in bob_sessions}

        assert alice_ids == {sa1["id"], sa2["id"]}
        assert bob_ids == {sb1["id"]}
        assert alice_ids.isdisjoint(bob_ids)
    finally:
        app.dependency_overrides.clear()


def test_multi_user_recommendation_with_separate_recall() -> None:
    """Two users get recommendations — recall service receives correct user_id each time."""
    recall_service = _FakeChatHistoryRecallService(recall_snippets=["通用历史片段"])
    runtime = RecommendationGraphRuntime.with_deterministic_services()
    runtime_with_recall = RecommendationGraphRuntime(
        replace(runtime._services, chat_history_recall=recall_service)
    )
    rec_service = RecommendationService(graph_runtime=runtime_with_recall)

    app.dependency_overrides[get_market_data_service] = _FakeMarketDataService
    app.dependency_overrides[get_recommendation_service] = lambda: rec_service

    try:
        client = TestClient(app)
        headers_a = _auth_header(client, "alice2@example.com")
        headers_b = _auth_header(client, "bob2@example.com")

        resp_a = client.post(
            "/api/recommendations/generate",
            json=_recommendation_payload(),
            headers=headers_a,
        )
        resp_b = client.post(
            "/api/recommendations/generate",
            json=_recommendation_payload(risk_profile="conservative"),
            headers=headers_b,
        )

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert len(recall_service.recall_calls) == 2

        user_ids = {call["user_id"] for call in recall_service.recall_calls}
        assert len(user_ids) == 2

        risk_profiles = [call["risk_profile"] for call in recall_service.recall_calls]
        assert "balanced" in risk_profiles
        assert "conservative" in risk_profiles
    finally:
        app.dependency_overrides.clear()


# ===================================================================
# E2E: Graceful degradation when recall service is unavailable
# ===================================================================


def test_recommendation_succeeds_when_recall_service_unavailable() -> None:
    """Recommendation completes even when recall service raises."""

    class _FailingRecall:
        def recall(self, **_: object) -> list[str]:
            raise RuntimeError("qdrant is down")

    runtime = RecommendationGraphRuntime.with_deterministic_services()
    runtime_with_failing_recall = RecommendationGraphRuntime(
        replace(runtime._services, chat_history_recall=_FailingRecall())
    )
    rec_service = RecommendationService(graph_runtime=runtime_with_failing_recall)

    app.dependency_overrides[get_market_data_service] = _FakeMarketDataService
    app.dependency_overrides[get_recommendation_service] = lambda: rec_service

    try:
        client = TestClient(app)
        headers = _auth_header(client, "degrade@example.com")

        resp = client.post(
            "/api/recommendations/generate",
            json=_recommendation_payload(),
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["recommendationStatus"] in ("ready", "limited", "blocked")
        assert body["agentTrace"]
    finally:
        app.dependency_overrides.clear()


def test_chat_send_succeeds_when_recall_indexing_fails() -> None:
    """Chat message is saved and streamed even if recall indexing throws."""

    class _ExplodingRecall:
        def index_user_message(self, **_: object) -> None:
            raise RuntimeError("embedding service down")

    store = ChatSessionStore(_FakeChatRedis())
    app.dependency_overrides[get_chat_session_store] = lambda: store
    app.dependency_overrides[get_chat_agent] = _FakeChatAgent
    app.dependency_overrides[get_chat_history_recall_service] = lambda: _ExplodingRecall()
    app.dependency_overrides[get_market_data_service] = _FakeMarketDataService

    try:
        client = TestClient(app)
        headers = _auth_header(client, "indexfail@example.com")

        session = client.post("/api/chat/sessions", headers=headers).json()
        resp = client.post(
            f"/api/chat/sessions/{session['id']}/messages",
            json={"content": "测试消息"},
            headers=headers,
        )
        assert resp.status_code == 200

        messages = client.get(
            f"/api/chat/sessions/{session['id']}/messages", headers=headers
        ).json()["messages"]
        assert any(m["content"] == "测试消息" for m in messages)
    finally:
        app.dependency_overrides.clear()
