from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from fastapi.testclient import TestClient

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
from financehub_market_api.recommendation.product_knowledge.service import (
    ProductKnowledgeRetrievalService,
)
from financehub_market_api.recommendation.services import ProductDetailService
from financehub_market_api.recommendations import RecommendationService

_SEED_DOCUMENTS_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "product_knowledge"
    / "seed_documents.json"
)


class _FixtureEmbeddingClient:
    def embed_query(self, text: str) -> list[float]:
        assert text
        return [0.25, 0.5, 0.75]


class _FixtureKnowledgeStore:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self._documents = documents

    def search(
        self,
        *,
        query_vector: list[float],
        product_ids: list[str],
        include_internal: bool,
        limit_per_product: int,
        total_limit: int,
    ) -> list[dict[str, object]]:
        del query_vector

        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for document in self._documents:
            if document["product_id"] not in product_ids:
                continue
            if not include_internal and document["visibility"] != "public":
                continue
            grouped[str(document["product_id"])].append(document)

        ranked_hits: list[dict[str, object]] = []
        for product_id in product_ids:
            hits = sorted(
                grouped.get(product_id, []),
                key=lambda item: float(item["score"]),
                reverse=True,
            )
            ranked_hits.extend(hits[:limit_per_product])
        return ranked_hits[:total_limit]


class _StaticProductDetailSnapshotCache:
    def __init__(self, snapshot: ProductDetailSnapshot) -> None:
        self._snapshot = snapshot

    def get_product_detail(self, product_id: str) -> ProductDetailSnapshot | None:
        if product_id == self._snapshot.id:
            return self._snapshot
        return None

    def peek_product_detail(self, product_id: str) -> ProductDetailSnapshot | None:
        return self.get_product_detail(product_id)


def _load_seed_documents() -> list[dict[str, object]]:
    return json.loads(_SEED_DOCUMENTS_PATH.read_text(encoding="utf-8"))


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


def _build_fixture_product_knowledge_service() -> ProductKnowledgeRetrievalService:
    return ProductKnowledgeRetrievalService(
        embedding_client=_FixtureEmbeddingClient(),
        knowledge_store=_FixtureKnowledgeStore(_load_seed_documents()),
    )


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
        source="seeded_product_rag_fixture",
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


def test_product_rag_api_e2e_keeps_internal_evidence_hidden() -> None:
    product_knowledge_service = _build_fixture_product_knowledge_service()
    recommendation_service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services(
            product_knowledge_service=product_knowledge_service,
        )
    )
    product_detail_service = ProductDetailService(
        cache=_StaticProductDetailSnapshotCache(_build_product_detail_snapshot()),
        product_knowledge_service=product_knowledge_service,
    )

    app.dependency_overrides[get_recommendation_service] = lambda: recommendation_service
    app.dependency_overrides[get_product_detail_service] = lambda: product_detail_service
    client = TestClient(app)

    try:
        recommendation = client.post(
            "/api/recommendations/generate",
            json=_build_generation_request_payload("balanced"),
        )
        assert recommendation.status_code == 200

        first_fund = recommendation.json()["sections"]["funds"]["items"][0]
        assert first_fund["id"] == "fund-001"
        assert [item["sourceTitle"] for item in first_fund["evidencePreview"]] == [
            "基金招募说明书",
        ]
        assert all(
            item["sourceTitle"] != "投顾内部备注"
            for item in first_fund["evidencePreview"]
        )

        detail = client.get(f"/api/recommendations/products/{first_fund['id']}")
        assert detail.status_code == 200
        assert [item["sourceTitle"] for item in detail.json()["evidence"]] == [
            "基金招募说明书",
            "基金定期报告",
        ]
        assert all(
            item["sourceTitle"] != "投顾内部备注"
            for item in detail.json()["evidence"]
        )
    finally:
        app.dependency_overrides.clear()
