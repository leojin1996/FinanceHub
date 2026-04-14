from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from financehub_market_api.env import (
    build_env_values as _build_shared_env_values,
    iter_env_file_candidates as _iter_shared_env_file_candidates,
    parse_env_file as _parse_shared_env_file,
    read_env as _read_env,
)
from financehub_market_api.recommendation.product_knowledge.embedding_client import (
    OpenAIEmbeddingClient,
    TextEmbeddingClient,
)
from financehub_market_api.recommendation.product_knowledge.qdrant_store import (
    ProductKnowledgeStore,
    QdrantProductKnowledgeStore,
)
from financehub_market_api.recommendation.product_knowledge.schemas import (
    ProductEvidenceBundle,
    RetrievedProductEvidence,
)


class ProductKnowledgeRetrievalService:
    def __init__(
        self,
        *,
        embedding_client: TextEmbeddingClient,
        knowledge_store: ProductKnowledgeStore,
    ) -> None:
        self._embedding_client = embedding_client
        self._knowledge_store = knowledge_store

    def retrieve_evidence(
        self,
        *,
        query_text: str,
        product_ids: list[str],
        include_internal: bool = True,
        limit_per_product: int = 2,
        total_limit: int = 12,
    ) -> list[ProductEvidenceBundle]:
        if not product_ids:
            return []

        query_vector = self._embedding_client.embed_query(query_text)
        hits = self._knowledge_store.search(
            query_vector=query_vector,
            product_ids=product_ids,
            include_internal=include_internal,
            limit_per_product=limit_per_product,
            total_limit=total_limit,
        )

        grouped: dict[str, list[RetrievedProductEvidence]] = {
            product_id: [] for product_id in product_ids
        }
        for hit in hits:
            evidence = RetrievedProductEvidence.model_validate(hit)
            if evidence.product_id not in grouped:
                continue
            if not include_internal and evidence.visibility != "public":
                continue
            if len(grouped[evidence.product_id]) >= limit_per_product:
                continue
            grouped[evidence.product_id].append(evidence)

        return [
            ProductEvidenceBundle(product_id=product_id, evidences=grouped[product_id])
            for product_id in product_ids
            if grouped.get(product_id)
        ]


def build_product_knowledge_retrieval_service_from_env(
    *,
    env: Mapping[str, str] | None = None,
) -> ProductKnowledgeRetrievalService | None:
    config = env if env is not None else _build_env_values()

    qdrant_url = _read_env(config, "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_URL")
    qdrant_collection = _read_env(
        config, "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_COLLECTION"
    )
    openai_api_key = _read_env(
        config, "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY"
    ) or _read_env(config, "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY")

    if not qdrant_url or not qdrant_collection or not openai_api_key:
        return None

    openai_base_url = _read_env(config, "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_BASE_URL")
    embedding_model = _read_env(config, "FINANCEHUB_PRODUCT_KNOWLEDGE_EMBEDDING_MODEL")
    qdrant_api_key = _read_env(config, "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_API_KEY")

    embedding_client_kwargs: dict[str, str] = {"api_key": openai_api_key}
    if openai_base_url:
        embedding_client_kwargs["base_url"] = openai_base_url
    if embedding_model:
        embedding_client_kwargs["model_name"] = embedding_model

    return ProductKnowledgeRetrievalService(
        embedding_client=OpenAIEmbeddingClient(**embedding_client_kwargs),
        knowledge_store=QdrantProductKnowledgeStore(
            base_url=qdrant_url,
            collection_name=qdrant_collection,
            api_key=qdrant_api_key,
        ),
    )


def _iter_env_file_candidates() -> list[Path]:
    return _iter_shared_env_file_candidates()


def _parse_env_file(env_file: Path) -> dict[str, str]:
    return _parse_shared_env_file(env_file)


def _build_env_values(
    environ: Mapping[str, str] | None = None,
    env_files: Sequence[Path] | None = None,
) -> dict[str, str]:
    return _build_shared_env_values(
        environ=environ,
        env_files=env_files if env_files is not None else _iter_env_file_candidates(),
    )
