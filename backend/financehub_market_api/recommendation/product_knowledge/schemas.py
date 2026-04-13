from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EvidenceVisibility = Literal["public", "internal"]
EvidenceSourceType = Literal["public_official", "internal_curated"]


class RetrievedProductEvidence(BaseModel):
    evidence_id: str
    product_id: str
    score: float
    snippet: str
    source_title: str
    source_uri: str | None = None
    doc_type: str
    source_type: EvidenceSourceType
    visibility: EvidenceVisibility
    user_displayable: bool
    as_of_date: str | None = None
    page_number: int | None = None
    section_title: str | None = None
    language: str = "zh-CN"


class ProductEvidenceBundle(BaseModel):
    product_id: str
    evidences: list[RetrievedProductEvidence] = Field(default_factory=list)
