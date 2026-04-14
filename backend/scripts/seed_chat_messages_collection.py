from __future__ import annotations

from collections.abc import Mapping

import httpx

from financehub_market_api.env import build_env_values

_DEFAULT_COLLECTION_NAME = "chat_messages"
_PAYLOAD_INDEX_SCHEMAS: tuple[tuple[str, str], ...] = (
    ("user_id", "keyword"),
    ("session_id", "keyword"),
    ("created_at", "datetime"),
)


def main(
    *,
    env: Mapping[str, str] | None = None,
    http_client: httpx.Client | None = None,
) -> None:
    config = build_env_values() if env is None else env
    base_url = config["FINANCEHUB_CHAT_RECALL_QDRANT_URL"].rstrip("/")
    collection = config.get(
        "FINANCEHUB_CHAT_RECALL_COLLECTION", _DEFAULT_COLLECTION_NAME
    )
    api_key = config.get("FINANCEHUB_CHAT_RECALL_QDRANT_API_KEY")
    headers = {"content-type": "application/json"}
    if api_key:
        headers["api-key"] = api_key

    client = http_client if http_client is not None else httpx.Client()
    client.put(
        f"{base_url}/collections/{collection}",
        headers=headers,
        json={
            "vectors": {"size": 1536, "distance": "Cosine"},
        },
        timeout=30.0,
    ).raise_for_status()
    for field_name, field_schema in _PAYLOAD_INDEX_SCHEMAS:
        client.put(
            f"{base_url}/collections/{collection}/index",
            headers=headers,
            json={"field_name": field_name, "field_schema": field_schema},
            timeout=30.0,
        ).raise_for_status()


if __name__ == "__main__":
    main()
