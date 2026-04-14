from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from financehub_market_api.auth.dependencies import AuthenticatedUser, get_current_user
from financehub_market_api.main import (
    app,
    get_product_detail_service,
    get_recommendation_service,
)
from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.candidate_pool.schemas import (
    ProductDetailSnapshot,
)
from financehub_market_api.recommendation.graph.runtime import (
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendation.product_knowledge import (
    ProductKnowledgeRetrievalService,
    build_product_knowledge_retrieval_service_from_env,
)
from financehub_market_api.recommendation.services import ProductDetailService
from financehub_market_api.recommendations import RecommendationService

LIVE_PRODUCT_RAG_E2E_ENV = "FINANCEHUB_RUN_PRODUCT_RAG_LIVE_E2E"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_TEST_USER = AuthenticatedUser(
    user_id="product-rag-live-e2e-user",
    email="rag@example.com",
)


class _StaticProductDetailSnapshotCache:
    def __init__(self, snapshot: ProductDetailSnapshot) -> None:
        self._snapshot = snapshot

    def get_product_detail(self, product_id: str) -> ProductDetailSnapshot | None:
        if product_id == self._snapshot.id:
            return self._snapshot
        return None

    def peek_product_detail(self, product_id: str) -> ProductDetailSnapshot | None:
        return self.get_product_detail(product_id)


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


def _build_product_detail_snapshot() -> ProductDetailSnapshot:
    return ProductDetailSnapshot(
        id="fund-001",
        category="fund",
        code="000001",
        provider_name="Public bond fund universe",
        name_zh="中欧稳利债券A",
        name_en="Zhongou Steady Bond A",
        as_of_date="2026-04-12",
        generated_at="2026-04-12T10:00:00+08:00",
        fresh_until="2026-04-13T10:00:00+08:00",
        source="live_product_rag_fixture",
        stale=False,
        risk_level="R2",
        liquidity="T+1",
        tags_zh=["低回撤", "债券底仓"],
        tags_en=["Low drawdown", "Bond core"],
        summary_zh="公开债券基金底仓候选，强调稳健与流动性。",
        summary_en="A public bond fund candidate focused on stability and liquidity.",
        recommendation_rationale_zh="作为稳健债券底仓候选，重点控制回撤。",
        recommendation_rationale_en="Selected as a steady bond core with controlled drawdown.",
        chart_label_zh="近期净值",
        chart_label_en="Recent NAV",
        chart=[],
        yield_metrics={"annualizedReturn": "3.42%"},
        fees={"managementFee": "0.30%"},
        drawdown_or_volatility={"maxDrawdown": "-0.80%"},
        fit_for_profile_zh="适合希望先用债券基金打底的稳健型用户。",
        fit_for_profile_en="Fits users who want a steadier bond-fund core.",
    )


def _build_live_product_detail_service(
    product_knowledge_service: ProductKnowledgeRetrievalService,
) -> ProductDetailService:
    return ProductDetailService(
        cache=_StaticProductDetailSnapshotCache(_build_product_detail_snapshot()),
        product_knowledge_service=product_knowledge_service,
    )


def test_live_product_rag_e2e_returns_public_detail_evidence() -> None:
    if not _enabled(LIVE_PRODUCT_RAG_E2E_ENV):
        pytest.skip(
            f"Set {LIVE_PRODUCT_RAG_E2E_ENV}=true to run live product RAG end-to-end coverage."
        )

    product_knowledge_service = build_product_knowledge_retrieval_service_from_env()
    if product_knowledge_service is None:
        pytest.skip("Live product knowledge env is incomplete for e2e coverage.")

    recommendation_service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services(
            product_knowledge_service=product_knowledge_service,
        )
    )
    product_detail_service = _build_live_product_detail_service(
        product_knowledge_service
    )

    app.dependency_overrides[get_recommendation_service] = lambda: recommendation_service
    app.dependency_overrides[get_product_detail_service] = lambda: product_detail_service
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    client = TestClient(app)

    try:
        recommendation = client.post(
            "/api/recommendations/generate",
            json=_build_generation_request_payload("balanced"),
        )
        assert recommendation.status_code == 200
        first_fund = recommendation.json()["sections"]["funds"]["items"][0]
        assert first_fund["evidencePreview"]
        assert all(
            item["sourceTitle"] != "投顾内部备注"
            for item in first_fund["evidencePreview"]
        )
        assert all(
            "example.com" not in (item.get("sourceUri") or "")
            for item in first_fund["evidencePreview"]
        )

        detail = client.get(f"/api/recommendations/products/{first_fund['id']}")
        assert detail.status_code == 200
        assert detail.json()["evidence"]
        assert all(
            item["sourceTitle"] != "投顾内部备注"
            for item in detail.json()["evidence"]
        )
        assert all(
            "example.com" not in (item.get("sourceUri") or "")
            for item in detail.json()["evidence"]
        )
    finally:
        app.dependency_overrides.clear()
