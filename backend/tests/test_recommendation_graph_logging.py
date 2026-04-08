import logging
import string
from collections.abc import Mapping
from json import loads

import pytest

from financehub_market_api.recommendation.llm_runtime import StructuredAgentExecutor, summarize_payload


class _FakeProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def chat_json(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        response_schema: Mapping[str, object],
        timeout_seconds: float,
        request_name: str | None = None,
    ) -> dict[str, object]:
        return self._payload


class _ExplodingProvider:
    def chat_json(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        response_schema: Mapping[str, object],
        timeout_seconds: float,
        request_name: str | None = None,
    ) -> dict[str, object]:
        raise RuntimeError("boom")


def test_structured_executor_logs_start_and_finish_with_summaries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    executor = StructuredAgentExecutor(
        provider=_FakeProvider({"summary_zh": "稳健", "summary_en": "steady"}),
        provider_name="anthropic",
        model_name="claude-opus-4-6",
        request_name="market_intelligence",
        timeout_seconds=5.0,
    )

    payload = executor.run_json(
        system_prompt="You are MarketIntelligenceAgent.",
        user_prompt="Return summary_zh and summary_en.",
        response_schema={"type": "object"},
    )

    assert payload["summary_zh"] == "稳健"
    assert any("agent_request_start" in record.message for record in caplog.records)
    assert any("agent_request_finish" in record.message for record in caplog.records)
    assert any(
        "agent_request_start" in record.message
        and "request_name=market_intelligence" in record.message
        and "provider_name=anthropic" in record.message
        and "model_name=claude-opus-4-6" in record.message
        and "request_summary=" in record.message
        for record in caplog.records
    )
    assert any(
        "agent_request_finish" in record.message
        and "request_name=market_intelligence" in record.message
        and "provider_name=anthropic" in record.message
        and "model_name=claude-opus-4-6" in record.message
        and "response_summary=" in record.message
        for record in caplog.records
    )


def test_structured_executor_logs_error_with_fallback_action(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    executor = StructuredAgentExecutor(
        provider=_ExplodingProvider(),
        provider_name="anthropic",
        model_name="claude-opus-4-6",
        request_name="user_profile_analyst",
        timeout_seconds=5.0,
    )

    with pytest.raises(RuntimeError):
        executor.run_json(
            system_prompt="You are MarketIntelligenceAgent.",
            user_prompt="Return summary_zh and summary_en.",
            response_schema={"type": "object"},
            fallback_action="use deterministic profile inference",
        )

    assert any("agent_request_error" in record.message for record in caplog.records)
    assert any(
        "agent_request_error" in record.message
        and "request_name=user_profile_analyst" in record.message
        and "provider_name=anthropic" in record.message
        and "model_name=claude-opus-4-6" in record.message
        and "fallback_action=use deterministic profile inference" in record.message
        for record in caplog.records
    )


def test_summarize_payload_trims_long_strings_lists_and_mappings() -> None:
    long_string = string.ascii_letters * 5
    payload = {
        "long_text": long_string,
        "many_items": list(range(12)),
        "many_keys": {f"k{i}": i for i in range(20)},
    }

    summary = summarize_payload(payload)
    parsed = loads(summary)

    assert len(parsed["long_text"]) == 243
    assert parsed["long_text"].endswith("...")
    assert parsed["long_text"].startswith(long_string[:20])
    assert len(parsed["many_items"]) == 8
    assert parsed["many_items"] == list(range(8))
    assert len(parsed["many_keys"]) == 16
    assert set(parsed["many_keys"]) == {f"k{i}" for i in range(16)}


def test_summarize_payload_is_best_effort_for_non_json_serializable_values() -> None:
    summary = summarize_payload({"non_serializable": object()})

    assert "non_serializable" in summary
