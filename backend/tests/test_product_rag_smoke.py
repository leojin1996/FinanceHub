from __future__ import annotations

import io
import json
from collections import defaultdict
from pathlib import Path

from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.graph.runtime import (
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendation.product_knowledge.service import (
    ProductKnowledgeRetrievalService,
)
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


class _FakeEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return [float(len(text))]


class _FakeQdrantClient:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []

    def collection_exists(self, collection_name: str) -> bool:
        assert collection_name == "financehub_product_knowledge"
        return True

    def upsert(self, *, collection_name: str, points: list[object]) -> None:
        self.upserts.append(
            {
                "collection_name": collection_name,
                "points": points,
            }
        )


def _load_seed_documents() -> list[dict[str, object]]:
    return json.loads(_SEED_DOCUMENTS_PATH.read_text(encoding="utf-8"))


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


def _build_fixture_product_knowledge_service() -> ProductKnowledgeRetrievalService:
    return ProductKnowledgeRetrievalService(
        embedding_client=_FixtureEmbeddingClient(),
        knowledge_store=_FixtureKnowledgeStore(_load_seed_documents()),
    )


def test_product_rag_smoke_returns_public_evidence_preview() -> None:
    service = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_deterministic_services(
            product_knowledge_service=_build_fixture_product_knowledge_service(),
        )
    )

    response = service.generate_recommendation(_build_generation_request("balanced"))

    assert response.sections.funds.items
    first_fund = response.sections.funds.items[0]
    assert first_fund.id == "fund-001"
    assert [reference.sourceTitle for reference in first_fund.evidencePreview] == [
        "基金招募说明书",
    ]
    assert all(
        reference.sourceTitle != "投顾内部备注"
        for reference in first_fund.evidencePreview
    )


def test_seed_product_knowledge_collection_embeds_fixture_documents_and_upserts_points() -> None:
    from scripts.seed_product_knowledge_collection import main

    fake_embedding_client = _FakeEmbeddingClient()
    fake_qdrant_client = _FakeQdrantClient()
    output = io.StringIO()

    exit_code = main(
        [
            "--fixture-path",
            str(_SEED_DOCUMENTS_PATH),
        ],
        env={
            "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_URL": "https://qdrant.example.com",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_COLLECTION": "financehub_product_knowledge",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY": "sk-test-product-knowledge",
        },
        out=output,
        qdrant_client_factory=lambda config: fake_qdrant_client,
        embedding_client_factory=lambda config: fake_embedding_client,
        point_factory=lambda chunk_id, vector, payload: {
            "id": chunk_id,
            "payload": payload,
            "vector": vector,
        },
    )

    assert exit_code == 0
    assert fake_embedding_client.calls
    assert len(fake_qdrant_client.upserts) == 1
    upsert_call = fake_qdrant_client.upserts[0]
    assert upsert_call["collection_name"] == "financehub_product_knowledge"
    assert len(upsert_call["points"]) == len(_load_seed_documents())
    assert "seeded" in output.getvalue()
