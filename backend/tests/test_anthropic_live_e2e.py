from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from financehub_market_api.recommendation.agents.provider import AgentRuntimeConfig
from financehub_market_api.recommendation.agents.sample_capture import run_live_agent_e2e

LIVE_AGENT_E2E_ENV = "FINANCEHUB_RUN_LIVE_AGENT_E2E"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_RISK_ORDER = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}


def _live_agent_e2e_enabled() -> bool:
    return os.environ.get(LIVE_AGENT_E2E_ENV, "").strip().lower() in _TRUTHY_ENV_VALUES


def _assert_live_provider_available() -> None:
    if not _live_agent_e2e_enabled():
        pytest.skip(f"Set {LIVE_AGENT_E2E_ENV}=true to run live Anthropic end-to-end coverage.")

    runtime_config = AgentRuntimeConfig.from_env()
    if not runtime_config.providers:
        pytest.skip("No live LLM provider configured for Anthropic end-to-end coverage.")


def _live_failure_context(response) -> str:
    warning_summary = [
        f"{warning.stage}:{warning.code}:{warning.message}"
        for warning in response.warnings
    ]
    trace_summary = [
        f"{event.requestName}:{event.status}:{event.responseSummary or '-'}"
        for event in response.agentTrace
    ]
    return (
        f"recommendationStatus={response.recommendationStatus} "
        f"reviewStatus={response.reviewStatus} "
        f"profileInsights={'present' if response.profileInsights is not None else 'missing'} "
        f"marketIntelligence={'present' if response.marketIntelligence is not None else 'missing'} "
        f"funds={len(response.sections.funds.items)} "
        f"wealth={len(response.sections.wealthManagement.items)} "
        f"stocks={len(response.sections.stocks.items)} "
        f"warnings={warning_summary} "
        f"trace={trace_summary}"
    )


def _assert_common_live_response(response) -> None:
    debug = _live_failure_context(response)
    assert response.profileInsights is not None, debug
    assert response.marketIntelligence is not None, debug
    assert response.whyThisPlan.zh, debug
    assert response.agentTrace, debug
    assert (
        response.sections.funds.items
        or response.sections.wealthManagement.items
        or response.sections.stocks.items
    ), debug


def test_live_failure_context_summarizes_warnings_and_trace() -> None:
    response = SimpleNamespace(
        recommendationStatus="blocked",
        reviewStatus="partial_pass",
        profileInsights=None,
        marketIntelligence=None,
        warnings=[
            SimpleNamespace(
                stage="product_match_expert",
                code="agent_product_match_failed",
                message="provider returned invalid JSON content",
            )
        ],
        agentTrace=[
            SimpleNamespace(
                requestName="product_match_expert",
                status="error",
                responseSummary="agent_product_match_failed",
            )
        ],
        sections=SimpleNamespace(
            funds=SimpleNamespace(items=[]),
            wealthManagement=SimpleNamespace(items=[]),
            stocks=SimpleNamespace(items=[]),
        ),
    )

    summary = _live_failure_context(response)

    assert "recommendationStatus=blocked" in summary
    assert "profileInsights=missing" in summary
    assert "marketIntelligence=missing" in summary
    assert "product_match_expert:agent_product_match_failed:provider returned invalid JSON content" in summary
    assert "product_match_expert:error:agent_product_match_failed" in summary


def test_run_live_agent_e2e_conservative_sample_remains_low_risk() -> None:
    _assert_live_provider_available()

    response = run_live_agent_e2e(risk_profile="conservative")

    _assert_common_live_response(response)
    assert response.recommendationStatus in {"ready", "limited"}
    assert response.profileInsights.riskTier in {"R1", "R2"}
    assert response.sections.stocks.items == []
    assert all(
        item.riskLevel in {"R1", "R2"}
        for item in response.sections.funds.items + response.sections.wealthManagement.items
    )


def test_run_live_agent_e2e_stable_sample_stays_defensive() -> None:
    _assert_live_provider_available()

    response = run_live_agent_e2e(risk_profile="stable")

    _assert_common_live_response(response)
    assert response.recommendationStatus in {"ready", "limited"}
    assert response.profileInsights.riskTier in {"R1", "R2", "R3"}
    assert response.sections.stocks.items == []
    assert all(
        _RISK_ORDER[item.riskLevel] <= _RISK_ORDER["R2"]
        for item in response.sections.funds.items + response.sections.wealthManagement.items
    )


def test_run_live_agent_e2e_balanced_sample_supports_selective_equity() -> None:
    _assert_live_provider_available()

    response = run_live_agent_e2e(risk_profile="balanced")

    _assert_common_live_response(response)
    assert response.recommendationStatus in {"ready", "limited"}
    assert response.profileInsights.riskTier in {"R2", "R3", "R4"}
    assert all(
        _RISK_ORDER[item.riskLevel] <= _RISK_ORDER["R3"]
        for item in response.sections.funds.items
        + response.sections.wealthManagement.items
        + response.sections.stocks.items
    )


def test_run_live_agent_e2e_growth_sample_can_include_stocks() -> None:
    _assert_live_provider_available()

    response = run_live_agent_e2e(risk_profile="growth")

    _assert_common_live_response(response)
    assert response.recommendationStatus in {"ready", "limited"}
    assert response.profileInsights.riskTier in {"R3", "R4", "R5"}
    assert response.marketIntelligence.stance == "offensive"
    assert response.sections.stocks.items
    assert all(item.category == "stock" for item in response.sections.stocks.items)
    assert all(item.riskLevel in {"R3", "R4", "R5"} for item in response.sections.stocks.items)


def test_run_live_agent_e2e_aggressive_sample_prefers_high_beta_equities() -> None:
    _assert_live_provider_available()

    response = run_live_agent_e2e(risk_profile="aggressive")

    _assert_common_live_response(response)
    assert response.recommendationStatus in {"ready", "limited"}
    assert response.profileInsights.riskTier in {"R4", "R5"}
    assert response.sections.stocks.items
    assert all(_RISK_ORDER[item.riskLevel] >= _RISK_ORDER["R4"] for item in response.sections.stocks.items)
