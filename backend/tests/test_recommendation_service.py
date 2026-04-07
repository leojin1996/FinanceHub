from financehub_market_api.models import RecommendationResponse
from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.agents import OpenAIMultiAgentRuntime
from financehub_market_api.recommendation.orchestration import RecommendationOrchestrator
from financehub_market_api.recommendation.repositories import StaticCandidateRepository
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
    orchestrator = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=OpenAIMultiAgentRuntime(providers={})
    )
    return DomainRecommendationService(orchestrator=orchestrator)


def _build_api_service() -> RecommendationService:
    orchestrator = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=OpenAIMultiAgentRuntime(providers={})
    )
    return RecommendationService(orchestrator=orchestrator)


def test_conservative_profile_keeps_stock_exposure_small_and_review_partial() -> None:
    service = _build_api_service()

    response = service.get_recommendation("conservative")

    assert isinstance(response, RecommendationResponse)
    assert response.allocationDisplay.stock == 5
    assert response.reviewStatus == "partial_pass"
    assert response.sections.stocks.items[0].nameZh == "招商银行"
    assert len(response.sections.stocks.items) == 1


def test_balanced_profile_returns_grouped_sections_and_aggressive_option() -> None:
    service = _build_api_service()

    response = service.get_recommendation("balanced")

    assert response.summary.titleZh == "适合您的平衡型配置建议"
    assert response.allocationDisplay.fund == 45
    assert response.allocationDisplay.wealthManagement == 35
    assert response.allocationDisplay.stock == 20
    assert response.aggressiveOption is not None
    assert response.aggressiveOption.allocation.stock == 35
    assert len(response.sections.funds.items) == 2
    assert len(response.sections.wealthManagement.items) == 2
    assert len(response.sections.stocks.items) == 2
    assert any("稳健资产" in reason for reason in response.whyThisPlan.zh)


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
    assert response.executionMode == "rules_fallback"
    assert response.warnings


def test_domain_service_can_hide_aggressive_option_from_new_contract() -> None:
    service = _build_domain_service()

    response = service.generate_recommendation(
        _build_generation_request("balanced", include_aggressive_option=False)
    )

    assert response.aggressiveOption is None
