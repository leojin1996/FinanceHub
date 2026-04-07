from financehub_market_api.models import RecommendationResponse
from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.agents import AnthropicMultiAgentRuntime
from financehub_market_api.recommendation.agents.provider import ANTHROPIC_PROVIDER_NAME
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
        multi_agent_runtime=AnthropicMultiAgentRuntime(providers={})
    )
    return DomainRecommendationService(orchestrator=orchestrator)


def _build_api_service() -> RecommendationService:
    orchestrator = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=AnthropicMultiAgentRuntime(providers={})
    )
    return RecommendationService(orchestrator=orchestrator)


class _SequenceProvider:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self._responses = responses
        self._index = 0

    def chat_json(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        response_schema: dict[str, object],
        timeout_seconds: float,
        request_name: str | None = None,
    ) -> dict[str, object]:
        del model_name, messages, response_schema, timeout_seconds, request_name
        if self._index >= len(self._responses):
            raise AssertionError("unexpected provider call")
        response = self._responses[self._index]
        self._index += 1
        return response


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


def test_domain_service_returns_agent_generated_content_when_runtime_succeeds() -> None:
    anthropic_provider = _SequenceProvider(
        [
            {"profile_focus_zh": "稳健增值", "profile_focus_en": "steady growth"},
            {"summary_zh": "智能市场摘要：继续均衡配置", "summary_en": "Agent market summary: stay diversified"},
            {"ranked_ids": ["fund-002", "fund-001"]},
            {"ranked_ids": ["wm-002", "wm-001"]},
            {"ranked_ids": ["stock-002", "stock-001"]},
            {
                "why_this_plan_zh": ["智能解释A", "智能解释B"],
                "why_this_plan_en": ["Agent reason A", "Agent reason B"],
            },
        ]
    )
    service = DomainRecommendationService(
        orchestrator=RecommendationOrchestrator(
            candidate_repository=StaticCandidateRepository(),
            multi_agent_runtime=AnthropicMultiAgentRuntime(
                providers={ANTHROPIC_PROVIDER_NAME: anthropic_provider}
            ),
        )
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.executionMode == "agent_assisted"
    assert response.warnings == []
    assert response.marketSummary.zh == "智能市场摘要：继续均衡配置"
    assert response.whyThisPlan.zh == ["智能解释A", "智能解释B"]
    assert [item.id for item in response.sections.funds.items] == ["fund-002", "fund-001"]
    assert [item.id for item in response.sections.wealthManagement.items] == ["wm-002", "wm-001"]
    assert [item.id for item in response.sections.stocks.items] == ["stock-002", "stock-001"]
