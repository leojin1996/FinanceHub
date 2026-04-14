from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol, TypedDict
from uuid import uuid4

from pydantic import BaseModel, Field

from financehub_market_api.models import (
    AgentTraceEvent,
    AgentTraceToolCall,
    MarketEvidenceItem,
    RecommendationGenerationRequest,
    RecommendationWarning,
)
from financehub_market_api.recommendation.compliance_knowledge import (
    ComplianceEvidenceBundle,
)
from financehub_market_api.recommendation.product_knowledge import ProductEvidenceBundle


class RequestContext(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    user_intent_text: str | None = None
    user_id: str | None = None
    payload: RecommendationGenerationRequest


class _TraceToolCall(Protocol):
    tool_name: str
    arguments: Mapping[str, object]
    result: Mapping[str, object]


class UserIntelligence(BaseModel):
    risk_tier: str
    liquidity_preference: str
    investment_horizon: str
    return_objective: str
    drawdown_sensitivity: str
    profile_summary_zh: str
    profile_summary_en: str
    derived_signals: list[str] = Field(default_factory=list)


class AgentProfileFocusState(BaseModel):
    profile_focus_zh: str
    profile_focus_en: str


class AgentMarketSummaryState(BaseModel):
    summary_zh: str
    summary_en: str


class MarketIntelligenceState(BaseModel):
    sentiment: str
    stance: str
    preferred_categories: list[str] = Field(default_factory=list)
    avoided_categories: list[str] = Field(default_factory=list)
    summary_zh: str
    summary_en: str
    evidence: list[MarketEvidenceItem] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ProductStrategy(BaseModel):
    recommended_categories: list[str] = Field(default_factory=list)
    ranking_rationale_zh: str = ""
    ranking_rationale_en: str = ""


class RuntimeCandidateSnapshot(BaseModel):
    id: str
    category: str
    code: str | None = None
    liquidity: str | None = None
    lockup_days: int | None = None
    max_drawdown_percent: float | None = None
    as_of_date: str | None = None
    detail_route: str | None = None
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
    product_evidences: list[ProductEvidenceBundle] = Field(default_factory=list)
    filtered_out_reasons: list[str] = Field(default_factory=list)


class ComplianceRetrievalContext(BaseModel):
    evidences: list[ComplianceEvidenceBundle] = Field(default_factory=list)


class ComplianceReviewState(BaseModel):
    verdict: Literal["approve", "revise_conservative", "block"]
    reason_zh: str
    reason_en: str
    disclosures_zh: list[str] = Field(default_factory=list)
    disclosures_en: list[str] = Field(default_factory=list)
    suitability_notes_zh: list[str] = Field(default_factory=list)
    suitability_notes_en: list[str] = Field(default_factory=list)
    applied_rule_ids: list[str] = Field(default_factory=list)
    blocking_reason_codes: list[str] = Field(default_factory=list)


class FinalResponseState(BaseModel):
    recommendation_status: Literal["ready", "limited", "blocked"]
    summary_zh: str
    summary_en: str


class ManagerBrief(BaseModel):
    recommendation_status: Literal["ready", "limited", "blocked"]
    summary_zh: str
    summary_en: str
    why_this_plan_zh: list[str] = Field(default_factory=list)
    why_this_plan_en: list[str] = Field(default_factory=list)


class RecommendationGraphState(TypedDict):
    request_context: RequestContext
    user_intelligence: UserIntelligence | None
    agent_profile_focus: AgentProfileFocusState | None
    agent_market_summary: AgentMarketSummaryState | None
    market_intelligence: MarketIntelligenceState | None
    retrieval_context: RetrievalContext | None
    compliance_retrieval: ComplianceRetrievalContext | None
    compliance_review: ComplianceReviewState | None
    final_response: FinalResponseState | None
    product_strategy: ProductStrategy | None
    manager_brief: ManagerBrief | None
    recommendation_draft: dict[str, object] | None
    warnings: list[RecommendationWarning]
    agent_trace: list[AgentTraceEvent]


def build_initial_graph_state(
    payload: RecommendationGenerationRequest,
    *,
    user_id: str | None = None,
) -> RecommendationGraphState:
    return {
        "request_context": RequestContext(
            user_intent_text=payload.userIntentText,
            user_id=user_id,
            payload=payload.model_copy(deep=True),
        ),
        "user_intelligence": None,
        "agent_profile_focus": None,
        "agent_market_summary": None,
        "market_intelligence": None,
        "retrieval_context": None,
        "compliance_retrieval": None,
        "compliance_review": None,
        "final_response": None,
        "product_strategy": None,
        "manager_brief": None,
        "recommendation_draft": None,
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
    tool_calls: Sequence[_TraceToolCall] = (),
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
                toolCalls=[
                    AgentTraceToolCall(
                        toolName=tool_call.tool_name,
                        arguments=_normalize_trace_mapping(tool_call.arguments),
                        result=_normalize_trace_mapping(tool_call.result),
                    )
                    for tool_call in tool_calls
                ],
            ),
        ],
    }


def _normalize_trace_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _normalize_trace_value(item) for key, item in value.items()}


def _normalize_trace_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _normalize_trace_mapping(value)
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_normalize_trace_value(item) for item in value]
    return value
