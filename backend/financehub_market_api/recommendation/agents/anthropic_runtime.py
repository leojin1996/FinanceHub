from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeVar

from pydantic import BaseModel, Field, ValidationError, model_validator

from financehub_market_api.recommendation.agents.contracts import (
    ExplanationAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductRankingAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.interfaces import StructuredOutputProvider
from financehub_market_api.recommendation.agents.provider import (
    LLMInvalidResponseError,
    LLMProviderError,
    _build_env_values,
    _is_agent_trace_logging_enabled,
)
from financehub_market_api.recommendation.agents.runtime_context import (
    AgentPromptContext,
    AgentPromptSection,
    AgentToolCallRecord,
    SelectedPlanContext,
)
from financehub_market_api.recommendation.schemas import (
    CandidateProduct,
    MarketContext,
    UserProfile,
)

LOGGER = logging.getLogger(__name__)
UVICORN_ERROR_LOGGER = logging.getLogger("uvicorn.error")

_MAX_TRACE_STRING_LENGTH = 240
_MAX_TRACE_LIST_ITEMS = 8
_MAX_TRACE_OBJECT_KEYS = 16
_MAX_TOOL_CALLS = 2
_ValidatedOutputT = TypeVar("_ValidatedOutputT")


@dataclass(frozen=True)
class _TraceRequestContext:
    trace_enabled: bool
    started_at: float


@dataclass(frozen=True)
class _ToolDefinition:
    name: str
    description: str
    handler: Callable[[dict[str, object]], dict[str, object]]


class _ToolLoopDecision(BaseModel):
    action: Literal["tool_call", "final"]
    tool_name: str | None = None
    tool_arguments: dict[str, object] = Field(default_factory=dict)
    final_payload: dict[str, object] | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> _ToolLoopDecision:
        if self.action == "tool_call":
            if not self.tool_name:
                raise ValueError("tool_name is required when action=tool_call")
            return self
        if self.final_payload is None:
            raise ValueError("final_payload is required when action=final")
        return self


def _trim_trace_value(value: object) -> object:
    if isinstance(value, str):
        if len(value) <= _MAX_TRACE_STRING_LENGTH:
            return value
        return f"{value[:_MAX_TRACE_STRING_LENGTH]}..."

    if isinstance(value, Mapping):
        trimmed: dict[str, object] = {}
        for index, (key, nested_value) in enumerate(value.items()):
            if index >= _MAX_TRACE_OBJECT_KEYS:
                break
            trimmed[str(key)] = _trim_trace_value(nested_value)
        return trimmed

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_trim_trace_value(item) for item in value[:_MAX_TRACE_LIST_ITEMS]]

    return value


def _response_summary(payload: Mapping[str, object]) -> str:
    return json.dumps(_trim_trace_value(payload), ensure_ascii=False, sort_keys=True)


def _emit_trace_log(message: str, *args: object) -> None:
    LOGGER.info(message, *args)
    if not logging.getLogger().handlers:
        UVICORN_ERROR_LOGGER.info(message, *args)


def _render_candidates(candidates: list[CandidateProduct]) -> str:
    lines: list[str] = []
    for candidate in candidates:
        parts = [
            f"id={candidate.id}",
            f"name_zh={candidate.name_zh}",
            f"name_en={candidate.name_en}",
            f"category={candidate.category}",
            f"risk={candidate.risk_level}",
        ]
        if candidate.code is not None:
            parts.append(f"code={candidate.code}")
        if candidate.liquidity is not None:
            parts.append(f"liquidity={candidate.liquidity}")
        if candidate.tags_zh:
            parts.append(f"tags_zh={', '.join(candidate.tags_zh)}")
        if candidate.tags_en:
            parts.append(f"tags_en={', '.join(candidate.tags_en)}")
        parts.append(f"rationale_zh={candidate.rationale_zh}")
        parts.append(f"rationale_en={candidate.rationale_en}")
        lines.append(f"- {'; '.join(parts)}")
    return "\n".join(lines)


def _serialize_mapping(value: Mapping[str, object]) -> str:
    return json.dumps(
        _json_ready(value),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(nested_value) for key, nested_value in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_ready(item) for item in value]
    return value


def _serialize_candidate(candidate: CandidateProduct) -> dict[str, object]:
    return {
        "id": candidate.id,
        "category": candidate.category,
        "code": candidate.code,
        "liquidity": candidate.liquidity,
        "name_zh": candidate.name_zh,
        "name_en": candidate.name_en,
        "rationale_zh": candidate.rationale_zh,
        "rationale_en": candidate.rationale_en,
        "risk_level": candidate.risk_level,
        "tags_zh": list(candidate.tags_zh),
        "tags_en": list(candidate.tags_en),
    }


def _combine_prompt_context(
    default_context: AgentPromptContext,
    prompt_context: AgentPromptContext | None,
) -> AgentPromptContext:
    if prompt_context is None:
        return default_context

    merged_sections = (*default_context.sections, *prompt_context.sections)
    merged_instructions = (*default_context.instructions, *prompt_context.instructions)
    return AgentPromptContext(
        task=prompt_context.task.strip() or default_context.task,
        sections=merged_sections,
        instructions=merged_instructions,
    )


def _build_tool_descriptions(tool_definitions: Mapping[str, _ToolDefinition]) -> tuple[str, ...]:
    return tuple(
        f"{tool.name}: {tool.description}" for tool in tool_definitions.values()
    )


class _BaseStructuredOutputAgent:
    def __init__(
        self,
        provider: StructuredOutputProvider,
        model_name: str,
        request_timeout_seconds: float,
        request_name: str,
        trace_logs_enabled: bool | None = None,
    ) -> None:
        self._provider = provider
        self._model_name = model_name
        self._request_timeout_seconds = request_timeout_seconds
        self._request_name = request_name
        if trace_logs_enabled is None:
            trace_logs_enabled = _is_agent_trace_logging_enabled(_build_env_values())
        self._trace_logs_enabled = trace_logs_enabled

    def _execute(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> tuple[dict[str, object], _TraceRequestContext]:
        trace_context = _TraceRequestContext(
            trace_enabled=self._trace_logs_enabled,
            started_at=time.perf_counter(),
        )
        if trace_context.trace_enabled:
            _emit_trace_log(
                "agent_request_start request_name=%s model_name=%s",
                self._request_name,
                self._model_name,
            )
        try:
            payload = self._provider.chat_json(
                model_name=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_schema=response_schema,
                timeout_seconds=self._request_timeout_seconds,
                request_name=self._request_name,
            )
        except LLMInvalidResponseError:
            raise
        except Exception as exc:  # noqa: BLE001
            wrapped_error = LLMProviderError(f"structured-output provider request failed: {exc}")
            self._log_trace_error(trace_context, wrapped_error)
            raise wrapped_error from exc

        return payload, trace_context

    def _validate_without_finish(
        self,
        payload: dict[str, object],
        trace_context: _TraceRequestContext,
        validator: Callable[[dict[str, object]], _ValidatedOutputT],
    ) -> _ValidatedOutputT:
        try:
            return validator(payload)
        except ValidationError as exc:
            self._log_trace_error(trace_context, exc)
            raise

    def _log_trace_error(self, trace_context: _TraceRequestContext, error: Exception) -> None:
        if not trace_context.trace_enabled:
            return
        duration_ms = int((time.perf_counter() - trace_context.started_at) * 1000)
        _emit_trace_log(
            "agent_request_error request_name=%s model_name=%s duration_ms=%s "
            "error_type=%s error_message=%s",
            self._request_name,
            self._model_name,
            duration_ms,
            type(error).__name__,
            json.dumps(str(error), ensure_ascii=False),
        )

    def _log_trace_finish(
        self,
        trace_context: _TraceRequestContext,
        payload: Mapping[str, object],
    ) -> None:
        if not trace_context.trace_enabled:
            return
        duration_ms = int((time.perf_counter() - trace_context.started_at) * 1000)
        _emit_trace_log(
            "agent_request_finish request_name=%s model_name=%s duration_ms=%s response_summary=%s",
            self._request_name,
            self._model_name,
            duration_ms,
            _response_summary(payload),
        )

    def _tool_error(
        self,
        trace_context: _TraceRequestContext,
        message: str,
    ) -> RuntimeError:
        error = RuntimeError(message)
        self._log_trace_error(trace_context, error)
        return error

    def _render_tool_history(
        self,
        tool_calls: Sequence[AgentToolCallRecord],
    ) -> str:
        if not tool_calls:
            return ""
        parts = ["Tool outputs so far"]
        for index, tool_call in enumerate(tool_calls, start=1):
            parts.append(
                "\n".join(
                    [
                        f"{index}. {tool_call.tool_name}",
                        f"arguments={_serialize_mapping(tool_call.arguments)}",
                        f"result={_serialize_mapping(tool_call.result)}",
                    ]
                )
            )
        return "\n\n".join(parts)

    def _run_tool_loop(
        self,
        *,
        system_prompt: str,
        prompt_context: AgentPromptContext,
        tool_definitions: Mapping[str, _ToolDefinition],
        output_validator: Callable[[dict[str, object]], _ValidatedOutputT],
    ) -> tuple[_ValidatedOutputT, tuple[AgentToolCallRecord, ...]]:
        tool_calls: list[AgentToolCallRecord] = []
        tool_descriptions = _build_tool_descriptions(tool_definitions)

        for _ in range(_MAX_TOOL_CALLS + 1):
            user_prompt = prompt_context.render_user_prompt(
                tool_descriptions=tool_descriptions
            )
            tool_history = self._render_tool_history(tool_calls)
            if tool_history:
                user_prompt = f"{user_prompt}\n\n{tool_history}"

            payload, trace_context = self._execute(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=_ToolLoopDecision.model_json_schema(),
            )
            try:
                decision = _ToolLoopDecision.model_validate(payload)
            except ValidationError as exc:
                error_message = (
                    "invalid final payload"
                    if payload.get("action") == "final"
                    else "invalid tool request"
                )
                raise self._tool_error(
                    trace_context,
                    error_message,
                ) from exc
            if decision.action == "final":
                final_payload = decision.final_payload
                if final_payload is None:
                    raise self._tool_error(trace_context, "invalid final payload")
                validated_output = self._validate_without_finish(
                    final_payload,
                    trace_context,
                    output_validator,
                )
                self._log_trace_finish(trace_context, final_payload)
                return validated_output, tuple(tool_calls)

            if len(tool_calls) >= _MAX_TOOL_CALLS:
                raise self._tool_error(trace_context, "tool loop exhausted")

            tool_definition = tool_definitions.get(decision.tool_name or "")
            if tool_definition is None:
                raise self._tool_error(
                    trace_context,
                    f"invalid tool request: {decision.tool_name}",
                )

            try:
                result = tool_definition.handler(decision.tool_arguments)
            except (TypeError, ValueError, KeyError) as exc:
                raise self._tool_error(
                    trace_context,
                    f"invalid tool request: {tool_definition.name}",
                ) from exc

            tool_calls.append(
                AgentToolCallRecord(
                    tool_name=tool_definition.name,
                    arguments=dict(decision.tool_arguments),
                    result=result,
                )
            )

        raise self._tool_error(trace_context, "tool loop exhausted")


class UserProfileRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> UserProfileAgentOutput:
        output, _ = self.run_with_trace(user_profile, prompt_context=prompt_context)
        return output

    def run_with_trace(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[UserProfileAgentOutput, tuple[AgentToolCallRecord, ...]]:
        default_context = AgentPromptContext(
            task=(
                "Summarize the investor profile in bilingual focus statements that are "
                "grounded in the provided profile and any richer prompt context."
            ),
            sections=(
                AgentPromptSection(
                    "User profile context",
                    _serialize_mapping(
                        {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                        }
                    ),
                ),
            ),
            instructions=(
                "Use tools before finalizing if they provide useful grounding.",
                "Return concise profile_focus_zh and profile_focus_en strings.",
            ),
        )
        tool_definitions = {
            "get_user_profile_context": _ToolDefinition(
                name="get_user_profile_context",
                description="Return the structured user profile inputs and labels.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {
                        "user_profile": {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                        }
                    },
                ),
            )
        }
        return self._run_tool_loop(
            system_prompt=(
                "You are UserProfileAgent. Use the available tools when you need "
                "grounding. Return only the requested structured decision JSON."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_validator=UserProfileAgentOutput.model_validate,
        )


class MarketIntelligenceRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        fallback_context: MarketContext,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> MarketIntelligenceAgentOutput:
        output, _ = self.run_with_trace(
            user_profile,
            profile_focus,
            fallback_context,
            prompt_context=prompt_context,
        )
        return output

    def run_with_trace(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        fallback_context: MarketContext,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[MarketIntelligenceAgentOutput, tuple[AgentToolCallRecord, ...]]:
        default_context = AgentPromptContext(
            task=(
                "Produce a bilingual market summary for the recommendation workflow "
                "that reflects the investor profile focus and market snapshot."
            ),
            sections=(
                AgentPromptSection(
                    "User profile context",
                    _serialize_mapping(
                        {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                            "profile_focus_zh": profile_focus.profile_focus_zh,
                            "profile_focus_en": profile_focus.profile_focus_en,
                        }
                    ),
                ),
                AgentPromptSection(
                    "Market snapshot context",
                    _serialize_mapping(
                        {
                            "fallback_summary_zh": fallback_context.summary_zh,
                            "fallback_summary_en": fallback_context.summary_en,
                        }
                    ),
                ),
            ),
            instructions=(
                "Use tools before finalizing if more grounded context is needed.",
                "Return summary_zh and summary_en suitable for recommendation copy.",
            ),
        )
        tool_definitions = {
            "get_user_profile_context": _ToolDefinition(
                name="get_user_profile_context",
                description="Return the structured user profile and profile-focus context.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {
                        "user_profile": {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                        },
                        "profile_focus": {
                            "profile_focus_zh": profile_focus.profile_focus_zh,
                            "profile_focus_en": profile_focus.profile_focus_en,
                        },
                    },
                ),
            ),
            "get_market_snapshot": _ToolDefinition(
                name="get_market_snapshot",
                description="Return the current fallback market snapshot.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {
                        "market_snapshot": {
                            "summary_zh": fallback_context.summary_zh,
                            "summary_en": fallback_context.summary_en,
                        }
                    },
                ),
            ),
        }
        return self._run_tool_loop(
            system_prompt=(
                "You are MarketIntelligenceAgent. Use the available tools when you "
                "need grounding. Return only the requested structured decision JSON."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_validator=MarketIntelligenceAgentOutput.model_validate,
        )


class _BaseRankingRuntimeAgent(_BaseStructuredOutputAgent):
    _agent_label = "Ranking"

    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ProductRankingAgentOutput:
        output, _ = self.run_with_trace(
            user_profile,
            profile_focus,
            candidates,
            prompt_context=prompt_context,
        )
        return output

    def run_with_trace(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductRankingAgentOutput, tuple[AgentToolCallRecord, ...]]:
        default_context = AgentPromptContext(
            task=(
                f"Rank the provided {self._agent_label.lower()} candidates for this "
                "investor. Only rank existing IDs and keep the ordering grounded in "
                "risk fit, liquidity, and the provided context."
            ),
            sections=(
                AgentPromptSection(
                    "User profile context",
                    _serialize_mapping(
                        {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                            "profile_focus_zh": profile_focus.profile_focus_zh,
                            "profile_focus_en": profile_focus.profile_focus_en,
                        }
                    ),
                ),
                AgentPromptSection(
                    "Candidate list context",
                    _render_candidates(candidates) or "(empty)",
                ),
            ),
            instructions=(
                "Use tools before finalizing if guardrails or candidate detail is needed.",
                "Return ranked_ids using only existing candidate IDs.",
                "Never return an empty ranked_ids list.",
            ),
        )
        candidate_lookup = {candidate.id: candidate for candidate in candidates}
        tool_definitions = {
            "get_ranking_guardrails": _ToolDefinition(
                name="get_ranking_guardrails",
                description=(
                    "Return valid candidate IDs, original order, and the investor risk profile."
                ),
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {
                        "guardrails": {
                            "risk_profile": user_profile.risk_profile,
                            "candidate_ids": [candidate.id for candidate in candidates],
                            "original_order": [candidate.id for candidate in candidates],
                        }
                    },
                ),
            ),
            "get_candidate_detail": _ToolDefinition(
                name="get_candidate_detail",
                description="Return the full structured detail for a single candidate_id.",
                handler=lambda arguments: {
                    "candidate": _serialize_candidate(
                        _candidate_from_arguments(candidate_lookup, arguments)
                    )
                },
            ),
            "list_candidate_products": _ToolDefinition(
                name="list_candidate_products",
                description="Return the full candidate list as structured objects.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {"candidates": [_serialize_candidate(candidate) for candidate in candidates]},
                ),
            ),
        }
        return self._run_tool_loop(
            system_prompt=(
                f"You are {self._agent_label}SelectionAgent. Use the available tools "
                "when you need grounding. Return only the requested structured decision JSON."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_validator=ProductRankingAgentOutput.model_validate,
        )


class FundSelectionRuntimeAgent(_BaseRankingRuntimeAgent):
    _agent_label = "Fund"


class WealthSelectionRuntimeAgent(_BaseRankingRuntimeAgent):
    _agent_label = "Wealth"


class StockSelectionRuntimeAgent(_BaseRankingRuntimeAgent):
    _agent_label = "Stock"


class ExplanationRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
        selected_plan_context: SelectedPlanContext | None = None,
    ) -> ExplanationAgentOutput:
        output, _ = self.run_with_trace(
            user_profile,
            profile_focus,
            market_context,
            prompt_context=prompt_context,
            selected_plan_context=selected_plan_context,
        )
        return output

    def run_with_trace(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
        selected_plan_context: SelectedPlanContext | None = None,
    ) -> tuple[ExplanationAgentOutput, tuple[AgentToolCallRecord, ...]]:
        sections = [
            AgentPromptSection(
                "User profile context",
                _serialize_mapping(
                    {
                        "risk_profile": user_profile.risk_profile,
                        "label_zh": user_profile.label_zh,
                        "label_en": user_profile.label_en,
                        "profile_focus_zh": profile_focus.profile_focus_zh,
                        "profile_focus_en": profile_focus.profile_focus_en,
                    }
                ),
            ),
            AgentPromptSection(
                "Market summary context",
                _serialize_mapping(
                    {
                        "summary_zh": market_context.summary_zh,
                        "summary_en": market_context.summary_en,
                    }
                ),
            ),
        ]
        if selected_plan_context is not None:
            sections.append(
                AgentPromptSection(
                    "Selected plan context",
                    _serialize_mapping(selected_plan_context.as_dict()),
                )
            )
        default_context = AgentPromptContext(
            task=(
                "Explain why this recommendation plan fits the investor using concise "
                "bilingual bullet points grounded in the selected plan and market context."
            ),
            sections=tuple(sections),
            instructions=(
                "Use tools before finalizing if selected-plan detail is available.",
                "Return why_this_plan_zh and why_this_plan_en as concise bullet lists.",
            ),
        )
        tool_definitions: dict[str, _ToolDefinition] = {
            "get_market_summary_context": _ToolDefinition(
                name="get_market_summary_context",
                description="Return the market summary context used for the explanation.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {
                        "market_summary": {
                            "summary_zh": market_context.summary_zh,
                            "summary_en": market_context.summary_en,
                        }
                    },
                ),
            )
        }
        if selected_plan_context is not None:
            tool_definitions["get_selected_plan"] = _ToolDefinition(
                name="get_selected_plan",
                description="Return the currently selected product IDs by category.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {"selected_plan": selected_plan_context.as_dict()},
                ),
            )
        return self._run_tool_loop(
            system_prompt=(
                "You are ExplanationAgent. Use the available tools when you need "
                "grounding. Return only the requested structured decision JSON."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_validator=ExplanationAgentOutput.model_validate,
        )


def _tool_result_no_args(
    arguments: dict[str, object],
    result: dict[str, object],
) -> dict[str, object]:
    if arguments:
        raise ValueError("tool does not accept arguments")
    return result


def _candidate_from_arguments(
    candidate_lookup: Mapping[str, CandidateProduct],
    arguments: Mapping[str, object],
) -> CandidateProduct:
    unexpected_keys = set(arguments) - {"candidate_id"}
    if unexpected_keys:
        raise ValueError("unexpected tool arguments")
    candidate_id = arguments.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate_id must be a non-empty string")
    candidate = candidate_lookup.get(candidate_id)
    if candidate is None:
        raise KeyError(candidate_id)
    return candidate


__all__ = [
    "ExplanationRuntimeAgent",
    "FundSelectionRuntimeAgent",
    "MarketIntelligenceRuntimeAgent",
    "StockSelectionRuntimeAgent",
    "UserProfileRuntimeAgent",
    "WealthSelectionRuntimeAgent",
]
