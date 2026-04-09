from __future__ import annotations

from dataclasses import dataclass, field, replace

from langgraph.graph import END, START, StateGraph

from financehub_market_api.cache import build_snapshot_cache
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
from financehub_market_api.recommendation.intelligence.service import MarketDataSnapshotSource
from financehub_market_api.recommendation.manager_synthesis import ManagerSynthesisService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.profile_intelligence import ProfileIntelligenceService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.repositories import (
    CandidateRepository,
    RealDataCandidateRepository,
    StaticCandidateRepository,
)
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.schemas import CandidateProduct
from financehub_market_api.service import MarketDataService
from financehub_market_api.upstreams.dolthub import DoltHubClient
from financehub_market_api.upstreams.index_data import IndexDataClient


@dataclass(frozen=True)
class GraphServices:
    market_intelligence: MarketIntelligenceService
    memory_recall: MemoryRecallService
    product_retrieval: ProductRetrievalService
    compliance_review: ComplianceReviewService
    product_candidates: list[CandidateProduct]
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


def _build_product_candidates(repository: CandidateRepository) -> list[CandidateProduct]:
    profile = map_user_profile("balanced")
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
            ),
        )
        graph.add_node(
            "market_intelligence",
            lambda state: market_intelligence_node(
                state,
                market_intelligence_service=services.market_intelligence,
            ),
        )
        graph.add_node(
            "product_match_expert",
            lambda state: product_match_expert_node(
                state,
                product_retrieval_service=services.product_retrieval,
                memory_recall_service=services.memory_recall,
                product_candidates=services.product_candidates,
            ),
        )
        graph.add_node(
            "compliance_risk_officer",
            lambda state: compliance_risk_officer_node(
                state,
                compliance_review_service=services.compliance_review,
                product_candidates=services.product_candidates,
            ),
        )
        graph.add_node(
            "manager_coordinator",
            lambda state: manager_coordinator_node(
                state,
                manager_synthesis_service=services.manager_synthesis,
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

    def _services_for_request(self) -> GraphServices:
        repository = self._services.candidate_repository
        if repository is None:
            return self._services

        product_candidates = _build_product_candidates(repository)
        return replace(
            self._services,
            product_retrieval=ProductRetrievalService(
                vector_store=_StaticVectorStore(product_candidates)
            ),
            product_candidates=product_candidates,
        )

    def run(self, payload: RecommendationGenerationRequest) -> RecommendationGraphState:
        initial_state = build_initial_graph_state(payload)
        services = self._services_for_request()
        graph = self._graph if services is self._services else self._build_graph(services)
        final_state = graph.invoke(initial_state)
        return final_state

    @classmethod
    def with_default_services(
        cls,
        *,
        repository: CandidateRepository | None = None,
        market_data_service: MarketDataSnapshotSource | None = None,
    ) -> RecommendationGraphRuntime:
        candidate_repository = repository or RealDataCandidateRepository()
        return cls(
            GraphServices(
                market_intelligence=MarketIntelligenceService(
                    market_data_service=market_data_service or _build_default_market_data_service()
                ),
                memory_recall=MemoryRecallService(store=_StaticMemoryStore()),
                product_retrieval=ProductRetrievalService(vector_store=_StaticVectorStore([])),
                compliance_review=ComplianceReviewService(),
                product_candidates=[],
                candidate_repository=candidate_repository,
            )
        )

    @classmethod
    def with_deterministic_services(cls) -> RecommendationGraphRuntime:
        candidates = _build_product_candidates(StaticCandidateRepository())
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
        candidates = _build_product_candidates(StaticCandidateRepository())

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
