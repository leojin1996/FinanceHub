from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Callable, TypeVar

from pydantic import ValidationError

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
from financehub_market_api.recommendation.schemas import (
    CandidateProduct,
    MarketContext,
    UserProfile,
)

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
UVICORN_ERROR_LOGGER = logging.getLogger("uvicorn.error")

_MAX_TRACE_STRING_LENGTH = 240
_MAX_TRACE_LIST_ITEMS = 8
_MAX_TRACE_OBJECT_KEYS = 16
_ValidatedOutputT = TypeVar("_ValidatedOutputT")


@dataclass(frozen=True)
class _TraceRequestContext:
    trace_enabled: bool
    started_at: float


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

    def _validate_and_log(
        self,
        payload: dict[str, object],
        trace_context: _TraceRequestContext,
        validator: Callable[[dict[str, object]], _ValidatedOutputT],
    ) -> _ValidatedOutputT:
        validated_payload = self._validate_without_finish(payload, trace_context, validator)
        self._log_trace_finish(trace_context, payload)
        return validated_payload

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


class UserProfileRuntimeAgent(_BaseStructuredOutputAgent):
    def run(self, user_profile: UserProfile) -> UserProfileAgentOutput:
        payload, trace_context = self._execute(
            system_prompt="You are UserProfileAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"label_zh={user_profile.label_zh}; label_en={user_profile.label_en}. "
                "Return two concise strings: profile_focus_zh and profile_focus_en."
            ),
            response_schema=UserProfileAgentOutput.model_json_schema(),
        )
        return self._validate_and_log(payload, trace_context, UserProfileAgentOutput.model_validate)


class MarketIntelligenceRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        fallback_context: MarketContext,
    ) -> MarketIntelligenceAgentOutput:
        payload, trace_context = self._execute(
            system_prompt="You are MarketIntelligenceAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}; "
                f"fallback_summary_zh={fallback_context.summary_zh}; fallback_summary_en={fallback_context.summary_en}. "
                "Return summary_zh and summary_en suitable for investment recommendation context."
            ),
            response_schema=MarketIntelligenceAgentOutput.model_json_schema(),
        )
        return self._validate_and_log(
            payload,
            trace_context,
            MarketIntelligenceAgentOutput.model_validate,
        )


class FundSelectionRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> ProductRankingAgentOutput:
        ranking, trace_context, payload = self._run_with_trace(
            user_profile,
            profile_focus,
            candidates,
        )
        self._log_trace_finish(trace_context, payload)
        return ranking

    def _run_with_trace(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> tuple[ProductRankingAgentOutput, _TraceRequestContext, dict[str, object]]:
        payload, trace_context = self._execute(
            system_prompt="You are FundSelectionAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}. "
                f"Candidates:\n{_render_candidates(candidates)}\n"
                "Return ranked_ids as a prioritized list using only existing IDs. "
                "Never return an empty list. "
                "If uncertain, return every candidate ID exactly once in the original order."
            ),
            response_schema=ProductRankingAgentOutput.model_json_schema(),
        )
        ranking = self._validate_without_finish(
            payload,
            trace_context,
            ProductRankingAgentOutput.model_validate,
        )
        return ranking, trace_context, payload


class WealthSelectionRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> ProductRankingAgentOutput:
        ranking, trace_context, payload = self._run_with_trace(
            user_profile,
            profile_focus,
            candidates,
        )
        self._log_trace_finish(trace_context, payload)
        return ranking

    def _run_with_trace(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> tuple[ProductRankingAgentOutput, _TraceRequestContext, dict[str, object]]:
        payload, trace_context = self._execute(
            system_prompt="You are WealthSelectionAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}. "
                f"Candidates:\n{_render_candidates(candidates)}\n"
                "Return ranked_ids as a prioritized list using only existing IDs. "
                "Never return an empty list. "
                "If uncertain, return every candidate ID exactly once in the original order."
            ),
            response_schema=ProductRankingAgentOutput.model_json_schema(),
        )
        ranking = self._validate_without_finish(
            payload,
            trace_context,
            ProductRankingAgentOutput.model_validate,
        )
        return ranking, trace_context, payload


class StockSelectionRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> ProductRankingAgentOutput:
        ranking, trace_context, payload = self._run_with_trace(
            user_profile,
            profile_focus,
            candidates,
        )
        self._log_trace_finish(trace_context, payload)
        return ranking

    def _run_with_trace(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> tuple[ProductRankingAgentOutput, _TraceRequestContext, dict[str, object]]:
        payload, trace_context = self._execute(
            system_prompt="You are StockSelectionAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}. "
                f"Candidates:\n{_render_candidates(candidates)}\n"
                "Return ranked_ids as a prioritized list using only existing IDs. "
                "Never return an empty list. "
                "If uncertain, return every candidate ID exactly once in the original order."
            ),
            response_schema=ProductRankingAgentOutput.model_json_schema(),
        )
        ranking = self._validate_without_finish(
            payload,
            trace_context,
            ProductRankingAgentOutput.model_validate,
        )
        return ranking, trace_context, payload


class ExplanationRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
    ) -> ExplanationAgentOutput:
        payload, trace_context = self._execute(
            system_prompt="You are ExplanationAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}; "
                f"market_summary_zh={market_context.summary_zh}; market_summary_en={market_context.summary_en}. "
                "Return why_this_plan_zh and why_this_plan_en as concise bullet list items."
            ),
            response_schema=ExplanationAgentOutput.model_json_schema(),
        )
        return self._validate_and_log(payload, trace_context, ExplanationAgentOutput.model_validate)


__all__ = [
    "ExplanationRuntimeAgent",
    "FundSelectionRuntimeAgent",
    "MarketIntelligenceRuntimeAgent",
    "StockSelectionRuntimeAgent",
    "UserProfileRuntimeAgent",
    "WealthSelectionRuntimeAgent",
]
