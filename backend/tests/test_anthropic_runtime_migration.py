from financehub_market_api.recommendation.agents import AnthropicMultiAgentRuntime
from financehub_market_api.recommendation.agents.provider import (
    ANTHROPIC_DEFAULT_MODEL,
    ANTHROPIC_PROVIDER_NAME,
    AgentRuntimeConfig,
)


def test_agents_package_exports_anthropic_multi_agent_runtime() -> None:
    runtime = AnthropicMultiAgentRuntime(providers={})

    assert runtime is not None


def test_runtime_config_only_reads_anthropic_provider_values() -> None:
    config = AgentRuntimeConfig.from_env(
        environ={
            "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY": "anthropic-key",
            "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_BASE_URL": "https://oneapi.hk",
        },
        env_files=[],
    )

    assert list(config.providers) == [ANTHROPIC_PROVIDER_NAME]
    assert config.providers[ANTHROPIC_PROVIDER_NAME].kind == "anthropic"
    assert all(route.provider_name == ANTHROPIC_PROVIDER_NAME for route in config.agent_routes.values())
    assert all(route.model_name == ANTHROPIC_DEFAULT_MODEL for route in config.agent_routes.values())
