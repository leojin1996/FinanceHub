from __future__ import annotations

from financehub_market_api.models import (
    RecommendationGenerationRequest,
    RecommendationResponse,
    RiskProfile,
)
from financehub_market_api.recommendation.graph.runtime import RecommendationGraphRuntime
from financehub_market_api.recommendation.orchestration import RecommendationOrchestrator
from financehub_market_api.recommendation.services.assembler import (
    assemble_domain_recommendation_response,
    assemble_graph_recommendation_response,
)


class RecommendationService:
    def __init__(
        self,
        orchestrator: RecommendationOrchestrator | None = None,
        graph_runtime: RecommendationGraphRuntime | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        if graph_runtime is not None:
            self._graph_runtime = graph_runtime
        elif orchestrator is not None:
            self._graph_runtime = None
        else:
            self._graph_runtime = RecommendationGraphRuntime.with_deterministic_services()

    def generate_recommendation(
        self, payload: RecommendationGenerationRequest
    ) -> RecommendationResponse:
        if self._graph_runtime is not None:
            graph_state = self._graph_runtime.run(payload)
            return assemble_graph_recommendation_response(
                graph_state,
                include_aggressive_option=payload.includeAggressiveOption,
            )
        if self._orchestrator is None:
            raise ValueError("recommendation runtime is not configured")
        recommendation = self._orchestrator.generate(payload.riskAssessmentResult.finalProfile)
        return assemble_domain_recommendation_response(
            recommendation,
            include_aggressive_option=payload.includeAggressiveOption,
        )

    def get_recommendation(self, risk_profile: RiskProfile) -> RecommendationResponse:
        if self._graph_runtime is None:
            if self._orchestrator is None:
                raise ValueError("recommendation runtime is not configured")
            recommendation = self._orchestrator.generate(risk_profile)
            return assemble_domain_recommendation_response(recommendation)

        payload = RecommendationGenerationRequest.model_validate(
            {
                "historicalHoldings": [],
                "historicalTransactions": [],
                "includeAggressiveOption": True,
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
        return self.generate_recommendation(payload)
