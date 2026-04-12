from __future__ import annotations

from collections.abc import Iterable

from financehub_market_api.models import RecommendationEvidenceReference
from financehub_market_api.recommendation.product_knowledge.schemas import (
    RetrievedProductEvidence,
)


def project_public_evidence_references(
    evidences: Iterable[RetrievedProductEvidence],
    *,
    limit: int | None = None,
) -> list[RecommendationEvidenceReference]:
    if limit is not None and limit <= 0:
        return []

    references: list[RecommendationEvidenceReference] = []
    for evidence in evidences:
        if evidence.visibility != "public" or not evidence.user_displayable:
            continue
        references.append(
            RecommendationEvidenceReference(
                evidenceId=evidence.evidence_id,
                excerpt=evidence.snippet,
                excerptLanguage=evidence.language,
                sourceTitle=evidence.source_title,
                docType=evidence.doc_type,
                asOfDate=evidence.as_of_date,
                pageNumber=evidence.page_number,
                sectionTitle=evidence.section_title,
                sourceUri=evidence.source_uri,
            )
        )
        if limit is not None and len(references) >= limit:
            break
    return references
