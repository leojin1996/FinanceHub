from __future__ import annotations

from financehub_market_api.models import (
    RecommendationGenerationRequest,
    RecommendationResponse,
    RiskProfile,
)
from financehub_market_api.recommendation.orchestration import RecommendationOrchestrator
from financehub_market_api.recommendation.services.assembler import assemble_recommendation_response


class RecommendationService:
    def __init__(self, orchestrator: RecommendationOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or RecommendationOrchestrator()

    def generate_recommendation(
        self, payload: RecommendationGenerationRequest
    ) -> RecommendationResponse:
        recommendation = self._orchestrator.generate(payload.riskAssessmentResult.finalProfile)
        return assemble_recommendation_response(
            recommendation,
            include_aggressive_option=payload.includeAggressiveOption,
        )

    def get_recommendation(self, risk_profile: RiskProfile) -> RecommendationResponse:
        recommendation = self._orchestrator.generate(risk_profile)
        return assemble_recommendation_response(recommendation)
