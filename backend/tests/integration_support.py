"""Shared helpers for integration tests (real Redis / MySQL / Qdrant / OpenAI).

Enable with::

    export FINANCEHUB_INTEGRATION_TESTS=1

Required environment (typical local dev):

- ``FINANCEHUB_MYSQL_URL`` — MySQL with ``financehub`` schema (tables created on app startup).
- ``FINANCEHUB_MARKET_CACHE_REDIS_URL`` — Redis for chat sessions (default ``redis://127.0.0.1:6379/0``).
- ``FINANCEHUB_CHAT_RECALL_QDRANT_URL`` — Qdrant HTTP API base URL.
- Embedding API key for chat recall (any one): ``FINANCEHUB_CHAT_RECALL_OPENAI_API_KEY``,
  ``FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY``, ``FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_API_KEY``,
  or ``FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY`` (same chain as ``build_chat_history_recall_service_from_env``).
  Base URL / model fall back in the same order: chat-recall-specific, then product knowledge, then compliance
  (e.g. local Ollama + ``FINANCEHUB_COMPLIANCE_KNOWLEDGE_EMBEDDING_MODEL``), then LLM provider.
- Optional: ``FINANCEHUB_CHAT_RECALL_QDRANT_API_KEY``, ``FINANCEHUB_CHAT_RECALL_COLLECTION``,
  ``FINANCEHUB_CHAT_STORE_BACKEND`` (omit or not ``memory`` for Redis).

Before first run, create the chat recall collection::

    cd backend && FINANCEHUB_CHAT_RECALL_QDRANT_URL=... python -m scripts.seed_chat_messages_collection
"""

from __future__ import annotations

import os

import httpx


def integration_enabled() -> bool:
    raw = os.environ.get("FINANCEHUB_INTEGRATION_TESTS", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def collect_integration_prerequisite_errors() -> list[str]:
    """Return human-readable errors; empty list means Redis/MySQL/Qdrant/OpenAI look usable."""
    errors: list[str] = []

    try:
        import redis as redis_lib

        client = redis_lib.from_url(redis_url(), decode_responses=False)
        # Some Redis builds return MISCONF on PING when RDB persistence is broken;
        # ECHO is read-only and still proves the server accepts commands.
        if client.echo(b"financehub-integration-check") != b"financehub-integration-check":
            errors.append(f"Redis ({redis_url()}): unexpected ECHO response")
        client.close()
    except Exception as exc:
        errors.append(f"Redis ({redis_url()}): {exc}")

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(mysql_url(), pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:
        errors.append(f"MySQL ({mysql_url()}): {exc}")

    base = qdrant_base_url()
    if not base:
        errors.append("FINANCEHUB_CHAT_RECALL_QDRANT_URL is not set")
    else:
        try:
            response = httpx.get(
                f"{base}/collections",
                headers=qdrant_headers(),
                timeout=15.0,
            )
            response.raise_for_status()
        except Exception as exc:
            errors.append(f"Qdrant ({base}): {exc}")

    from financehub_market_api.chat.recall_service import (
        build_chat_history_recall_service_from_env,
    )

    recall = build_chat_history_recall_service_from_env()
    if recall is None:
        errors.append(
            "ChatHistoryRecallService could not be built (need FINANCEHUB_CHAT_RECALL_QDRANT_URL "
            "and an embedding API key: FINANCEHUB_CHAT_RECALL_OPENAI_API_KEY, "
            "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY, "
            "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_API_KEY, or "
            "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY)"
        )
    # Do not call embed_query here: custom gateways may use non-standard paths; failures
    # surface clearly on the chat/recall tests that actually need embeddings.

    return errors


def redis_url() -> str:
    """Same as ``financehub_market_api.chat.store`` / market cache: ``FINANCEHUB_MARKET_CACHE_REDIS_URL``."""
    return os.environ.get(
        "FINANCEHUB_MARKET_CACHE_REDIS_URL", "redis://127.0.0.1:6379/0"
    ).strip()


def mysql_url() -> str:
    """Same DSN as ``financehub_market_api.auth.database`` (``FINANCEHUB_MYSQL_URL``)."""
    from financehub_market_api.auth.database import get_database_url

    return get_database_url()


def qdrant_base_url() -> str:
    return os.environ.get("FINANCEHUB_CHAT_RECALL_QDRANT_URL", "").strip().rstrip("/")


def qdrant_headers() -> dict[str, str]:
    headers = {"content-type": "application/json"}
    key = os.environ.get("FINANCEHUB_CHAT_RECALL_QDRANT_API_KEY", "").strip()
    if key:
        headers["api-key"] = key
    return headers


def chat_recall_collection_name() -> str:
    return os.environ.get("FINANCEHUB_CHAT_RECALL_COLLECTION", "chat_messages").strip() or "chat_messages"


def ensure_chat_messages_qdrant_collection() -> None:
    """Idempotent: create collection + payload indexes (same as seed script)."""
    base = qdrant_base_url()
    if not base:
        raise RuntimeError("FINANCEHUB_CHAT_RECALL_QDRANT_URL not set")
    collection = chat_recall_collection_name()
    headers = qdrant_headers()
    with httpx.Client(timeout=30.0) as client:
        client.put(
            f"{base}/collections/{collection}",
            headers=headers,
            json={"vectors": {"size": 1536, "distance": "Cosine"}},
        ).raise_for_status()
        for field_name, field_schema in (
            ("user_id", "keyword"),
            ("session_id", "keyword"),
            ("created_at", "datetime"),
        ):
            index_resp = client.put(
                f"{base}/collections/{collection}/index",
                headers=headers,
                json={"field_name": field_name, "field_schema": field_schema},
            )
            if index_resp.is_success:
                continue
            if index_resp.status_code == 409:
                continue
            index_resp.raise_for_status()


def clear_app_lru_caches() -> None:
    from financehub_market_api.chat.router import (
        get_chat_agent,
        get_chat_history_recall_service,
        get_chat_session_store,
    )
    from financehub_market_api.main import (
        get_market_data_service,
        get_product_detail_service,
        get_recommendation_service,
    )

    get_chat_session_store.cache_clear()
    get_chat_agent.cache_clear()
    get_chat_history_recall_service.cache_clear()
    get_recommendation_service.cache_clear()
    get_market_data_service.cache_clear()
    get_product_detail_service.cache_clear()


def delete_redis_chat_keys_for_session(session_id: str, user_id: str) -> None:
    import redis as redis_lib

    client = redis_lib.from_url(redis_url(), decode_responses=False)
    try:
        client.delete(f"financehub:chat:session:{session_id}")
        client.delete(f"financehub:chat:messages:{session_id}")
        client.zrem(f"financehub:chat:user_sessions:{user_id}", session_id)
    finally:
        client.close()


def delete_mysql_user_by_email(email: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(mysql_url(), pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM users WHERE email = :email"),
                {"email": email.strip().lower()},
            )
    finally:
        engine.dispose()
