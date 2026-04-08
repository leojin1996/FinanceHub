from __future__ import annotations

from typing import Literal, TypedDict
from uuid import uuid4

from pydantic import BaseModel, Field

from financehub_market_api.models import (
    AgentTraceEvent,
    MarketEvidenceItem,
    RecommendationGenerationRequest,
    RecommendationWarning,
)


class RequestContext(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    user_intent_text: str | None = None
    payload: RecommendationGenerationRequest


class UserIntelligence(BaseModel):
    risk_tier: str
    liquidity_preference: str
    investment_horizon: str
    return_objective: str
    drawdown_sensitivity: str
    profile_summary_zh: str
    profile_summary_en: str


class MarketIntelligenceState(BaseModel):
    sentiment: str
    stance: str
    summary_zh: str
    summary_en: str
    evidence: list[MarketEvidenceItem] = Field(default_factory=list)


class RuntimeCandidateSnapshot(BaseModel):
    id: str
    category: str
    code: str | None = None
    liquidity: str | None = None
    name_zh: str
    name_en: str
    rationale_zh: str
    rationale_en: str
    risk_level: str
    tags_zh: list[str] = Field(default_factory=list)
    tags_en: list[str] = Field(default_factory=list)


class RetrievedCandidate(BaseModel):
    product_id: str
    category: str
    score: float
    rationale: str
    runtime_candidate: RuntimeCandidateSnapshot | None = None


class RetrievalContext(BaseModel):
    recalled_memories: list[str] = Field(default_factory=list)
    candidates: list[RetrievedCandidate] = Field(default_factory=list)
    filtered_out_reasons: list[str] = Field(default_factory=list)


class ComplianceReviewState(BaseModel):
    verdict: Literal["approve", "revise_conservative", "block"]
    reason_zh: str
    reason_en: str
    disclosures_zh: list[str] = Field(default_factory=list)
    disclosures_en: list[str] = Field(default_factory=list)


class FinalResponseState(BaseModel):
    recommendation_status: Literal["ready", "limited", "blocked"]
    summary_zh: str
    summary_en: str


class RecommendationGraphState(TypedDict):
    request_context: RequestContext
    user_intelligence: UserIntelligence | None
    market_intelligence: MarketIntelligenceState | None
    retrieval_context: RetrievalContext | None
    compliance_review: ComplianceReviewState | None
    final_response: FinalResponseState | None
    warnings: list[RecommendationWarning]
    agent_trace: list[AgentTraceEvent]


def build_initial_graph_state(payload: RecommendationGenerationRequest) -> RecommendationGraphState:
    return {
        "request_context": RequestContext(
            user_intent_text=payload.userIntentText,
            payload=payload.model_copy(deep=True),
        ),
        "user_intelligence": None,
        "market_intelligence": None,
        "retrieval_context": None,
        "compliance_review": None,
        "final_response": None,
        "warnings": [],
        "agent_trace": [],
    }


def append_warning(
    state: RecommendationGraphState,
    *,
    stage: str,
    code: str,
    message: str,
) -> RecommendationGraphState:
    return {
        **state,
        "warnings": [
            *state["warnings"],
            RecommendationWarning(stage=stage, code=code, message=message),
        ],
    }


def append_agent_trace_event(
    state: RecommendationGraphState,
    *,
    node_name: str,
    request_name: str,
    status: Literal["start", "finish", "error", "transition"],
    provider_name: str | None = None,
    model_name: str | None = None,
    duration_ms: int | None = None,
    request_summary: str | None = None,
    response_summary: str | None = None,
) -> RecommendationGraphState:
    return {
        **state,
        "agent_trace": [
            *state["agent_trace"],
            AgentTraceEvent(
                nodeName=node_name,
                requestName=request_name,
                status=status,
                providerName=provider_name,
                modelName=model_name,
                durationMs=duration_ms,
                requestSummary=request_summary,
                responseSummary=response_summary,
            ),
        ],
    }
