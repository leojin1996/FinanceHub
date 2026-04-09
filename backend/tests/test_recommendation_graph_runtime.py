from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.agents.contracts import (
    ExplanationAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductRankingAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.live_runtime import (
    AgentInvocationMetadata,
)
from financehub_market_api.recommendation.agents.runtime_context import (
    AgentPromptContext,
    AgentToolCallRecord,
    SelectedPlanContext,
)
from financehub_market_api.recommendation.compliance import ComplianceReviewService
from financehub_market_api.recommendation.graph.runtime import (
    GraphServices,
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.repositories import StaticCandidateRepository
from financehub_market_api.recommendation.repositories.real_data_repository import (
    RealDataCandidateRepository,
)
from financehub_market_api.recommendation.schemas import (
    CandidateProduct,
    MarketContext,
    UserProfile,
)
from financehub_market_api.recommendation.services import RecommendationService


def _build_generation_request(
    risk_profile: str,
    *,
    include_aggressive_option: bool = True,
    user_intent_text: str | None = "我希望获得稳健配置建议",
    questionnaire_answers: list[dict[str, object]] | None = None,
    historical_holdings: list[dict[str, object]] | None = None,
    historical_transactions: list[dict[str, object]] | None = None,
    conversation_messages: list[dict[str, object]] | None = None,
    client_context: dict[str, object] | None = None,
) -> RecommendationGenerationRequest:
    return RecommendationGenerationRequest.model_validate(
        {
            "userIntentText": user_intent_text,
            "historicalHoldings": historical_holdings or [],
            "historicalTransactions": historical_transactions or [],
            "includeAggressiveOption": include_aggressive_option,
            "questionnaireAnswers": questionnaire_answers or [],
            "conversationMessages": conversation_messages or [],
            "clientContext": client_context,
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


def test_graph_runtime_executes_funnel_nodes_in_order() -> None:
    runtime = RecommendationGraphRuntime.with_deterministic_services()

    final_state = runtime.run(_build_generation_request("balanced"))

    assert [event.requestName for event in final_state["agent_trace"]] == [
        "user_profile_analyst",
        "market_intelligence",
        "product_match_expert",
        "compliance_risk_officer",
        "manager_coordinator",
    ]


def test_graph_runtime_filters_high_risk_candidates_before_compliance_for_conservative_users() -> (
    None
):
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_high_risk_candidate()
    )

    response = service.generate_recommendation(
        _build_generation_request("conservative")
    )

    assert response.recommendationStatus == "ready"
    assert response.reviewStatus == "pass"
    assert response.complianceReview is None
    assert response.sections.stocks.items == []
    assert all(
        item.riskLevel in {"R1", "R2"}
        for section in (
            response.sections.funds.items,
            response.sections.wealthManagement.items,
            response.sections.stocks.items,
        )
        for item in section
    )


def test_graph_runtime_builds_defensive_product_strategy_for_capital_preservation_intent() -> (
    None
):
    runtime = RecommendationGraphRuntime.with_deterministic_services()

    final_state = runtime.run(
        _build_generation_request(
            "stable",
            user_intent_text="我有10万闲钱，想存一年，不想亏本",
        )
    )

    product_strategy = final_state["product_strategy"]
    manager_brief = final_state["manager_brief"]
    retrieval_context = final_state["retrieval_context"]

    assert product_strategy is not None
    assert product_strategy.recommended_categories == ["wealth_management", "fund"]
    assert manager_brief is not None
    assert any("银行理财、基金" in line for line in manager_brief.why_this_plan_zh)
    assert retrieval_context is not None
    assert all(item.category != "stock" for item in retrieval_context.candidates)
    assert any("stock" in reason for reason in retrieval_context.filtered_out_reasons)


class _SingleMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        del query
        return ["runtime-memory"][:limit]


class _SingleVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [{"id": "fund-001", "score": 0.99}][:limit]


class _IlliquidVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [{"id": "wm-illiquid", "score": 0.99}][:limit]


class _FakeFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def iterrows(self):
        for index, row in enumerate(self._rows):
            yield index, row


class _RefreshingRepository:
    def __init__(self) -> None:
        self._fund_calls = 0

    def list_funds(self, user_profile) -> list[CandidateProduct]:
        del user_profile
        self._fund_calls += 1
        fund_name = "首次快照基金" if self._fund_calls == 1 else "恢复后基金"
        return [
            CandidateProduct(
                id="fund-001",
                category="fund",
                code="000001",
                liquidity="T+1",
                name_zh=fund_name,
                name_en=fund_name,
                rationale_zh="测试基金候选。",
                rationale_en="Test fund candidate.",
                risk_level="R2",
                tags_zh=["测试"],
                tags_en=["test"],
            )
        ]

    def list_wealth_management(self, user_profile) -> list[CandidateProduct]:
        del user_profile
        return [
            CandidateProduct(
                id="wm-001",
                category="wealth_management",
                code="511990",
                liquidity="T+0",
                name_zh="稳定现金管理",
                name_en="Stable Cash Management",
                rationale_zh="测试现金管理候选。",
                rationale_en="Test cash management candidate.",
                risk_level="R1",
                tags_zh=["测试"],
                tags_en=["test"],
            )
        ]

    def list_stocks(self, user_profile) -> list[CandidateProduct]:
        del user_profile
        return []


def test_graph_runtime_uses_runtime_candidate_metadata_over_static_catalog() -> None:
    runtime_candidate = CandidateProduct(
        id="fund-001",
        category="fund",
        code="900001",
        liquidity="T+0",
        name_zh="运行时自定义基金A",
        name_en="Runtime Custom Fund A",
        rationale_zh="使用实时候选产品元数据。",
        rationale_en="Use runtime candidate metadata.",
        risk_level="R2",
        tags_zh=["实时"],
        tags_en=["runtime"],
    )
    runtime = RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(
                vector_store=_SingleVectorStore()
            ),
            compliance_review=ComplianceReviewService(),
            product_candidates=[runtime_candidate],
        )
    )
    service = RecommendationService(graph_runtime=runtime)

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.sections.funds.items[0].id == "fund-001"
    assert response.sections.funds.items[0].nameZh == "运行时自定义基金A"
    assert response.sections.funds.items[0].nameZh != "中欧稳利债券A"


def test_graph_runtime_marks_low_risk_illiquid_candidates_as_limited() -> None:
    runtime = RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(
                vector_store=_IlliquidVectorStore()
            ),
            compliance_review=ComplianceReviewService(),
            product_candidates=[
                CandidateProduct(
                    id="wm-illiquid",
                    category="wealth_management",
                    code="WM9999",
                    liquidity="180天",
                    name_zh="封闭增强理财",
                    name_en="Closed-End Enhanced WM",
                    rationale_zh="测试长封闭期候选。",
                    rationale_en="Test illiquid candidate.",
                    risk_level="R2",
                    tags_zh=["封闭期较长"],
                    tags_en=["long lock-up"],
                )
            ],
        )
    )
    service = RecommendationService(graph_runtime=runtime)

    response = service.generate_recommendation(_build_generation_request("stable"))

    assert response.recommendationStatus == "limited"
    assert response.reviewStatus == "partial_pass"
    assert response.complianceReview is not None
    assert "流动性" in response.complianceReview.reasonSummary.zh
    assert any(
        "封闭期" in note for note in response.complianceReview.suitabilityNotes.zh
    )


def test_graph_runtime_uses_explicit_real_repository_candidates(monkeypatch) -> None:
    from financehub_market_api.recommendation.repositories import real_data_adapters

    monkeypatch.setattr(
        real_data_adapters.ak,
        "fund_open_fund_rank_em",
        lambda symbol: _FakeFrame(
            [
                {
                    "基金代码": "000001",
                    "基金简称": "稳健债券A",
                    "日期": "2026-04-02",
                    "单位净值": "1.1234",
                    "手续费": "0.15%",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        real_data_adapters.ak,
        "fund_money_rank_em",
        lambda: _FakeFrame(
            [
                {
                    "基金代码": "511990",
                    "基金简称": "华宝添益",
                    "日期": "2026-04-02",
                    "年化收益率7日": "1.88%",
                    "手续费": "0.00%",
                }
            ]
        ),
    )

    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_default_services(
            repository=RealDataCandidateRepository()
        )
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.executionMode == "agent_assisted"
    assert response.sections.funds.items[0].nameZh == "稳健债券A"
    assert response.sections.wealthManagement.items[0].nameZh == "华宝添益"


def test_app_default_graph_runtime_refreshes_repository_candidates_between_requests() -> (
    None
):
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_default_services(
            repository=_RefreshingRepository()
        )
    )

    first_response = service.generate_recommendation(
        _build_generation_request("balanced")
    )
    second_response = service.generate_recommendation(
        _build_generation_request("balanced")
    )

    assert first_response.sections.funds.items[0].nameZh == "首次快照基金"
    assert second_response.sections.funds.items[0].nameZh == "恢复后基金"


class _AllCandidatesVectorStore:
    def __init__(self, candidates: list[CandidateProduct]) -> None:
        self._ids = [candidate.id for candidate in candidates]

    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [
            {"id": product_id, "score": max(0.01, 1.0 - index * 0.05)}
            for index, product_id in enumerate(self._ids[:limit])
        ]


class _FakeAgentRuntime:
    _MODEL_BY_REQUEST = {
        "user_profile": "claude-user-profile",
        "market_intelligence": "claude-market-intel",
        "fund_selection": "claude-fund-ranker",
        "wealth_selection": "claude-wealth-ranker",
        "stock_selection": "claude-stock-ranker",
        "explanation": "claude-explainer",
    }

    def analyze_user_profile(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[UserProfileAgentOutput, AgentInvocationMetadata]:
        del user_profile, prompt_context
        return (
            UserProfileAgentOutput(
                profile_focus_zh="AI画像强调流动性和回撤控制。",
                profile_focus_en="AI profile focus prioritizes liquidity and drawdown control.",
            ),
            AgentInvocationMetadata(
                provider_name="anthropic",
                model_name=self._MODEL_BY_REQUEST["user_profile"],
            ),
        )

    def analyze_market_intelligence(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        fallback_context: MarketContext,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[MarketIntelligenceAgentOutput, AgentInvocationMetadata]:
        del user_profile, profile_focus, fallback_context, prompt_context
        return (
            MarketIntelligenceAgentOutput(
                summary_zh="AI市场解读：震荡市下优先稳健资产并控制回撤。",
                summary_en="AI market brief: favor resilient assets and control drawdown.",
            ),
            AgentInvocationMetadata(
                provider_name="anthropic",
                model_name=self._MODEL_BY_REQUEST["market_intelligence"],
            ),
        )

    def rank_candidates(
        self,
        request_name: str,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductRankingAgentOutput, AgentInvocationMetadata]:
        del user_profile, profile_focus, prompt_context
        return (
            ProductRankingAgentOutput(
                ranked_ids=list(reversed([candidate.id for candidate in candidates]))
            ),
            AgentInvocationMetadata(
                provider_name="anthropic",
                model_name=self._MODEL_BY_REQUEST[request_name],
            ),
        )

    def explain_plan(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
        selected_plan_context: SelectedPlanContext | None = None,
    ) -> tuple[ExplanationAgentOutput, AgentInvocationMetadata]:
        del (
            user_profile,
            profile_focus,
            market_context,
            prompt_context,
            selected_plan_context,
        )
        return (
            ExplanationAgentOutput(
                why_this_plan_zh=[
                    "AI理由：优先配置稳健底仓以降低回撤风险。",
                    "AI理由：保留适度增强仓位以平衡收益弹性。",
                ],
                why_this_plan_en=[
                    "AI rationale: prioritize a resilient core to reduce drawdown risk.",
                    "AI rationale: keep a measured satellite sleeve for upside balance.",
                ],
            ),
            AgentInvocationMetadata(
                provider_name="anthropic",
                model_name=self._MODEL_BY_REQUEST["explanation"],
            ),
        )


class _FailingAgentRuntime(_FakeAgentRuntime):
    def analyze_user_profile(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[UserProfileAgentOutput, AgentInvocationMetadata]:
        del user_profile, prompt_context
        raise RuntimeError("agent unavailable")


class _InvalidRankingAgentRuntime(_FakeAgentRuntime):
    def rank_candidates(
        self,
        request_name: str,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductRankingAgentOutput, AgentInvocationMetadata]:
        del request_name, user_profile, profile_focus, candidates, prompt_context
        ProductRankingAgentOutput.model_validate({"ranked_ids": []})
        raise AssertionError("expected ProductRankingAgentOutput validation to fail")


class _FailingExplanationAgentRuntime(_FakeAgentRuntime):
    def explain_plan(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
        selected_plan_context: SelectedPlanContext | None = None,
    ) -> tuple[ExplanationAgentOutput, AgentInvocationMetadata]:
        del (
            user_profile,
            profile_focus,
            market_context,
            prompt_context,
            selected_plan_context,
        )
        raise RuntimeError("explanation unavailable")


class _RecordingAgentRuntime(_FakeAgentRuntime):
    def __init__(self) -> None:
        self.user_profile_prompt_context: AgentPromptContext | None = None
        self.market_prompt_context: AgentPromptContext | None = None
        self.ranking_prompt_contexts: dict[str, AgentPromptContext | None] = {}
        self.explanation_prompt_context: AgentPromptContext | None = None
        self.selected_plan_context: SelectedPlanContext | None = None

    def analyze_user_profile(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[UserProfileAgentOutput, AgentInvocationMetadata]:
        self.user_profile_prompt_context = prompt_context
        output, metadata = super().analyze_user_profile(
            user_profile,
            prompt_context=prompt_context,
        )
        return (
            output,
            AgentInvocationMetadata(
                provider_name=metadata.provider_name,
                model_name=metadata.model_name,
                tool_calls=(
                    AgentToolCallRecord(
                        tool_name="get_user_profile_context",
                        arguments={},
                        result={"risk_profile": user_profile.risk_profile},
                    ),
                ),
            ),
        )

    def analyze_market_intelligence(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        fallback_context: MarketContext,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[MarketIntelligenceAgentOutput, AgentInvocationMetadata]:
        self.market_prompt_context = prompt_context
        output, metadata = super().analyze_market_intelligence(
            user_profile,
            profile_focus,
            fallback_context,
            prompt_context=prompt_context,
        )
        return (
            output,
            AgentInvocationMetadata(
                provider_name=metadata.provider_name,
                model_name=metadata.model_name,
                tool_calls=(
                    AgentToolCallRecord(
                        tool_name="get_market_snapshot",
                        arguments={},
                        result={"summary_zh": fallback_context.summary_zh},
                    ),
                ),
            ),
        )

    def rank_candidates(
        self,
        request_name: str,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductRankingAgentOutput, AgentInvocationMetadata]:
        self.ranking_prompt_contexts[request_name] = prompt_context
        output, metadata = super().rank_candidates(
            request_name,
            user_profile,
            profile_focus,
            candidates,
            prompt_context=prompt_context,
        )
        return (
            output,
            AgentInvocationMetadata(
                provider_name=metadata.provider_name,
                model_name=metadata.model_name,
                tool_calls=(
                    AgentToolCallRecord(
                        tool_name="get_ranking_guardrails",
                        arguments={},
                        result={
                            "candidate_ids": [candidate.id for candidate in candidates]
                        },
                    ),
                ),
            ),
        )

    def explain_plan(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
        selected_plan_context: SelectedPlanContext | None = None,
    ) -> tuple[ExplanationAgentOutput, AgentInvocationMetadata]:
        self.explanation_prompt_context = prompt_context
        self.selected_plan_context = selected_plan_context
        output, metadata = super().explain_plan(
            user_profile,
            profile_focus,
            market_context,
            prompt_context=prompt_context,
            selected_plan_context=selected_plan_context,
        )
        return (
            output,
            AgentInvocationMetadata(
                provider_name=metadata.provider_name,
                model_name=metadata.model_name,
                tool_calls=(
                    AgentToolCallRecord(
                        tool_name="get_selected_plan",
                        arguments={},
                        result={
                            "selected_plan": (
                                {}
                                if selected_plan_context is None
                                else selected_plan_context.as_dict()
                            )
                        },
                    ),
                ),
            ),
        )


def _build_runtime_with_agent_runtime(
    agent_runtime: object,
) -> RecommendationGraphRuntime:
    repository = StaticCandidateRepository()
    user_profile = map_user_profile("balanced")
    candidates = [
        *repository.list_funds(user_profile),
        *repository.list_wealth_management(user_profile),
        *repository.list_stocks(user_profile),
    ]
    return RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(
                vector_store=_AllCandidatesVectorStore(candidates)
            ),
            compliance_review=ComplianceReviewService(),
            product_candidates=candidates,
            agent_runtime=agent_runtime,
        )
    )


def test_graph_runtime_applies_ai_agent_outputs_when_runtime_is_available() -> None:
    service = RecommendationService(
        graph_runtime=_build_runtime_with_agent_runtime(_FakeAgentRuntime())
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert "AI画像强调流动性和回撤控制" in response.profileSummary.zh
    assert response.marketSummary.zh.startswith("AI市场解读：")
    assert response.whyThisPlan.zh == [
        "AI理由：优先配置稳健底仓以降低回撤风险。",
        "AI理由：保留适度增强仓位以平衡收益弹性。",
    ]
    assert response.sections.funds.items[0].id == "fund-002"
    assert response.sections.wealthManagement.items[0].id == "wm-002"

    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["user_profile_analyst"].providerName == "anthropic"
    assert trace_by_request["market_intelligence"].providerName == "anthropic"
    assert trace_by_request["product_match_expert"].providerName == "anthropic"
    assert trace_by_request["manager_coordinator"].providerName == "anthropic"


def test_graph_runtime_falls_back_to_deterministic_pipeline_when_agent_stage_fails() -> (
    None
):
    service = RecommendationService(
        graph_runtime=_build_runtime_with_agent_runtime(_FailingAgentRuntime())
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.profileSummary.zh.startswith("用户风险等级")
    assert any(
        warning.stage == "user_profile_analyst"
        and warning.code == "agent_user_profile_failed"
        and "agent unavailable" in warning.message
        for warning in response.warnings
    )
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["user_profile_analyst"].status == "error"


def test_graph_runtime_masks_ranking_validation_errors_with_friendly_warning() -> None:
    service = RecommendationService(
        graph_runtime=_build_runtime_with_agent_runtime(_InvalidRankingAgentRuntime())
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert any(
        warning.stage == "product_match_expert"
        and warning.code == "agent_fund_selection_failed"
        and warning.message == "基金智能排序暂时不可用，已自动回退到默认候选顺序。"
        for warning in response.warnings
    )
    assert all(
        "validation error for ProductRankingAgentOutput" not in warning.message
        for warning in response.warnings
    )
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["product_match_expert"].status == "error"


class _FailingMarketDataService:
    def get_market_overview(self):
        raise RuntimeError("market data unavailable")

    def get_indices(self):
        raise RuntimeError("market data unavailable")


def test_graph_runtime_marks_market_intelligence_trace_as_error_on_snapshot_fallback() -> (
    None
):
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_default_services(
            market_data_service=_FailingMarketDataService()
        )
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert any(
        warning.stage == "market_intelligence"
        and warning.code == "market_snapshot_fallback"
        for warning in response.warnings
    )
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["market_intelligence"].status == "error"


def test_graph_runtime_marks_manager_coordinator_trace_as_error_on_explanation_failure() -> (
    None
):
    service = RecommendationService(
        graph_runtime=_build_runtime_with_agent_runtime(_FailingExplanationAgentRuntime())
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert any(
        warning.stage == "manager_coordinator"
        and warning.code == "agent_explanation_failed"
        and "explanation unavailable" in warning.message
        for warning in response.warnings
    )
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["manager_coordinator"].status == "error"


def test_graph_runtime_passes_rich_prompt_context_and_selected_plan_context() -> None:
    runtime_double = _RecordingAgentRuntime()
    service = RecommendationService(
        graph_runtime=_build_runtime_with_agent_runtime(runtime_double)
    )

    response = service.generate_recommendation(
        _build_generation_request(
            "balanced",
            user_intent_text="我想要稳健投资，同时保留一部分流动性备用金。",
            questionnaire_answers=[
                {
                    "questionId": "q1",
                    "answerId": "a2",
                    "dimension": "riskTolerance",
                    "score": 14,
                }
            ],
            historical_holdings=[
                {
                    "symbol": "000001",
                    "category": "fund",
                    "quantity": 100.0,
                    "marketValue": 12345.0,
                }
            ],
            historical_transactions=[
                {
                    "symbol": "511990",
                    "action": "buy",
                    "category": "wealth_management",
                    "amount": 5000.0,
                    "occurredAt": "2026-04-01T10:00:00Z",
                }
            ],
            conversation_messages=[
                {
                    "role": "user",
                    "content": "最近市场波动有点大，我不想承担太高回撤。",
                    "occurredAt": "2026-04-02T09:00:00Z",
                }
            ],
            client_context={"channel": "web", "locale": "zh-CN"},
        )
    )

    assert runtime_double.user_profile_prompt_context is not None
    user_profile_prompt = runtime_double.user_profile_prompt_context.render_user_prompt()
    assert "我想要稳健投资，同时保留一部分流动性备用金" in user_profile_prompt
    assert "最近市场波动有点大" in user_profile_prompt
    assert "000001" in user_profile_prompt
    assert "questionnaire" in user_profile_prompt.lower()

    assert runtime_double.market_prompt_context is not None
    market_prompt = runtime_double.market_prompt_context.render_user_prompt()
    assert "AI画像强调流动性和回撤控制" in market_prompt
    assert "balanced" in market_prompt

    fund_prompt_context = runtime_double.ranking_prompt_contexts["fund_selection"]
    assert fund_prompt_context is not None
    fund_prompt = fund_prompt_context.render_user_prompt()
    assert "runtime-memory" in fund_prompt
    assert "fund-001" in fund_prompt

    assert runtime_double.explanation_prompt_context is not None
    explanation_prompt = runtime_double.explanation_prompt_context.render_user_prompt()
    assert "AI市场解读" in explanation_prompt
    assert "route=approved" in explanation_prompt
    assert runtime_double.selected_plan_context is not None
    assert runtime_double.selected_plan_context.fund_ids == tuple(
        item.id for item in response.sections.funds.items
    )
    assert runtime_double.selected_plan_context.wealth_management_ids == tuple(
        item.id for item in response.sections.wealthManagement.items
    )
    assert runtime_double.selected_plan_context.stock_ids == tuple(
        item.id for item in response.sections.stocks.items
    )


def test_graph_runtime_surfaces_tool_calls_in_agent_trace_events() -> None:
    service = RecommendationService(
        graph_runtime=_build_runtime_with_agent_runtime(_RecordingAgentRuntime())
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    trace_by_request = {event.requestName: event for event in response.agentTrace}

    assert trace_by_request["user_profile_analyst"].toolCalls[0].toolName == (
        "get_user_profile_context"
    )
    assert (
        trace_by_request["market_intelligence"].toolCalls[0].result["summary_zh"]
        .startswith("市场概览：")
    )
    assert trace_by_request["product_match_expert"].toolCalls[0].toolName == (
        "get_ranking_guardrails"
    )
    assert (
        trace_by_request["manager_coordinator"].toolCalls[0].result["selected_plan"][
            "fund_ids"
        ]
        == [item.id for item in response.sections.funds.items]
    )
