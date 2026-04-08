import logging
from collections.abc import Mapping

import pytest

from financehub_market_api.recommendation.llm_runtime import StructuredAgentExecutor


class _FakeProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def chat_json(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        response_schema: dict[str, object],
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


def test_structured_executor_logs_error_with_fallback_action(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    executor = StructuredAgentExecutor(
        provider=_ExplodingProvider(),
        provider_name="anthropic",
        model_name="claude-opus-4-6",
        request_name="market_intelligence",
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
