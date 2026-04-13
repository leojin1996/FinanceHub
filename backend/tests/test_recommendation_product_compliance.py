from financehub_market_api.recommendation.compliance import ComplianceReviewService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.schemas import CandidateProduct


class _StaticVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        return [
            {"id": "fund-002", "score": 0.92},
            {"id": "fund-001", "score": 0.88},
        ][:limit]


class _PreferenceVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [
            {"id": "stock-001", "score": 0.99},
            {"id": "fund-001", "score": 0.91},
            {"id": "wm-001", "score": 0.87},
            {"id": "wm-002", "score": 0.83},
        ][:limit]


def _candidate(
    product_id: str,
    risk_level: str,
    *,
    category: str = "fund",
    liquidity: str | None = "T+1",
) -> CandidateProduct:
    return CandidateProduct(
        id=product_id,
        category=category,
        name_zh="稳健债券精选",
        name_en="Stable Bond Select",
        risk_level=risk_level,
        tags_zh=["稳健", "债券"],
        tags_en=["stable", "bond"],
        rationale_zh="适合作为稳健配置底仓。",
        rationale_en="Suitable as a stable core allocation.",
        liquidity=liquidity,
    )


def test_product_retrieval_service_filters_and_orders_candidates() -> None:
    service = ProductRetrievalService(vector_store=_StaticVectorStore())

    candidates = service.retrieve(
        query_text="一年期稳健债券",
        candidates=[_candidate("fund-001", "R2"), _candidate("fund-002", "R2")],
        allowed_risk_levels={"R2"},
    )

    assert [candidate.id for candidate in candidates] == ["fund-002", "fund-001"]


def test_product_retrieval_service_filters_out_disallowed_risk_candidates() -> None:
    service = ProductRetrievalService(vector_store=_StaticVectorStore())

    candidates = service.retrieve(
        query_text="一年期稳健债券",
        candidates=[_candidate("fund-001", "R2"), _candidate("fund-002", "R4")],
        allowed_risk_levels={"R2"},
    )

    assert [candidate.id for candidate in candidates] == ["fund-001"]


def test_product_retrieval_service_appends_allowed_non_hit_candidates_in_input_order() -> None:
    service = ProductRetrievalService(vector_store=_StaticVectorStore())

    candidates = service.retrieve(
        query_text="一年期稳健债券",
        candidates=[
            _candidate("fund-003", "R2"),
            _candidate("fund-002", "R2"),
            _candidate("fund-004", "R2"),
        ],
        allowed_risk_levels={"R2"},
    )

    assert [candidate.id for candidate in candidates] == ["fund-002", "fund-003", "fund-004"]


def test_product_retrieval_service_prioritizes_market_preferred_categories() -> None:
    service = ProductRetrievalService(vector_store=_PreferenceVectorStore())

    candidates = service.retrieve(
        query_text="防守优先配置",
        candidates=[
            _candidate("stock-001", "R3", category="stock", liquidity=None),
            _candidate("fund-001", "R2", category="fund", liquidity="T+1"),
            _candidate("wm-001", "R2", category="wealth_management", liquidity="90天"),
        ],
        allowed_risk_levels={"R1", "R2", "R3"},
        preferred_categories={"wealth_management", "fund"},
    )

    assert [candidate.id for candidate in candidates] == ["fund-001", "wm-001", "stock-001"]


def test_product_retrieval_service_filters_blocked_categories_and_low_liquidity_items() -> None:
    service = ProductRetrievalService(vector_store=_PreferenceVectorStore())

    candidates = service.retrieve(
        query_text="一年期稳健配置",
        candidates=[
            _candidate("stock-001", "R2", category="stock", liquidity=None),
            _candidate("wm-001", "R2", category="wealth_management", liquidity="90天"),
            _candidate("wm-002", "R2", category="wealth_management", liquidity="180天"),
        ],
        allowed_risk_levels={"R1", "R2"},
        blocked_categories={"stock"},
        liquidity_preference="high",
    )

    assert [candidate.id for candidate in candidates] == ["wm-001"]


def test_compliance_review_service_revises_conservative_when_risk_exceeds_profile() -> None:
    service = ComplianceReviewService()

    review = service.review(risk_tier="R2", candidates=[_candidate("fund-001", "R4")])

    assert review.verdict == "revise_conservative"
    assert review.disclosures_zh


def test_compliance_review_service_fails_closed_on_unknown_candidate_risk_level() -> None:
    service = ComplianceReviewService()

    review = service.review(risk_tier="R2", candidates=[_candidate("fund-001", "RX")])

    assert review.verdict == "revise_conservative"


def test_compliance_review_service_revises_conservative_for_illiquid_candidates() -> None:
    service = ComplianceReviewService()

    review = service.review(
        risk_tier="R2",
        liquidity_preference="medium",
        candidates=[
            _candidate(
                "wm-002",
                "R2",
                category="wealth_management",
                liquidity="180天",
            )
        ],
    )

    assert review.verdict == "revise_conservative"
    assert "流动性" in review.reason_zh
    assert any("封闭期" in note for note in review.suitability_notes_zh)
