import pytest

from financehub_market_api.recommendation.product_knowledge.schemas import ProductEvidenceBundle
from financehub_market_api.recommendation.product_knowledge.service import (
    ProductKnowledgeRetrievalService,
    build_product_knowledge_retrieval_service_from_env,
)
import financehub_market_api.recommendation.product_knowledge.service as product_knowledge_service_module


class _FakeEmbeddingClient:
    def embed_query(self, text: str) -> list[float]:
        assert text
        return [0.1, 0.2, 0.3]


class _FakeKnowledgeStore:
    def search(
        self,
        *,
        query_vector: list[float],
        product_ids: list[str],
        include_internal: bool,
        limit_per_product: int,
        total_limit: int,
    ) -> list[dict[str, object]]:
        del query_vector, limit_per_product, total_limit
        hits = [
            {
                "evidence_id": "fund-001-public-1",
                "product_id": "fund-001",
                "score": 0.91,
                "snippet": "Fund allocates mostly to high-grade credit bonds.",
                "source_title": "Fund Prospectus",
                "source_uri": "https://example.test/fund-001.pdf",
                "doc_type": "prospectus",
                "source_type": "public_official",
                "visibility": "public",
                "user_displayable": True,
                "as_of_date": "2026-04-12",
                "page_number": 18,
                "section_title": "Investment Scope",
                "language": "en",
            },
            {
                "evidence_id": "fund-001-internal-1",
                "product_id": "fund-001",
                "score": 0.88,
                "snippet": "Internal fit note: suitable as conservative core holding.",
                "source_title": "Advisor Internal Note",
                "source_uri": None,
                "doc_type": "advisor_note",
                "source_type": "internal_curated",
                "visibility": "internal",
                "user_displayable": False,
                "as_of_date": "2026-04-12",
                "page_number": None,
                "section_title": None,
                "language": "en",
            },
        ]
        if not include_internal:
            hits = [hit for hit in hits if hit["visibility"] == "public"]
        return [hit for hit in hits if hit["product_id"] in product_ids]


def test_retrieve_evidence_groups_hits_per_product_and_keeps_internal_hits() -> None:
    service = ProductKnowledgeRetrievalService(
        embedding_client=_FakeEmbeddingClient(),
        knowledge_store=_FakeKnowledgeStore(),
    )

    bundles = service.retrieve_evidence(
        query_text="conservative wealth bond",
        product_ids=["fund-001"],
        include_internal=True,
    )

    assert bundles == [
        ProductEvidenceBundle(
            product_id="fund-001",
            evidences=[
                {
                    "evidence_id": "fund-001-public-1",
                    "product_id": "fund-001",
                    "score": 0.91,
                    "snippet": "Fund allocates mostly to high-grade credit bonds.",
                    "source_title": "Fund Prospectus",
                    "source_uri": "https://example.test/fund-001.pdf",
                    "doc_type": "prospectus",
                    "source_type": "public_official",
                    "visibility": "public",
                    "user_displayable": True,
                    "as_of_date": "2026-04-12",
                    "page_number": 18,
                    "section_title": "Investment Scope",
                    "language": "en",
                },
                {
                    "evidence_id": "fund-001-internal-1",
                    "product_id": "fund-001",
                    "score": 0.88,
                    "snippet": "Internal fit note: suitable as conservative core holding.",
                    "source_title": "Advisor Internal Note",
                    "source_uri": None,
                    "doc_type": "advisor_note",
                    "source_type": "internal_curated",
                    "visibility": "internal",
                    "user_displayable": False,
                    "as_of_date": "2026-04-12",
                    "page_number": None,
                    "section_title": None,
                    "language": "en",
                },
            ],
        )
    ]


def test_retrieve_evidence_only_returns_public_hits_when_include_internal_disabled() -> None:
    service = ProductKnowledgeRetrievalService(
        embedding_client=_FakeEmbeddingClient(),
        knowledge_store=_FakeKnowledgeStore(),
    )

    bundles = service.retrieve_evidence(
        query_text="conservative wealth bond",
        product_ids=["fund-001"],
        include_internal=False,
    )

    assert len(bundles) == 1
    assert len(bundles[0].evidences) == 1
    assert bundles[0].evidences[0].visibility == "public"


def test_retrieve_evidence_returns_empty_for_empty_product_ids() -> None:
    service = ProductKnowledgeRetrievalService(
        embedding_client=_FakeEmbeddingClient(),
        knowledge_store=_FakeKnowledgeStore(),
    )

    bundles = service.retrieve_evidence(
        query_text="conservative wealth bond",
        product_ids=[],
        include_internal=True,
    )

    assert bundles == []


def test_retrieve_evidence_groups_multiple_products_with_per_product_caps() -> None:
    class _MultiProductKnowledgeStore:
        def search(
            self,
            *,
            query_vector: list[float],
            product_ids: list[str],
            include_internal: bool,
            limit_per_product: int,
            total_limit: int,
        ) -> list[dict[str, object]]:
            del query_vector, include_internal, limit_per_product, total_limit
            hits = [
                {
                    "evidence_id": "fund-001-public-1",
                    "product_id": "fund-001",
                    "score": 0.99,
                    "snippet": "Fund 001 evidence #1",
                    "source_title": "Fund 001 Prospectus",
                    "source_uri": "https://example.test/fund-001.pdf",
                    "doc_type": "prospectus",
                    "source_type": "public_official",
                    "visibility": "public",
                    "user_displayable": True,
                    "as_of_date": "2026-04-12",
                    "page_number": 8,
                    "section_title": "Overview",
                    "language": "en",
                },
                {
                    "evidence_id": "fund-001-public-2",
                    "product_id": "fund-001",
                    "score": 0.98,
                    "snippet": "Fund 001 evidence #2",
                    "source_title": "Fund 001 Monthly Report",
                    "source_uri": "https://example.test/fund-001-monthly.pdf",
                    "doc_type": "report",
                    "source_type": "public_official",
                    "visibility": "public",
                    "user_displayable": True,
                    "as_of_date": "2026-04-12",
                    "page_number": 3,
                    "section_title": "Positioning",
                    "language": "en",
                },
                {
                    "evidence_id": "fund-002-public-1",
                    "product_id": "fund-002",
                    "score": 0.97,
                    "snippet": "Fund 002 evidence #1",
                    "source_title": "Fund 002 Prospectus",
                    "source_uri": "https://example.test/fund-002.pdf",
                    "doc_type": "prospectus",
                    "source_type": "public_official",
                    "visibility": "public",
                    "user_displayable": True,
                    "as_of_date": "2026-04-12",
                    "page_number": 11,
                    "section_title": "Overview",
                    "language": "en",
                },
            ]
            return [hit for hit in hits if hit["product_id"] in product_ids]

    service = ProductKnowledgeRetrievalService(
        embedding_client=_FakeEmbeddingClient(),
        knowledge_store=_MultiProductKnowledgeStore(),
    )

    bundles = service.retrieve_evidence(
        query_text="balanced allocation",
        product_ids=["fund-001", "fund-002"],
        include_internal=True,
        limit_per_product=1,
        total_limit=10,
    )

    assert [bundle.product_id for bundle in bundles] == ["fund-001", "fund-002"]
    assert [evidence.evidence_id for evidence in bundles[0].evidences] == [
        "fund-001-public-1"
    ]
    assert [evidence.evidence_id for evidence in bundles[1].evidences] == [
        "fund-002-public-1"
    ]


def test_build_product_knowledge_retrieval_service_from_env_returns_none_when_required_env_missing() -> None:
    assert build_product_knowledge_retrieval_service_from_env(env={}) is None
    assert (
        build_product_knowledge_retrieval_service_from_env(
            env={
                "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_URL": " ",
                "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_COLLECTION": "product_knowledge",
                "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY": "sk-test",
            }
        )
        is None
    )


def test_build_product_knowledge_retrieval_service_from_env_supports_openai_key_fallback() -> None:
    from financehub_market_api.recommendation.product_knowledge.embedding_client import (
        OpenAIEmbeddingClient,
    )
    from financehub_market_api.recommendation.product_knowledge.qdrant_store import (
        QdrantProductKnowledgeStore,
    )

    service = build_product_knowledge_retrieval_service_from_env(
        env={
            "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_URL": "https://qdrant.internal",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_API_KEY": "qdrant-key",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_COLLECTION": "financehub_product_knowledge",
            "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY": "fallback-openai-key",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_BASE_URL": "https://openai.internal/v1",
            "FINANCEHUB_PRODUCT_KNOWLEDGE_EMBEDDING_MODEL": "text-embedding-3-large",
        }
    )

    assert isinstance(service, ProductKnowledgeRetrievalService)
    assert isinstance(service._embedding_client, OpenAIEmbeddingClient)
    assert service._embedding_client._api_key == "fallback-openai-key"
    assert service._embedding_client._base_url == "https://openai.internal/v1"
    assert service._embedding_client._model_name == "text-embedding-3-large"
    assert isinstance(service._knowledge_store, QdrantProductKnowledgeStore)
    assert service._knowledge_store._base_url == "https://qdrant.internal"
    assert (
        service._knowledge_store._collection_name
        == "financehub_product_knowledge"
    )
    assert service._knowledge_store._api_key == "qdrant-key"


def test_build_product_knowledge_retrieval_service_from_env_reads_env_local_file(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from financehub_market_api.recommendation.product_knowledge.embedding_client import (
        OpenAIEmbeddingClient,
    )
    from financehub_market_api.recommendation.product_knowledge.qdrant_store import (
        QdrantProductKnowledgeStore,
    )

    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_URL=https://qdrant.from-file",
                "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_COLLECTION=file_collection",
                "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY=file-openai-key",
                "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_BASE_URL=http://127.0.0.1:11434/v1",
                "FINANCEHUB_PRODUCT_KNOWLEDGE_EMBEDDING_MODEL=bge-m3",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        product_knowledge_service_module,
        "_iter_env_file_candidates",
        lambda: [env_file],
    )
    for key in (
        "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_URL",
        "FINANCEHUB_PRODUCT_KNOWLEDGE_QDRANT_COLLECTION",
        "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_API_KEY",
        "FINANCEHUB_PRODUCT_KNOWLEDGE_OPENAI_BASE_URL",
        "FINANCEHUB_PRODUCT_KNOWLEDGE_EMBEDDING_MODEL",
        "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    service = build_product_knowledge_retrieval_service_from_env()

    assert isinstance(service, ProductKnowledgeRetrievalService)
    assert isinstance(service._embedding_client, OpenAIEmbeddingClient)
    assert service._embedding_client._api_key == "file-openai-key"
    assert service._embedding_client._base_url == "http://127.0.0.1:11434/v1"
    assert service._embedding_client._model_name == "bge-m3"
    assert isinstance(service._knowledge_store, QdrantProductKnowledgeStore)
    assert service._knowledge_store._base_url == "https://qdrant.from-file"
    assert service._knowledge_store._collection_name == "file_collection"


def test_product_knowledge_service_module_does_not_expose_api_projection_helper() -> None:
    assert not hasattr(product_knowledge_service_module, "project_public_evidence_references")
