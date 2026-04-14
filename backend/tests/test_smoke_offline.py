"""Offline smoke tests — fast, no Redis/MySQL/Qdrant/OpenAI.

The live integration suite is ``tests/test_smoke.py`` (requires
``FINANCEHUB_INTEGRATION_TESTS=1``).  This module keeps CI green without secrets.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from financehub_market_api.auth.database import Base, get_db
from financehub_market_api.auth.dependencies import AuthenticatedUser, get_current_user
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
from financehub_market_api.recommendations import RecommendationService

_TEST_USER = AuthenticatedUser(user_id="smoke-user-001", email="smoke@test.com")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


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


class _FakeRecommendationService:
    def generate_recommendation(
        self,
        payload: RecommendationGenerationRequest,
        *,
        user_id: str | None = None,
    ) -> RecommendationResponse:
        from financehub_market_api.recommendation.graph.runtime import (
            RecommendationGraphRuntime,
        )

        real_service = RecommendationService(
            graph_runtime=RecommendationGraphRuntime.with_deterministic_services()
        )
        return real_service.generate_recommendation(payload, user_id=user_id)

    def get_recommendation(self, risk_profile):
        from financehub_market_api.recommendation.graph.runtime import (
            RecommendationGraphRuntime,
        )

        real_service = RecommendationService(
            graph_runtime=RecommendationGraphRuntime.with_deterministic_services()
        )
        return real_service.get_recommendation(risk_profile)


class _FakeChatAgent:
    def stream(self, messages: list[dict[str, Any]]) -> Generator[Any, None, None]:
        yield from ()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure knowledge services read no env files."""
    from financehub_market_api.recommendation.compliance_knowledge import (
        service as compliance_mod,
    )
    from financehub_market_api.recommendation.product_knowledge import (
        service as product_mod,
    )
    from financehub_market_api.chat import recall_service as recall_mod

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


@pytest.fixture()
def authed_client() -> Generator[TestClient, None, None]:
    """TestClient with all external deps faked + authenticated user injected."""
    store = ChatSessionStore(_FakeChatRedis())
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_market_data_service] = _FakeMarketDataService
    app.dependency_overrides[get_recommendation_service] = _FakeRecommendationService
    app.dependency_overrides[get_chat_session_store] = lambda: store
    app.dependency_overrides[get_chat_agent] = _FakeChatAgent
    app.dependency_overrides[get_chat_history_recall_service] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def unauthed_client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_market_data_service] = _FakeMarketDataService
    app.dependency_overrides[get_recommendation_service] = _FakeRecommendationService
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ===================================================================
# Smoke: Application boots
# ===================================================================


def test_app_has_expected_routes() -> None:
    route_paths = {route.path for route in app.routes}
    for expected in (
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/me",
        "/api/market-overview",
        "/api/indices",
        "/api/stocks",
        "/api/recommendations/generate",
        "/api/chat/sessions",
    ):
        assert expected in route_paths, f"Missing route: {expected}"


# ===================================================================
# Smoke: Auth endpoints respond correctly
# ===================================================================


def test_register_and_login_roundtrip(unauthed_client: TestClient) -> None:
    reg = unauthed_client.post(
        "/api/auth/register",
        json={"email": "smoke@example.com", "password": "smoke123"},
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]

    login = unauthed_client.post(
        "/api/auth/login",
        json={"email": "smoke@example.com", "password": "smoke123"},
    )
    assert login.status_code == 200

    me = unauthed_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "smoke@example.com"


# ===================================================================
# Smoke: Protected endpoints reject unauthenticated requests
# ===================================================================


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/market-overview"),
        ("GET", "/api/indices"),
        ("GET", "/api/stocks"),
        ("POST", "/api/recommendations/generate"),
        ("POST", "/api/recommendations"),
        ("POST", "/api/chat/sessions"),
        ("GET", "/api/chat/sessions"),
    ],
)
def test_protected_endpoint_returns_401_without_auth(
    unauthed_client: TestClient, method: str, path: str
) -> None:
    response = unauthed_client.request(method, path)
    assert response.status_code == 401


# ===================================================================
# Smoke: Market data endpoints respond with auth
# ===================================================================


def test_market_overview_responds_200(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/market-overview")
    assert resp.status_code == 200
    assert resp.json()["asOfDate"] == "2026-04-13"
    assert resp.json()["metrics"][0]["label"] == "上证指数"


def test_indices_responds_200(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/indices")
    assert resp.status_code == 200
    assert "cards" in resp.json()


def test_stocks_responds_200(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/stocks")
    assert resp.status_code == 200
    assert "rows" in resp.json()


# ===================================================================
# Smoke: Chat CRUD
# ===================================================================


def test_chat_session_create_list_delete(authed_client: TestClient) -> None:
    create_resp = authed_client.post("/api/chat/sessions")
    assert create_resp.status_code == 200
    session_id = create_resp.json()["id"]

    list_resp = authed_client.get("/api/chat/sessions")
    assert list_resp.status_code == 200
    assert any(s["id"] == session_id for s in list_resp.json()["sessions"])

    delete_resp = authed_client.delete(f"/api/chat/sessions/{session_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    list_after = authed_client.get("/api/chat/sessions")
    assert all(s["id"] != session_id for s in list_after.json()["sessions"])


def test_chat_get_messages_for_new_session(authed_client: TestClient) -> None:
    session = authed_client.post("/api/chat/sessions").json()
    resp = authed_client.get(f"/api/chat/sessions/{session['id']}/messages")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []


def test_chat_unknown_session_returns_404(authed_client: TestClient) -> None:
    resp = authed_client.get("/api/chat/sessions/nonexistent/messages")
    assert resp.status_code == 404


# ===================================================================
# Smoke: Recommendation endpoint
# ===================================================================


def _make_recommendation_payload(
    risk_profile: str = "balanced",
) -> dict[str, object]:
    return {
        "userIntentText": "我想要稳健投资",
        "historicalHoldings": [],
        "historicalTransactions": [],
        "includeAggressiveOption": True,
        "questionnaireAnswers": [],
        "conversationMessages": [],
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


def test_generate_recommendation_responds_200(authed_client: TestClient) -> None:
    resp = authed_client.post(
        "/api/recommendations/generate",
        json=_make_recommendation_payload(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["executionMode"] == "agent_assisted"
    assert body["recommendationStatus"] in ("ready", "limited", "blocked")
    assert "sections" in body


def test_post_recommendations_legacy_responds_200(authed_client: TestClient) -> None:
    resp = authed_client.post(
        "/api/recommendations",
        json={"riskProfile": "conservative"},
    )
    assert resp.status_code == 200
    assert resp.json()["recommendationStatus"] in ("ready", "limited", "blocked")
