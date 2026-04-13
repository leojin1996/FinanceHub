from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from financehub_market_api.main import app, get_recommendation_service
from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.compliance_knowledge import (
    build_compliance_knowledge_retrieval_service_from_env,
)
from financehub_market_api.recommendation.graph.runtime import (
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendations import RecommendationService

LIVE_COMPLIANCE_RAG_E2E_ENV = "FINANCEHUB_RUN_COMPLIANCE_RAG_LIVE_E2E"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _enabled(env_key: str) -> bool:
    return os.environ.get(env_key, "").strip().lower() in _TRUTHY_ENV_VALUES


def _build_generation_request_payload(risk_profile: str) -> dict[str, object]:
    request = RecommendationGenerationRequest.model_validate(
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
    return request.model_dump(mode="json", by_alias=True)


def test_live_compliance_rag_e2e_keeps_regulatory_evidence_backend_only() -> None:
    if not _enabled(LIVE_COMPLIANCE_RAG_E2E_ENV):
        pytest.skip(
            f"Set {LIVE_COMPLIANCE_RAG_E2E_ENV}=true to run live compliance RAG end-to-end coverage."
        )

    compliance_knowledge_service = build_compliance_knowledge_retrieval_service_from_env()
    if compliance_knowledge_service is None:
        pytest.skip("Live compliance knowledge env is incomplete for e2e coverage.")

    recommendation_service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services(
            compliance_knowledge_service=compliance_knowledge_service,
        )
    )

    app.dependency_overrides[get_recommendation_service] = lambda: recommendation_service
    client = TestClient(app)

    try:
        recommendation = client.post(
            "/api/recommendations/generate",
            json=_build_generation_request_payload("balanced"),
        )
        assert recommendation.status_code == 200
        body = recommendation.json()
        assert body["reviewStatus"] in {"pass", "partial_pass"}
        assert "complianceEvidence" not in str(body)
        compliance_review = body["complianceReview"]
        if compliance_review is not None:
            assert "appliedRuleIds" in compliance_review
    finally:
        app.dependency_overrides.clear()
