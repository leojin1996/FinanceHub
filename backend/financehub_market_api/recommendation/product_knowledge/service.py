from __future__ import annotations

from financehub_market_api.recommendation.product_knowledge.embedding_client import TextEmbeddingClient
from financehub_market_api.recommendation.product_knowledge.qdrant_store import ProductKnowledgeStore
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
