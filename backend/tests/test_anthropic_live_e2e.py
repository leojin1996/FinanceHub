from __future__ import annotations

import os

import pytest

from financehub_market_api.recommendation.agents.provider import AgentRuntimeConfig
from financehub_market_api.recommendation.agents.sample_capture import run_live_agent_e2e

LIVE_AGENT_E2E_ENV = "FINANCEHUB_RUN_LIVE_AGENT_E2E"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _live_agent_e2e_enabled() -> bool:
    return os.environ.get(LIVE_AGENT_E2E_ENV, "").strip().lower() in _TRUTHY_ENV_VALUES


def test_run_live_agent_e2e_against_configured_provider() -> None:
    if not _live_agent_e2e_enabled():
        pytest.skip(f"Set {LIVE_AGENT_E2E_ENV}=true to run live Anthropic end-to-end coverage.")

    runtime_config = AgentRuntimeConfig.from_env()
    if not runtime_config.providers:
        pytest.skip("No live LLM provider configured for Anthropic end-to-end coverage.")

    response = run_live_agent_e2e()

    assert response.recommendationStatus == "ready"
    assert response.profileInsights is not None
    assert response.profileInsights.riskTier in {"R1", "R2"}
    assert response.marketIntelligence is not None
    assert response.marketIntelligence.stance == "defensive"
    assert response.whyThisPlan.zh
    assert response.agentTrace
    assert response.sections.funds.items
    assert response.sections.wealthManagement.items
    assert response.sections.stocks.items == []
    assert all(
        item.riskLevel in {"R1", "R2"}
        for item in response.sections.funds.items + response.sections.wealthManagement.items
    )


def test_run_live_agent_e2e_growth_sample_can_include_stocks() -> None:
    if not _live_agent_e2e_enabled():
        pytest.skip(f"Set {LIVE_AGENT_E2E_ENV}=true to run live Anthropic end-to-end coverage.")

    runtime_config = AgentRuntimeConfig.from_env()
    if not runtime_config.providers:
        pytest.skip("No live LLM provider configured for Anthropic end-to-end coverage.")

    response = run_live_agent_e2e(risk_profile="growth")

    assert response.recommendationStatus in {"ready", "limited"}
    assert response.profileInsights is not None
    assert response.profileInsights.riskTier in {"R3", "R4", "R5"}
    assert response.marketIntelligence is not None
    assert response.marketIntelligence.stance == "offensive"
    assert response.whyThisPlan.zh
    assert response.agentTrace
    assert response.sections.stocks.items
    assert all(item.category == "stock" for item in response.sections.stocks.items)
    assert all(item.riskLevel in {"R3", "R4", "R5"} for item in response.sections.stocks.items)
