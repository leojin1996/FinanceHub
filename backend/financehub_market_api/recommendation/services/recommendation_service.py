from __future__ import annotations

from financehub_market_api.models import (
    RecommendationGenerationRequest,
    RecommendationResponse,
    RiskProfile,
)
from financehub_market_api.recommendation.graph.runtime import RecommendationGraphRuntime
from financehub_market_api.recommendation.services.assembler import assemble_graph_recommendation_response


class RecommendationService:
    def __init__(
        self,
        orchestrator: object | None = None,
        graph_runtime: RecommendationGraphRuntime | None = None,
    ) -> None:
        if orchestrator is not None:
            raise ValueError("orchestrator is no longer supported; use graph_runtime only")

        self._graph_runtime = graph_runtime or RecommendationGraphRuntime.with_deterministic_services()
        self._orchestrator = None

    def generate_recommendation(
        self,
        payload: RecommendationGenerationRequest,
        *,
        user_id: str | None = None,
    ) -> RecommendationResponse:
        graph_state = self._graph_runtime.run(payload, user_id=user_id)
        return assemble_graph_recommendation_response(
            graph_state,
            include_aggressive_option=payload.includeAggressiveOption,
        )

    def get_recommendation(self, risk_profile: RiskProfile) -> RecommendationResponse:
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
