from __future__ import annotations

from financehub_market_api.recommendation.graph.state import (
    ComplianceReviewState,
    ManagerBrief,
    MarketIntelligenceState,
    ProductStrategy,
    UserIntelligence,
)

_CATEGORY_LABELS_ZH = {
    "wealth_management": "银行理财",
    "fund": "基金",
    "stock": "股票",
}
_CATEGORY_LABELS_EN = {
    "wealth_management": "wealth management",
    "fund": "funds",
    "stock": "stocks",
}
_HORIZON_LABELS_ZH = {
    "one_year": "一年左右",
    "medium": "中期",
}
_HORIZON_LABELS_EN = {
    "one_year": "around one year",
    "medium": "a medium-term horizon",
}
_LIQUIDITY_LABELS_ZH = {
    "high": "高流动性",
    "medium": "中等流动性",
}
_LIQUIDITY_LABELS_EN = {
    "high": "high liquidity",
    "medium": "medium liquidity",
}
_STATUS_BY_ROUTE = {
    "approved": "ready",
    "limited": "limited",
    "blocked": "blocked",
}
_SUMMARY_BY_ROUTE = {
    "approved": (
        "推荐结果已通过策略与合规校验，可按主方案查看。",
        "Recommendation passed strategy and compliance checks and is ready to present.",
    ),
    "limited": (
        "推荐结果已切换为更稳健版本，请先关注限制说明。",
        "Recommendation has been revised conservatively; review the limitation notes first.",
    ),
    "blocked": (
        "推荐结果暂不可下发，需转人工投顾复核。",
        "Recommendation is blocked and requires manual advisor review.",
    ),
}


class ManagerSynthesisService:
    def build_manager_brief(
        self,
        *,
        route: str,
        user_intelligence: UserIntelligence,
        market_intelligence: MarketIntelligenceState,
        product_strategy: ProductStrategy | None,
        compliance_review: ComplianceReviewState | None,
    ) -> ManagerBrief:
        recommendation_status = _STATUS_BY_ROUTE[route]
        summary_zh, summary_en = _SUMMARY_BY_ROUTE[route]

        recommended_categories = (
            []
            if product_strategy is None
            else list(product_strategy.recommended_categories)
        )
        category_summary_zh = _format_categories(
            recommended_categories,
            labels=_CATEGORY_LABELS_ZH,
            fallback="稳健候选",
            separator="、",
        )
        category_summary_en = _format_categories(
            recommended_categories,
            labels=_CATEGORY_LABELS_EN,
            fallback="risk-aligned candidates",
            separator=", ",
        )
        horizon_zh = _HORIZON_LABELS_ZH.get(
            user_intelligence.investment_horizon,
            user_intelligence.investment_horizon,
        )
        horizon_en = _HORIZON_LABELS_EN.get(
            user_intelligence.investment_horizon,
            user_intelligence.investment_horizon,
        )
        liquidity_zh = _LIQUIDITY_LABELS_ZH.get(
            user_intelligence.liquidity_preference,
            user_intelligence.liquidity_preference,
        )
        liquidity_en = _LIQUIDITY_LABELS_EN.get(
            user_intelligence.liquidity_preference,
            user_intelligence.liquidity_preference,
        )

        compliance_reason_zh = (
            "候选方案已通过适配性与风险校验。"
            if compliance_review is None
            else compliance_review.reason_zh
        )
        compliance_reason_en = (
            "The candidate plan passed suitability and risk checks."
            if compliance_review is None
            else compliance_review.reason_en
        )

        return ManagerBrief(
            recommendation_status=recommendation_status,
            summary_zh=summary_zh,
            summary_en=summary_en,
            why_this_plan_zh=[
                f"当前用户适配风险等级为 {user_intelligence.risk_tier}，更匹配{horizon_zh}、{liquidity_zh}的配置方案。",
                f"结合市场立场 {market_intelligence.stance}，本轮优先保留 {category_summary_zh} 作为推荐主线。",
                f"适配性与合规结论：{compliance_reason_zh}",
            ],
            why_this_plan_en=[
                f"The user maps to {user_intelligence.risk_tier} with {horizon_en} and {liquidity_en} needs.",
                f"Given the {market_intelligence.stance} market stance, this round prioritizes {category_summary_en}.",
                f"Suitability and compliance conclusion: {compliance_reason_en}",
            ],
        )


def _format_categories(
    categories: list[str],
    *,
    labels: dict[str, str],
    fallback: str,
    separator: str,
) -> str:
    mapped = [labels.get(category, category) for category in categories]
    if not mapped:
        return fallback
    return separator.join(mapped)
