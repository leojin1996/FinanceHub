from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from financehub_market_api.recommendation.schemas import CandidateProduct

_HIGH_LIQUIDITY_LABELS = {"T+0", "T+1", "开放式"}
_HIGH_LIQUIDITY_MAX_DAYS = 90


class VectorStore(Protocol):
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        """Return ranked vector hits containing product ids."""


@dataclass(frozen=True)
class RetrievalPlan:
    candidates: list[CandidateProduct]
    filtered_out_reasons: list[str]


class ProductRetrievalService:
    def __init__(self, vector_store: VectorStore) -> None:
        self._vector_store = vector_store

    def plan_retrieval(
        self,
        *,
        query_text: str,
        candidates: list[CandidateProduct],
        allowed_risk_levels: set[str],
        preferred_categories: set[str] | None = None,
        blocked_categories: set[str] | None = None,
        liquidity_preference: str | None = None,
        limit: int = 5,
    ) -> RetrievalPlan:
        preferred_categories = preferred_categories or set()
        blocked_categories = blocked_categories or set()

        filtered_out_reasons: list[str] = []
        eligible_candidates: list[CandidateProduct] = []
        for candidate in candidates:
            if candidate.risk_level not in allowed_risk_levels:
                filtered_out_reasons.append(
                    f"{candidate.id} filtered: risk {candidate.risk_level} not allowed"
                )
                continue
            if candidate.category in blocked_categories:
                filtered_out_reasons.append(
                    f"{candidate.id} filtered: category {candidate.category} blocked by strategy"
                )
                continue
            if not self._matches_liquidity_preference(
                candidate.liquidity,
                liquidity_preference=liquidity_preference,
            ):
                filtered_out_reasons.append(
                    f"{candidate.id} filtered: liquidity {candidate.liquidity or 'unknown'} incompatible with {liquidity_preference}"
                )
                continue
            eligible_candidates.append(candidate)

        if not eligible_candidates:
            return RetrievalPlan(
                candidates=[],
                filtered_out_reasons=filtered_out_reasons,
            )

        input_positions = {
            candidate.id: index for index, candidate in enumerate(eligible_candidates)
        }
        hits = self._vector_store.search(query_text, limit=limit)
        hit_positions: dict[str, int] = {}
        for index, hit in enumerate(hits):
            product_id = hit.get("id")
            if not isinstance(product_id, str) or product_id in hit_positions:
                continue
            hit_positions[product_id] = index

        ordered_candidates = sorted(
            eligible_candidates,
            key=lambda candidate: (
                0 if candidate.category in preferred_categories else 1,
                hit_positions.get(candidate.id, len(hit_positions) + input_positions[candidate.id]),
                input_positions[candidate.id],
            ),
        )
        return RetrievalPlan(
            candidates=ordered_candidates,
            filtered_out_reasons=filtered_out_reasons,
        )

    def retrieve(
        self,
        *,
        query_text: str,
        candidates: list[CandidateProduct],
        allowed_risk_levels: set[str],
        preferred_categories: set[str] | None = None,
        blocked_categories: set[str] | None = None,
        liquidity_preference: str | None = None,
        limit: int = 5,
    ) -> list[CandidateProduct]:
        return self.plan_retrieval(
            query_text=query_text,
            candidates=candidates,
            allowed_risk_levels=allowed_risk_levels,
            preferred_categories=preferred_categories,
            blocked_categories=blocked_categories,
            liquidity_preference=liquidity_preference,
            limit=limit,
        ).candidates

    def _matches_liquidity_preference(
        self,
        liquidity: str | None,
        *,
        liquidity_preference: str | None,
    ) -> bool:
        if liquidity_preference != "high":
            return True

        normalized = (liquidity or "").strip()
        if normalized in _HIGH_LIQUIDITY_LABELS:
            return True
        if normalized.endswith("天"):
            days_text = normalized.removesuffix("天")
            if days_text.isdigit():
                return int(days_text) <= _HIGH_LIQUIDITY_MAX_DAYS
        return False
