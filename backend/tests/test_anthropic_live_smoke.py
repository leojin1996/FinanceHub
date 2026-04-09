from __future__ import annotations

import os

import pytest

from financehub_market_api.recommendation.agents.provider import AgentRuntimeConfig
from financehub_market_api.recommendation.agents.sample_capture import (
    capture_request_names,
    run_live_agent_smoke,
)

LIVE_AGENT_SMOKE_ENV = "FINANCEHUB_RUN_LIVE_AGENT_SMOKE"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _live_agent_smoke_enabled() -> bool:
    return os.environ.get(LIVE_AGENT_SMOKE_ENV, "").strip().lower() in _TRUTHY_ENV_VALUES


def test_run_live_agent_smoke_against_configured_provider() -> None:
    if not _live_agent_smoke_enabled():
        pytest.skip(f"Set {LIVE_AGENT_SMOKE_ENV}=true to run live Anthropic smoke coverage.")

    runtime_config = AgentRuntimeConfig.from_env()
    if not runtime_config.providers:
        pytest.skip("No live LLM provider configured for Anthropic smoke coverage.")

    summary = run_live_agent_smoke()

    assert [item["request_name"] for item in summary] == list(capture_request_names())
    assert all(item["model_name"] for item in summary)
    assert all(item["output_summary"] for item in summary)
