from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Protocol

from financehub_market_api.chat.models import ChatMessage
from financehub_market_api.chat.recall_service import (
    ChatHistoryRecallService,
    build_chat_history_recall_service_from_env,
)
from financehub_market_api.env import build_env_values

_SESSION_KEY_PREFIX = "financehub:chat:session:"
_SESSION_SCAN_PATTERN = f"{_SESSION_KEY_PREFIX}*"
_MESSAGE_LIST_KEY_PREFIX = "financehub:chat:messages:"


class _RedisLike(Protocol):
    def scan_iter(self, pattern: str) -> Iterable[bytes | str]: ...

    def hgetall(self, key: bytes | str) -> dict[bytes, bytes]: ...

    def lrange(self, key: bytes | str, start: int, stop: int) -> list[bytes]: ...


def rebuild_chat_recall_index(
    *,
    redis_client: _RedisLike,
    recall_service: ChatHistoryRecallService,
) -> int:
    indexed_count = 0
    for raw_session_key in redis_client.scan_iter(_SESSION_SCAN_PATTERN):
        session_key = _decode_value(raw_session_key)
        if not session_key.startswith(_SESSION_KEY_PREFIX):
            continue
        session_id = session_key.removeprefix(_SESSION_KEY_PREFIX)
        session_payload = redis_client.hgetall(raw_session_key)
        user_id = _decode_hash_field(session_payload, "user_id")
        if not user_id:
            continue
        message_key = f"{_MESSAGE_LIST_KEY_PREFIX}{session_id}"
        for raw_message in redis_client.lrange(message_key, 0, -1):
            message = _parse_chat_message(raw_message)
            if message.role != "user":
                continue
            recall_service.index_user_message(
                user_id=user_id,
                session_id=session_id,
                message_id=message.id,
                content=message.content,
                created_at=message.created_at,
            )
            indexed_count += 1
    return indexed_count


def main(
    *,
    env: Mapping[str, str] | None = None,
    redis_client: _RedisLike | None = None,
    recall_service: ChatHistoryRecallService | None = None,
) -> int:
    config = build_env_values() if env is None else dict(env)
    recall = recall_service or build_chat_history_recall_service_from_env(env=config)
    if recall is None:
        raise RuntimeError("ChatHistoryRecallService could not be built from environment.")
    redis_handle = redis_client or _build_redis_client(config)
    return rebuild_chat_recall_index(
        redis_client=redis_handle,
        recall_service=recall,
    )


def _build_redis_client(env: Mapping[str, str]) -> _RedisLike:
    import redis  # type: ignore[import-untyped]

    redis_url = env.get("FINANCEHUB_MARKET_CACHE_REDIS_URL", "redis://127.0.0.1:6379/0")
    return redis.from_url(redis_url, decode_responses=False)


def _decode_hash_field(payload: dict[bytes, bytes], field: str) -> str | None:
    raw_value = payload.get(field.encode("utf-8"))
    if raw_value is None:
        return None
    return _decode_value(raw_value)


def _parse_chat_message(raw_message: bytes) -> ChatMessage:
    decoded = raw_message.decode("utf-8")
    body = json.loads(decoded)
    if not isinstance(body, dict):
        raise TypeError("Chat message payload must be a JSON object")
    return ChatMessage.model_validate(body)


def _decode_value(raw_value: bytes | str) -> str:
    if isinstance(raw_value, bytes):
        return raw_value.decode("utf-8")
    return raw_value


if __name__ == "__main__":
    main()
