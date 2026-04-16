from __future__ import annotations

from collections.abc import Mapping, Sequence

import httpx

from financehub_market_api.chat.recall_service import (
    build_chat_history_recall_service_from_env,
)

DEFAULT_CHAT_RECALL_COLLECTION_NAME = "chat_messages_v2"
DEFAULT_CHAT_RECALL_VECTOR_SIZE = 1536
CHAT_RECALL_PAYLOAD_INDEX_SCHEMAS: tuple[tuple[str, str], ...] = (
    ("user_id", "keyword"),
    ("session_id", "keyword"),
    ("created_at", "datetime"),
    ("is_preference_memory", "bool"),
    ("recency_bucket", "keyword"),
    ("preference_tags", "keyword"),
    ("topic_tags", "keyword"),
    ("symbol_mentions", "keyword"),
    ("content_fingerprint", "keyword"),
)


def resolve_chat_recall_vector_size(*, env: Mapping[str, str]) -> int:
    recall_service = build_chat_history_recall_service_from_env(env=env)
    if recall_service is None:
        return DEFAULT_CHAT_RECALL_VECTOR_SIZE
    probe_vector = recall_service._embedding_client.embed_query(
        "financehub chat recall vector size probe"
    )
    if not probe_vector:
        raise ValueError("embedding client returned an empty chat recall vector")
    return len(probe_vector)


def ensure_chat_recall_qdrant_collection(
    *,
    base_url: str,
    collection_name: str,
    vector_size: int,
    api_key: str | None = None,
    payload_index_schemas: Sequence[tuple[str, str]] = CHAT_RECALL_PAYLOAD_INDEX_SCHEMAS,
    http_client: httpx.Client | None = None,
    timeout_seconds: float = 30.0,
) -> None:
    headers = {"content-type": "application/json"}
    if api_key:
        headers["api-key"] = api_key
    client = http_client if http_client is not None else httpx.Client()
    create_response = client.put(
        f"{base_url.rstrip('/')}/collections/{collection_name}",
        headers=headers,
        json={"vectors": {"size": vector_size, "distance": "Cosine"}},
        timeout=timeout_seconds,
    )
    if create_response.is_success:
        pass
    elif create_response.status_code == 409:
        existing_size = _fetch_existing_vector_size(
            client=client,
            base_url=base_url,
            collection_name=collection_name,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )
        if existing_size != vector_size:
            raise RuntimeError(
                "chat recall collection vector size mismatch: "
                f"existing={existing_size}, expected={vector_size}"
            )
    else:
        create_response.raise_for_status()

    for field_name, field_schema in payload_index_schemas:
        index_response = client.put(
            f"{base_url.rstrip('/')}/collections/{collection_name}/index",
            headers=headers,
            json={"field_name": field_name, "field_schema": field_schema},
            timeout=timeout_seconds,
        )
        if index_response.is_success or index_response.status_code == 409:
            continue
        index_response.raise_for_status()


def _fetch_existing_vector_size(
    *,
    client: httpx.Client,
    base_url: str,
    collection_name: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> int:
    response = client.get(
        f"{base_url.rstrip('/')}/collections/{collection_name}",
        headers=dict(headers),
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    size = _extract_vector_size(response.json())
    if size is None:
        raise RuntimeError(
            f"could not determine vector size for existing collection {collection_name!r}"
        )
    return size


def _extract_vector_size(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    config = result.get("config")
    if not isinstance(config, dict):
        return None
    params = config.get("params")
    if not isinstance(params, dict):
        return None
    vectors = params.get("vectors")
    if isinstance(vectors, dict):
        size = vectors.get("size")
        if isinstance(size, int) and not isinstance(size, bool):
            return size
        if len(vectors) == 1:
            nested = next(iter(vectors.values()))
            if isinstance(nested, dict):
                nested_size = nested.get("size")
                if isinstance(nested_size, int) and not isinstance(nested_size, bool):
                    return nested_size
    return None
