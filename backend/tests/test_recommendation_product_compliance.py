from financehub_market_api.recommendation.compliance import ComplianceReviewService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.schemas import CandidateProduct


class _StaticVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        return [
            {"id": "fund-002", "score": 0.92},
            {"id": "fund-001", "score": 0.88},
        ][:limit]


def _candidate(product_id: str, risk_level: str) -> CandidateProduct:
    return CandidateProduct(
        id=product_id,
        category="fund",
        name_zh="稳健债券精选",
        name_en="Stable Bond Select",
        risk_level=risk_level,
        tags_zh=["稳健", "债券"],
        tags_en=["stable", "bond"],
        rationale_zh="适合作为稳健配置底仓。",
        rationale_en="Suitable as a stable core allocation.",
    )


def test_product_retrieval_service_filters_and_orders_candidates() -> None:
    service = ProductRetrievalService(vector_store=_StaticVectorStore())

    candidates = service.retrieve(
        query_text="一年期稳健债券",
        candidates=[_candidate("fund-001", "R2"), _candidate("fund-002", "R2")],
        allowed_risk_levels={"R2"},
    )

    assert [candidate.id for candidate in candidates] == ["fund-002", "fund-001"]


def test_compliance_review_service_revises_conservative_when_risk_exceeds_profile() -> None:
    service = ComplianceReviewService()

    review = service.review(risk_tier="R2", candidates=[_candidate("fund-001", "R4")])

    assert review.verdict == "revise_conservative"
    assert review.disclosures_zh
