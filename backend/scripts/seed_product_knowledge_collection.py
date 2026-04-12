from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TextIO

from financehub_market_api.recommendation.product_knowledge.embedding_client import (
    OpenAIEmbeddingClient,
)

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "product_knowledge"
    / "seed_documents.json"
)


class _EmbeddingClient(Protocol):
    def embed_query(self, text: str) -> list[float]:
        """Return an embedding vector for the provided text."""


@dataclass(frozen=True)
class ProductKnowledgeSeedConfig:
    qdrant_url: str
    collection_name: str
    openai_api_key: str
    qdrant_api_key: str | None
    openai_base_url: str | None
    embedding_model: str | None
    fixture_path: Path

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str],
        fixture_path: Path,
    ) -> "ProductKnowledgeSeedConfig":
        qdrant_url = _require_env(env, "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_URL")
        collection_name = _require_env(
            env,
            "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_COLLECTION",
        )
        openai_api_key = _read_env(env, "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY")
        if not openai_api_key:
            openai_api_key = _read_env(env, "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError(
                "Configure FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY "
                "or FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY to seed product knowledge"
            )
        return cls(
            qdrant_url=qdrant_url,
            collection_name=collection_name,
            openai_api_key=openai_api_key,
            qdrant_api_key=_read_env(
                env, "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_API_KEY"
            ),
            openai_base_url=_read_env(
                env, "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_BASE_URL"
            ),
            embedding_model=_read_env(
                env, "FINANCEHUB_PRODUCT_KNOWLEDGE_EMBEDDING_MODEL"
            ),
            fixture_path=fixture_path,
        )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the product knowledge Qdrant collection with canonical fixture documents.",
    )
    parser.add_argument(
        "--fixture-path",
        default=str(DEFAULT_FIXTURE_PATH),
        help="Path to the canonical product knowledge seed fixture JSON file.",
    )
    return parser.parse_args(argv)


def _load_documents(fixture_path: Path) -> list[dict[str, Any]]:
    documents = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(documents, list):
        raise ValueError("seed fixture must be a JSON array of document payloads")
    return [dict(document) for document in documents]


def _default_embedding_client_factory(
    config: ProductKnowledgeSeedConfig,
) -> _EmbeddingClient:
    embedding_client_kwargs: dict[str, str] = {"api_key": config.openai_api_key}
    if config.openai_base_url:
        embedding_client_kwargs["base_url"] = config.openai_base_url
    if config.embedding_model:
        embedding_client_kwargs["model_name"] = config.embedding_model
    return OpenAIEmbeddingClient(**embedding_client_kwargs)


def _default_qdrant_client_factory(config: ProductKnowledgeSeedConfig) -> Any:
    try:
        from qdrant_client import QdrantClient
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in real env
        raise RuntimeError(
            "qdrant-client is required to seed the product knowledge collection."
        ) from exc

    return QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)


def _default_point_factory(
    chunk_id: str,
    vector: list[float],
    payload: dict[str, Any],
) -> Any:
    try:
        from qdrant_client import models
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in real env
        raise RuntimeError(
            "qdrant-client is required to build Qdrant point payloads."
        ) from exc

    return models.PointStruct(id=chunk_id, vector=vector, payload=payload)


def _ensure_collection(
    client: Any,
    *,
    collection_name: str,
    vector_size: int,
) -> None:
    if not hasattr(client, "collection_exists"):
        return
    if client.collection_exists(collection_name):
        return
    try:
        from qdrant_client import models
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in real env
        raise RuntimeError(
            "qdrant-client is required to create the product knowledge collection."
        ) from exc
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )


def _build_points(
    documents: list[dict[str, Any]],
    *,
    embedding_client: _EmbeddingClient,
    point_factory: Callable[[str, list[float], dict[str, Any]], Any],
) -> tuple[list[Any], int]:
    points: list[Any] = []
    vector_size = 0
    for document in documents:
        text = document.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("seed document text must be a non-empty string")
        chunk_id = document.get("chunk_id") or document.get("evidence_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError("seed document must define chunk_id or evidence_id")
        vector = embedding_client.embed_query(text)
        if vector_size == 0:
            vector_size = len(vector)
        points.append(point_factory(chunk_id, vector, document))
    return points, vector_size


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    out: TextIO | None = None,
    qdrant_client_factory: Callable[[ProductKnowledgeSeedConfig], Any] | None = None,
    embedding_client_factory: Callable[[ProductKnowledgeSeedConfig], _EmbeddingClient]
    | None = None,
    point_factory: Callable[[str, list[float], dict[str, Any]], Any] | None = None,
) -> int:
    args = _parse_args(argv)
    target = out or sys.stdout
    config = ProductKnowledgeSeedConfig.from_env(
        env=env or os.environ,
        fixture_path=Path(args.fixture_path),
    )
    documents = _load_documents(config.fixture_path)
    embedding_client = (
        embedding_client_factory(config)
        if embedding_client_factory is not None
        else _default_embedding_client_factory(config)
    )
    points, vector_size = _build_points(
        documents,
        embedding_client=embedding_client,
        point_factory=point_factory or _default_point_factory,
    )
    if not points:
        raise ValueError("seed fixture did not produce any Qdrant points")
    qdrant_client = (
        qdrant_client_factory(config)
        if qdrant_client_factory is not None
        else _default_qdrant_client_factory(config)
    )
    _ensure_collection(
        qdrant_client,
        collection_name=config.collection_name,
        vector_size=vector_size,
    )
    qdrant_client.upsert(collection_name=config.collection_name, points=points)
    print(
        f"seeded {len(points)} product knowledge points into {config.collection_name}",
        file=target,
    )
    return 0


def _read_env(env: Mapping[str, str], key: str) -> str | None:
    raw_value = env.get(key)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value if value else None


def _require_env(env: Mapping[str, str], key: str) -> str:
    value = _read_env(env, key)
    if value:
        return value
    raise ValueError(f"{key} must be configured to seed product knowledge")


if __name__ == "__main__":
    raise SystemExit(main())
