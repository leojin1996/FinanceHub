from __future__ import annotations

from financehub_market_api.recommendation.product_knowledge.schemas import (
    RetrievedProductEvidence,
)
from financehub_market_api.recommendation.services.evidence_projection import (
    project_public_evidence_references,
)


def test_project_public_evidence_references_drops_placeholder_example_domain_links() -> None:
    references = project_public_evidence_references(
        [
            RetrievedProductEvidence(
                evidence_id="fund-001-public-1",
                product_id="fund-001",
                score=0.97,
                snippet="基金主要投资高等级信用债，兼顾流动性与回撤控制。",
                source_title="基金招募说明书",
                source_uri="https://example.com/fund-001/prospectus",
                doc_type="prospectus",
                source_type="public_official",
                visibility="public",
                user_displayable=True,
                as_of_date="2026-04-10",
                page_number=12,
                section_title="投资范围",
            )
        ]
    )

    assert len(references) == 1
    assert references[0].sourceUri is None
