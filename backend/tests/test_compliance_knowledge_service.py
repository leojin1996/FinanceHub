import pytest

from financehub_market_api.recommendation.compliance_knowledge.schemas import (
    ComplianceEvidenceBundle,
)
from financehub_market_api.recommendation.compliance_knowledge.service import (
    ComplianceKnowledgeQuery,
    ComplianceKnowledgeRetrievalService,
    build_compliance_knowledge_retrieval_service_from_env,
)
import financehub_market_api.recommendation.compliance_knowledge.service as compliance_knowledge_service_module


class _FakeEmbeddingClient:
    def embed_query(self, text: str) -> list[float]:
        assert "适当性" in text
        return [0.1, 0.2, 0.3]


class _FakeComplianceStore:
    def search(
        self,
        *,
        query_vector: list[float],
        query: ComplianceKnowledgeQuery,
        total_limit: int,
    ) -> list[dict[str, object]]:
        del query_vector, total_limit
        hits = [
            {
                "evidence_id": "rule-001#1",
                "score": 0.94,
                "snippet": "销售机构应当将产品风险等级与投资者风险承受能力进行匹配。",
                "source_title": "基金销售适当性管理办法",
                "source_uri": "https://example.test/rule-001.pdf",
                "doc_type": "regulation_pdf",
                "source_type": "public_regulation",
                "jurisdiction": "CN",
                "rule_id": "suitability-risk-tier-match",
                "rule_type": "suitability",
                "audience": "fund_sales",
                "applies_to_categories": ["fund"],
                "applies_to_risk_tiers": ["R1", "R2", "R3", "R4", "R5"],
                "liquidity_requirement": None,
                "lockup_limit_days": None,
                "disclosure_type": "suitability_warning",
                "effective_date": "2025-01-01",
                "section_title": "适当性匹配要求",
                "page_number": 6,
            },
            {
                "evidence_id": "rule-002#1",
                "score": 0.91,
                "snippet": "低风险客户应优先匹配高流动性或短封闭期产品。",
                "source_title": "理财销售风险管理指引",
                "source_uri": "https://example.test/rule-002.pdf",
                "doc_type": "guideline_pdf",
                "source_type": "public_guideline",
                "jurisdiction": "CN",
                "rule_id": "low-risk-liquidity-guardrail",
                "rule_type": "liquidity_guardrail",
                "audience": "wealth_management",
                "applies_to_categories": ["wealth_management"],
                "applies_to_risk_tiers": ["R1", "R2"],
                "liquidity_requirement": "t_plus_1_or_better",
                "lockup_limit_days": 90,
                "disclosure_type": "manual_review_notice",
                "effective_date": "2025-02-01",
                "section_title": "流动性要求",
                "page_number": 4,
            },
        ]
        return [
            hit
            for hit in hits
            if hit["rule_type"] in query.rule_types
            and any(category in query.categories for category in hit["applies_to_categories"])
        ]


def test_retrieve_evidence_groups_hits_by_rule_type() -> None:
    service = ComplianceKnowledgeRetrievalService(
        embedding_client=_FakeEmbeddingClient(),
        knowledge_store=_FakeComplianceStore(),
    )

    bundles = service.retrieve_evidence(
        ComplianceKnowledgeQuery(
            query_text="公募基金 低风险投资者 适当性匹配 风险等级 流动性 封闭期 披露要求",
            rule_types=["suitability", "liquidity_guardrail"],
            categories=["fund"],
            risk_tiers=["R2"],
            audience="fund_sales",
            jurisdiction="CN",
            effective_on="2026-04-13",
        )
    )

    assert bundles == [
        ComplianceEvidenceBundle(
            rule_type="suitability",
            evidences=[
                {
                    "evidence_id": "rule-001#1",
                    "score": 0.94,
                    "snippet": "销售机构应当将产品风险等级与投资者风险承受能力进行匹配。",
                    "source_title": "基金销售适当性管理办法",
                    "source_uri": "https://example.test/rule-001.pdf",
                    "doc_type": "regulation_pdf",
                    "source_type": "public_regulation",
                    "jurisdiction": "CN",
                    "rule_id": "suitability-risk-tier-match",
                    "rule_type": "suitability",
                    "audience": "fund_sales",
                    "applies_to_categories": ["fund"],
                    "applies_to_risk_tiers": ["R1", "R2", "R3", "R4", "R5"],
                    "liquidity_requirement": None,
                    "lockup_limit_days": None,
                    "disclosure_type": "suitability_warning",
                    "effective_date": "2025-01-01",
                    "section_title": "适当性匹配要求",
                    "page_number": 6,
                }
            ],
        )
    ]


def test_retrieve_evidence_returns_empty_for_blank_query_or_rule_types() -> None:
    service = ComplianceKnowledgeRetrievalService(
        embedding_client=_FakeEmbeddingClient(),
        knowledge_store=_FakeComplianceStore(),
    )

    assert (
        service.retrieve_evidence(
            ComplianceKnowledgeQuery(
                query_text="  ",
                rule_types=["suitability"],
                categories=["fund"],
            )
        )
        == []
    )
    assert (
        service.retrieve_evidence(
            ComplianceKnowledgeQuery(
                query_text="适当性 匹配",
                rule_types=[],
                categories=["fund"],
            )
        )
        == []
    )


def test_build_compliance_knowledge_retrieval_service_from_env_returns_none_when_required_env_missing() -> None:
    assert build_compliance_knowledge_retrieval_service_from_env(env={}) is None
    assert (
        build_compliance_knowledge_retrieval_service_from_env(
            env={
                "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_URL": " ",
                "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_COLLECTION": "financehub_compliance_knowledge",
                "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_API_KEY": "sk-test",
            }
        )
        is None
    )


def test_build_compliance_knowledge_retrieval_service_from_env_supports_openai_key_fallback() -> None:
    from financehub_market_api.recommendation.compliance_knowledge.qdrant_store import (
        QdrantComplianceKnowledgeStore,
    )
    from financehub_market_api.recommendation.product_knowledge.embedding_client import (
        OpenAIEmbeddingClient,
    )

    service = build_compliance_knowledge_retrieval_service_from_env(
        env={
            "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_URL": "https://qdrant.internal",
            "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_API_KEY": "qdrant-key",
            "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_COLLECTION": "financehub_compliance_knowledge",
            "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY": "fallback-openai-key",
            "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_BASE_URL": "https://openai.internal/v1",
            "FINANCEHUB_COMPLIANCE_KNOWLEDGE_EMBEDDING_MODEL": "text-embedding-3-large",
        }
    )

    assert isinstance(service, ComplianceKnowledgeRetrievalService)
    assert isinstance(service._embedding_client, OpenAIEmbeddingClient)
    assert service._embedding_client._api_key == "fallback-openai-key"
    assert service._embedding_client._base_url == "https://openai.internal/v1"
    assert service._embedding_client._model_name == "text-embedding-3-large"
    assert isinstance(service._knowledge_store, QdrantComplianceKnowledgeStore)
    assert service._knowledge_store._base_url == "https://qdrant.internal"
    assert (
        service._knowledge_store._collection_name
        == "financehub_compliance_knowledge"
    )
    assert service._knowledge_store._api_key == "qdrant-key"


def test_build_compliance_knowledge_retrieval_service_from_env_reads_env_local_file(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from financehub_market_api.recommendation.compliance_knowledge.qdrant_store import (
        QdrantComplianceKnowledgeStore,
    )
    from financehub_market_api.recommendation.product_knowledge.embedding_client import (
        OpenAIEmbeddingClient,
    )

    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_URL=https://qdrant.from-file",
                "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_COLLECTION=file_collection",
                "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_API_KEY=file-openai-key",
                "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_BASE_URL=http://127.0.0.1:11434/v1",
                "FINANCEHUB_COMPLIANCE_KNOWLEDGE_EMBEDDING_MODEL=bge-m3",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        compliance_knowledge_service_module,
        "_iter_env_file_candidates",
        lambda: [env_file],
    )
    for key in (
        "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_URL",
        "FINANCEHUB_COMPLIANCE_KNOWLEDGE_QDRANT_COLLECTION",
        "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_API_KEY",
        "FINANCEHUB_COMPLIANCE_KNOWLEDGE_OPENAI_BASE_URL",
        "FINANCEHUB_COMPLIANCE_KNOWLEDGE_EMBEDDING_MODEL",
        "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    service = build_compliance_knowledge_retrieval_service_from_env()

    assert isinstance(service, ComplianceKnowledgeRetrievalService)
    assert isinstance(service._embedding_client, OpenAIEmbeddingClient)
    assert service._embedding_client._api_key == "file-openai-key"
    assert service._embedding_client._base_url == "http://127.0.0.1:11434/v1"
    assert service._embedding_client._model_name == "bge-m3"
    assert isinstance(service._knowledge_store, QdrantComplianceKnowledgeStore)
    assert service._knowledge_store._base_url == "https://qdrant.from-file"
    assert service._knowledge_store._collection_name == "file_collection"

