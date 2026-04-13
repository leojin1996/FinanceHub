from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Protocol

from redis.exceptions import RedisError

from .models import ChatMessage, ChatSession

LOGGER = logging.getLogger(__name__)


class ChatStoreError(Exception):
    """Raised when a chat store write fails due to Redis or an unexpected client error."""

    def __init__(self, message: str, *, session_id: str | None = None) -> None:
        self.session_id = session_id
        super().__init__(message)


def _utc_iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _session_hash_key(session_id: str) -> str:
    return f"financehub:chat:session:{session_id}"


def _messages_list_key(session_id: str) -> str:
    return f"financehub:chat:messages:{session_id}"


USER_SESSIONS_ZSET_KEY = "financehub:chat:user_sessions"


class ChatRedisLike(Protocol):
    """Redis client surface needed for chat persistence (hash, list, sorted set)."""

    def hset(self, key: str, mapping: dict[bytes, bytes]) -> int: ...

    def hgetall(self, key: str) -> dict[bytes, bytes]: ...

    def delete(self, key: str) -> int: ...

    def rpush(self, key: str, *values: bytes) -> int: ...

    def lrange(self, key: str, start: int, stop: int) -> list[bytes]: ...

    def zadd(self, key: str, mapping: dict[str, float]) -> int: ...

    def zrevrange(self, key: str, start: int, stop: int) -> list[bytes]: ...

    def zrem(self, key: str, *members: str) -> int: ...


def _decode_zset_member(raw: bytes) -> str:
    return raw.decode("utf-8")


class ChatSessionStore:
    def __init__(self, redis_client: ChatRedisLike) -> None:
        self._redis = redis_client

    def _touch_session(self, session_id: str) -> None:
        updated_at = _utc_iso_now()
        try:
            self._redis.hset(
                _session_hash_key(session_id),
                mapping={b"updated_at": updated_at.encode("utf-8")},
            )
            self._redis.zadd(USER_SESSIONS_ZSET_KEY, {session_id: time.time()})
        except RedisError as exc:
            msg = f"Failed to update session timestamp in Redis: {exc}"
            raise ChatStoreError(msg, session_id=session_id) from exc

    def create_session(self, title: str = "New Chat") -> ChatSession:
        session_id = uuid.uuid4().hex
        created_at = _utc_iso_now()
        updated_at = created_at
        session_key = _session_hash_key(session_id)
        try:
            self._redis.hset(
                session_key,
                mapping={
                    b"title": title.encode("utf-8"),
                    b"created_at": created_at.encode("utf-8"),
                    b"updated_at": updated_at.encode("utf-8"),
                },
            )
            self._redis.zadd(USER_SESSIONS_ZSET_KEY, {session_id: time.time()})
        except RedisError as exc:
            msg = f"Failed to create chat session in Redis: {exc}"
            raise ChatStoreError(msg, session_id=session_id) from exc
        return ChatSession(
            id=session_id,
            title=title,
            created_at=created_at,
            updated_at=updated_at,
        )

    def list_sessions(self, limit: int = 50) -> list[ChatSession]:
        if limit <= 0:
            return []
        try:
            raw_ids = self._redis.zrevrange(USER_SESSIONS_ZSET_KEY, 0, limit - 1)
        except RedisError:
            LOGGER.warning(
                "Redis error while listing chat sessions; returning empty list",
                exc_info=True,
            )
            return []
        sessions: list[ChatSession] = []
        for raw_id in raw_ids:
            session_id = _decode_zset_member(raw_id)
            session = self.get_session(session_id)
            if session is not None:
                sessions.append(session)
        return sessions

    def get_session(self, session_id: str) -> ChatSession | None:
        try:
            raw = self._redis.hgetall(_session_hash_key(session_id))
        except RedisError:
            LOGGER.warning(
                "Redis error while loading chat session %s; returning None",
                session_id,
                exc_info=True,
            )
            return None
        if not raw:
            return None
        title_b = raw.get(b"title")
        created_b = raw.get(b"created_at")
        updated_b = raw.get(b"updated_at")
        if title_b is None or created_b is None or updated_b is None:
            return None
        try:
            return ChatSession(
                id=session_id,
                title=title_b.decode("utf-8"),
                created_at=created_b.decode("utf-8"),
                updated_at=updated_b.decode("utf-8"),
            )
        except UnicodeDecodeError:
            return None

    def delete_session(self, session_id: str) -> bool:
        session_key = _session_hash_key(session_id)
        try:
            raw = self._redis.hgetall(session_key)
        except RedisError as exc:
            msg = f"Failed to read chat session before delete: {exc}"
            raise ChatStoreError(msg, session_id=session_id) from exc
        if not raw:
            return False
        try:
            self._redis.delete(session_key)
            self._redis.delete(_messages_list_key(session_id))
            self._redis.zrem(USER_SESSIONS_ZSET_KEY, session_id)
        except RedisError as exc:
            msg = f"Failed to delete chat session from Redis: {exc}"
            raise ChatStoreError(msg, session_id=session_id) from exc
        return True

    def add_message(self, session_id: str, message: ChatMessage) -> None:
        session_key = _session_hash_key(session_id)
        try:
            raw = self._redis.hgetall(session_key)
        except RedisError as exc:
            msg = f"Failed to verify chat session before add_message: {exc}"
            raise ChatStoreError(msg, session_id=session_id) from exc
        if not raw:
            msg = f"Unknown chat session: {session_id}"
            raise ValueError(msg)
        payload = json.dumps(
            message.model_dump(mode="json"),
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            self._redis.rpush(_messages_list_key(session_id), payload)
        except RedisError as exc:
            msg = f"Failed to append chat message in Redis: {exc}"
            raise ChatStoreError(msg, session_id=session_id) from exc
        self._touch_session(session_id)

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        try:
            raw_items = self._redis.lrange(_messages_list_key(session_id), 0, -1)
        except RedisError:
            LOGGER.warning(
                "Redis error while loading messages for session %s; returning empty list",
                session_id,
                exc_info=True,
            )
            return []
        messages: list[ChatMessage] = []
        for raw in raw_items:
            try:
                body = json.loads(raw.decode("utf-8"))
            except UnicodeDecodeError as exc:
                msg = "Chat message payload must be UTF-8 JSON"
                raise ValueError(msg) from exc
            except json.JSONDecodeError as exc:
                msg = "Chat message payload must be valid JSON"
                raise ValueError(msg) from exc
            if not isinstance(body, dict):
                msg = "Chat message payload must be a JSON object"
                raise TypeError(msg)
            messages.append(ChatMessage.model_validate(body))
        return messages

    def update_session_title(self, session_id: str, title: str) -> None:
        session_key = _session_hash_key(session_id)
        try:
            raw = self._redis.hgetall(session_key)
        except RedisError as exc:
            msg = f"Failed to verify chat session before update_session_title: {exc}"
            raise ChatStoreError(msg, session_id=session_id) from exc
        if not raw:
            msg = f"Unknown chat session: {session_id}"
            raise ValueError(msg)
        try:
            self._redis.hset(
                session_key,
                mapping={b"title": title.encode("utf-8")},
            )
        except RedisError as exc:
            msg = f"Failed to update chat session title in Redis: {exc}"
            raise ChatStoreError(msg, session_id=session_id) from exc
        self._touch_session(session_id)


class InMemoryChatSessionStore:
    """In-process chat persistence when Redis is unavailable (dev / no Redis)."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._messages: dict[str, list[ChatMessage]] = {}
        self._recent: list[str] = []

    def _bump_recent(self, session_id: str) -> None:
        self._recent = [session_id] + [x for x in self._recent if x != session_id]

    def create_session(self, title: str = "New Chat") -> ChatSession:
        session_id = uuid.uuid4().hex
        now = _utc_iso_now()
        session = ChatSession(
            id=session_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        self._sessions[session_id] = session
        self._messages[session_id] = []
        self._bump_recent(session_id)
        return session

    def list_sessions(self, limit: int = 50) -> list[ChatSession]:
        if limit <= 0:
            return []
        out: list[ChatSession] = []
        for sid in self._recent[:limit]:
            s = self._sessions.get(sid)
            if s is not None:
                out.append(s)
        return out

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        self._messages.pop(session_id, None)
        self._recent = [x for x in self._recent if x != session_id]
        return True

    def _touch_session(self, session_id: str) -> None:
        s = self._sessions[session_id]
        now = _utc_iso_now()
        self._sessions[session_id] = s.model_copy(update={"updated_at": now})
        self._bump_recent(session_id)

    def add_message(self, session_id: str, message: ChatMessage) -> None:
        if session_id not in self._sessions:
            msg = f"Unknown chat session: {session_id}"
            raise ValueError(msg)
        self._messages.setdefault(session_id, []).append(message)
        self._touch_session(session_id)

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        return list(self._messages.get(session_id, []))

    def update_session_title(self, session_id: str, title: str) -> None:
        if session_id not in self._sessions:
            msg = f"Unknown chat session: {session_id}"
            raise ValueError(msg)
        s = self._sessions[session_id]
        now = _utc_iso_now()
        self._sessions[session_id] = s.model_copy(update={"title": title, "updated_at": now})
        self._bump_recent(session_id)


def build_chat_session_store(
    *,
    environ: dict[str, str] | None = None,
) -> ChatSessionStore | InMemoryChatSessionStore:
    """Prefer Redis; fall back to in-memory store if Redis is down or redis is not installed."""
    import os

    env = os.environ if environ is None else environ
    if env.get("FINANCEHUB_CHAT_STORE_BACKEND", "").strip().lower() in {"memory", "inmemory", "ram"}:
        LOGGER.warning(
            "FINANCEHUB_CHAT_STORE_BACKEND=memory — chat sessions are not persisted across restarts",
        )
        return InMemoryChatSessionStore()

    try:
        import redis  # type: ignore[import-untyped]
    except ImportError:
        LOGGER.warning(
            "redis package not installed — using in-memory chat store (sessions are not persisted across restarts)",
        )
        return InMemoryChatSessionStore()

    redis_url = env.get(
        "FINANCEHUB_MARKET_CACHE_REDIS_URL",
        "redis://127.0.0.1:6379/0",
    )
    try:
        # Chat store uses bytes for hash fields; URL must not force decode_responses=True.
        client = redis.from_url(redis_url, decode_responses=False)
        client.ping()
    except (RedisError, OSError) as exc:
        LOGGER.warning(
            "Redis unavailable for chat (%s: %s) — using in-memory chat store",
            type(exc).__name__,
            exc,
        )
        return InMemoryChatSessionStore()

    return ChatSessionStore(client)
