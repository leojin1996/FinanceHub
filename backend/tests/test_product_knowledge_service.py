from financehub_market_api.recommendation.product_knowledge.schemas import ProductEvidenceBundle
from financehub_market_api.recommendation.product_knowledge.service import ProductKnowledgeRetrievalService


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
