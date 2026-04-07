import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from financehub_market_api.recommendation.agents import provider as provider_module
from financehub_market_api.recommendation.agents.provider import (
    AGENT_MODEL_ROUTE_ENV_NAMES,
    ANTHROPIC_DEFAULT_MODEL,
    ANTHROPIC_PROVIDER_NAME,
    AgentRuntimeConfig,
    AnthropicChatProvider,
    LLMInvalidResponseError,
    LLMProviderError,
    ProviderConfig,
)
from financehub_market_api.recommendation.agents.contracts import ProductRankingAgentOutput


class _FakeResponse:
    def __init__(self, payload: object, *, json_error: Exception | None = None) -> None:
        self._payload = payload
        self._json_error = json_error

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _FakeHttpClient:
    def __init__(
        self,
        response_payload: object,
        *,
        json_error: Exception | None = None,
    ) -> None:
        self._response_payload = response_payload
        self._json_error = json_error
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> _FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return _FakeResponse(self._response_payload, json_error=self._json_error)


class _SequentialFakeHttpClient:
    def __init__(self, response_payloads: list[object | Exception]) -> None:
        self._response_payloads = response_payloads
        self._index = 0
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> _FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        if self._index >= len(self._response_payloads):
            raise AssertionError("unexpected HTTP call")
        response_payload = self._response_payloads[self._index]
        self._index += 1
        if isinstance(response_payload, Exception):
            raise response_payload
        return _FakeResponse(response_payload)


def _build_anthropic_provider(
    response_payload: object,
    *,
    json_error: Exception | None = None,
) -> tuple[AnthropicChatProvider, _FakeHttpClient]:
    http_client = _FakeHttpClient(response_payload, json_error=json_error)
    provider = AnthropicChatProvider(
        ProviderConfig(
            name=ANTHROPIC_PROVIDER_NAME,
            kind="anthropic",
            api_key="anthropic-test-key",
            base_url="https://oneapi.hk/v1",
        ),
        http_client=http_client,
    )
    return provider, http_client


def test_anthropic_provider_uses_messages_api_and_parses_text_json() -> None:
    provider, http_client = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "text",
                    "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
                }
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-opus-4-6",
        messages=[
            {"role": "system", "content": "You are MarketIntelligenceAgent."},
            {"role": "user", "content": "Return summary_zh and summary_en."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
    )

    assert payload == {"summary_zh": "稳健", "summary_en": "Steady"}
    assert http_client.calls[0]["url"] == "https://oneapi.hk/v1/messages"
    assert http_client.calls[0]["headers"]["x-api-key"] == "anthropic-test-key"
    assert http_client.calls[0]["json"]["model"] == "claude-opus-4-6"
    assert http_client.calls[0]["json"]["system"] == "You are MarketIntelligenceAgent."
    assert http_client.calls[0]["json"]["output_config"]["format"]["type"] == "json_schema"


def test_anthropic_provider_retries_without_output_config_when_structured_response_is_empty() -> None:
    http_client = _SequentialFakeHttpClient(
        [
            {"content": []},
            {
                "content": [
                    {
                        "type": "text",
                        "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
                    }
                ]
            },
        ]
    )
    provider = AnthropicChatProvider(
        ProviderConfig(
            name=ANTHROPIC_PROVIDER_NAME,
            kind="anthropic",
            api_key="anthropic-test-key",
            base_url="https://oneapi.hk/v1",
        ),
        http_client=http_client,
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "You are MarketIntelligenceAgent. Return strict JSON only."},
            {"role": "user", "content": "Return summary_zh and summary_en."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
    )

    assert payload == {"summary_zh": "稳健", "summary_en": "Steady"}
    assert "output_config" in http_client.calls[0]["json"]
    assert "output_config" not in http_client.calls[1]["json"]


def test_anthropic_provider_captures_raw_response_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = {
        "content": [
            {
                "type": "text",
                "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
            }
        ]
    }
    provider, _ = _build_anthropic_provider(response_body)
    capture_dir = tmp_path / "llm-captures"
    monkeypatch.setenv("FINANCEHUB_LLM_CAPTURE_RAW_RESPONSES", "true")
    monkeypatch.setenv("FINANCEHUB_LLM_CAPTURE_DIR", str(capture_dir))

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "You are MarketIntelligenceAgent. Return strict JSON only."},
            {"role": "user", "content": "Return summary_zh and summary_en."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
        request_name="market_intelligence",
    )

    assert payload == {"summary_zh": "稳健", "summary_en": "Steady"}
    capture_files = list(capture_dir.glob("*.json"))
    assert len(capture_files) == 1
    capture_payload = json.loads(capture_files[0].read_text(encoding="utf-8"))
    assert capture_payload["request_name"] == "market_intelligence"
    assert capture_payload["model_name"] == "claude-sonnet-4-6"
    assert capture_payload["phase"] == "structured"
    assert capture_payload["body"] == response_body


def test_anthropic_provider_capture_reads_env_file_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = {
        "content": [
            {
                "type": "text",
                "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
            }
        ]
    }
    provider, _ = _build_anthropic_provider(response_body)
    capture_dir = tmp_path / "llm-captures"
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            [
                "FINANCEHUB_LLM_CAPTURE_RAW_RESPONSES=true",
                f"FINANCEHUB_LLM_CAPTURE_DIR={capture_dir}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("FINANCEHUB_LLM_CAPTURE_RAW_RESPONSES", raising=False)
    monkeypatch.delenv("FINANCEHUB_LLM_CAPTURE_DIR", raising=False)
    monkeypatch.setattr(provider_module, "_iter_env_file_candidates", lambda: [env_path])

    provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "You are MarketIntelligenceAgent. Return strict JSON only."},
            {"role": "user", "content": "Return summary_zh and summary_en."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
        request_name="market_intelligence",
    )

    capture_files = list(capture_dir.glob("*.json"))
    assert len(capture_files) == 1
    capture_payload = json.loads(capture_files[0].read_text(encoding="utf-8"))
    assert capture_payload["request_name"] == "market_intelligence"
    assert capture_payload["model_name"] == "claude-sonnet-4-6"


def test_anthropic_provider_capture_write_failure_raises_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = {
        "content": [
            {
                "type": "text",
                "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
            }
        ]
    }
    provider, _ = _build_anthropic_provider(response_body)
    capture_dir = tmp_path / "not-a-directory"
    capture_dir.write_text("occupied", encoding="utf-8")
    monkeypatch.setenv("FINANCEHUB_LLM_CAPTURE_RAW_RESPONSES", "true")
    monkeypatch.setenv("FINANCEHUB_LLM_CAPTURE_DIR", str(capture_dir))

    with pytest.raises(LLMProviderError, match="failed to write raw response capture"):
        provider.chat_json(
            model_name="claude-sonnet-4-6",
            messages=[
                {"role": "system", "content": "You are MarketIntelligenceAgent. Return strict JSON only."},
                {"role": "user", "content": "Return summary_zh and summary_en."},
            ],
            response_schema={"type": "object"},
            timeout_seconds=5.0,
            request_name="market_intelligence",
        )


def test_product_ranking_output_rejects_empty_ranked_ids() -> None:
    with pytest.raises(ValidationError):
        ProductRankingAgentOutput.model_validate({"ranked_ids": []})


def test_anthropic_provider_accepts_json_wrapped_in_markdown_fence() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "```json\n"
                        "{\n"
                        '  "profile_focus_zh": "平衡风险与收益，追求稳健增长",\n'
                        '  "profile_focus_en": "Balance risk and return for steady growth"\n'
                        "}\n"
                        "```"
                    ),
                }
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "You are UserProfileAgent. Return strict JSON only."},
            {"role": "user", "content": "Return profile_focus_zh and profile_focus_en."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
    )

    assert payload == {
        "profile_focus_zh": "平衡风险与收益，追求稳健增长",
        "profile_focus_en": "Balance risk and return for steady growth",
    }


def test_anthropic_provider_accepts_json_fence_with_intro_text() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Here is the structured result you requested:\n"
                        "```json\n"
                        "{\n"
                        '  "summary_zh": "稳健配置更合适",\n'
                        '  "summary_en": "A balanced allocation is more appropriate"\n'
                        "}\n"
                        "```"
                    ),
                }
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "You are MarketIntelligenceAgent. Return strict JSON only."},
            {"role": "user", "content": "Return summary_zh and summary_en."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
    )

    assert payload == {
        "summary_zh": "稳健配置更合适",
        "summary_en": "A balanced allocation is more appropriate",
    }


def test_anthropic_provider_accepts_embedded_json_with_trailing_text() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "I normalized the result for you below.\n"
                        "{\n"
                        '  "summary_zh": "更适合均衡配置",\n'
                        '  "summary_en": "A balanced allocation is preferable"\n'
                        "}\n"
                        "Let me know if you need a shorter variant."
                    ),
                }
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "You are MarketIntelligenceAgent. Return strict JSON only."},
            {"role": "user", "content": "Return summary_zh and summary_en."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
    )

    assert payload == {
        "summary_zh": "更适合均衡配置",
        "summary_en": "A balanced allocation is preferable",
    }


def test_anthropic_provider_ignores_non_json_braces_before_object() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Use the fields {summary_zh, summary_en} exactly.\n"
                        "{\n"
                        '  "summary_zh": "建议均衡布局",\n'
                        '  "summary_en": "A balanced layout is recommended"\n'
                        "}\n"
                    ),
                }
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "You are MarketIntelligenceAgent. Return strict JSON only."},
            {"role": "user", "content": "Return summary_zh and summary_en."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
    )

    assert payload == {
        "summary_zh": "建议均衡布局",
        "summary_en": "A balanced layout is recommended",
    }


def test_anthropic_provider_extracts_schema_object_from_nested_non_text_block() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {
                        "summary_zh": "从工具输入提取",
                        "summary_en": "Extracted from tool input",
                    },
                }
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "Return summary_zh and summary_en."},
            {"role": "user", "content": "Provide the result."},
        ],
        response_schema={
            "type": "object",
            "required": ["summary_zh", "summary_en"],
            "properties": {
                "summary_zh": {"type": "string"},
                "summary_en": {"type": "string"},
            },
        },
        timeout_seconds=5.0,
    )

    assert payload == {
        "summary_zh": "从工具输入提取",
        "summary_en": "Extracted from tool input",
    }


def test_anthropic_provider_rejects_nested_object_not_matching_schema() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {"summary_zh": "缺少英文字段"},
                }
            ]
        }
    )

    with pytest.raises(
        LLMInvalidResponseError,
        match="provider response has no schema-matching structured content",
    ):
        provider.chat_json(
            model_name="claude-sonnet-4-6",
            messages=[
                {"role": "system", "content": "Return summary_zh and summary_en."},
                {"role": "user", "content": "Provide the result."},
            ],
            response_schema={
                "type": "object",
                "required": ["summary_zh", "summary_en"],
                "properties": {
                    "summary_zh": {"type": "string"},
                    "summary_en": {"type": "string"},
                },
            },
            timeout_seconds=5.0,
        )


def test_anthropic_provider_rejects_ambiguous_multiple_schema_matches() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {
                        "summary_zh": "第一版",
                        "summary_en": "First",
                    },
                },
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {
                        "summary_zh": "第二版",
                        "summary_en": "Second",
                    },
                },
            ]
        }
    )

    with pytest.raises(
        LLMInvalidResponseError,
        match="provider response has multiple schema-matching structured objects",
    ):
        provider.chat_json(
            model_name="claude-sonnet-4-6",
            messages=[
                {"role": "system", "content": "Return summary_zh and summary_en."},
                {"role": "user", "content": "Provide the result."},
            ],
            response_schema={
                "type": "object",
                "required": ["summary_zh", "summary_en"],
                "properties": {
                    "summary_zh": {"type": "string"},
                    "summary_en": {"type": "string"},
                },
            },
            timeout_seconds=5.0,
        )


def test_anthropic_provider_skips_non_json_text_and_extracts_nested_schema_object() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "text",
                    "text": "I will call a tool to provide the structured result now.",
                },
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {
                        "summary_zh": "来自嵌套对象",
                        "summary_en": "From nested object",
                    },
                },
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "Return summary_zh and summary_en."},
            {"role": "user", "content": "Provide the result."},
        ],
        response_schema={
            "type": "object",
            "required": ["summary_zh", "summary_en"],
            "properties": {
                "summary_zh": {"type": "string"},
                "summary_en": {"type": "string"},
            },
        },
        timeout_seconds=5.0,
    )

    assert payload == {
        "summary_zh": "来自嵌套对象",
        "summary_en": "From nested object",
    }


def test_anthropic_provider_ignores_incidental_braces_in_text_preamble() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "text",
                    "text": "I will call {emit_result} next and then provide the final object.",
                },
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {
                        "summary_zh": "括号前言不应阻断提取",
                        "summary_en": "Brace preamble should not block extraction",
                    },
                },
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "Return summary_zh and summary_en."},
            {"role": "user", "content": "Provide the result."},
        ],
        response_schema={
            "type": "object",
            "required": ["summary_zh", "summary_en"],
            "properties": {
                "summary_zh": {"type": "string"},
                "summary_en": {"type": "string"},
            },
        },
        timeout_seconds=5.0,
    )

    assert payload == {
        "summary_zh": "括号前言不应阻断提取",
        "summary_en": "Brace preamble should not block extraction",
    }


def test_anthropic_provider_ignores_non_json_fenced_text_preamble() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "I will call a tool next.\n"
                        "```python\n"
                        "def helper():\n"
                        "    return 'not json'\n"
                        "```\n"
                    ),
                },
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {
                        "summary_zh": "非JSON代码块不应阻断提取",
                        "summary_en": "Non-JSON fence should not block extraction",
                    },
                },
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "Return summary_zh and summary_en."},
            {"role": "user", "content": "Provide the result."},
        ],
        response_schema={
            "type": "object",
            "required": ["summary_zh", "summary_en"],
            "properties": {
                "summary_zh": {"type": "string"},
                "summary_en": {"type": "string"},
            },
        },
        timeout_seconds=5.0,
    )

    assert payload == {
        "summary_zh": "非JSON代码块不应阻断提取",
        "summary_en": "Non-JSON fence should not block extraction",
    }


def test_anthropic_provider_bare_object_schema_prefers_nested_non_text_object() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {
                        "summary_zh": "兼容旧调用",
                        "summary_en": "Compatible fallback",
                    },
                }
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "Return summary_zh and summary_en."},
            {"role": "user", "content": "Provide the result."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
    )

    assert payload == {
        "summary_zh": "兼容旧调用",
        "summary_en": "Compatible fallback",
    }


def test_anthropic_provider_rejects_non_object_json_text_for_bare_object_schema() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "text",
                    "text": "[]",
                }
            ]
        }
    )

    with pytest.raises(LLMInvalidResponseError, match="provider JSON content must be an object"):
        provider.chat_json(
            model_name="claude-sonnet-4-6",
            messages=[
                {"role": "system", "content": "Return a JSON object."},
                {"role": "user", "content": "Provide the result."},
            ],
            response_schema={"type": "object"},
            timeout_seconds=5.0,
        )


def test_anthropic_provider_bare_object_schema_prefers_nested_object_with_list_values() -> None:
    provider, _ = _build_anthropic_provider(
        {
            "content": [
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {
                        "ranked_ids": ["fund_a", "fund_b"],
                        "note": "ordered by confidence",
                    },
                }
            ]
        }
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "Return a JSON object."},
            {"role": "user", "content": "Provide the result."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
    )

    assert payload == {
        "ranked_ids": ["fund_a", "fund_b"],
        "note": "ordered by confidence",
    }


def test_anthropic_provider_retries_after_read_timeout() -> None:
    http_client = _SequentialFakeHttpClient(
        [
            httpx.ReadTimeout("timed out"),
            {
                "content": [
                    {
                        "type": "text",
                        "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
                    }
                ]
            },
        ]
    )
    provider = AnthropicChatProvider(
        ProviderConfig(
            name=ANTHROPIC_PROVIDER_NAME,
            kind="anthropic",
            api_key="anthropic-test-key",
            base_url="https://oneapi.hk/v1",
        ),
        http_client=http_client,
    )

    payload = provider.chat_json(
        model_name="claude-sonnet-4-6",
        messages=[
            {"role": "system", "content": "You are MarketIntelligenceAgent. Return strict JSON only."},
            {"role": "user", "content": "Return summary_zh and summary_en."},
        ],
        response_schema={"type": "object"},
        timeout_seconds=5.0,
    )

    assert payload == {"summary_zh": "稳健", "summary_en": "Steady"}
    assert len(http_client.calls) == 2


def test_runtime_config_reads_anthropic_values_from_explicit_env_file(tmp_path) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            [
                "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY=test-key",
                "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_BASE_URL=https://example.invalid",
                "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_MODEL_DEFAULT=claude-sonnet-4-6",
            ]
        ),
        encoding="utf-8",
    )

    config = AgentRuntimeConfig.from_env(environ={}, env_files=[env_path])

    assert config.providers[ANTHROPIC_PROVIDER_NAME].api_key == "test-key"
    assert config.providers[ANTHROPIC_PROVIDER_NAME].base_url == "https://example.invalid/v1"
    assert config.agent_routes["user_profile"].provider_name == ANTHROPIC_PROVIDER_NAME
    assert config.agent_routes["user_profile"].model_name == "claude-sonnet-4-6"


def test_runtime_config_loads_anthropic_provider_and_agent_overrides() -> None:
    config = AgentRuntimeConfig.from_env(
        environ={
            "ANTHROPIC_AUTH_TOKEN": "anthropic-key",
            "ANTHROPIC_BASE_URL": "https://oneapi.hk",
            "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_MODEL_DEFAULT": "claude-opus-4-6",
            "FINANCEHUB_LLM_AGENT_EXPLANATION_MODEL": "claude-sonnet-4-6",
        },
        env_files=[],
    )

    assert config.providers[ANTHROPIC_PROVIDER_NAME].api_key == "anthropic-key"
    assert config.providers[ANTHROPIC_PROVIDER_NAME].base_url == "https://oneapi.hk/v1"
    assert config.providers[ANTHROPIC_PROVIDER_NAME].kind == "anthropic"
    assert config.agent_routes["market_intelligence"].provider_name == ANTHROPIC_PROVIDER_NAME
    assert config.agent_routes["market_intelligence"].model_name == "claude-opus-4-6"
    assert config.agent_routes["explanation"].provider_name == ANTHROPIC_PROVIDER_NAME
    assert config.agent_routes["explanation"].model_name == "claude-sonnet-4-6"


def test_runtime_config_applies_single_agent_override_without_replacing_default_map() -> None:
    config = AgentRuntimeConfig.from_env(
        environ={
            "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY": "anthropic-key",
            "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_BASE_URL": "https://oneapi.hk/v1",
            "FINANCEHUB_LLM_AGENT_STOCK_SELECTION_MODEL": "claude-sonnet-4-6",
        },
        env_files=[],
    )

    assert AGENT_MODEL_ROUTE_ENV_NAMES["stock_selection"] == "STOCK_SELECTION"
    assert config.agent_routes["stock_selection"].provider_name == ANTHROPIC_PROVIDER_NAME
    assert config.agent_routes["stock_selection"].model_name == "claude-sonnet-4-6"
    assert config.agent_routes["fund_selection"].provider_name == ANTHROPIC_PROVIDER_NAME
    assert config.agent_routes["fund_selection"].model_name == ANTHROPIC_DEFAULT_MODEL


def test_runtime_config_reads_llm_timeout_seconds_from_env() -> None:
    config = AgentRuntimeConfig.from_env(
        environ={
            "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY": "anthropic-key",
            "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_BASE_URL": "https://oneapi.hk/v1",
            "FINANCEHUB_LLM_TIMEOUT_SECONDS": "30",
        },
        env_files=[],
    )

    assert config.request_timeout_seconds == 30.0
