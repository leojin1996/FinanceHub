import pytest

from financehub_market_api.recommendation.agents.provider import (
    AGENT_MODEL_ROUTE_ENV_NAMES,
    ANTHROPIC_PROVIDER_NAME,
    OPENAI_PROVIDER_NAME,
    AgentRuntimeConfig,
    AnthropicChatProvider,
    LLMInvalidResponseError,
    OpenAICompatibleChatProvider,
    ProviderConfig,
)


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


def _build_provider(
    response_payload: object,
    *,
    json_error: Exception | None = None,
) -> tuple[OpenAICompatibleChatProvider, _FakeHttpClient]:
    http_client = _FakeHttpClient(response_payload, json_error=json_error)
    provider = OpenAICompatibleChatProvider(
        ProviderConfig(
            name=OPENAI_PROVIDER_NAME,
            kind="openai_compatible",
            api_key="test-key",
            base_url="https://example.invalid/v1",
        ),
        http_client=http_client,
    )
    return provider, http_client


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


@pytest.mark.parametrize(
    "response_payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": {"not": "a string"}}}]},
    ],
)
def test_provider_raises_for_missing_or_invalid_message_content(response_payload: object) -> None:
    provider, _ = _build_provider(response_payload)

    with pytest.raises(LLMInvalidResponseError, match="assistant message content|JSON string"):
        provider.chat_json(
            model_name="gpt-test",
            messages=[{"role": "user", "content": "hello"}],
            response_schema={"type": "object"},
            timeout_seconds=10.0,
        )


def test_provider_raises_for_non_json_content_text() -> None:
    provider, _ = _build_provider(
        {"choices": [{"message": {"content": "not-json-content"}}]}
    )

    with pytest.raises(LLMInvalidResponseError, match="invalid JSON content"):
        provider.chat_json(
            model_name="gpt-test",
            messages=[{"role": "user", "content": "hello"}],
            response_schema={"type": "object"},
            timeout_seconds=10.0,
        )


def test_provider_raises_when_http_body_is_not_valid_json() -> None:
    provider, _ = _build_provider({}, json_error=ValueError("malformed json body"))

    with pytest.raises(LLMInvalidResponseError, match="response is not valid JSON"):
        provider.chat_json(
            model_name="gpt-test",
            messages=[{"role": "user", "content": "hello"}],
            response_schema={"type": "object"},
            timeout_seconds=10.0,
        )


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

def test_runtime_config_reads_legacy_openai_values_from_explicit_env_file(
    tmp_path,
) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "\n".join(
            [
                "FINANCEHUB_LLM_API_KEY=test-key",
                "FINANCEHUB_LLM_BASE_URL=https://example.invalid",
                "FINANCEHUB_LLM_MODEL_DEFAULT=gpt-test",
            ]
        ),
        encoding="utf-8",
    )

    config = AgentRuntimeConfig.from_env(environ={}, env_files=[env_path])

    assert config is not None
    assert config.providers[OPENAI_PROVIDER_NAME].api_key == "test-key"
    assert config.providers[OPENAI_PROVIDER_NAME].base_url == "https://example.invalid/v1"
    assert config.agent_routes["user_profile"].provider_name == OPENAI_PROVIDER_NAME
    assert config.agent_routes["user_profile"].model_name == "gpt-test"


def test_runtime_config_loads_multi_provider_registry_and_agent_overrides() -> None:
    config = AgentRuntimeConfig.from_env(
        environ={
            "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY": "openai-key",
            "FINANCEHUB_LLM_PROVIDER_OPENAI_BASE_URL": "https://letsaicode.com",
            "ANTHROPIC_AUTH_TOKEN": "anthropic-key",
            "ANTHROPIC_BASE_URL": "https://oneapi.hk",
            "FINANCEHUB_LLM_AGENT_EXPLANATION_MODEL": "claude-opus-4-6",
            "FINANCEHUB_LLM_AGENT_EXPLANATION_PROVIDER": ANTHROPIC_PROVIDER_NAME,
        },
        env_files=[],
    )

    assert config is not None
    assert config.providers[OPENAI_PROVIDER_NAME].base_url == "https://letsaicode.com/v1"
    assert config.providers[OPENAI_PROVIDER_NAME].kind == "openai_compatible"
    assert config.providers[ANTHROPIC_PROVIDER_NAME].api_key == "anthropic-key"
    assert config.providers[ANTHROPIC_PROVIDER_NAME].base_url == "https://oneapi.hk/v1"
    assert config.providers[ANTHROPIC_PROVIDER_NAME].kind == "anthropic"
    assert config.agent_routes["market_intelligence"].provider_name == ANTHROPIC_PROVIDER_NAME
    assert config.agent_routes["market_intelligence"].model_name == "claude-opus-4-6"
    assert config.agent_routes["explanation"].provider_name == ANTHROPIC_PROVIDER_NAME
    assert config.agent_routes["explanation"].model_name == "claude-opus-4-6"


def test_runtime_config_applies_single_agent_override_without_replacing_default_map() -> None:
    config = AgentRuntimeConfig.from_env(
        environ={
            "FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY": "openai-key",
            "FINANCEHUB_LLM_PROVIDER_OPENAI_BASE_URL": "https://letsaicode.com/v1",
            "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY": "anthropic-key",
            "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_BASE_URL": "https://oneapi.hk/v1",
            "FINANCEHUB_LLM_AGENT_STOCK_SELECTION_PROVIDER": ANTHROPIC_PROVIDER_NAME,
            "FINANCEHUB_LLM_AGENT_STOCK_SELECTION_MODEL": "claude-opus-4-6",
        },
        env_files=[],
    )

    assert config is not None
    assert AGENT_MODEL_ROUTE_ENV_NAMES["stock_selection"] == "STOCK_SELECTION"
    assert config.agent_routes["stock_selection"].provider_name == ANTHROPIC_PROVIDER_NAME
    assert config.agent_routes["stock_selection"].model_name == "claude-opus-4-6"
    assert config.agent_routes["fund_selection"].provider_name == OPENAI_PROVIDER_NAME
