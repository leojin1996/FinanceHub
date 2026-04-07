from __future__ import annotations

from financehub_market_api.models import RiskProfile
from financehub_market_api.recommendation.repositories import RealDataCandidateRepository
from financehub_market_api.recommendation.rules import RuleBasedFallbackEngine, map_user_profile
from financehub_market_api.recommendation.schemas import UserProfile
from financehub_market_api.recommendation_types import RecommendationContext, RecommendationState


def build_recommendation_context(risk_profile: RiskProfile) -> RecommendationContext:
    user_profile = map_user_profile(risk_profile)
    return RecommendationContext(
        risk_profile=risk_profile,
        profile_label_zh=user_profile.label_zh,
        profile_label_en=user_profile.label_en,
    )


def run_recommendation_flow(context: RecommendationContext) -> RecommendationState:
    fallback_engine = RuleBasedFallbackEngine(RealDataCandidateRepository())
    user_profile = UserProfile(
        risk_profile=context.risk_profile,
        label_zh=context.profile_label_zh,
        label_en=context.profile_label_en,
    )
    domain_state = fallback_engine.run(user_profile)
    if (
        domain_state.allocation is None
        or domain_state.aggressive_allocation is None
        or domain_state.market_context is None
    ):
        raise ValueError("recommendation fallback state is incomplete")

    return RecommendationState(
        allocation=domain_state.allocation.to_display(),
        aggressive_allocation=domain_state.aggressive_allocation.to_display(),
        fund_items=[item.to_api_model() for item in domain_state.fund_items],
        wealth_management_items=[item.to_api_model() for item in domain_state.wealth_management_items],
        stock_items=[item.to_api_model() for item in domain_state.stock_items],
        market_summary_zh=domain_state.market_context.summary_zh,
        market_summary_en=domain_state.market_context.summary_en,
        review_status=domain_state.review_result.review_status,
        why_this_plan_zh=domain_state.why_this_plan_zh,
        why_this_plan_en=domain_state.why_this_plan_en,
        applied_rules=domain_state.execution_trace.applied_rules,
        decision_trace=domain_state.execution_trace.decision_trace,
    )
