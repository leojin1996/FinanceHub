from __future__ import annotations

import json
from dataclasses import replace

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
from financehub_market_api.recommendation.compliance_knowledge.schemas import (
    ComplianceEvidenceBundle,
    RetrievedComplianceEvidence,
)
from financehub_market_api.recommendation.compliance import (
    ComplianceFactsService,
    ComplianceReviewService,
)
from financehub_market_api.recommendation.graph.runtime import (
    GraphServices,
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.product_knowledge.schemas import (
    ProductEvidenceBundle,
    RetrievedProductEvidence,
)
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


def test_graph_runtime_prefilters_high_risk_candidate_for_conservative_users() -> None:
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_high_risk_candidate()
    )

    response = service.generate_recommendation(_build_generation_request("conservative"))

    assert response.recommendationStatus == "limited"
    assert response.reviewStatus == "partial_pass"
    assert response.complianceReview is not None
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


def test_graph_runtime_default_services_wire_market_news_service(monkeypatch) -> None:
    fake_news_service = object()
    monkeypatch.setattr(
        "financehub_market_api.recommendation.graph.runtime.build_market_news_service_from_env",
        lambda: fake_news_service,
        raising=False,
    )

    runtime = RecommendationGraphRuntime.with_default_services(
        repository=StaticCandidateRepository(),
        market_data_service=_NegativeMarketDataSource(),
    )

    assert (
        runtime._services.market_intelligence._market_news_service is fake_news_service
    )


class _SingleMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        del query
        return ["runtime-memory"][:limit]


class _SingleVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [{"id": "fund-001", "score": 0.99}][:limit]


class _StockFirstVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [
            {"id": "stock-001", "score": 0.99},
            {"id": "wm-001", "score": 0.95},
            {"id": "fund-001", "score": 0.9},
        ][:limit]


class _IlliquidFirstVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [
            {"id": "fund-locked-001", "score": 0.99},
            {"id": "fund-liquid-001", "score": 0.95},
        ][:limit]


class _HighRiskFirstVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [
            {"id": "fund-aggressive-001", "score": 0.99},
            {"id": "fund-balanced-001", "score": 0.95},
        ][:limit]


class _MultiCandidateVectorStore:
    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [
            {"id": "wm-001", "score": 0.99},
            {"id": "fund-001", "score": 0.95},
            {"id": "stock-001", "score": 0.9},
        ][:limit]


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
        "user_profile_analyst": "gpt-5.4-user-profile",
        "market_intelligence": "gpt-5.4-market",
        "product_match_expert": "gpt-5.4-product-match",
        "compliance_risk_officer": "gpt-5.4-compliance",
        "manager_coordinator": "gpt-5.4-manager",
    }

    def _metadata(self, request_name: str, *, tool_calls=()) -> AgentInvocationMetadata:
        return AgentInvocationMetadata(
            provider_name="openai",
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


class _CandidatePassthroughRuntime(_CurrentAgentRuntime):
    def __init__(self) -> None:
        self.match_candidate_ids: list[str] = []

    def match_products(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductMatchAgentOutput, AgentInvocationMetadata]:
        del (
            user_profile,
            user_profile_insights,
            market_intelligence,
            prompt_context,
        )
        self.match_candidate_ids = [candidate.id for candidate in candidates]
        selected_product_ids = [candidate.id for candidate in candidates]
        recommended_categories = list(
            dict.fromkeys(candidate.category for candidate in candidates)
        )
        return (
            ProductMatchAgentOutput(
                recommended_categories=recommended_categories,
                selected_product_ids=selected_product_ids,
                ranking_rationale_zh="测试运行时直接返回检索层传入的候选。",
                ranking_rationale_en="The test runtime returns the candidates passed from retrieval.",
                filtered_out_reasons=[],
            ),
            self._metadata("product_match_expert"),
        )


class _HighLiquidityPassthroughRuntime(_CandidatePassthroughRuntime):
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
                liquidity_preference="high",
                investment_horizon="medium",
                return_objective="capital_preservation",
                drawdown_sensitivity="high",
                profile_focus_zh="AI画像强调高流动性和回撤控制。",
                profile_focus_en="AI profile focus prioritizes high liquidity and drawdown control.",
                derived_signals=["intent:高流动性"],
            ),
            self._metadata("user_profile_analyst"),
        )


class _FailingMarketDataService:
    def get_market_overview(self):
        raise RuntimeError("market data unavailable")

    def get_indices(self):
        raise RuntimeError("market data unavailable")


class _SubsetSelectionRuntime(_CurrentAgentRuntime):
    def match_products(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductMatchAgentOutput, AgentInvocationMetadata]:
        del user_profile, user_profile_insights, market_intelligence, prompt_context
        selected = [candidate.id for candidate in candidates][:2]
        recommended_categories = list(
            dict.fromkeys(
                candidate.category
                for candidate in candidates
                if candidate.id in selected
            )
        )
        return (
            ProductMatchAgentOutput(
                recommended_categories=recommended_categories,
                selected_product_ids=selected,
                ranking_rationale_zh="测试仅选择部分候选。",
                ranking_rationale_en="Test runtime selects a subset of candidates.",
                filtered_out_reasons=[],
            ),
            self._metadata("product_match_expert"),
        )


class _ComplianceFilteringRuntime(_CurrentAgentRuntime):
    def analyze_user_profile(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[UserProfileAgentOutput, AgentInvocationMetadata]:
        del user_profile, prompt_context
        return (
            UserProfileAgentOutput(
                risk_tier="R2",
                liquidity_preference="medium",
                investment_horizon="medium",
                return_objective="capital_preservation",
                drawdown_sensitivity="high",
                profile_focus_zh="测试画像：更保守风险等级。",
                profile_focus_en="Test profile: conservative risk tier.",
                derived_signals=["test:compliance_filter"],
            ),
            self._metadata("user_profile_analyst"),
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
        del user_profile, user_profile_insights, market_intelligence, prompt_context
        by_category = {candidate.category: candidate.id for candidate in candidates}
        selected_ids = [
            by_category[category]
            for category in ("wealth_management", "fund", "stock")
            if category in by_category
        ]
        recommended_categories = ["wealth_management", "fund", "stock"]
        return (
            ProductMatchAgentOutput(
                recommended_categories=recommended_categories,
                selected_product_ids=selected_ids,
                ranking_rationale_zh="测试要求纳入股票后由合规过滤。",
                ranking_rationale_en="Test includes stock so compliance must filter it.",
                filtered_out_reasons=[],
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
        del user_profile, user_profile_insights, compliance_facts, prompt_context
        approved_ids = [
            candidate.id
            for candidate in selected_candidates
            if candidate.category != "stock"
        ]
        rejected_ids = [
            candidate.id for candidate in selected_candidates if candidate.id not in approved_ids
        ]
        verdict = "revise_conservative" if approved_ids else "block"
        return (
            ComplianceReviewAgentOutput(
                verdict=verdict,
                approved_ids=approved_ids,
                rejected_ids=rejected_ids,
                reason_summary_zh="测试合规：移除股票候选。",
                reason_summary_en="Test compliance: removed stock candidates.",
                required_disclosures_zh=["测试披露。"],
                required_disclosures_en=["Test disclosure."],
                suitability_notes_zh=["测试适当性说明。"],
                suitability_notes_en=["Test suitability note."],
                applied_rule_ids=["test:remove_stock"],
                blocking_reason_codes=[],
            ),
            self._metadata("compliance_risk_officer"),
        )


class _StubProductKnowledgeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def retrieve_evidence(
        self,
        *,
        query_text: str,
        product_ids: list[str],
        include_internal: bool = True,
        limit_per_product: int = 2,
        total_limit: int = 12,
    ) -> list[ProductEvidenceBundle]:
        self.calls.append(
            {
                "query_text": query_text,
                "product_ids": list(product_ids),
                "include_internal": include_internal,
                "limit_per_product": limit_per_product,
                "total_limit": total_limit,
            }
        )
        return [
            ProductEvidenceBundle(
                product_id=product_id,
                evidences=[
                    RetrievedProductEvidence(
                        evidence_id=f"{product_id}-evidence",
                        product_id=product_id,
                        score=0.95,
                        snippet=f"{product_id} evidence snippet",
                        source_title="Product prospectus",
                        source_uri="https://example.com/prospectus",
                        doc_type="prospectus",
                        source_type="public_official",
                        visibility="public",
                        user_displayable=True,
                    )
                ],
            )
            for product_id in product_ids
        ]


class _FailingProductKnowledgeService:
    def retrieve_evidence(
        self,
        *,
        query_text: str,
        product_ids: list[str],
        include_internal: bool = True,
        limit_per_product: int = 2,
        total_limit: int = 12,
    ) -> list[ProductEvidenceBundle]:
        del (
            query_text,
            product_ids,
            include_internal,
            limit_per_product,
            total_limit,
        )
        raise RuntimeError("product evidence unavailable")


class _StubComplianceKnowledgeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def retrieve_evidence(
        self,
        query,
        *,
        total_limit: int = 12,
    ) -> list[ComplianceEvidenceBundle]:
        self.calls.append(
            {
                "query_text": query.query_text,
                "rule_types": list(query.rule_types),
                "categories": list(query.categories),
                "risk_tiers": list(query.risk_tiers),
                "audience": query.audience,
                "jurisdiction": query.jurisdiction,
                "effective_on": query.effective_on,
                "total_limit": total_limit,
            }
        )
        return [
            ComplianceEvidenceBundle(
                rule_type="suitability",
                evidences=[
                    RetrievedComplianceEvidence(
                        evidence_id="rule-001#1",
                        score=0.94,
                        snippet="销售机构应当将产品风险等级与投资者风险承受能力进行匹配。",
                        source_title="基金销售适当性管理办法",
                        source_uri="https://example.com/rule-001.pdf",
                        doc_type="regulation_pdf",
                        source_type="public_regulation",
                        jurisdiction="CN",
                        rule_id="suitability-risk-tier-match",
                        rule_type="suitability",
                        audience=query.audience or "fund_sales",
                        applies_to_categories=list(query.categories),
                        applies_to_risk_tiers=list(query.risk_tiers),
                        disclosure_type="suitability_warning",
                        effective_date=query.effective_on,
                        section_title="适当性匹配要求",
                        page_number=6,
                    )
                ],
            ),
            ComplianceEvidenceBundle(
                rule_type="risk_disclosure",
                evidences=[
                    RetrievedComplianceEvidence(
                        evidence_id="rule-002#1",
                        score=0.91,
                        snippet="销售前应向投资者充分揭示产品风险特征和流动性安排。",
                        source_title="基金销售风险揭示指引",
                        source_uri="https://example.com/rule-002.pdf",
                        doc_type="guideline_pdf",
                        source_type="public_guideline",
                        jurisdiction="CN",
                        rule_id="risk-disclosure-liquidity",
                        rule_type="risk_disclosure",
                        audience=query.audience or "fund_sales",
                        applies_to_categories=list(query.categories),
                        applies_to_risk_tiers=list(query.risk_tiers),
                        disclosure_type="general_risk_notice",
                        effective_date=query.effective_on,
                        section_title="风险揭示",
                        page_number=4,
                    )
                ],
            ),
        ]


class _FailingComplianceKnowledgeService:
    def retrieve_evidence(
        self,
        query,
        *,
        total_limit: int = 12,
    ) -> list[ComplianceEvidenceBundle]:
        del query, total_limit
        raise RuntimeError("compliance evidence unavailable")


class _FailingComplianceRuntime(_CandidatePassthroughRuntime):
    def review_compliance(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        selected_candidates: list[CandidateProduct],
        compliance_facts: dict[str, object],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ComplianceReviewAgentOutput, AgentInvocationMetadata]:
        del (
            user_profile,
            user_profile_insights,
            selected_candidates,
            compliance_facts,
            prompt_context,
        )
        raise RuntimeError("compliance agent unavailable")


class _PermissiveComplianceRuntime(_CandidatePassthroughRuntime):
    def review_compliance(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        selected_candidates: list[CandidateProduct],
        compliance_facts: dict[str, object],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ComplianceReviewAgentOutput, AgentInvocationMetadata]:
        del user_profile, user_profile_insights, compliance_facts, prompt_context
        approved_ids = [candidate.id for candidate in selected_candidates]
        return (
            ComplianceReviewAgentOutput(
                verdict="approve",
                approved_ids=approved_ids,
                rejected_ids=[],
                reason_summary_zh="测试 agent: 直接放行。",
                reason_summary_en="Test agent: approve everything.",
                required_disclosures_zh=["测试披露。"],
                required_disclosures_en=["Test disclosure."],
                suitability_notes_zh=["测试说明。"],
                suitability_notes_en=["Test note."],
                applied_rule_ids=["test:approve_all"],
                blocking_reason_codes=[],
            ),
            self._metadata("compliance_risk_officer"),
        )


def _build_runtime(
    *,
    agent_runtime: object,
    product_candidates: list[CandidateProduct] | None = None,
    product_retrieval_service: ProductRetrievalService | None = None,
    product_knowledge_service: object | None = None,
    compliance_knowledge_service: object | None = None,
    compliance_review_service: object | None = None,
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
            product_retrieval=product_retrieval_service
            or ProductRetrievalService(vector_store=_SingleVectorStore()),
            product_knowledge=product_knowledge_service,
            compliance_knowledge=compliance_knowledge_service,
            compliance_review_service=compliance_review_service,
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


def test_graph_runtime_filters_market_avoided_categories_before_product_match() -> None:
    runtime_double = _CandidatePassthroughRuntime()
    candidates = [
        CandidateProduct(
            id="fund-001",
            category="fund",
            name_zh="测试基金",
            name_en="Test Fund",
            risk_level="R2",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="测试基金候选。",
            rationale_en="Test fund candidate.",
            liquidity="T+1",
        ),
        CandidateProduct(
            id="wm-001",
            category="wealth_management",
            name_zh="测试理财",
            name_en="Test Wealth",
            risk_level="R2",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="测试理财候选。",
            rationale_en="Test wealth candidate.",
            liquidity="T+0",
        ),
        CandidateProduct(
            id="stock-001",
            category="stock",
            name_zh="测试股票",
            name_en="Test Stock",
            risk_level="R3",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="测试股票候选。",
            rationale_en="Test stock candidate.",
            code="600036",
        ),
    ]
    graph_runtime = RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(
                market_data_service=_NegativeMarketDataSource()
            ),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(
                vector_store=_StockFirstVectorStore()
            ),
            compliance_facts_service=ComplianceFactsService(),
            product_candidates=candidates,
            agent_runtime=runtime_double,
        )
    )

    response = RecommendationService(graph_runtime=graph_runtime).generate_recommendation(
        _build_generation_request("balanced")
    )

    assert response.marketIntelligence is not None
    assert response.marketIntelligence.stance == "defensive"
    assert runtime_double.match_candidate_ids == ["wm-001", "fund-001"]
    assert response.sections.stocks.items == []


def test_graph_runtime_filters_low_liquidity_candidates_before_product_match() -> None:
    runtime_double = _HighLiquidityPassthroughRuntime()
    candidates = [
        CandidateProduct(
            id="fund-liquid-001",
            category="fund",
            name_zh="高流动性基金",
            name_en="Liquid Fund",
            risk_level="R2",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="高流动性基金候选。",
            rationale_en="High-liquidity fund candidate.",
            liquidity="T+1",
        ),
        CandidateProduct(
            id="fund-locked-001",
            category="fund",
            name_zh="封闭期基金",
            name_en="Locked Fund",
            risk_level="R2",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="封闭期基金候选。",
            rationale_en="Locked fund candidate.",
            liquidity="180天",
        ),
    ]
    graph_runtime = RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(
                market_data_service=_NegativeMarketDataSource()
            ),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(
                vector_store=_IlliquidFirstVectorStore()
            ),
            compliance_facts_service=ComplianceFactsService(),
            product_candidates=candidates,
            agent_runtime=runtime_double,
        )
    )

    response = RecommendationService(graph_runtime=graph_runtime).generate_recommendation(
        _build_generation_request("balanced")
    )

    assert response.recommendationStatus == "ready"
    assert runtime_double.match_candidate_ids == ["fund-liquid-001"]
    assert [item.id for item in response.sections.funds.items] == ["fund-liquid-001"]
    assert response.sections.wealthManagement.items == []
    assert response.sections.stocks.items == []


def test_graph_runtime_filters_high_risk_candidates_before_product_match() -> None:
    runtime_double = _CandidatePassthroughRuntime()
    candidates = [
        CandidateProduct(
            id="fund-balanced-001",
            category="fund",
            name_zh="平衡型基金",
            name_en="Balanced Fund",
            risk_level="R3",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="匹配平衡型用户。",
            rationale_en="Suitable for balanced users.",
            liquidity="T+1",
        ),
        CandidateProduct(
            id="fund-aggressive-001",
            category="fund",
            name_zh="激进型基金",
            name_en="Aggressive Fund",
            risk_level="R5",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="风险更高的基金候选。",
            rationale_en="A higher-risk fund candidate.",
            liquidity="T+1",
        ),
    ]
    graph_runtime = RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(
                market_data_service=_NegativeMarketDataSource()
            ),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(
                vector_store=_HighRiskFirstVectorStore()
            ),
            compliance_facts_service=ComplianceFactsService(),
            product_candidates=candidates,
            agent_runtime=runtime_double,
        )
    )

    response = RecommendationService(graph_runtime=graph_runtime).generate_recommendation(
        _build_generation_request("balanced")
    )

    assert response.recommendationStatus == "ready"
    assert runtime_double.match_candidate_ids == ["fund-balanced-001"]
    assert [item.id for item in response.sections.funds.items] == ["fund-balanced-001"]
    assert response.sections.wealthManagement.items == []
    assert response.sections.stocks.items == []


def test_graph_runtime_rebalances_allocation_when_only_stock_recommendations_remain() -> None:
    stock_only_candidate = CandidateProduct(
        id="stock-only-001",
        category="stock",
        code="600001",
        name_zh="高弹性股票",
        name_en="High Beta Equity",
        risk_level="R5",
        tags_zh=["测试"],
        tags_en=["test"],
        rationale_zh="仅保留股票候选。",
        rationale_en="Only stock candidate survives.",
        liquidity="T+1",
    )
    graph_runtime = RecommendationGraphRuntime(
        GraphServices(
            market_intelligence=MarketIntelligenceService(),
            memory_recall=MemoryRecallService(store=_SingleMemoryStore()),
            product_retrieval=ProductRetrievalService(vector_store=_SingleVectorStore()),
            compliance_facts_service=ComplianceFactsService(),
            product_candidates=[stock_only_candidate],
            agent_runtime=_CandidatePassthroughRuntime(),
        )
    )

    response = RecommendationService(graph_runtime=graph_runtime).generate_recommendation(
        _build_generation_request("aggressive")
    )

    assert response.recommendationStatus == "ready"
    assert response.sections.funds.items == []
    assert response.sections.wealthManagement.items == []
    assert [item.id for item in response.sections.stocks.items] == ["stock-only-001"]
    assert response.allocationDisplay.model_dump() == {
        "fund": 0,
        "wealthManagement": 0,
        "stock": 100,
    }
    assert response.aggressiveOption is not None
    assert response.aggressiveOption.allocation.model_dump() == {
        "fund": 0,
        "wealthManagement": 0,
        "stock": 100,
    }


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
    assert trace_by_request["user_profile_analyst"].providerName == "openai"
    assert trace_by_request["market_intelligence"].providerName == "openai"
    assert trace_by_request["product_match_expert"].providerName == "openai"
    assert trace_by_request["compliance_risk_officer"].providerName == "openai"
    assert trace_by_request["manager_coordinator"].providerName == "openai"


def test_graph_runtime_falls_back_when_user_profile_agent_stage_fails() -> None:
    response = RecommendationService(
        graph_runtime=_build_runtime(agent_runtime=_FailingUserProfileRuntime())
    ).generate_recommendation(_build_generation_request("balanced"))

    assert response.recommendationStatus == "ready"
    assert response.profileInsights is not None
    assert response.profileInsights.riskTier == "R3"
    assert response.warnings == []
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["user_profile_analyst"].status == "error"
    assert trace_by_request["market_intelligence"].status == "finish"


def test_graph_runtime_falls_back_to_retrieval_plan_when_product_match_fails() -> None:
    response = RecommendationService(
        graph_runtime=_build_runtime(agent_runtime=_InvalidProductMatchRuntime())
    ).generate_recommendation(_build_generation_request("balanced"))

    assert response.recommendationStatus in {"ready", "limited"}
    assert (
        response.sections.funds.items
        or response.sections.wealthManagement.items
        or response.sections.stocks.items
    )
    assert any(
        warning.stage == "product_match_expert"
        and warning.code == "agent_product_match_failed"
        and "product match unavailable" in warning.message
        for warning in response.warnings
    )
    trace_by_request = {event.requestName: event for event in response.agentTrace}
    assert trace_by_request["product_match_expert"].status == "error"


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


def test_graph_runtime_stores_product_evidence_bundles_in_retrieval_context() -> None:
    knowledge_service = _StubProductKnowledgeService()
    runtime = _build_runtime(
        agent_runtime=_SubsetSelectionRuntime(),
        product_retrieval_service=ProductRetrievalService(
            vector_store=_MultiCandidateVectorStore()
        ),
        product_knowledge_service=knowledge_service,
    )

    final_state = runtime.run(_build_generation_request("balanced"))

    retrieval_context = final_state["retrieval_context"]
    assert retrieval_context is not None
    assert retrieval_context.product_evidences
    assert knowledge_service.calls
    assert knowledge_service.calls[0]["query_text"] == "我希望获得稳健配置建议"
    assert {bundle.product_id for bundle in retrieval_context.product_evidences} == set(
        knowledge_service.calls[0]["product_ids"]
    )


def test_graph_runtime_injects_product_evidence_into_product_match_prompt_context() -> None:
    runtime_double = _RecordingAgentRuntime()
    runtime = _build_runtime(
        agent_runtime=runtime_double,
        product_retrieval_service=ProductRetrievalService(
            vector_store=_MultiCandidateVectorStore()
        ),
        product_knowledge_service=_StubProductKnowledgeService(),
    )

    runtime.run(_build_generation_request("balanced"))

    assert runtime_double.product_prompt_context is not None
    product_prompt = runtime_double.product_prompt_context.render_user_prompt()
    assert "wm-001 evidence snippet" in product_prompt
    assert "fund-001 evidence snippet" in product_prompt
    assert "stock-001 evidence snippet" in product_prompt
    assert "https://example.com/prospectus" not in product_prompt


def test_graph_runtime_preserves_product_evidence_after_compliance_filtering() -> None:
    knowledge_service = _StubProductKnowledgeService()
    runtime = _build_runtime(
        agent_runtime=_ComplianceFilteringRuntime(),
        product_retrieval_service=ProductRetrievalService(
            vector_store=_MultiCandidateVectorStore()
        ),
        product_knowledge_service=knowledge_service,
    )

    final_state = runtime.run(_build_generation_request("balanced"))

    compliance_review = final_state["compliance_review"]
    retrieval_context = final_state["retrieval_context"]
    assert compliance_review is not None
    assert compliance_review.verdict == "revise_conservative"
    assert retrieval_context is not None
    shortlist_ids = set(knowledge_service.calls[0]["product_ids"])
    approved_candidate_ids = {
        item.product_id for item in retrieval_context.candidates
    }
    evidence_ids = {bundle.product_id for bundle in retrieval_context.product_evidences}
    assert shortlist_ids - approved_candidate_ids
    assert evidence_ids == shortlist_ids


def test_graph_runtime_handles_none_product_knowledge_service_with_empty_product_evidence() -> None:
    runtime = _build_runtime(
        agent_runtime=_SubsetSelectionRuntime(),
        product_retrieval_service=ProductRetrievalService(
            vector_store=_MultiCandidateVectorStore()
        ),
        product_knowledge_service=None,
    )

    final_state = runtime.run(_build_generation_request("balanced"))

    retrieval_context = final_state["retrieval_context"]
    assert retrieval_context is not None
    assert retrieval_context.product_evidences == []
    assert final_state["warnings"] == []


def test_graph_runtime_degrades_when_product_evidence_retrieval_fails() -> None:
    runtime = _build_runtime(
        agent_runtime=_SubsetSelectionRuntime(),
        product_retrieval_service=ProductRetrievalService(
            vector_store=_MultiCandidateVectorStore()
        ),
        product_knowledge_service=_FailingProductKnowledgeService(),
    )

    final_state = runtime.run(_build_generation_request("balanced"))

    retrieval_context = final_state["retrieval_context"]
    assert retrieval_context is not None
    assert retrieval_context.product_evidences == []
    assert any(
        warning.stage == "product_match_expert"
        and warning.code == "product_evidence_unavailable"
        and "product evidence unavailable" in warning.message
        for warning in final_state["warnings"]
    )

    response = RecommendationService(graph_runtime=runtime).generate_recommendation(
        _build_generation_request("balanced")
    )
    assert any(
        warning.stage == "product_match_expert"
        and warning.code == "product_evidence_unavailable"
        and "product evidence unavailable" in warning.message
        for warning in response.warnings
    )


def test_graph_runtime_stores_compliance_retrieval_evidence() -> None:
    knowledge_service = _StubComplianceKnowledgeService()
    runtime = _build_runtime(
        agent_runtime=_CurrentAgentRuntime(),
        product_retrieval_service=ProductRetrievalService(
            vector_store=_MultiCandidateVectorStore()
        ),
        compliance_knowledge_service=knowledge_service,
    )

    final_state = runtime.run(_build_generation_request("balanced"))

    compliance_retrieval = final_state["compliance_retrieval"]
    assert compliance_retrieval is not None
    assert [bundle.rule_type for bundle in compliance_retrieval.evidences] == [
        "suitability",
        "risk_disclosure",
    ]
    assert knowledge_service.calls
    assert knowledge_service.calls[0]["categories"] == [
        "wealth_management",
        "fund",
        "stock",
    ]
    assert knowledge_service.calls[0]["risk_tiers"] == ["R3"]


def test_graph_runtime_injects_compliance_evidence_into_compliance_prompt_context() -> None:
    runtime_double = _RecordingAgentRuntime()
    runtime = _build_runtime(
        agent_runtime=runtime_double,
        product_retrieval_service=ProductRetrievalService(
            vector_store=_MultiCandidateVectorStore()
        ),
        compliance_knowledge_service=_StubComplianceKnowledgeService(),
    )

    runtime.run(_build_generation_request("balanced"))

    assert runtime_double.compliance_prompt_context is not None
    compliance_prompt = runtime_double.compliance_prompt_context.render_user_prompt()
    assert "销售机构应当将产品风险等级与投资者风险承受能力进行匹配。" in compliance_prompt
    assert "销售前应向投资者充分揭示产品风险特征和流动性安排。" in compliance_prompt
    assert "https://example.com/rule-001.pdf" not in compliance_prompt


def test_graph_runtime_falls_back_to_static_review_when_compliance_agent_fails() -> None:
    candidates = [
        CandidateProduct(
            id="fund-locked-001",
            category="fund",
            name_zh="封闭基金",
            name_en="Locked Fund",
            risk_level="R2",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="测试低流动性基金。",
            rationale_en="Test illiquid fund.",
            liquidity="180天",
        ),
        CandidateProduct(
            id="fund-liquid-001",
            category="fund",
            name_zh="稳健基金",
            name_en="Liquid Fund",
            risk_level="R2",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="测试稳健基金。",
            rationale_en="Test liquid fund.",
            liquidity="T+1",
        ),
    ]
    runtime = _build_runtime(
        agent_runtime=_FailingComplianceRuntime(),
        product_candidates=candidates,
        product_retrieval_service=ProductRetrievalService(
            vector_store=_IlliquidFirstVectorStore()
        ),
        compliance_knowledge_service=_StubComplianceKnowledgeService(),
        compliance_review_service=ComplianceReviewService(),
    )

    final_state = runtime.run(_build_generation_request("conservative"))

    compliance_review = final_state["compliance_review"]
    assert compliance_review is not None
    assert compliance_review.verdict == "revise_conservative"
    assert "compliance_fallback_static_review" in compliance_review.blocking_reason_codes
    assert any(
        warning.stage == "compliance_risk_officer"
        and warning.code == "agent_compliance_review_failed"
        and "compliance agent unavailable" in warning.message
        for warning in final_state["warnings"]
    )


def test_graph_runtime_falls_back_to_static_review_when_compliance_evidence_retrieval_fails() -> None:
    candidates = [
        CandidateProduct(
            id="fund-locked-001",
            category="fund",
            name_zh="封闭基金",
            name_en="Locked Fund",
            risk_level="R2",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="测试低流动性基金。",
            rationale_en="Test illiquid fund.",
            liquidity="180天",
        ),
        CandidateProduct(
            id="fund-liquid-001",
            category="fund",
            name_zh="稳健基金",
            name_en="Liquid Fund",
            risk_level="R2",
            tags_zh=["测试"],
            tags_en=["test"],
            rationale_zh="测试稳健基金。",
            rationale_en="Test liquid fund.",
            liquidity="T+1",
        ),
    ]
    runtime = _build_runtime(
        agent_runtime=_PermissiveComplianceRuntime(),
        product_candidates=candidates,
        product_retrieval_service=ProductRetrievalService(
            vector_store=_IlliquidFirstVectorStore()
        ),
        compliance_knowledge_service=_FailingComplianceKnowledgeService(),
        compliance_review_service=ComplianceReviewService(),
    )

    final_state = runtime.run(_build_generation_request("conservative"))

    compliance_review = final_state["compliance_review"]
    assert compliance_review is not None
    assert compliance_review.verdict == "revise_conservative"
    assert "compliance_fallback_static_review" in compliance_review.blocking_reason_codes
    assert any(
        warning.stage == "compliance_risk_officer"
        and warning.code == "compliance_evidence_unavailable"
        and "compliance evidence unavailable" in warning.message
        for warning in final_state["warnings"]
    )


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
    assert "Client context" in user_profile_prompt
    assert "zh-CN" in user_profile_prompt
    assert "web" in user_profile_prompt

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
    assert "Market intelligence" in compliance_prompt
    assert "AI市场解读" in compliance_prompt
    assert "Product match" in compliance_prompt
    assert "AI认为当前候选更匹配当前用户画像与市场环境" in compliance_prompt
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


def test_runtime_run_threads_user_id_into_request_context() -> None:
    runtime = RecommendationGraphRuntime.with_deterministic_services()
    state = runtime.run(_build_generation_request("balanced"), user_id="user-123")
    assert state["request_context"].user_id == "user-123"


def test_runtime_run_defaults_user_id_to_none() -> None:
    runtime = RecommendationGraphRuntime.with_deterministic_services()
    state = runtime.run(_build_generation_request("balanced"))
    assert state["request_context"].user_id is None


class _FakeChatHistoryRecallService:
    def __init__(self, snippets: list[str]) -> None:
        self._snippets = snippets
        self.calls: list[dict[str, object]] = []

    def recall(
        self,
        *,
        user_id: str,
        risk_profile: str,
        user_intent_text: str | None,
        latest_user_message: str | None,
        limit: int = 10,
    ) -> list[str]:
        self.calls.append(
            {
                "user_id": user_id,
                "risk_profile": risk_profile,
                "user_intent_text": user_intent_text,
                "latest_user_message": latest_user_message,
                "limit": limit,
            }
        )
        return list(self._snippets)


def test_user_profile_prompt_includes_recalled_chat_snippets() -> None:
    recall_service = _FakeChatHistoryRecallService(
        ["我更看重流动性", "我计划持有三到五年"]
    )
    runtime = RecommendationGraphRuntime.with_deterministic_services()
    runtime = RecommendationGraphRuntime(
        replace(runtime._services, chat_history_recall=recall_service)
    )

    payload = _build_generation_request(
        "balanced",
        conversation_messages=[
            {
                "role": "user",
                "content": "最近市场波动很大",
                "occurredAt": "2026-04-13T10:00:00Z",
            }
        ],
    )
    state = runtime.run(payload, user_id="user-123")

    assert len(recall_service.calls) == 1
    assert recall_service.calls[0]["user_id"] == "user-123"
    assert recall_service.calls[0]["risk_profile"] == "balanced"
    assert recall_service.calls[0]["latest_user_message"] == "最近市场波动很大"
    assert state["user_intelligence"] is not None


def test_graph_continues_when_chat_recall_fails() -> None:
    class _FailingRecallService:
        def recall(self, **_: object) -> list[str]:
            raise RuntimeError("qdrant unavailable")

    runtime = RecommendationGraphRuntime.with_deterministic_services()
    runtime = RecommendationGraphRuntime(
        replace(runtime._services, chat_history_recall=_FailingRecallService())
    )

    state = runtime.run(_build_generation_request("balanced"), user_id="user-123")

    assert state["final_response"] is not None


def test_chat_recall_skipped_when_no_user_id() -> None:
    recall_service = _FakeChatHistoryRecallService(["snippet"])
    runtime = RecommendationGraphRuntime.with_deterministic_services()
    runtime = RecommendationGraphRuntime(
        replace(runtime._services, chat_history_recall=recall_service)
    )

    state = runtime.run(_build_generation_request("balanced"))

    assert recall_service.calls == []
    assert state["user_intelligence"] is not None
