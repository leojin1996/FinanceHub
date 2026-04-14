from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from financehub_market_api.auth.database import Base, get_db
from financehub_market_api.auth.models import User  # noqa: F401 — registers User with Base.metadata
from financehub_market_api.main import app


@pytest.fixture(autouse=True)
def _setup_db():
    """Create a fresh per-test SQLite database so auth tests don't need MySQL."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=test_engine)

    def _override_get_db() -> Session:  # type: ignore[type-arg]
        db = TestSessionLocal()
        try:
            yield db  # type: ignore[misc]
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _register(client: TestClient, email: str = "test@example.com", password: str = "secret123"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def _login(client: TestClient, email: str = "test@example.com", password: str = "secret123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


class TestRegister:
    def test_successful_register(self, client: TestClient) -> None:
        resp = _register(client)
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["user"]["email"] == "test@example.com"
        assert body["user"]["id"]

    def test_duplicate_email_returns_409(self, client: TestClient) -> None:
        _register(client)
        resp = _register(client)
        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()

    def test_short_password_returns_422(self, client: TestClient) -> None:
        resp = _register(client, password="12345")
        assert resp.status_code == 422

    def test_email_is_case_insensitive(self, client: TestClient) -> None:
        _register(client, email="User@Example.COM")
        resp = _register(client, email="user@example.com")
        assert resp.status_code == 409


class TestLogin:
    def test_successful_login(self, client: TestClient) -> None:
        _register(client)
        resp = _login(client)
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"]
        assert body["user"]["email"] == "test@example.com"

    def test_wrong_password_returns_401(self, client: TestClient) -> None:
        _register(client)
        resp = _login(client, password="wrongpassword")
        assert resp.status_code == 401

    def test_unknown_email_returns_401(self, client: TestClient) -> None:
        resp = _login(client, email="nobody@example.com")
        assert resp.status_code == 401


class TestGetMe:
    def test_me_returns_user_info(self, client: TestClient) -> None:
        reg = _register(client).json()
        token = reg["access_token"]
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"

    def test_me_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401


class TestProtectedEndpoints:
    def test_market_overview_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/market-overview")
        assert resp.status_code == 401

    def test_chat_sessions_require_auth(self, client: TestClient) -> None:
        resp = client.post("/api/chat/sessions")
        assert resp.status_code == 401

    def test_chat_list_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/api/chat/sessions")
        assert resp.status_code == 401
