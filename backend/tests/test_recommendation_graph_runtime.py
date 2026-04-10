from __future__ import annotations

import json

from financehub_market_api.models import (
    IndexCard,
    IndicesResponse,
    MarketOverviewResponse,
    MetricCard,
    RecommendationGenerationRequest,
    TrendPoint,
)
from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    ManagerCoordinatorAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.live_runtime import (
    AgentInvocationMetadata,
)
from financehub_market_api.recommendation.agents.runtime_context import (
    AgentPromptContext,
    AgentToolCallRecord,
)
from financehub_market_api.recommendation.compliance import ComplianceFactsService
from financehub_market_api.recommendation.graph.runtime import (
    GraphServices,
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.repositories import StaticCandidateRepository
from financehub_market_api.recommendation.repositories.real_data_repository import (
    RealDataCandidateRepository,
)
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile
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


def test_graph_runtime_marks_high_risk_candidate_result_as_limited_for_conservative_users() -> None:
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_high_risk_candidate()
    )

    response = service.generate_recommendation(_build_generation_request("conservative"))

    assert response.recommendationStatus == "limited"
    assert response.reviewStatus == "partial_pass"
    assert response.complianceReview is not None
    assert response.complianceReview.verdict == "revise_conservative"
    assert response.sections.stocks.items == []


def test_graph_runtime_builds_defensive_product_strategy_for_capital_preservation_intent() -> None:
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


class _NegativeMarketDataSource:
    def get_market_overview(self) -> MarketOverviewResponse:
        return MarketOverviewResponse(
            asOfDate="2026-04-09",
            stale=False,
            metrics=[
                MetricCard(
                    label="上证指数",
                    value="3966.17",
                    delta="-0.7%",
                    changeValue=-27.8,
                    changePercent=-0.7,
                    tone="negative",
                ),
                MetricCard(
                    label="深证成指",
                    value="13996.27",
                    delta="-0.3%",
                    changeValue=-42.1,
                    changePercent=-0.3,
                    tone="negative",
                ),
            ],
            chartLabel="近20日走势",
            trendSeries=[TrendPoint(date="2026-04-09", value=3966.17)],
            topGainers=[],
            topLosers=[],
        )

    def get_indices(self) -> IndicesResponse:
        return IndicesResponse(
            asOfDate="2026-04-09",
            stale=False,
            cards=[
                IndexCard(
                    name="上证指数",
                    code="000001",
                    market="CN",
                    description="negative day",
                    value="3966.17",
                    valueNumber=3966.17,
                    changeValue=-27.8,
                    changePercent=-0.7,
                    tone="negative",
                    trendSeries=[TrendPoint(date="2026-04-09", value=3966.17)],
                ),
                IndexCard(
                    name="深证成指",
                    code="399001",
                    market="CN",
                    description="negative day",
                    value="13996.27",
                    valueNumber=13996.27,
                    changeValue=-42.1,
                    changePercent=-0.3,
                    tone="negative",
                    trendSeries=[TrendPoint(date="2026-04-09", value=13996.27)],
                ),
            ],
        )


class _SingleMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        del query
        return ["runtime-memory"][:limit]


class _SingleVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [{"id": "fund-001", "score": 0.99}][:limit]


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


def _risk_tier_for_profile(risk_profile: str) -> str:
    return {
        "conservative": "R2",
        "stable": "R2",
        "balanced": "R3",
        "growth": "R4",
        "aggressive": "R5",
    }[risk_profile]


class _CurrentAgentRuntime:
    _MODELS = {
        "user_profile_analyst": "claude-user-profile",
        "market_intelligence": "claude-market",
        "product_match_expert": "claude-product-match",
        "compliance_risk_officer": "claude-compliance",
        "manager_coordinator": "claude-manager",
    }

    def _metadata(self, request_name: str, *, tool_calls=()) -> AgentInvocationMetadata:
        return AgentInvocationMetadata(
            provider_name="anthropic",
            model_name=self._MODELS[request_name],
            tool_calls=tool_calls,
        )

    def analyze_user_profile(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[UserProfileAgentOutput, AgentInvocationMetadata]:
        del prompt_context
        return (
            UserProfileAgentOutput(
                risk_tier=_risk_tier_for_profile(user_profile.risk_profile),
                liquidity_preference="medium",
                investment_horizon="medium",
                return_objective="balanced_growth",
                drawdown_sensitivity="medium",
                profile_focus_zh="AI画像强调流动性和回撤控制。",
                profile_focus_en="AI profile focus prioritizes liquidity and drawdown control.",
                derived_signals=["questionnaire:test"],
            ),
            self._metadata("user_profile_analyst"),
        )

    def analyze_market_intelligence(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_facts: dict[str, object],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[MarketIntelligenceAgentOutput, AgentInvocationMetadata]:
        del user_profile, user_profile_insights, prompt_context
        summary_zh = str(market_facts.get("summary_zh", ""))
        summary_en = str(market_facts.get("summary_en", ""))
        defensive = "承压" in summary_zh or "negative" in json.dumps(market_facts, ensure_ascii=False)
        return (
            MarketIntelligenceAgentOutput(
                sentiment="negative" if defensive else "positive",
                stance="defensive" if defensive else "balanced",
                preferred_categories=["wealth_management", "fund"] if defensive else ["fund", "stock"],
                avoided_categories=["stock"] if defensive else [],
                summary_zh=f"AI市场解读：{summary_zh}",
                summary_en=f"AI market brief: {summary_en}",
                evidence_refs=["market_overview", "indices"],
            ),
            self._metadata("market_intelligence"),
        )

    def match_products(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductMatchAgentOutput, AgentInvocationMetadata]:
        del user_profile, prompt_context
        defensive = (
            market_intelligence.stance == "defensive"
            or user_profile_insights.risk_tier in {"R1", "R2"}
        )
        selected_product_ids: list[str] = []
        if any(candidate.category == "wealth_management" for candidate in candidates):
            selected_product_ids.append(
                next(candidate.id for candidate in candidates if candidate.category == "wealth_management")
            )
        if any(candidate.category == "fund" for candidate in candidates):
            selected_product_ids.append(
                next(candidate.id for candidate in candidates if candidate.category == "fund")
            )
        if (
            not defensive
            and any(candidate.category == "stock" for candidate in candidates)
        ):
            selected_product_ids.append(
                next(candidate.id for candidate in candidates if candidate.category == "stock")
            )
        recommended_categories = list(
            dict.fromkeys(
                candidate.category
                for candidate_id in selected_product_ids
                for candidate in candidates
                if candidate.id == candidate_id
            )
        )
        return (
            ProductMatchAgentOutput(
                recommended_categories=recommended_categories,
                selected_product_ids=selected_product_ids,
                ranking_rationale_zh="AI认为当前候选更匹配当前用户画像与市场环境。",
                ranking_rationale_en="AI selected the candidates that best match the user profile and market context.",
                filtered_out_reasons=(["stock filtered by defensive stance"] if defensive else []),
            ),
            self._metadata("product_match_expert"),
        )

    def review_compliance(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        selected_candidates: list[CandidateProduct],
        compliance_facts: dict[str, object],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ComplianceReviewAgentOutput, AgentInvocationMetadata]:
        del user_profile, compliance_facts, prompt_context
        allowed_order = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}
        max_allowed = allowed_order[user_profile_insights.risk_tier]
        approved = [
            candidate.id
            for candidate in selected_candidates
            if allowed_order.get(candidate.risk_level, 99) <= max_allowed
        ]
        verdict = (
            "approve"
            if len(approved) == len(selected_candidates)
            else "revise_conservative"
            if approved
            else "block"
        )
        rejected = [
            candidate.id for candidate in selected_candidates if candidate.id not in approved
        ]
        return (
            ComplianceReviewAgentOutput(
                verdict=verdict,
                approved_ids=approved,
                rejected_ids=rejected,
                reason_summary_zh="候选通过审核。" if verdict == "approve" else "已移除更激进候选。",
                reason_summary_en="Candidates passed review." if verdict == "approve" else "More aggressive candidates were removed.",
                required_disclosures_zh=["理财非存款，投资需谨慎。"],
                required_disclosures_en=["Investing involves risk. Proceed prudently."],
                suitability_notes_zh=["风险等级和流动性匹配。"],
                suitability_notes_en=["Risk and liquidity are aligned."],
                applied_rule_ids=["test-rule"],
                blocking_reason_codes=[],
            ),
            self._metadata("compliance_risk_officer"),
        )

    def coordinate_manager(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        product_match: ProductMatchAgentOutput,
        compliance_review: ComplianceReviewAgentOutput,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ManagerCoordinatorAgentOutput, AgentInvocationMetadata]:
        del (
            user_profile,
            user_profile_insights,
            market_intelligence,
            product_match,
            prompt_context,
        )
        recommendation_status = (
            "blocked"
            if compliance_review.verdict == "block"
            else "limited"
            if compliance_review.verdict == "revise_conservative"
            else "ready"
        )
        return (
            ManagerCoordinatorAgentOutput(
                recommendation_status=recommendation_status,
                summary_zh="建议优先配置稳健底仓。",
                summary_en="Favor a resilient core allocation.",
                why_this_plan_zh=["AI理由：优先配置稳健底仓以降低回撤风险。"],
                why_this_plan_en=["AI rationale: prioritize a resilient core to reduce drawdown risk."],
            ),
            self._metadata("manager_coordinator"),
        )


class _FailingUserProfileRuntime(_CurrentAgentRuntime):
    def analyze_user_profile(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[UserProfileAgentOutput, AgentInvocationMetadata]:
        del user_profile, prompt_context
        raise RuntimeError("agent unavailable")


class _InvalidProductMatchRuntime(_CurrentAgentRuntime):
    def match_products(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductMatchAgentOutput, AgentInvocationMetadata]:
        del user_profile, user_profile_insights, market_intelligence, candidates, prompt_context
        raise RuntimeError("product match unavailable")


class _FailingManagerRuntime(_CurrentAgentRuntime):
    def coordinate_manager(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        product_match: ProductMatchAgentOutput,
        compliance_review: ComplianceReviewAgentOutput,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ManagerCoordinatorAgentOutput, AgentInvocationMetadata]:
        del (
            user_profile,
            user_profile_insights,
            market_intelligence,
            product_match,
            compliance_review,
            prompt_context,
        )
        raise RuntimeError("manager unavailable")


class _RecordingAgentRuntime(_CurrentAgentRuntime):
    def __init__(self) -> None:
        self.user_profile_prompt_context: AgentPromptContext | None = None
        self.market_prompt_context: AgentPromptContext | None = None
        self.product_prompt_context: AgentPromptContext | None = None
        self.compliance_prompt_context: AgentPromptContext | None = None
        self.manager_prompt_context: AgentPromptContext | None = None

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
        user_profile_insights: UserProfileAgentOutput,
        market_facts: dict[str, object],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[MarketIntelligenceAgentOutput, AgentInvocationMetadata]:
        self.market_prompt_context = prompt_context
        output, metadata = super().analyze_market_intelligence(
            user_profile,
            user_profile_insights,
            market_facts,
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
                        result={"summary_zh": str(market_facts["summary_zh"])},
                    ),
                ),
            ),
        )

    def match_products(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductMatchAgentOutput, AgentInvocationMetadata]:
        self.product_prompt_context = prompt_context
        output, metadata = super().match_products(
            user_profile,
            user_profile_insights=user_profile_insights,
            market_intelligence=market_intelligence,
            candidates=candidates,
            prompt_context=prompt_context,
        )
        return (
            output,
            AgentInvocationMetadata(
                provider_name=metadata.provider_name,
                model_name=metadata.model_name,
                tool_calls=(
                    AgentToolCallRecord(
                        tool_name="list_candidate_products",
                        arguments={},
                        result={"candidate_ids": [candidate.id for candidate in candidates]},
                    ),
                ),
            ),
        )

    def review_compliance(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        selected_candidates: list[CandidateProduct],
        compliance_facts: dict[str, object],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ComplianceReviewAgentOutput, AgentInvocationMetadata]:
        self.compliance_prompt_context = prompt_context
        output, metadata = super().review_compliance(
            user_profile,
            user_profile_insights=user_profile_insights,
            selected_candidates=selected_candidates,
            compliance_facts=compliance_facts,
            prompt_context=prompt_context,
        )
        return (
            output,
            AgentInvocationMetadata(
                provider_name=metadata.provider_name,
                model_name=metadata.model_name,
                tool_calls=(
                    AgentToolCallRecord(
                        tool_name="get_rule_snapshot",
                        arguments={},
                        result={"available": True},
                    ),
                ),
            ),
        )

    def coordinate_manager(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        product_match: ProductMatchAgentOutput,
        compliance_review: ComplianceReviewAgentOutput,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ManagerCoordinatorAgentOutput, AgentInvocationMetadata]:
        self.manager_prompt_context = prompt_context
        output, metadata = super().coordinate_manager(
            user_profile,
            user_profile_insights=user_profile_insights,
            market_intelligence=market_intelligence,
            product_match=product_match,
            compliance_review=compliance_review,
            prompt_context=prompt_context,
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
                        result={"selected_ids": list(product_match.selected_product_ids)},
                    ),
                ),
            ),
        )


class _FailingMarketDataService:
    def get_market_overview(self):
        raise RuntimeError("market data unavailable")

    def get_indices(self):
        raise RuntimeError("market data unavailable")


def _build_runtime(
    *,
    agent_runtime: object,
    product_candidates: list[CandidateProduct] | None = None,
    market_data_service=None,
    candidate_repository=None,
) -> RecommendationGraphRuntime:
    candidates = (
        product_candidates
        if product_candidates is not None
        else [
            *StaticCandidateRepository().list_funds(map_user_profile("balanced")),
            *StaticCandidateRepository().list_wealth_management(map_user_profile("balanced")),
            *StaticCandidateRepository().list_stocks(map_user_profile("balanced")),
        ]
    )
    return RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(
                market_data_service=market_data_service
            )
            if market_data_service is not None
            else MarketIntelligenceService(),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(vector_store=_SingleVectorStore()),
            compliance_facts_service=ComplianceFactsService(),
            product_candidates=candidates,
            agent_runtime=agent_runtime,
            candidate_repository=candidate_repository,
        )
    )


def test_graph_runtime_omits_stock_candidates_for_balanced_users_in_defensive_market() -> None:
    response = RecommendationService(
        graph_runtime=_build_runtime(
            agent_runtime=_CurrentAgentRuntime(),
            market_data_service=_NegativeMarketDataSource(),
        )
    ).generate_recommendation(_build_generation_request("balanced"))

    assert response.recommendationStatus == "ready"
    assert response.sections.stocks.items == []
    assert response.marketIntelligence is not None
    assert response.marketIntelligence.stance == "defensive"


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
    response = RecommendationService(
        graph_runtime=_build_runtime(
            agent_runtime=_CurrentAgentRuntime(),
            product_candidates=[runtime_candidate],
        )
    ).generate_recommendation(_build_generation_request("balanced"))

    assert response.sections.funds.items[0].id == "fund-001"
    assert response.sections.funds.items[0].nameZh == "运行时自定义基金A"


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

    response = RecommendationService(
        graph_runtime=_build_runtime(
            agent_runtime=_CurrentAgentRuntime(),
            candidate_repository=RealDataCandidateRepository(),
            product_candidates=[],
        )
    ).generate_recommendation(_build_generation_request("balanced"))

    assert response.executionMode == "agent_assisted"
    assert response.sections.funds.items[0].nameZh == "稳健债券A"
    assert response.sections.wealthManagement.items[0].nameZh == "华宝添益"


def test_graph_runtime_refreshes_repository_candidates_between_requests() -> None:
    service = RecommendationService(
        graph_runtime=_build_runtime(
            agent_runtime=_CurrentAgentRuntime(),
            candidate_repository=_RefreshingRepository(),
            product_candidates=[],
        )
    )

    first_response = service.generate_recommendation(_build_generation_request("balanced"))
    second_response = service.generate_recommendation(_build_generation_request("balanced"))

    assert first_response.sections.funds.items[0].nameZh == "首次快照基金"
    assert second_response.sections.funds.items[0].nameZh == "恢复后基金"


def test_graph_runtime_applies_ai_agent_outputs_when_runtime_is_available() -> None:
    response = RecommendationService(
        graph_runtime=_build_runtime(agent_runtime=_CurrentAgentRuntime())
    ).generate_recommendation(_build_generation_request("balanced"))

    assert "AI画像强调流动性和回撤控制" in response.profileSummary.zh
    assert response.marketSummary.zh.startswith("AI市场解读：")
    assert response.whyThisPlan.zh == [
        "AI理由：优先配置稳健底仓以降低回撤风险。",
    ]
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["user_profile_analyst"].providerName == "anthropic"
    assert trace_by_request["market_intelligence"].providerName == "anthropic"
    assert trace_by_request["product_match_expert"].providerName == "anthropic"
    assert trace_by_request["compliance_risk_officer"].providerName == "anthropic"
    assert trace_by_request["manager_coordinator"].providerName == "anthropic"


def test_graph_runtime_blocks_when_agent_stage_fails() -> None:
    response = RecommendationService(
        graph_runtime=_build_runtime(agent_runtime=_FailingUserProfileRuntime())
    ).generate_recommendation(_build_generation_request("balanced"))

    assert response.recommendationStatus == "blocked"
    assert any(
        warning.stage == "user_profile_analyst"
        and warning.code == "agent_user_profile_failed"
        and "agent unavailable" in warning.message
        for warning in response.warnings
    )
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["user_profile_analyst"].status == "error"


def test_graph_runtime_blocks_when_product_match_fails() -> None:
    response = RecommendationService(
        graph_runtime=_build_runtime(agent_runtime=_InvalidProductMatchRuntime())
    ).generate_recommendation(_build_generation_request("balanced"))

    assert response.recommendationStatus == "blocked"
    assert any(
        warning.stage == "product_match_expert"
        and warning.code == "agent_product_match_failed"
        and "product match unavailable" in warning.message
        for warning in response.warnings
    )


def test_graph_runtime_marks_market_intelligence_trace_as_error_when_market_facts_fail() -> None:
    response = RecommendationService(
        graph_runtime=_build_runtime(
            agent_runtime=_CurrentAgentRuntime(),
            market_data_service=_FailingMarketDataService(),
        )
    ).generate_recommendation(_build_generation_request("balanced"))

    assert response.recommendationStatus == "blocked"
    assert any(
        warning.stage == "market_intelligence"
        and warning.code == "market_facts_unavailable"
        and "market data unavailable" in warning.message
        for warning in response.warnings
    )
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["market_intelligence"].status == "error"


def test_graph_runtime_marks_manager_coordinator_trace_as_error_on_manager_failure() -> None:
    response = RecommendationService(
        graph_runtime=_build_runtime(agent_runtime=_FailingManagerRuntime())
    ).generate_recommendation(_build_generation_request("balanced"))

    assert response.recommendationStatus == "blocked"
    assert any(
        warning.stage == "manager_coordinator"
        and warning.code == "agent_manager_coordinator_failed"
        and "manager unavailable" in warning.message
        for warning in response.warnings
    )
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["manager_coordinator"].status == "error"


def test_graph_runtime_passes_rich_prompt_contexts_and_tool_calls() -> None:
    runtime_double = _RecordingAgentRuntime()
    response = RecommendationService(
        graph_runtime=_build_runtime(agent_runtime=runtime_double)
    ).generate_recommendation(
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

    assert runtime_double.market_prompt_context is not None
    market_prompt = runtime_double.market_prompt_context.render_user_prompt()
    assert "AI画像强调流动性和回撤控制" in market_prompt

    assert runtime_double.product_prompt_context is not None
    product_prompt = runtime_double.product_prompt_context.render_user_prompt()
    assert "runtime-memory" in product_prompt
    assert "fund-001" in product_prompt

    assert runtime_double.compliance_prompt_context is not None
    compliance_prompt = runtime_double.compliance_prompt_context.render_user_prompt()
    assert "test-rule" not in compliance_prompt
    assert "Compliance facts" in compliance_prompt

    assert runtime_double.manager_prompt_context is not None
    manager_prompt = runtime_double.manager_prompt_context.render_user_prompt()
    assert "Product match" in manager_prompt
    assert "Compliance review" in manager_prompt

    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["user_profile_analyst"].toolCalls[0].toolName == "get_user_profile_context"
    assert trace_by_request["market_intelligence"].toolCalls[0].toolName == "get_market_snapshot"
    assert trace_by_request["product_match_expert"].toolCalls[0].toolName == "list_candidate_products"
    assert trace_by_request["compliance_risk_officer"].toolCalls[0].toolName == "get_rule_snapshot"
    assert trace_by_request["manager_coordinator"].toolCalls[0].result["selected_ids"]
