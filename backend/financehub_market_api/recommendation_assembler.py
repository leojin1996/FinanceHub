from __future__ import annotations

from financehub_market_api.models import RecommendationProduct, RecommendationResponse
from financehub_market_api.recommendation.schemas import (
    AllocationPlan,
    CandidateProduct,
    ExecutionTrace,
    FinalRecommendation,
    MarketContext,
    RiskReviewResult,
    UserProfile,
)
from financehub_market_api.recommendation.services.assembler import assemble_recommendation_response as assemble_from_domain
from financehub_market_api.recommendation_types import RecommendationContext, RecommendationState


def assemble_recommendation_response(
    context: RecommendationContext,
    state: RecommendationState,
) -> RecommendationResponse:
    if state.allocation is None or state.aggressive_allocation is None:
        raise ValueError("recommendation state must include allocations before assembly")

    return assemble_from_domain(
        recommendation=FinalRecommendation(
            user_profile=UserProfile(
                risk_profile=context.risk_profile,
                label_zh=context.profile_label_zh,
                label_en=context.profile_label_en,
            ),
            market_context=MarketContext(
                summary_zh=state.market_summary_zh,
                summary_en=state.market_summary_en,
            ),
            allocation_plan=AllocationPlan(
                fund=state.allocation.fund,
                wealth_management=state.allocation.wealthManagement,
                stock=state.allocation.stock,
            ),
            aggressive_allocation_plan=AllocationPlan(
                fund=state.aggressive_allocation.fund,
                wealth_management=state.aggressive_allocation.wealthManagement,
                stock=state.aggressive_allocation.stock,
            ),
            fund_items=[_to_candidate_product(item) for item in state.fund_items],
            wealth_management_items=[_to_candidate_product(item) for item in state.wealth_management_items],
            stock_items=[_to_candidate_product(item) for item in state.stock_items],
            risk_review_result=RiskReviewResult(review_status=state.review_status),
            why_this_plan_zh=state.why_this_plan_zh,
            why_this_plan_en=state.why_this_plan_en,
            execution_trace=ExecutionTrace(
                applied_rules=list(state.applied_rules),
                decision_trace=list(state.decision_trace),
            ),
        )
    )


def _to_candidate_product(item: RecommendationProduct) -> CandidateProduct:
    return CandidateProduct(
        id=item.id,
        category=item.category,
        code=item.code,
        liquidity=item.liquidity,
        name_en=item.nameEn,
        name_zh=item.nameZh,
        rationale_en=item.rationaleEn,
        rationale_zh=item.rationaleZh,
        risk_level=item.riskLevel,
        tags_en=list(item.tagsEn),
        tags_zh=list(item.tagsZh),
    )
