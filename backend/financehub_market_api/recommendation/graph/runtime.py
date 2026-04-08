from __future__ import annotations

from dataclasses import dataclass, replace

from langgraph.graph import END, START, StateGraph

from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.compliance import ComplianceReviewService
from financehub_market_api.recommendation.graph.nodes import (
    compliance_risk_officer_node,
    manager_coordinator_node,
    market_intelligence_node,
    product_match_expert_node,
    user_profile_analyst_node,
)
from financehub_market_api.recommendation.graph.routing import route_compliance_verdict
from financehub_market_api.recommendation.graph.state import RecommendationGraphState, build_initial_graph_state
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.repositories import StaticCandidateRepository
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.schemas import CandidateProduct


@dataclass(frozen=True)
class GraphServices:
    market_intelligence: MarketIntelligenceService
    memory_recall: MemoryRecallService
    product_retrieval: ProductRetrievalService
    compliance_review: ComplianceReviewService
    product_candidates: list[CandidateProduct]


class _StaticMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        seeds = [
            f"intent:{query}",
            "prefers:stable_drawdown",
            "liquidity:medium",
            "horizon:one_year",
        ]
        return seeds[:limit]


class _StaticVectorStore:
    def __init__(self, candidates: list[CandidateProduct]) -> None:
        self._ids = [candidate.id for candidate in candidates]

    def search(self, query_text: str, *, limit: int) -> list[dict[str, object]]:
        del query_text
        return [{"id": product_id, "score": 1.0 - index * 0.05} for index, product_id in enumerate(self._ids[:limit])]


class RecommendationGraphRuntime:
    def __init__(self, services: GraphServices) -> None:
        self._services = services
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(RecommendationGraphState)

        graph.add_node("user_profile_analyst", user_profile_analyst_node)
        graph.add_node(
            "market_intelligence",
            lambda state: market_intelligence_node(
                state,
                market_intelligence_service=self._services.market_intelligence,
            ),
        )
        graph.add_node(
            "product_match_expert",
            lambda state: product_match_expert_node(
                state,
                product_retrieval_service=self._services.product_retrieval,
                memory_recall_service=self._services.memory_recall,
                product_candidates=self._services.product_candidates,
            ),
        )
        graph.add_node(
            "compliance_risk_officer",
            lambda state: compliance_risk_officer_node(
                state,
                compliance_review_service=self._services.compliance_review,
                product_candidates=self._services.product_candidates,
            ),
        )
        graph.add_node("manager_coordinator", manager_coordinator_node)

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

    def run(self, payload: RecommendationGenerationRequest) -> RecommendationGraphState:
        initial_state = build_initial_graph_state(payload)
        final_state = self._graph.invoke(initial_state)
        return final_state

    @classmethod
    def with_deterministic_services(cls) -> RecommendationGraphRuntime:
        repository = StaticCandidateRepository()
        profile = map_user_profile("balanced")
        candidates = [
            *repository.list_funds(profile),
            *repository.list_wealth_management(profile),
            *repository.list_stocks(profile),
        ]
        return cls(
            GraphServices(
                market_intelligence=MarketIntelligenceService(),
                memory_recall=MemoryRecallService(store=_StaticMemoryStore()),
                product_retrieval=ProductRetrievalService(vector_store=_StaticVectorStore(candidates)),
                compliance_review=ComplianceReviewService(),
                product_candidates=candidates,
            )
        )

    @classmethod
    def with_high_risk_candidate(cls) -> RecommendationGraphRuntime:
        repository = StaticCandidateRepository()
        profile = map_user_profile("balanced")
        candidates = [
            *repository.list_funds(profile),
            *repository.list_wealth_management(profile),
            *repository.list_stocks(profile),
        ]

        adjusted_candidates: list[CandidateProduct] = []
        for candidate in candidates:
            if candidate.id == "stock-001":
                adjusted_candidates.append(replace(candidate, risk_level="R5"))
            else:
                adjusted_candidates.append(candidate)

        return cls(
            GraphServices(
                market_intelligence=MarketIntelligenceService(),
                memory_recall=MemoryRecallService(store=_StaticMemoryStore()),
                product_retrieval=ProductRetrievalService(
                    vector_store=_StaticVectorStore(adjusted_candidates)
                ),
                compliance_review=ComplianceReviewService(),
                product_candidates=adjusted_candidates,
            )
        )
