from financehub_market_api.models import RecommendationGenerationRequest, RecommendationResponse
from financehub_market_api.recommendation.graph.runtime import RecommendationGraphRuntime
from financehub_market_api.recommendation.services import RecommendationService as DomainRecommendationService
from financehub_market_api.recommendations import RecommendationService


def _build_generation_request(
    risk_profile: str,
    *,
    include_aggressive_option: bool = True,
) -> RecommendationGenerationRequest:
    return RecommendationGenerationRequest.model_validate(
        {
            "historicalHoldings": [],
            "historicalTransactions": [],
            "includeAggressiveOption": include_aggressive_option,
            "questionnaireAnswers": [],
            "riskAssessmentResult": {
                "baseProfile": risk_profile,
                "dimensionLevels": {
                    "capitalStability": "medium",
                    "investmentExperience": "medium",
                    "investmentHorizon": "medium",
                    "returnObjective": "medium",
                    "riskTolerance": "medium",
                },
                "dimensionScores": {
                    "capitalStability": 12,
                    "investmentExperience": 12,
                    "investmentHorizon": 12,
                    "returnObjective": 12,
                    "riskTolerance": 12,
                },
                "finalProfile": risk_profile,
                "totalScore": 60,
            },
        }
    )


def _build_domain_service() -> DomainRecommendationService:
    return DomainRecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services()
    )


def _build_api_service() -> RecommendationService:
    return RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services()
    )


def test_conservative_profile_keeps_stock_exposure_small_and_review_partial() -> None:
    service = _build_api_service()

    response = service.get_recommendation("conservative")

    assert isinstance(response, RecommendationResponse)
    assert response.allocationDisplay.stock == 5
    assert response.reviewStatus == "partial_pass"
    assert response.sections.stocks.items


def test_balanced_profile_returns_grouped_sections_and_aggressive_option() -> None:
    service = _build_api_service()

    response = service.get_recommendation("balanced")

    assert response.summary.titleZh == "适合您的平衡型配置建议"
    assert response.allocationDisplay.fund == 45
    assert response.allocationDisplay.wealthManagement == 35
    assert response.allocationDisplay.stock == 20
    assert response.aggressiveOption is not None
    assert response.aggressiveOption.allocation.stock == 35
    assert response.sections.funds.items
    assert response.sections.wealthManagement.items
    assert response.sections.stocks.items


def test_domain_service_entrypoint_keeps_api_compatible_payload() -> None:
    service = _build_domain_service()

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert isinstance(response, RecommendationResponse)
    assert response.allocationDisplay.model_dump() == {
        "fund": 45,
        "wealthManagement": 35,
        "stock": 20,
    }
    assert response.sections.funds.titleZh == "基金推荐"
    assert response.profileSummary.zh
    assert response.marketSummary.zh
    assert response.riskNotice.zh
    assert response.whyThisPlan.zh
    assert response.executionMode == "agent_assisted"


def test_domain_service_can_hide_aggressive_option_from_new_contract() -> None:
    service = _build_domain_service()

    response = service.generate_recommendation(
        _build_generation_request("balanced", include_aggressive_option=False)
    )

    assert response.aggressiveOption is None


def test_generation_request_accepts_intent_and_conversation_messages() -> None:
    intent_text = "我有 10 万闲钱，想存一年，不想亏本"
    payload = RecommendationGenerationRequest.model_validate(
        {
            "userIntentText": intent_text,
            "conversationMessages": [
                {
                    "role": "user",
                    "content": intent_text,
                    "occurredAt": "2026-04-08T10:00:00Z",
                }
            ],
            "clientContext": {"channel": "web", "locale": "zh-CN"},
            "historicalHoldings": [],
            "historicalTransactions": [],
            "includeAggressiveOption": True,
            "questionnaireAnswers": [],
            "riskAssessmentResult": {
                "baseProfile": "balanced",
                "dimensionLevels": {
                    "capitalStability": "medium",
                    "investmentExperience": "medium",
                    "investmentHorizon": "medium",
                    "returnObjective": "medium",
                    "riskTolerance": "medium",
                },
                "dimensionScores": {
                    "capitalStability": 12,
                    "investmentExperience": 12,
                    "investmentHorizon": 12,
                    "returnObjective": 12,
                    "riskTolerance": 12,
                },
                "finalProfile": "balanced",
                "totalScore": 60,
            },
        }
    )

    assert payload.userIntentText == intent_text
    assert payload.conversationMessages[0].role == "user"
    assert payload.clientContext is not None
    assert payload.clientContext.locale == "zh-CN"


def test_recommendation_response_exposes_graph_fields() -> None:
    service = _build_api_service()

    response = service.get_recommendation("balanced")

    assert response.executionMode == "agent_assisted"
    assert response.recommendationStatus == "ready"
    assert response.complianceReview is None
    assert response.marketEvidence
    assert response.agentTrace


def test_domain_service_returns_limited_response_for_high_risk_candidates() -> None:
    service = DomainRecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_high_risk_candidate()
    )

    response = service.generate_recommendation(_build_generation_request("conservative"))

    assert response.executionMode == "agent_assisted"
    assert response.recommendationStatus == "limited"
    assert response.complianceReview is not None
    assert response.complianceReview.verdict == "revise_conservative"
