from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from starlette.testclient import TestClient

from financehub_market_api.chat.models import ChatMessage
from financehub_market_api.chat.store import ChatSessionStore, ChatStoreError
from financehub_market_api.main import app
from financehub_market_api.chat.router import get_chat_session_store, get_chat_agent


# ---------------------------------------------------------------------------
# FakeChatRedis — satisfies ChatRedisLike (hash + list + sorted set)
# ---------------------------------------------------------------------------

class FakeChatRedis:
    """In-memory Redis fake that correctly merges fields on hset."""

    def __init__(self) -> None:
        self._hashes: dict[str, dict[bytes, bytes]] = {}
        self._lists: dict[str, list[bytes]] = {}
        self._zsets: dict[str, dict[str, float]] = {}

    # -- hash ----------------------------------------------------------------

    def hset(self, key: str, mapping: dict[bytes, bytes]) -> int:
        existing = self._hashes.setdefault(key, {})
        existing.update(mapping)
        return len(mapping)

    def hgetall(self, key: str) -> dict[bytes, bytes]:
        value = self._hashes.get(key)
        if value is None:
            return {}
        return dict(value)

    # -- generic -------------------------------------------------------------

    def delete(self, key: str) -> int:
        removed = 0
        if self._hashes.pop(key, None) is not None:
            removed = 1
        if self._lists.pop(key, None) is not None:
            removed = 1
        return removed

    # -- list ----------------------------------------------------------------

    def rpush(self, key: str, *values: bytes) -> int:
        lst = self._lists.setdefault(key, [])
        lst.extend(values)
        return len(lst)

    def lrange(self, key: str, start: int, stop: int) -> list[bytes]:
        lst = self._lists.get(key, [])
        if stop == -1:
            return list(lst[start:])
        return list(lst[start : stop + 1])

    # -- sorted set ----------------------------------------------------------

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        zset = self._zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            if member not in zset:
                added += 1
            zset[member] = score
        return added

    def zrevrange(self, key: str, start: int, stop: int) -> list[bytes]:
        zset = self._zsets.get(key, {})
        sorted_members = sorted(zset, key=lambda m: zset[m], reverse=True)
        return [m.encode("utf-8") for m in sorted_members[start : stop + 1]]

    def zrem(self, key: str, *members: str) -> int:
        zset = self._zsets.get(key, {})
        removed = 0
        for m in members:
            if zset.pop(m, None) is not None:
                removed += 1
        return removed


# ---------------------------------------------------------------------------
# ChatSessionStore unit tests
# ---------------------------------------------------------------------------


def _make_store() -> ChatSessionStore:
    return ChatSessionStore(FakeChatRedis())


def test_create_session_returns_session_with_id_and_timestamps() -> None:
    store = _make_store()
    session = store.create_session()

    assert session.id
    assert session.title == "New Chat"
    assert session.created_at
    assert session.updated_at
    assert session.created_at == session.updated_at


def test_list_sessions_returns_sessions_in_reverse_order() -> None:
    store = _make_store()
    s1 = store.create_session(title="first")
    time.sleep(0.01)
    s2 = store.create_session(title="second")
    time.sleep(0.01)
    s3 = store.create_session(title="third")

    sessions = store.list_sessions()
    assert len(sessions) == 3
    assert sessions[0].id == s3.id
    assert sessions[1].id == s2.id
    assert sessions[2].id == s1.id


def test_list_sessions_respects_limit() -> None:
    store = _make_store()
    store.create_session(title="a")
    time.sleep(0.01)
    store.create_session(title="b")
    time.sleep(0.01)
    store.create_session(title="c")

    sessions = store.list_sessions(limit=2)
    assert len(sessions) == 2


def test_get_session_returns_none_for_unknown_id() -> None:
    store = _make_store()
    assert store.get_session("nonexistent-id") is None


def test_delete_session_removes_session_and_messages() -> None:
    store = _make_store()
    session = store.create_session()

    msg = ChatMessage(
        id=uuid.uuid4().hex,
        role="user",
        content="hello",
        created_at="2026-04-13T00:00:00+00:00",
    )
    store.add_message(session.id, msg)
    assert len(store.get_messages(session.id)) == 1

    deleted = store.delete_session(session.id)
    assert deleted is True
    assert store.get_session(session.id) is None
    assert store.get_messages(session.id) == []


def test_delete_session_returns_false_for_unknown_id() -> None:
    store = _make_store()
    assert store.delete_session("nonexistent-id") is False


def test_add_message_and_get_messages_roundtrip() -> None:
    store = _make_store()
    session = store.create_session()

    m1 = ChatMessage(
        id=uuid.uuid4().hex,
        role="user",
        content="hi",
        created_at="2026-04-13T00:00:00+00:00",
    )
    m2 = ChatMessage(
        id=uuid.uuid4().hex,
        role="assistant",
        content="hello!",
        created_at="2026-04-13T00:00:01+00:00",
    )
    store.add_message(session.id, m1)
    store.add_message(session.id, m2)

    messages = store.get_messages(session.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "hi"
    assert messages[1].role == "assistant"
    assert messages[1].content == "hello!"


def test_add_message_raises_for_unknown_session() -> None:
    store = _make_store()
    msg = ChatMessage(
        id=uuid.uuid4().hex,
        role="user",
        content="hello",
        created_at="2026-04-13T00:00:00+00:00",
    )
    with pytest.raises(ValueError, match="Unknown chat session"):
        store.add_message("nonexistent-id", msg)


def test_update_session_title_changes_title() -> None:
    store = _make_store()
    session = store.create_session(title="Old Title")

    store.update_session_title(session.id, "New Title")

    updated = store.get_session(session.id)
    assert updated is not None
    assert updated.title == "New Title"


def test_update_session_title_bumps_updated_at() -> None:
    store = _make_store()
    session = store.create_session()
    original_updated_at = session.updated_at

    time.sleep(0.01)
    store.update_session_title(session.id, "Changed")

    updated = store.get_session(session.id)
    assert updated is not None
    assert updated.updated_at != original_updated_at


# ---------------------------------------------------------------------------
# Chat Router tests (FastAPI TestClient)
# ---------------------------------------------------------------------------


class _FakeChatAgent:
    """Minimal agent stub that satisfies the ``ChatAgent`` interface for non-SSE tests."""

    def stream(self, messages: list[dict[str, Any]]) -> Generator[Any, None, None]:
        yield from ()


@pytest.fixture()
def _override_dependencies():
    """Inject FakeChatRedis-backed store and a stub agent into the FastAPI app."""
    redis = FakeChatRedis()
    store = ChatSessionStore(redis)
    agent = _FakeChatAgent()

    app.dependency_overrides[get_chat_session_store] = lambda: store
    app.dependency_overrides[get_chat_agent] = lambda: agent
    try:
        yield store
    finally:
        app.dependency_overrides.clear()


def test_create_session_endpoint(_override_dependencies: ChatSessionStore) -> None:
    client = TestClient(app)
    resp = client.post("/api/chat/sessions")
    assert resp.status_code == 200

    body = resp.json()
    assert "id" in body
    assert body["title"] == "New Chat"
    assert "created_at" in body
    assert "updated_at" in body


def test_list_sessions_endpoint(_override_dependencies: ChatSessionStore) -> None:
    client = TestClient(app)
    client.post("/api/chat/sessions")
    client.post("/api/chat/sessions")

    resp = client.get("/api/chat/sessions")
    assert resp.status_code == 200

    body = resp.json()
    assert len(body["sessions"]) == 2


def test_get_messages_returns_404_for_unknown_session(
    _override_dependencies: ChatSessionStore,
) -> None:
    client = TestClient(app)
    resp = client.get("/api/chat/sessions/bad-id/messages")
    assert resp.status_code == 404


def test_delete_session_returns_404_for_unknown_session(
    _override_dependencies: ChatSessionStore,
) -> None:
    client = TestClient(app)
    resp = client.delete("/api/chat/sessions/bad-id")
    assert resp.status_code == 404
