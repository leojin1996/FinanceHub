from __future__ import annotations

from collections.abc import Callable

from financehub_market_api.models import RiskProfile
from financehub_market_api.recommendation.repositories import CandidateRepository
from financehub_market_api.recommendation.rules.profile_catalog import (
    AGGRESSIVE_ALLOCATIONS,
    BASE_ALLOCATIONS,
    PROFILE_LABELS_EN,
    PROFILE_LABELS_ZH,
    PROFILE_MARKET_SUMMARY_EN,
    PROFILE_MARKET_SUMMARY_ZH,
)
from financehub_market_api.recommendation.schemas import (
    MarketContext,
    RiskReviewResult,
    RuleEvaluationState,
    UserProfile,
)


def map_user_profile(risk_profile: RiskProfile) -> UserProfile:
    return UserProfile(
        risk_profile=risk_profile,
        label_zh=PROFILE_LABELS_ZH[risk_profile],
        label_en=PROFILE_LABELS_EN[risk_profile],
    )


def apply_base_plan(user_profile: UserProfile, state: RuleEvaluationState) -> RuleEvaluationState:
    state.allocation = BASE_ALLOCATIONS[user_profile.risk_profile]
    state.aggressive_allocation = AGGRESSIVE_ALLOCATIONS[user_profile.risk_profile]
    state.mark_applied("apply_base_plan", f"base allocation seeded for {user_profile.risk_profile}")
    return state


def attach_market_summary(user_profile: UserProfile, state: RuleEvaluationState) -> RuleEvaluationState:
    state.market_context = MarketContext(
        summary_zh=PROFILE_MARKET_SUMMARY_ZH[user_profile.risk_profile],
        summary_en=PROFILE_MARKET_SUMMARY_EN[user_profile.risk_profile],
    )
    state.mark_applied("attach_market_summary", f"market summary attached for {user_profile.risk_profile}")
    return state


def select_candidate_products(
    user_profile: UserProfile,
    state: RuleEvaluationState,
    repository: CandidateRepository,
) -> RuleEvaluationState:
    state.fund_items = repository.list_funds(user_profile)
    state.wealth_management_items = repository.list_wealth_management(user_profile)
    state.stock_items = repository.list_stocks(user_profile)
    state.mark_applied(
        "select_candidate_products",
        f"candidate products selected: funds={len(state.fund_items)}, wealth_management={len(state.wealth_management_items)}, stocks={len(state.stock_items)}",
    )
    return state


def limit_stock_exposure_for_low_risk(user_profile: UserProfile, state: RuleEvaluationState) -> RuleEvaluationState:
    if user_profile.risk_profile == "conservative":
        state.stock_items = state.stock_items[:1]
        detail = "low-risk stock exposure limited to top 1 item"
    else:
        detail = f"stock exposure unchanged for {user_profile.risk_profile}"
    state.mark_applied("limit_stock_exposure_for_low_risk", detail)
    return state


def derive_review_status(user_profile: UserProfile, state: RuleEvaluationState) -> RuleEvaluationState:
    review_status = "partial_pass" if user_profile.risk_profile in {"conservative", "stable"} else "pass"
    state.review_result = RiskReviewResult(review_status=review_status)
    state.mark_applied("derive_review_status", f"review status set to {review_status}")
    return state


def derive_plan_rationale(user_profile: UserProfile, state: RuleEvaluationState) -> RuleEvaluationState:
    state.why_this_plan_zh = [
        f"您的风险画像为{user_profile.label_zh}，主方案优先控制整体波动。",
        "当前市场更适合稳健资产打底，再用权益类做小比例增强。",
        "基金、银行理财与股票分层配置，兼顾流动性、稳健性与收益弹性。",
    ]
    state.why_this_plan_en = [
        f"Your profile screens as {user_profile.label_en}, so the base plan prioritizes overall volatility control.",
        "Current conditions favor steadier assets as the base, with a smaller equity sleeve for upside.",
        "Layering funds, wealth management, and stocks helps balance liquidity, stability, and upside potential.",
    ]
    state.mark_applied("derive_plan_rationale", f"plan rationale generated for {user_profile.risk_profile}")
    return state


Rule = Callable[[UserProfile, RuleEvaluationState], RuleEvaluationState]


class RuleBasedFallbackEngine:
    def __init__(self, repository: CandidateRepository) -> None:
        self._repository = repository

    def run(self, user_profile: UserProfile) -> RuleEvaluationState:
        state = RuleEvaluationState()
        state.execution_trace.path = "rules_fallback"
        pipeline: tuple[Rule, ...] = (
            apply_base_plan,
            attach_market_summary,
            lambda profile, current_state: select_candidate_products(profile, current_state, self._repository),
            limit_stock_exposure_for_low_risk,
            derive_review_status,
            derive_plan_rationale,
        )
        for rule in pipeline:
            state = rule(user_profile, state)
        return state
