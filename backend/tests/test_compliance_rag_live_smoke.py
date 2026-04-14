from __future__ import annotations

import os

import pytest

from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.compliance_knowledge import (
    build_compliance_knowledge_retrieval_service_from_env,
)
from financehub_market_api.recommendation.graph.runtime import (
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendations import RecommendationService

LIVE_COMPLIANCE_RAG_SMOKE_ENV = "FINANCEHUB_RUN_COMPLIANCE_RAG_LIVE_SMOKE"
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


def test_live_compliance_rag_smoke_returns_regulatory_evidence() -> None:
    if not _enabled(LIVE_COMPLIANCE_RAG_SMOKE_ENV):
        pytest.skip(
            f"Set {LIVE_COMPLIANCE_RAG_SMOKE_ENV}=true to run live compliance RAG smoke coverage."
        )

    compliance_knowledge_service = build_compliance_knowledge_retrieval_service_from_env()
    if compliance_knowledge_service is None:
        pytest.skip("Live compliance knowledge env is incomplete for smoke coverage.")

    runtime = RecommendationGraphRuntime.with_deterministic_services(
        compliance_knowledge_service=compliance_knowledge_service,
    )
    state = runtime.run(_build_generation_request("balanced"))

    assert state["compliance_retrieval"] is not None
    assert state["compliance_retrieval"].evidences

    response = RecommendationService(graph_runtime=runtime).generate_recommendation(
        _build_generation_request("balanced")
    )
    assert response.reviewStatus in {"pass", "partial_pass"}
    assert "complianceEvidence" not in str(response.model_dump(mode="json", by_alias=True))
