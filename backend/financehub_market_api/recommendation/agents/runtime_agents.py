from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar
from uuid import uuid4 as _uuid4

from pydantic import BaseModel, ValidationError

from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    ExplanationAgentOutput,
    ManagerCoordinatorAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
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
    UserProfile,
)

LOGGER = logging.getLogger(__name__)
UVICORN_ERROR_LOGGER = logging.getLogger("uvicorn.error")

_MAX_TRACE_STRING_LENGTH = 240
_MAX_TRACE_LIST_ITEMS = 8
_MAX_TRACE_OBJECT_KEYS = 16
_MAX_TOOL_CALLS = 4
_MAX_VALIDATION_RETRIES = 1
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


_SUBMIT_RESULT_FUNCTION_NAME = "submit_result"


def _build_openai_tools(
    tool_definitions: Mapping[str, _ToolDefinition],
    output_model_class: type[BaseModel],
) -> tuple[list[dict[str, object]], dict[str, Callable[[dict[str, object]], dict[str, object]]]]:
    tools: list[dict[str, object]] = []
    handler_registry: dict[str, Callable[[dict[str, object]], dict[str, object]]] = {}

    for tool_def in tool_definitions.values():
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool_def.name,
                    "description": tool_def.description,
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }
        )
        handler_registry[tool_def.name] = tool_def.handler

    tools.append(
        {
            "type": "function",
            "function": {
                "name": _SUBMIT_RESULT_FUNCTION_NAME,
                "description": "Submit the final structured output for this agent.",
                "parameters": output_model_class.model_json_schema(),
            },
        }
    )

    return tools, handler_registry


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


def _candidate_pool_facts(candidates: list[CandidateProduct]) -> dict[str, object]:
    candidate_ids_by_category: dict[str, list[str]] = {}
    for candidate in candidates:
        candidate_ids_by_category.setdefault(candidate.category, []).append(candidate.id)
    return {
        "candidate_count": len(candidates),
        "candidate_ids": [candidate.id for candidate in candidates],
        "candidate_ids_by_category": candidate_ids_by_category,
        "candidates": [_serialize_candidate(candidate) for candidate in candidates],
    }


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


def _legacy_action_payload_to_tool_response(payload: Mapping[str, object]) -> dict[str, object]:
    if "tool_calls" in payload:
        return dict(payload)

    action = payload.get("action")
    if action == "tool_call":
        tool_name = payload.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise RuntimeError("legacy tool_call payload missing tool_name")
        tool_arguments = payload.get("tool_arguments")
        arguments = tool_arguments if isinstance(tool_arguments, Mapping) else {}
        return _single_tool_call_response(tool_name, arguments)

    if action == "final":
        final_payload = payload.get("final_payload")
        arguments = final_payload if isinstance(final_payload, Mapping) else {}
        return _single_tool_call_response(_SUBMIT_RESULT_FUNCTION_NAME, arguments)

    if action == "return_decision":
        decision = payload.get("decision")
        arguments = (
            decision
            if isinstance(decision, Mapping)
            else {key: value for key, value in payload.items() if key != "action"}
        )
        return _single_tool_call_response(_SUBMIT_RESULT_FUNCTION_NAME, arguments)

    return _single_tool_call_response(_SUBMIT_RESULT_FUNCTION_NAME, payload)


def _single_tool_call_response(
    function_name: str,
    arguments: Mapping[str, object],
) -> dict[str, object]:
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": f"call_{_uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": json.dumps(_json_ready(arguments), ensure_ascii=False),
                },
            }
        ],
    }


def _legacy_chat_json_messages(
    messages: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    system_content = ""
    user_content = ""
    tool_names_by_id: dict[str, str] = {}
    tool_outputs: list[str] = []
    validation_errors: list[str] = []

    for message in messages:
        role = message.get("role")
        if role == "system" and not system_content:
            system_content = str(message.get("content") or "")
            continue
        if role == "user" and not user_content:
            user_content = str(message.get("content") or "")
            continue
        if role == "assistant":
            raw_tool_calls = message.get("tool_calls")
            if isinstance(raw_tool_calls, Sequence) and not isinstance(
                raw_tool_calls,
                (str, bytes, bytearray),
            ):
                for raw_tool_call in raw_tool_calls:
                    if not isinstance(raw_tool_call, Mapping):
                        continue
                    tool_call_id = raw_tool_call.get("id")
                    function_info = raw_tool_call.get("function")
                    if not isinstance(tool_call_id, str) or not isinstance(
                        function_info,
                        Mapping,
                    ):
                        continue
                    function_name = function_info.get("name")
                    if isinstance(function_name, str):
                        tool_names_by_id[tool_call_id] = function_name
            continue
        if role == "tool":
            content = str(message.get("content") or "")
            if content.startswith("Validation error:"):
                validation_errors.append(content)
                continue
            tool_call_id = message.get("tool_call_id")
            tool_name = (
                tool_names_by_id.get(tool_call_id)
                if isinstance(tool_call_id, str)
                else None
            ) or "unknown_tool"
            tool_outputs.append(f"{len(tool_outputs) + 1}. {tool_name}\n{content}")

    parts = [user_content]
    if tool_outputs:
        parts.append("Tool outputs so far\n" + "\n\n".join(tool_outputs))
    if validation_errors:
        parts.append(
            "Previous response was invalid\n"
            + "\n".join(validation_errors)
            + "\nCandidate pool is not empty. Valid supplied candidate ids are listed in Candidate pool facts."
        )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "\n\n".join(part for part in parts if part)},
    ]


def _serialize_candidate(candidate: CandidateProduct) -> dict[str, object]:
    return {
        "id": candidate.id,
        "category": candidate.category,
        "code": candidate.code,
        "liquidity": candidate.liquidity,
        "lockup_days": candidate.lockup_days,
        "max_drawdown_percent": candidate.max_drawdown_percent,
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

    def _run_tool_loop(
        self,
        *,
        system_prompt: str,
        prompt_context: AgentPromptContext,
        tool_definitions: Mapping[str, _ToolDefinition],
        output_model_class: type[BaseModel],
        output_validator: Callable[[dict[str, object]], _ValidatedOutputT],
        prefilled_tool_calls: Sequence[AgentToolCallRecord] = (),
    ) -> tuple[_ValidatedOutputT, tuple[AgentToolCallRecord, ...]]:
        openai_tools, handler_registry = _build_openai_tools(tool_definitions, output_model_class)
        tool_call_records: list[AgentToolCallRecord] = []
        validation_retries = 0

        user_prompt = prompt_context.render_user_prompt()
        messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for record in prefilled_tool_calls:
            fake_id = f"call_{_uuid4().hex[:12]}"
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": fake_id,
                            "type": "function",
                            "function": {
                                "name": record.tool_name,
                                "arguments": json.dumps(
                                    _json_ready(record.arguments), ensure_ascii=False
                                ),
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": fake_id,
                    "content": json.dumps(
                        _json_ready(record.result), ensure_ascii=False
                    ),
                }
            )

        for _ in range(_MAX_TOOL_CALLS + _MAX_VALIDATION_RETRIES + 1):
            response = self._request_tool_response(
                messages=messages,
                tools=openai_tools,
                output_model_class=output_model_class,
            )

            raw_tool_calls = response.get("tool_calls")
            if not raw_tool_calls:
                raise RuntimeError(
                    f"[{self._request_name}] model stopped without calling submit_result"
                )

            assistant_message = dict(response)
            messages.append(assistant_message)

            for tc in raw_tool_calls:
                function_info = tc["function"]
                fn_name = function_info["name"]
                fn_args_raw = function_info["arguments"]
                fn_args = (
                    json.loads(fn_args_raw)
                    if isinstance(fn_args_raw, str)
                    else fn_args_raw
                )
                tc_id = tc["id"]

                if fn_name == _SUBMIT_RESULT_FUNCTION_NAME:
                    try:
                        validated_output = output_validator(fn_args)
                    except ValidationError as exc:
                        if validation_retries < _MAX_VALIDATION_RETRIES:
                            validation_retries += 1
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": (
                                        f"Validation error: {exc}. "
                                        "Please correct and call submit_result again."
                                    ),
                                }
                            )
                            break
                        raise RuntimeError(
                            f"[{self._request_name}] submit_result validation failed after retries"
                        ) from exc
                    return validated_output, tuple(tool_call_records)

                handler = handler_registry.get(fn_name)
                if handler is None:
                    raise RuntimeError(
                        f"[{self._request_name}] invalid tool request: {fn_name}"
                    )

                if len(tool_call_records) >= _MAX_TOOL_CALLS:
                    raise RuntimeError(
                        f"[{self._request_name}] tool loop exhausted"
                    )

                try:
                    result = handler(fn_args)
                except (TypeError, ValueError, KeyError) as exc:
                    raise RuntimeError(
                        f"[{self._request_name}] invalid tool request: {fn_name}"
                    ) from exc

                tool_call_records.append(
                    AgentToolCallRecord(
                        tool_name=fn_name,
                        arguments=fn_args,
                        result=result,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(
                            result, ensure_ascii=False, default=str
                        ),
                    }
                )

        raise RuntimeError(f"[{self._request_name}] tool loop exhausted")

    def _request_tool_response(
        self,
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        output_model_class: type[BaseModel],
    ) -> dict[str, object]:
        chat_with_tools = getattr(self._provider, "chat_with_tools", None)
        if callable(chat_with_tools):
            return chat_with_tools(
                model_name=self._model_name,
                messages=messages,
                tools=tools,
                timeout_seconds=self._request_timeout_seconds,
                request_name=self._request_name,
            )

        payload = self._provider.chat_json(
            model_name=self._model_name,
            messages=_legacy_chat_json_messages(messages),  # type: ignore[arg-type]
            response_schema=output_model_class.model_json_schema(),
            timeout_seconds=self._request_timeout_seconds,
            request_name=self._request_name,
        )
        return _legacy_action_payload_to_tool_response(payload)


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
                "\nWhen you have gathered enough information, call submit_result with the final structured output."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_model_class=UserProfileAgentOutput,
            output_validator=UserProfileAgentOutput.model_validate,
        )


class MarketIntelligenceRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_facts: dict[str, object],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> MarketIntelligenceAgentOutput:
        output, _ = self.run_with_trace(
            user_profile,
            user_profile_insights,
            market_facts,
            prompt_context=prompt_context,
        )
        return output

    def run_with_trace(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_facts: dict[str, object],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[MarketIntelligenceAgentOutput, tuple[AgentToolCallRecord, ...]]:
        default_context = AgentPromptContext(
            task=(
                "Produce a structured market intelligence output for the recommendation "
                "workflow. Decide sentiment, stance, preferred categories, avoided "
                "categories, bilingual summaries, and evidence references."
            ),
            sections=(
                AgentPromptSection(
                    "User profile insights",
                    _serialize_mapping(
                        {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                            "user_profile_insights": user_profile_insights.model_dump(
                                mode="json"
                            ),
                        }
                    ),
                ),
                AgentPromptSection(
                    "Market facts",
                    _serialize_mapping(market_facts),
                ),
            ),
            instructions=(
                "Use tools before finalizing if more grounded market facts are needed.",
                "Decide sentiment and stance from the supplied facts rather than copying any upstream label.",
                "Return evidence_refs using only source keys that are present in the supplied facts.",
            ),
        )
        tool_definitions = {
            "get_user_profile_context": _ToolDefinition(
                name="get_user_profile_context",
                description="Return the structured user profile and profile insights context.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {
                        "user_profile": {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                        },
                        "user_profile_insights": user_profile_insights.model_dump(
                            mode="json"
                        ),
                    },
                ),
            ),
            "get_market_facts": _ToolDefinition(
                name="get_market_facts",
                description="Return the structured market facts for this request.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {"market_facts": _json_ready(market_facts)},
                ),
            ),
        }
        return self._run_tool_loop(
            system_prompt=(
                "You are MarketIntelligenceAgent. Use the available tools when you "
                "need grounding. Return only the requested structured decision JSON."
                "\nWhen you have gathered enough information, call submit_result with the final structured output."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_model_class=MarketIntelligenceAgentOutput,
            output_validator=MarketIntelligenceAgentOutput.model_validate,
        )


class ProductMatchRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ProductMatchAgentOutput:
        output, _ = self.run_with_trace(
            user_profile,
            user_profile_insights,
            market_intelligence,
            candidates,
            prompt_context=prompt_context,
        )
        return output

    def run_with_trace(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductMatchAgentOutput, tuple[AgentToolCallRecord, ...]]:
        default_context = AgentPromptContext(
            task=(
                "Choose the final recommendation candidates. Return recommended "
                "categories, per-category selected IDs, bilingual ranking rationale, "
                "and filtered-out reasons."
            ),
            sections=(
                AgentPromptSection(
                    "User profile insights",
                    _serialize_mapping(
                        {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                            "user_profile_insights": user_profile_insights.model_dump(
                                mode="json"
                            ),
                        }
                    ),
                ),
                AgentPromptSection(
                    "Market intelligence",
                    _serialize_mapping(
                        {"market_intelligence": market_intelligence.model_dump(mode="json")}
                    ),
                ),
                AgentPromptSection(
                    "Candidate pool facts",
                    _serialize_mapping(_candidate_pool_facts(candidates)),
                ),
                AgentPromptSection(
                    "Candidate list context",
                    _render_candidates(candidates) or "(empty)",
                ),
            ),
            instructions=(
                "Use tools before finalizing if candidate detail or the full candidate list is needed.",
                "The candidate pool facts section is authoritative. If candidate_count > 0, never describe the candidate pool as empty.",
                "Only return IDs that exist in the supplied candidate list.",
                "Choose the final recommendation set; do not ask the caller to filter candidates after you decide.",
                "Return selected_product_ids as the final chosen ids, ranking_rationale_zh and ranking_rationale_en as the bilingual rationale, and filtered_out_reasons as a string list.",
            ),
        )
        candidate_lookup = {candidate.id: candidate for candidate in candidates}
        tool_definitions = {
            "list_candidate_products": _ToolDefinition(
                name="list_candidate_products",
                description="Return the full candidate list as structured objects.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {"candidates": [_serialize_candidate(candidate) for candidate in candidates]},
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
        }
        prefilled_tool_calls = (
            AgentToolCallRecord(
                tool_name="list_candidate_products",
                arguments={},
                result={
                    "candidates": [
                        _serialize_candidate(candidate) for candidate in candidates
                    ]
                },
            ),
        )
        return self._run_tool_loop(
            system_prompt=(
                "You are ProductMatchExpertAgent. Use the available tools when you "
                "need grounding. Return only the requested structured decision JSON."
                "\nWhen you have gathered enough information, call submit_result with the final structured output."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_model_class=ProductMatchAgentOutput,
            output_validator=ProductMatchAgentOutput.model_validate,
            prefilled_tool_calls=prefilled_tool_calls,
        )


class ComplianceReviewRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        selected_candidates: list[CandidateProduct],
        compliance_facts: dict[str, object],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ComplianceReviewAgentOutput:
        output, _ = self.run_with_trace(
            user_profile,
            user_profile_insights,
            selected_candidates,
            compliance_facts,
            prompt_context=prompt_context,
        )
        return output

    def run_with_trace(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        selected_candidates: list[CandidateProduct],
        compliance_facts: dict[str, object],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ComplianceReviewAgentOutput, tuple[AgentToolCallRecord, ...]]:
        default_context = AgentPromptContext(
            task=(
                "Review the selected candidates for suitability and compliance. "
                "Return the verdict, approved and rejected IDs, bilingual reason "
                "summary, disclosures, suitability notes, applied rule IDs, and "
                "blocking reason codes."
            ),
            sections=(
                AgentPromptSection(
                    "User profile insights",
                    _serialize_mapping(
                        {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                            "user_profile_insights": user_profile_insights.model_dump(
                                mode="json"
                            ),
                        }
                    ),
                ),
                AgentPromptSection(
                    "Selected candidates",
                    _render_candidates(selected_candidates) or "(empty)",
                ),
                AgentPromptSection(
                    "Compliance facts",
                    _serialize_mapping(compliance_facts),
                ),
            ),
            instructions=(
                "Use tools before finalizing if candidate or rule facts need grounding.",
                "Return verdict as approve, revise_conservative, or block.",
                "Only use candidate IDs that exist in the supplied selected candidates list.",
                "Return reason_summary_zh and reason_summary_en as concise summaries, approved_ids and rejected_ids as candidate id lists, required_disclosures_zh/en as string lists, and suitability_notes_zh/en as string lists.",
            ),
        )
        candidate_lookup = {candidate.id: candidate for candidate in selected_candidates}
        tool_definitions = {
            "get_selected_candidates": _ToolDefinition(
                name="get_selected_candidates",
                description="Return the selected candidates as structured objects.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {
                        "selected_candidates": [
                            _serialize_candidate(candidate)
                            for candidate in selected_candidates
                        ]
                    },
                ),
            ),
            "get_candidate_detail": _ToolDefinition(
                name="get_candidate_detail",
                description="Return the full structured detail for a single selected candidate_id.",
                handler=lambda arguments: {
                    "candidate": _serialize_candidate(
                        _candidate_from_arguments(candidate_lookup, arguments)
                    )
                },
            ),
            "get_compliance_facts": _ToolDefinition(
                name="get_compliance_facts",
                description="Return the structured compliance facts for this request.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {"compliance_facts": _json_ready(compliance_facts)},
                ),
            ),
        }
        return self._run_tool_loop(
            system_prompt=(
                "You are ComplianceRiskOfficerAgent. Use the available tools when "
                "you need grounding. Return only the requested structured decision JSON."
                "\nWhen you have gathered enough information, call submit_result with the final structured output."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_model_class=ComplianceReviewAgentOutput,
            output_validator=ComplianceReviewAgentOutput.model_validate,
        )


class ManagerCoordinatorRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        product_match: ProductMatchAgentOutput,
        compliance_review: ComplianceReviewAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ManagerCoordinatorAgentOutput:
        output, _ = self.run_with_trace(
            user_profile,
            user_profile_insights,
            market_intelligence,
            product_match,
            compliance_review,
            prompt_context=prompt_context,
        )
        return output

    def run_with_trace(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        product_match: ProductMatchAgentOutput,
        compliance_review: ComplianceReviewAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ManagerCoordinatorAgentOutput, tuple[AgentToolCallRecord, ...]]:
        default_context = AgentPromptContext(
            task=(
                "Coordinate the final user-facing recommendation. Return recommendation "
                "status, bilingual summary, and bilingual why-this-plan bullet lists."
            ),
            sections=(
                AgentPromptSection(
                    "User profile insights",
                    _serialize_mapping(
                        {"user_profile_insights": user_profile_insights.model_dump(mode="json")}
                    ),
                ),
                AgentPromptSection(
                    "Market intelligence",
                    _serialize_mapping(
                        {"market_intelligence": market_intelligence.model_dump(mode="json")}
                    ),
                ),
                AgentPromptSection(
                    "Product match",
                    _serialize_mapping(
                        {"product_match": product_match.model_dump(mode="json")}
                    ),
                ),
                AgentPromptSection(
                    "Compliance review",
                    _serialize_mapping(
                        {"compliance_review": compliance_review.model_dump(mode="json")}
                    ),
                ),
            ),
            instructions=(
                "Use tools before finalizing if context needs to be refreshed.",
                "Do not change the supplied compliance verdict semantics.",
                "Write summary_zh and why_this_plan_zh in Simplified Chinese only.",
                "Do not include English enum values, English category names, or internal system labels in Chinese fields.",
                "Do not mention missing rule snapshots, absent payload fields, or empty historical arrays in user-facing copy.",
                "If holdings or transactions are empty, describe the plan as based mainly on the risk assessment, market information, and selected candidates.",
            ),
        )
        tool_definitions = {
            "get_decision_context": _ToolDefinition(
                name="get_decision_context",
                description="Return the assembled context from upstream agents.",
                handler=lambda arguments: _tool_result_no_args(
                    arguments,
                    {
                        "user_profile": {
                            "risk_profile": user_profile.risk_profile,
                            "label_zh": user_profile.label_zh,
                            "label_en": user_profile.label_en,
                        },
                        "user_profile_insights": user_profile_insights.model_dump(
                            mode="json"
                        ),
                        "market_intelligence": market_intelligence.model_dump(mode="json"),
                        "product_match": product_match.model_dump(mode="json"),
                        "compliance_review": compliance_review.model_dump(mode="json"),
                    },
                ),
            ),
        }
        return self._run_tool_loop(
            system_prompt=(
                "You are ManagerCoordinatorAgent. Use the available tools when you "
                "need grounding. Return only the requested structured decision JSON."
                "\nWhen you have gathered enough information, call submit_result with the final structured output."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_model_class=ManagerCoordinatorAgentOutput,
            output_validator=ManagerCoordinatorAgentOutput.model_validate,
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
                "\nWhen you have gathered enough information, call submit_result with the final structured output."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_model_class=ProductRankingAgentOutput,
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
                "\nWhen you have gathered enough information, call submit_result with the final structured output."
            ),
            prompt_context=_combine_prompt_context(default_context, prompt_context),
            tool_definitions=tool_definitions,
            output_model_class=ExplanationAgentOutput,
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
    "ComplianceReviewRuntimeAgent",
    "ExplanationRuntimeAgent",
    "FundSelectionRuntimeAgent",
    "ManagerCoordinatorRuntimeAgent",
    "MarketIntelligenceRuntimeAgent",
    "ProductMatchRuntimeAgent",
    "StockSelectionRuntimeAgent",
    "UserProfileRuntimeAgent",
    "WealthSelectionRuntimeAgent",
]
