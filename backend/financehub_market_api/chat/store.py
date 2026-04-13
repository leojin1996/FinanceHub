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
            msg = "Failed to update session timestamp in Redis"
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
            msg = "Failed to create chat session in Redis"
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
            msg = "Failed to read chat session before delete"
            raise ChatStoreError(msg, session_id=session_id) from exc
        if not raw:
            return False
        try:
            self._redis.delete(session_key)
            self._redis.delete(_messages_list_key(session_id))
            self._redis.zrem(USER_SESSIONS_ZSET_KEY, session_id)
        except RedisError as exc:
            msg = "Failed to delete chat session from Redis"
            raise ChatStoreError(msg, session_id=session_id) from exc
        return True

    def add_message(self, session_id: str, message: ChatMessage) -> None:
        session_key = _session_hash_key(session_id)
        try:
            raw = self._redis.hgetall(session_key)
        except RedisError as exc:
            msg = "Failed to verify chat session before add_message"
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
            msg = "Failed to append chat message in Redis"
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
            msg = "Failed to verify chat session before update_session_title"
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
            msg = "Failed to update chat session title in Redis"
            raise ChatStoreError(msg, session_id=session_id) from exc
        self._touch_session(session_id)
