from __future__ import annotations

import logging

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

LOGGER = logging.getLogger(__name__)
_GRAPH_RUNTIME_FALLBACK_MESSAGE = (
    "Recommendation graph runtime unavailable; using rules fallback."
)


class RecommendationService:
    def __init__(
        self,
        orchestrator: RecommendationOrchestrator | None = None,
        graph_runtime: RecommendationGraphRuntime | None = None,
    ) -> None:
        if graph_runtime is not None:
            self._graph_runtime = graph_runtime
        elif orchestrator is not None:
            self._graph_runtime = None
        else:
            self._graph_runtime = RecommendationGraphRuntime.with_deterministic_services()
        if orchestrator is not None:
            self._orchestrator = orchestrator
        elif self._graph_runtime is not None:
            # Keep a legacy rules engine available only for emergency fallback.
            self._orchestrator = RecommendationOrchestrator()
        else:
            self._orchestrator = None

    def generate_recommendation(
        self, payload: RecommendationGenerationRequest
    ) -> RecommendationResponse:
        if self._graph_runtime is not None:
            try:
                graph_state = self._graph_runtime.run(payload)
            except Exception:
                if self._orchestrator is None:
                    raise
                LOGGER.exception(
                    "recommendation graph runtime failed; falling back to rules path"
                )
                recommendation = self._orchestrator.generate_rules_fallback(
                    payload.riskAssessmentResult.finalProfile,
                    warning_stage="graph_runtime",
                    warning_code="graph_runtime_error",
                    warning_message=_GRAPH_RUNTIME_FALLBACK_MESSAGE,
                )
                return assemble_domain_recommendation_response(
                    recommendation,
                    include_aggressive_option=payload.includeAggressiveOption,
                )
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
