from __future__ import annotations

from typing import Protocol

from financehub_market_api.recommendation.schemas import CandidateProduct


class VectorStore(Protocol):
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        """Return ranked vector hits containing product ids."""


class ProductRetrievalService:
    def __init__(self, vector_store: VectorStore) -> None:
        self._vector_store = vector_store

    def retrieve(
        self,
        *,
        query_text: str,
        candidates: list[CandidateProduct],
        allowed_risk_levels: set[str],
        limit: int = 5,
    ) -> list[CandidateProduct]:
        filtered = [
            candidate for candidate in candidates if candidate.risk_level in allowed_risk_levels
        ]
        if not filtered:
            return []

        candidates_by_id = {candidate.id: candidate for candidate in filtered}
        hits = self._vector_store.search(query_text, limit=limit)

        ordered: list[CandidateProduct] = []
        seen_ids: set[str] = set()
        for hit in hits:
            product_id = hit.get("id")
            if not isinstance(product_id, str) or product_id in seen_ids:
                continue
            candidate = candidates_by_id.get(product_id)
            if candidate is None:
                continue
            ordered.append(candidate)
            seen_ids.add(product_id)

        for candidate in filtered:
            if candidate.id not in seen_ids:
                ordered.append(candidate)

        return ordered
