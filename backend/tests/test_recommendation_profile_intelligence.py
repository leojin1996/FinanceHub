from financehub_market_api.models import (
    HistoricalHolding,
    HistoricalTransaction,
    QuestionnaireAnswer,
)
from financehub_market_api.recommendation.profile_intelligence.service import (
    ProfileIntelligenceService,
)


def test_profile_service_derives_capital_preservation_preferences_from_intent() -> None:
    service = ProfileIntelligenceService()

    result = service.build_user_intelligence(
        risk_profile="stable",
        questionnaire_answers=[
            QuestionnaireAnswer(
                questionId="q1",
                answerId="a1",
                dimension="riskTolerance",
                score=2,
            )
        ],
        historical_holdings=[
            HistoricalHolding(
                symbol="CASH-001",
                category="deposit",
                quantity=1,
                marketValue=100000,
            )
        ],
        historical_transactions=[
            HistoricalTransaction(
                symbol="BOND-001",
                action="buy",
                category="bond_fund",
                amount=50000,
                occurredAt="2026-03-01T10:00:00Z",
            )
        ],
        user_intent_text="我有10万闲钱，想存一年，不想亏本",
    )

    assert result.risk_tier == "R2"
    assert result.liquidity_preference == "high"
    assert result.investment_horizon == "one_year"
    assert result.return_objective == "steady_income"
    assert result.drawdown_sensitivity == "high"
    assert "不想亏本" in result.profile_summary_zh
    assert "capital-preservation" in result.profile_summary_en


def test_profile_service_defaults_to_balanced_preferences_without_clear_signal() -> None:
    service = ProfileIntelligenceService()

    result = service.build_user_intelligence(
        risk_profile="balanced",
        questionnaire_answers=[],
        historical_holdings=[],
        historical_transactions=[],
        user_intent_text="希望资产稳健增值，同时保留一些增长空间",
    )

    assert result.risk_tier == "R3"
    assert result.liquidity_preference == "medium"
    assert result.investment_horizon == "medium"
    assert result.return_objective == "balanced_growth"
    assert result.drawdown_sensitivity == "medium"
