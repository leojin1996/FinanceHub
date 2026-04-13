from financehub_market_api.recommendation.graph.state import (
    ComplianceReviewState,
    MarketIntelligenceState,
    ProductStrategy,
    UserIntelligence,
)
from financehub_market_api.recommendation.manager_synthesis.service import (
    ManagerSynthesisService,
)


def test_manager_synthesis_service_builds_grounded_brief() -> None:
    service = ManagerSynthesisService()

    brief = service.build_manager_brief(
        route="approved",
        user_intelligence=UserIntelligence(
            risk_tier="R2",
            liquidity_preference="high",
            investment_horizon="one_year",
            return_objective="steady_income",
            drawdown_sensitivity="high",
            profile_summary_zh="用户表达了不想亏本，希望保留流动性。",
            profile_summary_en="User expressed a capital-preservation preference.",
        ),
        market_intelligence=MarketIntelligenceState(
            sentiment="neutral",
            stance="balanced",
            preferred_categories=["fund", "stock"],
            avoided_categories=[],
            summary_zh="市场处于震荡环境。",
            summary_en="Markets are range-bound.",
            evidence=[],
        ),
        product_strategy=ProductStrategy(
            recommended_categories=["wealth_management", "fund"],
            ranking_rationale_zh="优先配置银行理财和基金。",
            ranking_rationale_en="Prioritize wealth management and funds.",
        ),
        compliance_review=ComplianceReviewState(
            verdict="approve",
            reason_zh="候选产品均在风险承受范围内。",
            reason_en="All products are within the allowed risk range.",
            disclosures_zh=["市场有风险，投资需谨慎。"],
            disclosures_en=["Investing involves risk."],
        ),
    )

    assert brief.recommendation_status == "ready"
    assert any("R2" in line for line in brief.why_this_plan_zh)
    assert any("银行理财、基金" in line for line in brief.why_this_plan_zh)
    assert brief.summary_zh.startswith("推荐结果")
