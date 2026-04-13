from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    ManagerCoordinatorAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.graph.runtime import (
    GraphServices,
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.schemas import CandidateProduct
from financehub_market_api.recommendation.services import RecommendationService


class _SingleMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        del query
        return ["memory:capital_preservation"][:limit]


class _SingleVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [{"id": "fund-001", "score": 0.99}, {"id": "wm-001", "score": 0.95}][:limit]


class _AIOnlyRuntimeDouble:
    def analyze_user_profile(self, user_profile, *, prompt_context=None):
        del user_profile, prompt_context
        return (
            UserProfileAgentOutput(
                risk_tier="R2",
                liquidity_preference="high",
                investment_horizon="one_year",
                return_objective="capital_preservation",
                drawdown_sensitivity="high",
                profile_focus_zh="用户强调一年期保本与高流动性。",
                profile_focus_en="The user emphasizes one-year capital preservation and high liquidity.",
                derived_signals=["questionnaire:low_risk", "conversation:reserve_cash"],
            ),
            type(
                "Metadata",
                (),
                {"provider_name": "openai", "model_name": "gpt-5.4-user-profile", "tool_calls": ()},
            )(),
        )

    def analyze_market_intelligence(
        self,
        user_profile,
        user_profile_insights,
        market_facts,
        *,
        prompt_context=None,
    ):
        del user_profile, user_profile_insights, market_facts, prompt_context
        return (
            MarketIntelligenceAgentOutput(
                sentiment="negative",
                stance="defensive",
                preferred_categories=["wealth_management", "fund"],
                avoided_categories=["stock"],
                summary_zh="市场震荡偏弱，优先稳健和流动性。",
                summary_en="Markets are soft and volatile, so favor resilience and liquidity.",
                evidence_refs=["market_overview", "macro_and_rates"],
            ),
            type(
                "Metadata",
                (),
                {"provider_name": "openai", "model_name": "gpt-5.4-market", "tool_calls": ()},
            )(),
        )

    def match_products(
        self,
        user_profile,
        *,
        user_profile_insights,
        market_intelligence,
        candidates,
        prompt_context=None,
    ):
        del user_profile, user_profile_insights, market_intelligence, candidates, prompt_context
        return (
            ProductMatchAgentOutput(
                recommended_categories=["wealth_management", "fund"],
                fund_ids=["fund-001"],
                wealth_management_ids=["wm-001"],
                stock_ids=[],
                ranking_rationale_zh="AI 认为固收与现金管理更适配。",
                ranking_rationale_en="AI prefers fixed-income and cash-management products.",
                filtered_out_reasons=["stock filtered by defensive stance"],
            ),
            type(
                "Metadata",
                (),
                {"provider_name": "openai", "model_name": "gpt-5.4-product-match", "tool_calls": ()},
            )(),
        )

    def review_compliance(
        self,
        user_profile,
        *,
        user_profile_insights,
        selected_candidates,
        compliance_facts,
        prompt_context=None,
    ):
        del user_profile, user_profile_insights, selected_candidates, compliance_facts, prompt_context
        return (
            ComplianceReviewAgentOutput(
                verdict="approve",
                approved_ids=["fund-001", "wm-001"],
                rejected_ids=[],
                reason_summary_zh="候选通过适当性与合规审核。",
                reason_summary_en="Candidates passed suitability and compliance review.",
                required_disclosures_zh=["理财非存款，投资需谨慎。"],
                required_disclosures_en=["Investing involves risk. Proceed prudently."],
                suitability_notes_zh=["风险等级和流动性均匹配。"],
                suitability_notes_en=["Risk level and liquidity are aligned."],
                applied_rule_ids=["cn-suitability-r2"],
                blocking_reason_codes=[],
            ),
            type(
                "Metadata",
                (),
                {"provider_name": "openai", "model_name": "gpt-5.4-compliance", "tool_calls": ()},
            )(),
        )

    def coordinate_manager(
        self,
        user_profile,
        *,
        user_profile_insights,
        market_intelligence,
        product_match,
        compliance_review,
        prompt_context=None,
    ):
        del (
            user_profile,
            user_profile_insights,
            market_intelligence,
            product_match,
            compliance_review,
            prompt_context,
        )
        return (
            ManagerCoordinatorAgentOutput(
                recommendation_status="ready",
                summary_zh="建议以稳健基金和现金管理为主。",
                summary_en="Favor resilient funds and cash management products.",
                why_this_plan_zh=["优先满足一年期保本与流动性要求。"],
                why_this_plan_en=["This plan prioritizes one-year capital preservation and liquidity."],
            ),
            type(
                "Metadata",
                (),
                {"provider_name": "openai", "model_name": "gpt-5.4-manager", "tool_calls": ()},
            )(),
        )


class _FlatSelectionRuntimeDouble(_AIOnlyRuntimeDouble):
    def match_products(
        self,
        user_profile,
        *,
        user_profile_insights,
        market_intelligence,
        candidates,
        prompt_context=None,
    ):
        del user_profile, user_profile_insights, market_intelligence, candidates, prompt_context
        return (
            ProductMatchAgentOutput(
                recommended_categories=[],
                selected_product_ids=["wm-001", "fund-001"],
                fund_ids=[],
                wealth_management_ids=[],
                stock_ids=[],
                ranking_rationale_zh="AI 以扁平 ID 列表返回最终候选。",
                ranking_rationale_en="AI returned the final selection as a flat id list.",
                filtered_out_reasons=[],
            ),
            type(
                "Metadata",
                (),
                {"provider_name": "openai", "model_name": "gpt-5.4-product-match", "tool_calls": ()},
            )(),
        )


def _build_generation_request() -> RecommendationGenerationRequest:
    return RecommendationGenerationRequest.model_validate(
        {
            "userIntentText": "我有10万闲钱，想存一年，不想亏本。",
            "conversationMessages": [
                {
                    "role": "user",
                    "content": "最近市场波动大，我更在意保本和流动性。",
                    "occurredAt": "2026-04-10T08:00:00Z",
                }
            ],
            "historicalHoldings": [],
            "historicalTransactions": [],
            "questionnaireAnswers": [
                {
                    "questionId": "q1",
                    "answerId": "a1",
                    "dimension": "riskTolerance",
                    "score": 2,
                }
            ],
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


def _candidate(product_id: str, *, category: str, risk_level: str) -> CandidateProduct:
    return CandidateProduct(
        id=product_id,
        category=category,
        code=product_id.upper(),
        liquidity="T+1",
        name_zh=f"{product_id}-zh",
        name_en=f"{product_id}-en",
        rationale_zh="候选理由",
        rationale_en="candidate rationale",
        risk_level=risk_level,
        tags_zh=["稳健"],
        tags_en=["stable"],
    )


def test_graph_runtime_blocks_when_ai_runtime_is_missing() -> None:
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_default_services(use_ai_agents=False)
    )

    response = service.generate_recommendation(_build_generation_request())

    assert response.recommendationStatus == "blocked"
    assert response.complianceReview is not None
    assert response.complianceReview.verdict == "block"


def test_graph_runtime_accepts_flat_selected_product_ids_from_agent() -> None:
    candidates = [
        _candidate("fund-001", category="fund", risk_level="R2"),
        _candidate("wm-001", category="wealth_management", risk_level="R1"),
    ]
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime(
            GraphServices(
                market_intelligence=MarketIntelligenceService(),
                memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
                product_retrieval=ProductRetrievalService(vector_store=_SingleVectorStore()),
                product_candidates=candidates,
                agent_runtime=_FlatSelectionRuntimeDouble(),
            )
        )
    )

    response = service.generate_recommendation(_build_generation_request())

    assert response.recommendationStatus == "ready"
    assert [item.id for item in response.sections.wealthManagement.items] == ["wm-001"]
    assert [item.id for item in response.sections.funds.items] == ["fund-001"]


def test_graph_runtime_exposes_structured_ai_outputs_in_response() -> None:
    runtime = RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(vector_store=_SingleVectorStore()),
            compliance_review_service=None,
            compliance_facts_service=None,
            product_candidates=[
                _candidate("fund-001", category="fund", risk_level="R2"),
                _candidate("wm-001", category="wealth_management", risk_level="R1"),
            ],
            agent_runtime=_AIOnlyRuntimeDouble(),
        )
    )
    service = RecommendationService(graph_runtime=runtime)

    response = service.generate_recommendation(_build_generation_request())

    assert response.recommendationStatus == "ready"
    assert response.profileInsights is not None
    assert response.profileInsights.riskTier == "R2"
    assert response.marketIntelligence is not None
    assert response.marketIntelligence.stance == "defensive"
    assert response.sections.stocks.items == []
    assert all(item.riskLevel in {"R1", "R2"} for item in response.sections.funds.items + response.sections.wealthManagement.items)
    assert [event.requestName for event in response.agentTrace] == [
        "user_profile_analyst",
        "market_intelligence",
        "product_match_expert",
        "compliance_risk_officer",
        "manager_coordinator",
    ]
