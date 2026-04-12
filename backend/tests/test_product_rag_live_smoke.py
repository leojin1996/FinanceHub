from __future__ import annotations

import os

import pytest

from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.graph.runtime import (
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendation.product_knowledge import (
    build_product_knowledge_retrieval_service_from_env,
)
from financehub_market_api.recommendations import RecommendationService

LIVE_PRODUCT_RAG_SMOKE_ENV = "FINANCEHUB_RUN_PRODUCT_RAG_LIVE_SMOKE"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _enabled(env_key: str) -> bool:
    return os.environ.get(env_key, "").strip().lower() in _TRUTHY_ENV_VALUES


def _build_generation_request(risk_profile: str) -> RecommendationGenerationRequest:
    return RecommendationGenerationRequest.model_validate(
        {
            "userIntentText": "我希望获得稳健配置建议",
            "historicalHoldings": [],
            "historicalTransactions": [],
            "includeAggressiveOption": True,
            "questionnaireAnswers": [],
            "conversationMessages": [],
            "clientContext": {
                "channel": "web",
                "locale": "zh-CN",
            },
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


def test_live_product_rag_smoke_returns_public_evidence_preview() -> None:
    if not _enabled(LIVE_PRODUCT_RAG_SMOKE_ENV):
        pytest.skip(
            f"Set {LIVE_PRODUCT_RAG_SMOKE_ENV}=true to run live product RAG smoke coverage."
        )

    product_knowledge_service = build_product_knowledge_retrieval_service_from_env()
    if product_knowledge_service is None:
        pytest.skip("Live product knowledge env is incomplete for smoke coverage.")

    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services(
            product_knowledge_service=product_knowledge_service,
        )
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.sections.funds.items
    assert response.sections.funds.items[0].evidencePreview
    assert all(
        reference.sourceTitle != "投顾内部备注"
        for reference in response.sections.funds.items[0].evidencePreview
    )
