from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from financehub_market_api.recommendation.agents.provider import AgentRuntimeConfig
from financehub_market_api.recommendation.agents.sample_capture import run_live_agent_e2e

LIVE_AGENT_E2E_ENV = "FINANCEHUB_RUN_LIVE_AGENT_E2E"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_STABLE_RISK_TIERS = {"R1", "R2", "R3"}
_STABLE_RISK_LABELS = {"conservative", "stable", "稳健", "保守"}

_DEFENSIVE_STANCES = {"defensive", "very_defensive", "risk_off", "underweight"}


def _risk_tier_matches(tier: str, accepted_codes: set[str], accepted_labels: set[str]) -> bool:
    """Accept both coded tiers (R1-R5) and free-text labels from the LLM."""
    if tier in accepted_codes:
        return True
    lower = tier.lower()
    return any(label in lower for label in accepted_labels)


def _live_agent_e2e_enabled() -> bool:
    return os.environ.get(LIVE_AGENT_E2E_ENV, "").strip().lower() in _TRUTHY_ENV_VALUES


def _assert_live_provider_available() -> None:
    if not _live_agent_e2e_enabled():
        pytest.skip(f"Set {LIVE_AGENT_E2E_ENV}=true to run live OpenAI end-to-end coverage.")

    runtime_config = AgentRuntimeConfig.from_env()
    if not runtime_config.providers:
        pytest.skip("No live LLM provider configured for OpenAI end-to-end coverage.")


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


def _assert_common_live_response(response, *, require_items: bool = True) -> None:
    debug = _live_failure_context(response)
    assert response.profileInsights is not None, debug
    assert response.marketIntelligence is not None, debug
    assert response.whyThisPlan.zh, debug
    assert response.agentTrace, debug
    if require_items:
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
    assert _risk_tier_matches(
        response.profileInsights.riskTier,
        {"R1", "R2"},
        {"conservative", "保守", "谨慎"},
    ), f"unexpected riskTier for conservative profile: {response.profileInsights.riskTier}"


def test_run_live_agent_e2e_stable_sample_stays_defensive() -> None:
    _assert_live_provider_available()

    response = run_live_agent_e2e(risk_profile="stable")

    _assert_common_live_response(response)
    assert response.recommendationStatus in {"ready", "limited"}
    assert _risk_tier_matches(
        response.profileInsights.riskTier, _STABLE_RISK_TIERS, _STABLE_RISK_LABELS
    ), f"unexpected riskTier for stable profile: {response.profileInsights.riskTier}"


def test_run_live_agent_e2e_balanced_sample_supports_selective_equity() -> None:
    _assert_live_provider_available()

    response = run_live_agent_e2e(risk_profile="balanced")

    _assert_common_live_response(response)
    assert response.recommendationStatus in {"ready", "limited"}
    assert _risk_tier_matches(
        response.profileInsights.riskTier,
        {"R2", "R3", "R4"},
        {"balanced", "平衡", "均衡"},
    ), f"unexpected riskTier for balanced profile: {response.profileInsights.riskTier}"


def test_run_live_agent_e2e_growth_sample_can_include_stocks() -> None:
    _assert_live_provider_available()

    response = run_live_agent_e2e(risk_profile="growth")

    _assert_common_live_response(response, require_items=False)
    assert response.recommendationStatus in {"ready", "limited", "blocked"}
    assert _risk_tier_matches(
        response.profileInsights.riskTier,
        {"R3", "R4", "R5"},
        {"growth", "积极", "成长", "高"},
    ), f"unexpected riskTier for growth profile: {response.profileInsights.riskTier}"
    assert response.marketIntelligence.stance not in _DEFENSIVE_STANCES, (
        f"stance should not be defensive for growth profile: {response.marketIntelligence.stance}"
    )


def test_run_live_agent_e2e_aggressive_sample_prefers_high_beta_equities() -> None:
    _assert_live_provider_available()

    response = run_live_agent_e2e(risk_profile="aggressive")

    _assert_common_live_response(response)
    assert response.recommendationStatus in {"ready", "limited"}
    assert _risk_tier_matches(
        response.profileInsights.riskTier,
        {"R4", "R5"},
        {"aggressive", "激进", "进取"},
    ), f"unexpected riskTier for aggressive profile: {response.profileInsights.riskTier}"
    assert response.sections.stocks.items
