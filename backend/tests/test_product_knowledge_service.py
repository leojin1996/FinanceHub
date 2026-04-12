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
