from __future__ import annotations

from collections.abc import Mapping

import httpx

from financehub_market_api.chat.qdrant_collection_bootstrap import (
    DEFAULT_CHAT_RECALL_COLLECTION_NAME,
    ensure_chat_recall_qdrant_collection,
    resolve_chat_recall_vector_size,
)
from financehub_market_api.env import build_env_values

_DEFAULT_COLLECTION_NAME = DEFAULT_CHAT_RECALL_COLLECTION_NAME


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
    vector_size = resolve_chat_recall_vector_size(env=config)
    client = http_client if http_client is not None else httpx.Client()
    ensure_chat_recall_qdrant_collection(
        base_url=base_url,
        collection_name=collection,
        api_key=api_key,
        vector_size=vector_size,
        http_client=client,
        timeout_seconds=30.0,
    )


if __name__ == "__main__":
    main()
