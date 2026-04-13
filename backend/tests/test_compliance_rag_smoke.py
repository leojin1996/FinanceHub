from __future__ import annotations

import io
import json
from pathlib import Path

from financehub_market_api.models import RecommendationGenerationRequest
from financehub_market_api.recommendation.compliance_knowledge.schemas import (
    ComplianceEvidenceBundle,
    RetrievedComplianceEvidence,
)
from financehub_market_api.recommendation.graph.runtime import (
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendations import RecommendationService

_SEED_DOCUMENTS_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "compliance_knowledge"
    / "seed_documents.json"
)


class _FixtureComplianceKnowledgeService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def retrieve_evidence(
        self,
        query,
        *,
        total_limit: int = 12,
    ) -> list[ComplianceEvidenceBundle]:
        self.calls.append(
            {
                "query_text": query.query_text,
                "rule_types": list(query.rule_types),
                "categories": list(query.categories),
                "risk_tiers": list(query.risk_tiers),
                "audience": query.audience,
                "jurisdiction": query.jurisdiction,
                "effective_on": query.effective_on,
                "total_limit": total_limit,
            }
        )
        return [
            ComplianceEvidenceBundle(
                rule_type="suitability",
                evidences=[
                    RetrievedComplianceEvidence(
                        evidence_id="rule-001#1",
                        score=0.94,
                        snippet="销售机构应当将产品风险等级与投资者风险承受能力进行匹配。",
                        source_title="基金销售适当性管理办法",
                        source_uri="https://example.com/rule-001.pdf",
                        doc_type="regulation_pdf",
                        source_type="public_regulation",
                        jurisdiction="CN",
                        rule_id="suitability-risk-tier-match",
                        rule_type="suitability",
                        audience=query.audience or "fund_sales",
                        applies_to_categories=list(query.categories),
                        applies_to_risk_tiers=list(query.risk_tiers),
                        disclosure_type="suitability_warning",
                        effective_date=query.effective_on,
                        section_title="适当性匹配要求",
                        page_number=6,
                    )
                ],
            )
        ]


class _FakeEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return [float(len(text))]


class _FakeQdrantClient:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []
        self.payload_indexes: list[dict[str, object]] = []

    def collection_exists(self, collection_name: str) -> bool:
        assert collection_name == "financehub_compliance_knowledge"
        return True

    def create_payload_index(
        self,
        *,
        collection_name: str,
        field_name: str,
        field_schema: object = None,
        field_type: object = None,
        wait: bool = True,
        ordering: object = None,
        timeout: int | None = None,
        **kwargs: object,
    ) -> None:
        self.payload_indexes.append(
            {
                "collection_name": collection_name,
                "field_name": field_name,
                "field_schema": field_schema,
                "field_type": field_type,
                "wait": wait,
                "ordering": ordering,
                "timeout": timeout,
                "kwargs": kwargs,
            }
        )

    def upsert(self, *, collection_name: str, points: list[object]) -> None:
        self.upserts.append(
            {
                "collection_name": collection_name,
                "points": points,
            }
        )


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


def _load_seed_documents() -> list[dict[str, object]]:
    return json.loads(_SEED_DOCUMENTS_PATH.read_text(encoding="utf-8"))


def test_seed_fixture_uses_non_placeholder_public_rule_links() -> None:
    documents = _load_seed_documents()

    public_uris = [
        str(document["source_uri"])
        for document in documents
        if document.get("source_type") in {"public_regulation", "public_guideline"}
    ]

    assert public_uris
    assert all("example.com" not in uri for uri in public_uris)


def test_compliance_rag_smoke_keeps_compliance_evidence_backend_only() -> None:
    compliance_knowledge_service = _FixtureComplianceKnowledgeService()
    runtime = RecommendationGraphRuntime.with_deterministic_services(
        compliance_knowledge_service=compliance_knowledge_service,
    )

    state = runtime.run(_build_generation_request("balanced"))

    assert state["compliance_retrieval"] is not None
    assert [bundle.rule_type for bundle in state["compliance_retrieval"].evidences] == [
        "suitability"
    ]
    assert compliance_knowledge_service.calls

    response = RecommendationService(graph_runtime=runtime).generate_recommendation(
        _build_generation_request("balanced")
    )

    assert response.reviewStatus in {"pass", "partial_pass"}
    assert "complianceEvidence" not in str(response.model_dump(mode="json", by_alias=True))


def test_seed_compliance_knowledge_collection_embeds_fixture_documents_and_upserts_points() -> None:
    from scripts.seed_compliance_knowledge_collection import main

    fake_embedding_client = _FakeEmbeddingClient()
    fake_qdrant_client = _FakeQdrantClient()
    output = io.StringIO()

    exit_code = main(
        [
            "--fixture-path",
            str(_SEED_DOCUMENTS_PATH),
        ],
        env={
            "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_URL": "https://qdrant.example.com",
            "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_COLLECTION": "financehub_compliance_knowledge",
            "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_API_KEY": "sk-test-compliance-knowledge",
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
    assert upsert_call["collection_name"] == "financehub_compliance_knowledge"
    assert len(upsert_call["points"]) == len(_load_seed_documents())
    assert [index["field_name"] for index in fake_qdrant_client.payload_indexes] == [
        "jurisdiction",
        "audience",
        "rule_type",
        "applies_to_categories",
        "effective_date",
    ]
    assert "seeded" in output.getvalue()
