from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.graph.runtime import RecommendationGraphRuntime
from financehub_market_api.recommendation.services import RecommendationService


def _build_generation_request(
    risk_profile: str,
    *,
    include_aggressive_option: bool = True,
) -> RecommendationGenerationRequest:
    return RecommendationGenerationRequest.model_validate(
        {
            "userIntentText": "我希望获得稳健配置建议",
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


def test_graph_runtime_produces_ready_response_with_trace_and_evidence() -> None:
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services()
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.executionMode == "agent_assisted"
    assert response.recommendationStatus == "ready"
    assert response.marketEvidence
    assert response.agentTrace


def test_graph_runtime_returns_limited_response_when_compliance_revises() -> None:
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_high_risk_candidate()
    )

    response = service.generate_recommendation(_build_generation_request("conservative"))

    assert response.recommendationStatus == "limited"
    assert response.complianceReview is not None
    assert response.complianceReview.verdict == "revise_conservative"
