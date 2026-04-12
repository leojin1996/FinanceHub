from __future__ import annotations

import os
from collections.abc import Iterable, Mapping

from financehub_market_api.models import RecommendationEvidenceReference
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


def project_public_evidence_references(
    evidences: Iterable[RetrievedProductEvidence],
    *,
    limit: int | None = None,
) -> list[RecommendationEvidenceReference]:
    if limit is not None and limit <= 0:
        return []

    references: list[RecommendationEvidenceReference] = []
    for evidence in evidences:
        if evidence.visibility != "public" or not evidence.user_displayable:
            continue
        references.append(
            RecommendationEvidenceReference(
                evidenceId=evidence.evidence_id,
                excerpt=evidence.snippet,
                excerptLanguage=evidence.language,
                sourceTitle=evidence.source_title,
                docType=evidence.doc_type,
                asOfDate=evidence.as_of_date,
                pageNumber=evidence.page_number,
                sectionTitle=evidence.section_title,
                sourceUri=evidence.source_uri,
            )
        )
        if limit is not None and len(references) >= limit:
            break
    return references


def build_product_knowledge_retrieval_service_from_env(
    *,
    env: Mapping[str, str] | None = None,
) -> ProductKnowledgeRetrievalService | None:
    config = env if env is not None else os.environ

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


def _read_env(env: Mapping[str, str], key: str) -> str | None:
    raw_value = env.get(key)
    if raw_value is None:
        return None
    value = raw_value.strip()
    return value if value else None
