from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping, Sequence
from typing import Protocol

LOGGER = logging.getLogger(__name__)

_MAX_TRACE_STRING_LENGTH = 240
_MAX_TRACE_LIST_ITEMS = 8
_MAX_TRACE_OBJECT_KEYS = 16


class _StructuredChatProvider(Protocol):
    def chat_json(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        response_schema: Mapping[str, object],
        timeout_seconds: float,
        request_name: str | None = None,
    ) -> dict[str, object]:
        ...


def _trim_trace_value(value: object) -> object:
    if isinstance(value, str):
        if len(value) <= _MAX_TRACE_STRING_LENGTH:
            return value
        return f"{value[:_MAX_TRACE_STRING_LENGTH]}..."

    if isinstance(value, Mapping):
        trimmed: dict[str, object] = {}
        for index, key in enumerate(value):
            if index >= _MAX_TRACE_OBJECT_KEYS:
                break
            trimmed[str(key)] = _trim_trace_value(value[key])
        return trimmed

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_trim_trace_value(item) for item in value[:_MAX_TRACE_LIST_ITEMS]]

    return value


def summarize_payload(payload: Mapping[str, object]) -> str:
    return json.dumps(_trim_trace_value(payload), ensure_ascii=False, sort_keys=True)


class StructuredAgentExecutor:
    def __init__(
        self,
        *,
        provider: _StructuredChatProvider,
        provider_name: str,
        model_name: str,
        request_name: str,
        timeout_seconds: float,
    ) -> None:
        self._provider = provider
        self._provider_name = provider_name
        self._model_name = model_name
        self._request_name = request_name
        self._timeout_seconds = timeout_seconds

    def run_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, object],
        fallback_action: str = "raise",
    ) -> dict[str, object]:
        started_at = time.monotonic()
        request_summary = summarize_payload(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_schema": dict(response_schema),
            }
        )
        LOGGER.info(
            "agent_request_start request_name=%s provider_name=%s model_name=%s request_summary=%s",
            self._request_name,
            self._provider_name,
            self._model_name,
            request_summary,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            payload = self._provider.chat_json(
                model_name=self._model_name,
                messages=messages,
                response_schema=dict(response_schema),
                timeout_seconds=self._timeout_seconds,
                request_name=self._request_name,
            )
        except Exception as exc:
            duration_ms = round((time.monotonic() - started_at) * 1000.0, 3)
            LOGGER.exception(
                (
                    "agent_request_error request_name=%s provider_name=%s model_name=%s "
                    "duration_ms=%s error_type=%s error_message=%s fallback_action=%s"
                ),
                self._request_name,
                self._provider_name,
                self._model_name,
                duration_ms,
                type(exc).__name__,
                str(exc),
                fallback_action,
            )
            raise

        duration_ms = round((time.monotonic() - started_at) * 1000.0, 3)
        response_summary = summarize_payload(payload)
        LOGGER.info(
            (
                "agent_request_finish request_name=%s provider_name=%s model_name=%s "
                "duration_ms=%s response_summary=%s"
            ),
            self._request_name,
            self._provider_name,
            self._model_name,
            duration_ms,
            response_summary,
        )
        return payload
