from __future__ import annotations

from financehub_market_api.models import AllocationDisplay
from financehub_market_api.recommendation_catalog import (
    AGGRESSIVE_ALLOCATIONS,
    BASE_ALLOCATIONS,
    FUNDS,
    PROFILE_MARKET_SUMMARY_EN,
    PROFILE_MARKET_SUMMARY_ZH,
    STOCKS,
    WEALTH_MANAGEMENT,
)
from financehub_market_api.recommendation_types import RecommendationContext, RecommendationState


def apply_base_plan(context: RecommendationContext, state: RecommendationState) -> RecommendationState:
    state.allocation = _clone_allocation(BASE_ALLOCATIONS[context.risk_profile])
    state.aggressive_allocation = _clone_allocation(AGGRESSIVE_ALLOCATIONS[context.risk_profile])
    state.mark_applied("apply_base_plan", f"base allocation seeded for {context.risk_profile}")
    return state


def attach_market_summary(context: RecommendationContext, state: RecommendationState) -> RecommendationState:
    state.market_summary_zh = PROFILE_MARKET_SUMMARY_ZH[context.risk_profile]
    state.market_summary_en = PROFILE_MARKET_SUMMARY_EN[context.risk_profile]
    state.mark_applied("attach_market_summary", f"market summary attached for {context.risk_profile}")
    return state


def select_candidate_products(context: RecommendationContext, state: RecommendationState) -> RecommendationState:
    state.fund_items = list(FUNDS)
    state.wealth_management_items = list(WEALTH_MANAGEMENT)
    state.stock_items = list(STOCKS)
    state.mark_applied(
        "select_candidate_products",
        f"candidate products selected: funds={len(state.fund_items)}, wealth_management={len(state.wealth_management_items)}, stocks={len(state.stock_items)}",
    )
    return state


def limit_stock_exposure_for_low_risk(context: RecommendationContext, state: RecommendationState) -> RecommendationState:
    if context.risk_profile == "conservative":
        state.stock_items = state.stock_items[:1]
        detail = "low-risk stock exposure limited to top 1 item"
    else:
        detail = f"stock exposure unchanged for {context.risk_profile}"
    state.mark_applied("limit_stock_exposure_for_low_risk", detail)
    return state


def derive_review_status(context: RecommendationContext, state: RecommendationState) -> RecommendationState:
    state.review_status = "partial_pass" if context.risk_profile in {"conservative", "stable"} else "pass"
    state.mark_applied("derive_review_status", f"review status set to {state.review_status}")
    return state


def derive_plan_rationale(context: RecommendationContext, state: RecommendationState) -> RecommendationState:
    state.why_this_plan_zh = [
        f"您的风险画像为{context.profile_label_zh}，主方案优先控制整体波动。",
        "当前市场更适合稳健资产打底，再用权益类做小比例增强。",
        "基金、银行理财与股票分层配置，兼顾流动性、稳健性与收益弹性。",
    ]
    state.why_this_plan_en = [
        f"Your profile screens as {context.profile_label_en}, so the base plan prioritizes overall volatility control.",
        "Current conditions favor steadier assets as the base, with a smaller equity sleeve for upside.",
        "Layering funds, wealth management, and stocks helps balance liquidity, stability, and upside potential.",
    ]
    state.mark_applied("derive_plan_rationale", f"plan rationale generated for {context.risk_profile}")
    return state


def _clone_allocation(allocation: AllocationDisplay) -> AllocationDisplay:
    return AllocationDisplay(
        fund=allocation.fund,
        wealthManagement=allocation.wealthManagement,
        stock=allocation.stock,
    )
