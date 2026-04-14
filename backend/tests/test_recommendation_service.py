import pytest

from financehub_market_api.models import (
    IndexCard,
    IndicesResponse,
    MarketOverviewResponse,
    MetricCard,
    OverviewStockSummary,
    RecommendationGenerationRequest,
    RecommendationResponse,
    TrendPoint,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.graph.runtime import RecommendationGraphRuntime
from financehub_market_api.recommendation.repositories import StaticCandidateRepository
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.services import RecommendationService as DomainRecommendationService
from financehub_market_api.recommendations import RecommendationService


class _FailingGraphRuntime:
    def run(self, payload: RecommendationGenerationRequest, *, user_id: str | None = None) -> None:
        del payload, user_id
        raise RuntimeError("graph runtime crashed")


class _FakeMarketDataService:
    def get_market_overview(self) -> MarketOverviewResponse:
        return MarketOverviewResponse(
            asOfDate="2026-04-02",
            stale=False,
            metrics=[
                MetricCard(
                    label="上证指数",
                    value="3,210.12",
                    delta="+0.8%",
                    changeValue=25.1,
                    changePercent=0.8,
                    tone="positive",
                ),
                MetricCard(
                    label="深证成指",
                    value="10,120.45",
                    delta="+0.3%",
                    changeValue=30.2,
                    changePercent=0.3,
                    tone="positive",
                ),
            ],
            chartLabel="上证指数",
            trendSeries=[
                TrendPoint(date="2026-03-27", value=3180.0),
                TrendPoint(date="2026-03-30", value=3192.0),
                TrendPoint(date="2026-03-31", value=3201.0),
                TrendPoint(date="2026-04-01", value=3205.0),
                TrendPoint(date="2026-04-02", value=3210.12),
            ],
            topGainers=[
                OverviewStockSummary(
                    code="300750",
                    name="宁德时代",
                    price="210.00",
                    priceValue=210.0,
                    change="+5.00",
                    changePercent=2.4,
                )
            ],
            topLosers=[
                OverviewStockSummary(
                    code="600519",
                    name="贵州茅台",
                    price="1500.00",
                    priceValue=1500.0,
                    change="-12.00",
                    changePercent=-0.8,
                )
            ],
        )

    def get_indices(self) -> IndicesResponse:
        return IndicesResponse(
            asOfDate="2026-04-02",
            stale=False,
            cards=[
                IndexCard(
                    name="上证指数",
                    code="000001",
                    market="SH",
                    description="上海证券交易所综合指数",
                    value="3,210.12",
                    valueNumber=3210.12,
                    changeValue=25.1,
                    changePercent=0.8,
                    tone="positive",
                    trendSeries=[
                        TrendPoint(date="2026-03-31", value=3201.0),
                        TrendPoint(date="2026-04-01", value=3205.0),
                        TrendPoint(date="2026-04-02", value=3210.12),
                    ],
                ),
                IndexCard(
                    name="深证成指",
                    code="399001",
                    market="SZ",
                    description="深圳证券交易所成份指数",
                    value="10,120.45",
                    valueNumber=10120.45,
                    changeValue=30.2,
                    changePercent=0.3,
                    tone="positive",
                    trendSeries=[
                        TrendPoint(date="2026-03-31", value=10050.0),
                        TrendPoint(date="2026-04-01", value=10090.0),
                        TrendPoint(date="2026-04-02", value=10120.45),
                    ],
                ),
                IndexCard(
                    name="创业板指",
                    code="399006",
                    market="SZ",
                    description="创业板指数",
                    value="2,150.00",
                    valueNumber=2150.0,
                    changeValue=-5.0,
                    changePercent=-0.2,
                    tone="negative",
                    trendSeries=[
                        TrendPoint(date="2026-03-31", value=2160.0),
                        TrendPoint(date="2026-04-01", value=2155.0),
                        TrendPoint(date="2026-04-02", value=2150.0),
                    ],
                ),
            ],
        )


def _build_generation_request(
    risk_profile: str,
    *,
    include_aggressive_option: bool = True,
    user_intent_text: str | None = None,
) -> RecommendationGenerationRequest:
    return RecommendationGenerationRequest.model_validate(
        {
            "userIntentText": user_intent_text,
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


def test_conservative_profile_zeroes_stock_allocation_when_no_stock_candidates_survive() -> None:
    service = _build_api_service()

    response = service.get_recommendation("conservative")

    assert isinstance(response, RecommendationResponse)
    assert response.allocationDisplay.fund == 25
    assert response.allocationDisplay.wealthManagement == 75
    assert response.allocationDisplay.stock == 0
    assert response.reviewStatus == "partial_pass"
    assert response.recommendationStatus == "limited"
    assert response.complianceReview is not None
    assert response.sections.stocks.items == []


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


def test_recommendation_service_prefers_graph_runtime_output_by_default() -> None:
    service = DomainRecommendationService()

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.executionMode == "agent_assisted"
    assert response.agentTrace[-1].requestName == "manager_coordinator"


def test_domain_service_uses_manager_brief_for_grounded_plan_explanation() -> None:
    service = _build_domain_service()

    response = service.generate_recommendation(
        _build_generation_request(
            "stable",
            user_intent_text="我有10万闲钱，想存一年，不想亏本",
        )
    )

    assert any("银行理财、基金" in line for line in response.whyThisPlan.zh)
    assert any("R2" in line for line in response.whyThisPlan.zh)


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


def test_recommendation_response_exposes_detail_routes_and_as_of_dates() -> None:
    service = _build_api_service()

    response = service.get_recommendation("balanced")

    first_fund = response.sections.funds.items[0]
    assert first_fund.detailRoute is not None
    assert first_fund.detailRoute.startswith("/recommendations/products/")
    assert first_fund.asOfDate is not None


def test_default_graph_runtime_uses_market_data_service_for_market_intelligence() -> None:
    from financehub_market_api.recommendation.compliance import ComplianceFactsService
    from financehub_market_api.recommendation.graph.runtime import GraphServices
    from financehub_market_api.recommendation.memory import MemoryRecallService
    from financehub_market_api.recommendation.product_index import ProductRetrievalService

    class _MemoryStore:
        def search(self, query: str, *, limit: int) -> list[str]:
            del query
            return ["memory:balanced"][:limit]

    class _VectorStore:
        def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
            del query_text
            return [
                {"id": "fund-001", "score": 0.99},
                {"id": "wm-001", "score": 0.95},
                {"id": "stock-001", "score": 0.9},
            ][:limit]

    class _RuntimeDouble:
        def analyze_user_profile(self, user_profile, *, prompt_context=None):
            del user_profile, prompt_context
            from financehub_market_api.recommendation.agents.contracts import UserProfileAgentOutput
            from financehub_market_api.recommendation.agents.live_runtime import AgentInvocationMetadata

            return (
                UserProfileAgentOutput(
                    risk_tier="R3",
                    liquidity_preference="medium",
                    investment_horizon="medium",
                    return_objective="balanced_growth",
                    drawdown_sensitivity="medium",
                    profile_focus_zh="测试画像。",
                    profile_focus_en="Test profile.",
                    derived_signals=["questionnaire:test"],
                ),
                AgentInvocationMetadata(provider_name="openai", model_name="test-user"),
            )

        def analyze_market_intelligence(
            self,
            user_profile,
            user_profile_insights,
            market_facts,
            *,
            prompt_context=None,
        ):
            del user_profile, user_profile_insights, prompt_context
            from financehub_market_api.recommendation.agents.contracts import MarketIntelligenceAgentOutput
            from financehub_market_api.recommendation.agents.live_runtime import AgentInvocationMetadata

            return (
                MarketIntelligenceAgentOutput(
                    sentiment="positive",
                    stance="offensive",
                    preferred_categories=["fund", "stock"],
                    avoided_categories=[],
                    summary_zh=market_facts["summary_zh"],
                    summary_en=market_facts["summary_en"],
                    evidence_refs=["market_overview", "indices", "market_leadership"],
                ),
                AgentInvocationMetadata(provider_name="openai", model_name="test-market"),
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
            del user_profile, user_profile_insights, market_intelligence, prompt_context
            from financehub_market_api.recommendation.agents.contracts import ProductMatchAgentOutput
            from financehub_market_api.recommendation.agents.live_runtime import AgentInvocationMetadata

            return (
                ProductMatchAgentOutput(
                    recommended_categories=["fund", "wealth_management", "stock"],
                    fund_ids=[candidate.id for candidate in candidates if candidate.category == "fund"][:1],
                    wealth_management_ids=[candidate.id for candidate in candidates if candidate.category == "wealth_management"][:1],
                    stock_ids=[candidate.id for candidate in candidates if candidate.category == "stock"][:1],
                    ranking_rationale_zh="测试匹配。",
                    ranking_rationale_en="Test match.",
                    filtered_out_reasons=[],
                ),
                AgentInvocationMetadata(provider_name="openai", model_name="test-match"),
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
            del user_profile, user_profile_insights, compliance_facts, prompt_context
            from financehub_market_api.recommendation.agents.contracts import ComplianceReviewAgentOutput
            from financehub_market_api.recommendation.agents.live_runtime import AgentInvocationMetadata

            return (
                ComplianceReviewAgentOutput(
                    verdict="approve",
                    approved_ids=[candidate.id for candidate in selected_candidates],
                    rejected_ids=[],
                    reason_summary_zh="测试通过。",
                    reason_summary_en="Approved for test.",
                    required_disclosures_zh=["理财非存款，投资需谨慎。"],
                    required_disclosures_en=["Investing involves risk. Proceed prudently."],
                    suitability_notes_zh=["适配通过。"],
                    suitability_notes_en=["Approved."],
                    applied_rule_ids=["test-rule"],
                    blocking_reason_codes=[],
                ),
                AgentInvocationMetadata(provider_name="openai", model_name="test-compliance"),
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
            del user_profile, user_profile_insights, market_intelligence, product_match, compliance_review, prompt_context
            from financehub_market_api.recommendation.agents.contracts import ManagerCoordinatorAgentOutput
            from financehub_market_api.recommendation.agents.live_runtime import AgentInvocationMetadata

            return (
                ManagerCoordinatorAgentOutput(
                    recommendation_status="ready",
                    summary_zh="测试经理总结。",
                    summary_en="Test manager summary.",
                    why_this_plan_zh=["测试理由。"],
                    why_this_plan_en=["Test reason."],
                ),
                AgentInvocationMetadata(provider_name="openai", model_name="test-manager"),
            )

    repository = StaticCandidateRepository()
    user_profile = map_user_profile("balanced")
    candidates = [
        *repository.list_funds(user_profile),
        *repository.list_wealth_management(user_profile),
        *repository.list_stocks(user_profile),
    ]
    service = DomainRecommendationService(
        graph_runtime=RecommendationGraphRuntime(
            GraphServices(
                market_intelligence=MarketIntelligenceService(
                    market_data_service=_FakeMarketDataService()
                ),
                memory_recall=MemoryRecallService(store=_MemoryStore()),
                product_retrieval=ProductRetrievalService(vector_store=_VectorStore()),
                compliance_facts_service=ComplianceFactsService(),
                product_candidates=candidates,
                agent_runtime=_RuntimeDouble(),
            )
        )
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.marketSummary.zh.startswith("市场概览（截至 2026-04-02）")
    assert "宁德时代" in response.marketSummary.zh
    assert response.marketSummary.en.startswith("Market overview as of 2026-04-02")
    assert response.marketEvidence[0].source == "market_overview"
    assert response.marketEvidence[0].asOf == "2026-04-02"


def test_domain_service_filters_high_risk_candidates_before_compliance_for_conservative_users() -> None:
    service = DomainRecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_high_risk_candidate()
    )

    response = service.generate_recommendation(_build_generation_request("conservative"))

    assert response.executionMode == "agent_assisted"
    assert response.recommendationStatus == "limited"
    assert response.reviewStatus == "partial_pass"
    assert response.complianceReview is not None
    assert response.sections.stocks.items == []


def test_domain_service_raises_when_graph_runtime_fails() -> None:
    service = DomainRecommendationService(graph_runtime=_FailingGraphRuntime())

    with pytest.raises(RuntimeError, match="graph runtime crashed"):
        service.generate_recommendation(_build_generation_request("balanced"))


def test_domain_service_rejects_legacy_orchestrator_injection() -> None:
    with pytest.raises(ValueError, match="orchestrator"):
        DomainRecommendationService(orchestrator=object())  # type: ignore[arg-type]


def test_domain_service_does_not_fallback_when_graph_response_assembly_raises(
    monkeypatch,
) -> None:
    service = DomainRecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services(),
    )

    def _raise_assembly_error(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("assembly failed")

    monkeypatch.setattr(
        "financehub_market_api.recommendation.services.recommendation_service.assemble_graph_recommendation_response",
        _raise_assembly_error,
    )

    with pytest.raises(RuntimeError, match="assembly failed"):
        service.generate_recommendation(_build_generation_request("balanced"))
