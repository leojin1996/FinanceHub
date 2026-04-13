from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievedComplianceEvidence(BaseModel):
    evidence_id: str
    score: float
    snippet: str
    source_title: str
    source_uri: str | None = None
    doc_type: str
    source_type: str
    jurisdiction: str
    rule_id: str
    rule_type: str
    audience: str
    applies_to_categories: list[str] = Field(default_factory=list)
    applies_to_risk_tiers: list[str] = Field(default_factory=list)
    liquidity_requirement: str | None = None
    lockup_limit_days: int | None = None
    disclosure_type: str | None = None
    effective_date: str | None = None
    section_title: str | None = None
    page_number: int | None = None


class ComplianceEvidenceBundle(BaseModel):
    rule_type: str
    evidences: list[RetrievedComplianceEvidence] = Field(default_factory=list)


class ComplianceKnowledgeQuery(BaseModel):
    query_text: str
    rule_types: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    risk_tiers: list[str] = Field(default_factory=list)
    audience: str | None = None
    jurisdiction: str = "CN"
    effective_on: str | None = None
