from __future__ import annotations

from financehub_market_api.models import (
    HistoricalHolding,
    HistoricalTransaction,
    QuestionnaireAnswer,
    RiskProfile,
)
from financehub_market_api.recommendation.graph.state import UserIntelligence

_RISK_PROFILE_TO_TIER = {
    "conservative": "R2",
    "stable": "R2",
    "balanced": "R3",
    "growth": "R4",
    "aggressive": "R5",
}

_HIGH_LIQUIDITY_TOKENS = ("闲钱", "存一年", "流动", "随时", "备用")
_CAPITAL_PRESERVATION_TOKENS = ("不想亏本", "保本", "不能亏", "稳一点", "低风险")
_ONE_YEAR_TOKENS = ("一年", "12个月", "365天")


class ProfileIntelligenceService:
    def build_user_intelligence(
        self,
        *,
        risk_profile: RiskProfile,
        questionnaire_answers: list[QuestionnaireAnswer],
        historical_holdings: list[HistoricalHolding],
        historical_transactions: list[HistoricalTransaction],
        user_intent_text: str | None,
    ) -> UserIntelligence:
        normalized_text = (user_intent_text or "").strip()
        questionnaire_score = _average_questionnaire_score(questionnaire_answers)
        conservative_history = _looks_conservative_history(
            historical_holdings,
            historical_transactions,
        )

        liquidity_preference = (
            "high"
            if _contains_any(normalized_text, _HIGH_LIQUIDITY_TOKENS) or conservative_history
            else "medium"
        )
        investment_horizon = (
            "one_year" if _contains_any(normalized_text, _ONE_YEAR_TOKENS) else "medium"
        )
        drawdown_sensitivity = (
            "high"
            if _contains_any(normalized_text, _CAPITAL_PRESERVATION_TOKENS)
            or (questionnaire_score is not None and questionnaire_score <= 2.5)
            or conservative_history
            else "medium"
        )
        return_objective = (
            "steady_income" if drawdown_sensitivity == "high" else "balanced_growth"
        )
        risk_tier = _RISK_PROFILE_TO_TIER.get(risk_profile, "R2")

        profile_summary_zh = (
            f"用户风险等级{risk_tier}，偏好{investment_horizon}期限，"
            f"流动性需求{liquidity_preference}，并体现出“{normalized_text or '稳健增值'}”的诉求。"
        )
        profile_summary_en = (
            f"User maps to {risk_tier} with a {investment_horizon} horizon, "
            f"{liquidity_preference}-liquidity preference, and a capital-preservation preference."
            if drawdown_sensitivity == "high"
            else (
                f"User maps to {risk_tier} with a {investment_horizon} horizon, "
                f"{liquidity_preference}-liquidity preference, and a balanced-growth preference."
            )
        )

        return UserIntelligence(
            risk_tier=risk_tier,
            liquidity_preference=liquidity_preference,
            investment_horizon=investment_horizon,
            return_objective=return_objective,
            drawdown_sensitivity=drawdown_sensitivity,
            profile_summary_zh=profile_summary_zh,
            profile_summary_en=profile_summary_en,
        )


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _average_questionnaire_score(
    questionnaire_answers: list[QuestionnaireAnswer],
) -> float | None:
    scores = [answer.score for answer in questionnaire_answers if answer.score is not None]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _looks_conservative_history(
    holdings: list[HistoricalHolding],
    transactions: list[HistoricalTransaction],
) -> bool:
    conservative_categories = {"deposit", "bond_fund", "cash_management", "wealth_management"}
    holding_categories = {
        holding.category for holding in holdings if isinstance(holding.category, str)
    }
    transaction_categories = {
        transaction.category
        for transaction in transactions
        if isinstance(transaction.category, str)
    }
    observed_categories = holding_categories | transaction_categories
    return bool(observed_categories) and observed_categories <= conservative_categories
