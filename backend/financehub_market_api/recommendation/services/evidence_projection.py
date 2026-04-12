from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from financehub_market_api.models import RecommendationEvidenceReference
from financehub_market_api.recommendation.product_knowledge.schemas import (
    RetrievedProductEvidence,
)

_PLACEHOLDER_HOSTNAMES = (
    "example.com",
    "example.org",
    "example.net",
    "example.edu",
    "localhost",
)
_PLACEHOLDER_TLDS = {"example", "invalid", "localhost", "test"}


def _public_source_uri_or_none(source_uri: str | None) -> str | None:
    if not source_uri:
        return None

    parsed = urlparse(source_uri)
    if parsed.scheme not in {"http", "https"}:
        return None
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return None
    if any(hostname == value or hostname.endswith(f".{value}") for value in _PLACEHOLDER_HOSTNAMES):
        return None
    if hostname.rsplit(".", maxsplit=1)[-1] in _PLACEHOLDER_TLDS:
        return None
    return parsed.geturl()


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
                sourceUri=_public_source_uri_or_none(evidence.source_uri),
            )
        )
        if limit is not None and len(references) >= limit:
            break
    return references
