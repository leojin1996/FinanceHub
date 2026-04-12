from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from langgraph.graph import END, START, StateGraph

from financehub_market_api.cache import build_snapshot_cache
from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    ManagerCoordinatorAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.live_runtime import (
    AgentInvocationMetadata,
    RecommendationAgentRuntime,
)
from financehub_market_api.recommendation.compliance import (
    ComplianceFactsService,
    ComplianceReviewService,
)
from financehub_market_api.recommendation.graph.nodes import (
    compliance_risk_officer_node,
    manager_coordinator_node,
    market_intelligence_node,
    product_match_expert_node,
    user_profile_analyst_node,
)
from financehub_market_api.recommendation.graph.routing import route_compliance_verdict
from financehub_market_api.recommendation.graph.state import (
    RecommendationGraphState,
    build_initial_graph_state,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.intelligence.service import (
    MarketDataSnapshotSource,
)
from financehub_market_api.recommendation.manager_synthesis import (
    ManagerSynthesisService,
)
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.profile_intelligence import (
    ProfileIntelligenceService,
)
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.repositories import (
    CandidateRepository,
    PrefetchedCandidateRepository,
    StaticCandidateRepository,
)
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile
from financehub_market_api.service import MarketDataService
from financehub_market_api.upstreams.dolthub import DoltHubClient
from financehub_market_api.upstreams.index_data import IndexDataClient

_RISK_TIER_BY_PROFILE = {
    "conservative": "R2",
    "stable": "R2",
    "balanced": "R3",
    "growth": "R4",
    "aggressive": "R5",
}
_RISK_ORDER = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}


@dataclass(frozen=True)
class GraphServices:
    market_intelligence: MarketIntelligenceService
    memory_recall: MemoryRecallService
    product_retrieval: ProductRetrievalService
    product_candidates: list[CandidateProduct]
    compliance_review: ComplianceReviewService | None = None
    compliance_review_service: ComplianceReviewService | None = None
    compliance_facts_service: ComplianceFactsService | None = None
    agent_runtime: object | None = None
    candidate_repository: CandidateRepository | None = None
    profile_intelligence: ProfileIntelligenceService = field(
        default_factory=ProfileIntelligenceService
    )
    manager_synthesis: ManagerSynthesisService = field(
        default_factory=ManagerSynthesisService
    )


class _StaticMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        seeds = [
            f"intent:{query}",
            "prefers:stable_drawdown",
            "liquidity:high",
            "horizon:one_year",
        ]
        return seeds[:limit]


class _StaticVectorStore:
    def __init__(self, candidates: list[CandidateProduct]) -> None:
        self._ids = [candidate.id for candidate in candidates]

    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [
            {"id": product_id, "score": 1.0 - index * 0.05}
            for index, product_id in enumerate(self._ids[:limit])
        ]


class _DeterministicAgentRuntime:
    _MODEL_BY_REQUEST = {
        "user_profile_analyst": "deterministic-user-profile",
        "market_intelligence": "deterministic-market",
        "product_match_expert": "deterministic-product-match",
        "compliance_risk_officer": "deterministic-compliance",
        "manager_coordinator": "deterministic-manager",
    }

    def route_metadata(self, request_name: str) -> AgentInvocationMetadata:
        return AgentInvocationMetadata(
            provider_name="openai",
            model_name=self._MODEL_BY_REQUEST[request_name],
        )

    def analyze_user_profile(
        self,
        user_profile: UserProfile,
        *,
        prompt_context=None,
    ) -> tuple[UserProfileAgentOutput, AgentInvocationMetadata]:
        prompt_text = (
            prompt_context.render_user_prompt()
            if prompt_context is not None
            else ""
        )
        emphasizes_capital_preservation = any(
            phrase in prompt_text for phrase in ("不想亏本", "保本", "高流动性", "流动性")
        )
        risk_tier = (
            "R2"
            if emphasizes_capital_preservation
            and _RISK_ORDER[_RISK_TIER_BY_PROFILE[user_profile.risk_profile]] > 2
            else _RISK_TIER_BY_PROFILE[user_profile.risk_profile]
        )
        liquidity_preference = "high" if "流动性" in prompt_text else "medium"
        investment_horizon = "one_year" if "一年" in prompt_text else "medium"
        return_objective = (
            "capital_preservation"
            if emphasizes_capital_preservation
            else "balanced_growth"
        )
        drawdown_sensitivity = "high" if emphasizes_capital_preservation else "medium"
        output = UserProfileAgentOutput(
            risk_tier=risk_tier,
            liquidity_preference=liquidity_preference,
            investment_horizon=investment_horizon,
            return_objective=return_objective,
            drawdown_sensitivity=drawdown_sensitivity,
            profile_focus_zh=(
                "用户强调一年期保本与高流动性。"
                if emphasizes_capital_preservation
                else f"用户当前画像更接近{user_profile.label_zh}配置。"
            ),
            profile_focus_en=(
                "The user emphasizes one-year principal protection and strong liquidity."
                if emphasizes_capital_preservation
                else f"The user aligns with a {user_profile.label_en} allocation profile."
            ),
            derived_signals=(
                ["intent:capital_preservation", "conversation:liquidity"]
                if emphasizes_capital_preservation
                else [f"profile:{user_profile.risk_profile}"]
            ),
        )
        return output, self.route_metadata("user_profile_analyst")

    def analyze_market_intelligence(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_facts: dict[str, object],
        *,
        prompt_context=None,
    ) -> tuple[MarketIntelligenceAgentOutput, AgentInvocationMetadata]:
        del user_profile, prompt_context
        facts_text = json.dumps(market_facts, ensure_ascii=False)
        defensive = (
            "negative" in facts_text
            or "承压" in facts_text
            or user_profile_insights.risk_tier in {"R1", "R2"}
        )
        output = MarketIntelligenceAgentOutput(
            sentiment="negative" if defensive else "positive",
            stance="defensive" if defensive else "balanced",
            preferred_categories=["wealth_management", "fund"]
            if defensive
            else ["fund", "stock"],
            avoided_categories=["stock"] if defensive else [],
            summary_zh=(
                "市场震荡偏弱，建议优先稳健资产和流动性。"
                if defensive
                else "市场环境相对平衡，可在稳健底仓上适度增加弹性。"
            ),
            summary_en=(
                "Markets are soft and volatile, so favor resilience and liquidity."
                if defensive
                else "Conditions are broadly balanced, allowing moderate upside on top of a resilient core."
            ),
            evidence_refs=["market_overview", "macro_and_rates"] if defensive else ["market_overview"],
        )
        return output, self.route_metadata("market_intelligence")

    def match_products(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        prompt_context=None,
    ) -> tuple[ProductMatchAgentOutput, AgentInvocationMetadata]:
        del user_profile, prompt_context
        allow_stock = (
            user_profile_insights.risk_tier not in {"R1", "R2"}
            and market_intelligence.stance != "defensive"
        )
        fund_ids = [
            candidate.id for candidate in candidates if candidate.category == "fund"
        ][:2]
        wealth_ids = [
            candidate.id
            for candidate in candidates
            if candidate.category == "wealth_management"
        ][:2]
        stock_ids = (
            [candidate.id for candidate in candidates if candidate.category == "stock"][:1]
            if allow_stock
            else []
        )
        recommended_categories = ["wealth_management", "fund"]
        if allow_stock and stock_ids:
            recommended_categories.append("stock")
        output = ProductMatchAgentOutput(
            recommended_categories=recommended_categories,
            fund_ids=fund_ids,
            wealth_management_ids=wealth_ids,
            stock_ids=stock_ids,
            ranking_rationale_zh=(
                "优先保留稳健和高流动性候选。"
                if not allow_stock
                else "在稳健底仓基础上保留少量权益增强。"
            ),
            ranking_rationale_en=(
                "Prefer resilient and high-liquidity candidates."
                if not allow_stock
                else "Keep a resilient core with a limited equity sleeve."
            ),
            filtered_out_reasons=([] if allow_stock else ["stock filtered by defensive suitability analysis"]),
        )
        return output, self.route_metadata("product_match_expert")

    def review_compliance(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        selected_candidates: list[CandidateProduct],
        compliance_facts: dict[str, object],
        prompt_context=None,
    ) -> tuple[ComplianceReviewAgentOutput, AgentInvocationMetadata]:
        del user_profile, compliance_facts, prompt_context
        allowed_level = _RISK_ORDER.get(user_profile_insights.risk_tier, 2)
        approved = [
            candidate.id
            for candidate in selected_candidates
            if _RISK_ORDER.get(candidate.risk_level, 99) <= allowed_level
        ]
        rejected = [
            candidate.id for candidate in selected_candidates if candidate.id not in approved
        ]
        verdict = (
            "approve"
            if len(approved) == len(selected_candidates)
            else "revise_conservative"
            if approved
            else "block"
        )
        output = ComplianceReviewAgentOutput(
            verdict=verdict,
            approved_ids=approved,
            rejected_ids=rejected,
            reason_summary_zh=(
                "候选通过适当性审核。"
                if verdict == "approve"
                else "已移除超出风险承受范围的候选。"
                if verdict == "revise_conservative"
                else "候选均超出适当性范围，需人工复核。"
            ),
            reason_summary_en=(
                "The candidate set passed suitability review."
                if verdict == "approve"
                else "Candidates exceeding suitability limits were removed."
                if verdict == "revise_conservative"
                else "All candidates exceeded suitability limits and require manual review."
            ),
            required_disclosures_zh=["理财非存款，投资需谨慎。"],
            required_disclosures_en=["Investing involves risk. Proceed prudently."],
            suitability_notes_zh=["风险等级需与用户画像一致。"],
            suitability_notes_en=["Candidate risk levels must align with the user profile."],
            applied_rule_ids=[f"suitability-{user_profile_insights.risk_tier.lower()}"],
            blocking_reason_codes=[] if verdict != "block" else ["risk_tier_exceeded"],
        )
        return output, self.route_metadata("compliance_risk_officer")

    def coordinate_manager(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        product_match: ProductMatchAgentOutput,
        compliance_review: ComplianceReviewAgentOutput,
        prompt_context=None,
    ) -> tuple[ManagerCoordinatorAgentOutput, AgentInvocationMetadata]:
        del user_profile, prompt_context
        if compliance_review.verdict == "block":
            status = "blocked"
        elif (
            compliance_review.verdict == "revise_conservative"
            or "stock" not in product_match.recommended_categories
        ):
            status = "limited"
        else:
            status = "ready"
        category_phrase = "、".join(
            {
                "wealth_management": "银行理财",
                "fund": "基金",
                "stock": "股票",
            }.get(category, category)
            for category in product_match.recommended_categories
        ) or "稳健资产"
        output = ManagerCoordinatorAgentOutput(
            recommendation_status=status,
            summary_zh=f"建议优先配置{category_phrase}，兼顾风险与流动性。",
            summary_en="Favor resilient categories that balance risk control and liquidity.",
            why_this_plan_zh=[
                f"当前画像为 {user_profile_insights.risk_tier}，优先控制回撤。",
                f"市场立场为 {market_intelligence.stance}，因此先配置{category_phrase}。",
            ],
            why_this_plan_en=[
                f"The user screens as {user_profile_insights.risk_tier}, so drawdown control comes first.",
                f"The market stance is {market_intelligence.stance}, so the plan favors {category_phrase}.",
            ],
        )
        return output, self.route_metadata("manager_coordinator")


def _build_product_candidates(
    repository: CandidateRepository,
    *,
    risk_profile: str,
) -> list[CandidateProduct]:
    profile = map_user_profile(risk_profile)
    return [
        *repository.list_funds(profile),
        *repository.list_wealth_management(profile),
        *repository.list_stocks(profile),
    ]


def _build_default_market_data_service() -> MarketDataService:
    return MarketDataService(
        stock_client=DoltHubClient(),
        index_client=IndexDataClient(),
        cache=build_snapshot_cache(),
    )


class RecommendationGraphRuntime:
    def __init__(self, services: GraphServices) -> None:
        self._services = services
        self._graph = self._build_graph(services)

    def _build_graph(self, services: GraphServices):
        graph = StateGraph(RecommendationGraphState)

        graph.add_node(
            "user_profile_analyst",
            lambda state: user_profile_analyst_node(
                state,
                profile_intelligence_service=services.profile_intelligence,
                agent_runtime=services.agent_runtime,
            ),
        )
        graph.add_node(
            "market_intelligence",
            lambda state: market_intelligence_node(
                state,
                market_intelligence_service=services.market_intelligence,
                agent_runtime=services.agent_runtime,
            ),
        )
        graph.add_node(
            "product_match_expert",
            lambda state: product_match_expert_node(
                state,
                product_retrieval_service=services.product_retrieval,
                memory_recall_service=services.memory_recall,
                product_candidates=services.product_candidates,
                agent_runtime=services.agent_runtime,
            ),
        )
        graph.add_node(
            "compliance_risk_officer",
            lambda state: compliance_risk_officer_node(
                state,
                compliance_review_service=(
                    services.compliance_review_service or services.compliance_review
                ),
                compliance_facts_service=services.compliance_facts_service,
                product_candidates=services.product_candidates,
                agent_runtime=services.agent_runtime,
            ),
        )
        graph.add_node(
            "manager_coordinator",
            lambda state: manager_coordinator_node(
                state,
                manager_synthesis_service=services.manager_synthesis,
                agent_runtime=services.agent_runtime,
            ),
        )

        graph.add_edge(START, "user_profile_analyst")
        graph.add_edge("user_profile_analyst", "market_intelligence")
        graph.add_edge("market_intelligence", "product_match_expert")
        graph.add_edge("product_match_expert", "compliance_risk_officer")
        graph.add_conditional_edges(
            "compliance_risk_officer",
            route_compliance_verdict,
            {
                "approved": "manager_coordinator",
                "limited": "manager_coordinator",
                "blocked": "manager_coordinator",
            },
        )
        graph.add_edge("manager_coordinator", END)
        return graph.compile()

    def _services_for_request(
        self,
        payload: RecommendationGenerationRequest,
    ) -> GraphServices:
        repository = self._services.candidate_repository
        if repository is None:
            return self._services

        risk_profile = payload.riskAssessmentResult.finalProfile
        product_candidates = _build_product_candidates(
            repository,
            risk_profile=risk_profile,
        )
        return replace(
            self._services,
            product_retrieval=ProductRetrievalService(
                vector_store=_StaticVectorStore(product_candidates)
            ),
            product_candidates=product_candidates,
        )

    def run(self, payload: RecommendationGenerationRequest) -> RecommendationGraphState:
        initial_state = build_initial_graph_state(payload)
        services = self._services_for_request(payload)
        graph = (
            self._graph if services is self._services else self._build_graph(services)
        )
        return graph.invoke(initial_state)

    @classmethod
    def with_default_services(
        cls,
        *,
        repository: CandidateRepository | None = None,
        market_data_service: MarketDataSnapshotSource | None = None,
        use_ai_agents: bool = False,
    ) -> RecommendationGraphRuntime:
        candidate_repository = (
            repository or PrefetchedCandidateRepository.with_default_cache()
        )
        agent_runtime = (
            RecommendationAgentRuntime.from_env() if use_ai_agents else None
        )
        return cls(
            GraphServices(
                market_intelligence=MarketIntelligenceService(
                    market_data_service=market_data_service
                    or _build_default_market_data_service()
                ),
                memory_recall=MemoryRecallService(store=_StaticMemoryStore()),
                product_retrieval=ProductRetrievalService(
                    vector_store=_StaticVectorStore([])
                ),
                compliance_review_service=ComplianceReviewService(),
                compliance_facts_service=ComplianceFactsService(),
                product_candidates=[],
                agent_runtime=agent_runtime,
                candidate_repository=candidate_repository,
            )
        )

    @classmethod
    def with_deterministic_services(cls) -> RecommendationGraphRuntime:
        candidates = _build_product_candidates(
            StaticCandidateRepository(),
            risk_profile="balanced",
        )
        return cls(
            GraphServices(
                market_intelligence=MarketIntelligenceService(),
                memory_recall=MemoryRecallService(store=_StaticMemoryStore()),
                product_retrieval=ProductRetrievalService(
                    vector_store=_StaticVectorStore(candidates)
                ),
                compliance_review_service=ComplianceReviewService(),
                compliance_facts_service=ComplianceFactsService(),
                product_candidates=candidates,
                agent_runtime=_DeterministicAgentRuntime(),
            )
        )

    @classmethod
    def with_high_risk_candidate(cls) -> RecommendationGraphRuntime:
        candidates = _build_product_candidates(
            StaticCandidateRepository(),
            risk_profile="balanced",
        )
        adjusted_candidates = [
            replace(candidate, risk_level="R5")
            if candidate.id == "stock-001"
            else candidate
            for candidate in candidates
        ]
        return cls(
            GraphServices(
                market_intelligence=MarketIntelligenceService(),
                memory_recall=MemoryRecallService(store=_StaticMemoryStore()),
                product_retrieval=ProductRetrievalService(
                    vector_store=_StaticVectorStore(adjusted_candidates)
                ),
                compliance_review_service=ComplianceReviewService(),
                compliance_facts_service=ComplianceFactsService(),
                product_candidates=adjusted_candidates,
                agent_runtime=_DeterministicAgentRuntime(),
            )
        )
