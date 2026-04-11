from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

import financehub_market_api.recommendation.agents.sample_capture as sample_capture_module
from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    ManagerCoordinatorAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.provider import AgentModelRoute, AgentRuntimeConfig
from financehub_market_api.recommendation.agents.sample_capture import (
    CaptureRunError,
    build_fixture_payload,
    capture_all_agents,
    capture_request_names,
    fixture_filename_for_request_name,
    run_live_agent_smoke,
    sanitize_captured_body,
)


def _load_capture_cli_module() -> object:
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "capture_anthropic_agent_responses.py"
    )
    spec = importlib.util.spec_from_file_location(
        "capture_anthropic_agent_responses_cli",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_config() -> AgentRuntimeConfig:
    return AgentRuntimeConfig(
        providers={},
        agent_routes={
            request_name: AgentModelRoute(
                provider_name="anthropic",
                model_name="claude-test",
            )
            for request_name in capture_request_names()
        },
        request_timeout_seconds=7.5,
    )


class _FakeRuntime:
    def __init__(self, *, fail_market: bool = False, run_order: list[str] | None = None) -> None:
        self._fail_market = fail_market
        self._run_order = run_order if run_order is not None else []

    def analyze_user_profile(self, user_profile, *, prompt_context=None):
        del user_profile, prompt_context
        self._run_order.append("user_profile_analyst")
        return (
            UserProfileAgentOutput(
                risk_tier="R2",
                liquidity_preference="high",
                investment_horizon="one_year",
                return_objective="capital_preservation",
                drawdown_sensitivity="high",
                profile_focus_zh="稳健",
                profile_focus_en="steady",
                derived_signals=[],
            ),
            type("Metadata", (), {"provider_name": "anthropic", "model_name": "claude-test"})(),
        )

    def analyze_market_intelligence(
        self,
        user_profile,
        user_profile_insights,
        market_facts,
        *,
        prompt_context=None,
    ):
        del user_profile, user_profile_insights, market_facts, prompt_context
        self._run_order.append("market_intelligence")
        if self._fail_market:
            raise RuntimeError("market failed")
        return (
            MarketIntelligenceAgentOutput(
                sentiment="negative",
                stance="defensive",
                preferred_categories=["wealth_management", "fund"],
                avoided_categories=["stock"],
                summary_zh="市场平稳",
                summary_en="Market is steady",
                evidence_refs=["market_overview"],
            ),
            type("Metadata", (), {"provider_name": "anthropic", "model_name": "claude-test"})(),
        )

    def match_products(
        self,
        user_profile,
        *,
        user_profile_insights,
        market_intelligence,
        candidates,
        prompt_context=None,
    ):
        del user_profile, user_profile_insights, market_intelligence, candidates, prompt_context
        self._run_order.append("product_match_expert")
        return (
            ProductMatchAgentOutput(
                recommended_categories=["wealth_management", "fund"],
                selected_product_ids=["wm-001", "fund-001"],
                ranking_rationale_zh="优先稳健候选。",
                ranking_rationale_en="Prefer resilient candidates.",
                filtered_out_reasons=[],
            ),
            type("Metadata", (), {"provider_name": "anthropic", "model_name": "claude-test"})(),
        )

    def review_compliance(
        self,
        user_profile,
        *,
        user_profile_insights,
        selected_candidates,
        compliance_facts,
        prompt_context=None,
    ):
        del user_profile, user_profile_insights, selected_candidates, compliance_facts, prompt_context
        self._run_order.append("compliance_risk_officer")
        return (
            ComplianceReviewAgentOutput(
                verdict="approve",
                approved_ids=["wm-001", "fund-001"],
                rejected_ids=[],
                reason_summary_zh="候选通过审核。",
                reason_summary_en="Candidates passed review.",
                required_disclosures_zh=["理财非存款，投资需谨慎。"],
                required_disclosures_en=["Investing involves risk. Proceed prudently."],
                suitability_notes_zh=["风险等级和流动性匹配。"],
                suitability_notes_en=["Risk and liquidity are aligned."],
                applied_rule_ids=["test-rule"],
                blocking_reason_codes=[],
            ),
            type("Metadata", (), {"provider_name": "anthropic", "model_name": "claude-test"})(),
        )

    def coordinate_manager(
        self,
        user_profile,
        *,
        user_profile_insights,
        market_intelligence,
        product_match,
        compliance_review,
        prompt_context=None,
    ):
        del (
            user_profile,
            user_profile_insights,
            market_intelligence,
            product_match,
            compliance_review,
            prompt_context,
        )
        self._run_order.append("manager_coordinator")
        return (
            ManagerCoordinatorAgentOutput(
                recommendation_status="ready",
                summary_zh="建议保持稳健配置。",
                summary_en="Favor a resilient allocation.",
                why_this_plan_zh=["理由一"],
                why_this_plan_en=["Reason one"],
            ),
            type("Metadata", (), {"provider_name": "anthropic", "model_name": "claude-test"})(),
        )


def _write_capture_file(capture_dir: Path, request_name: str, text: str) -> None:
    payload = {
        "request_name": request_name,
        "phase": "structured",
        "body": {
            "id": f"msg-{request_name}",
            "content": [{"type": "text", "text": text}],
        },
    }
    (capture_dir / f"{request_name}.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_capture_request_names_covers_all_five_agent_stages() -> None:
    assert capture_request_names() == (
        "user_profile_analyst",
        "market_intelligence",
        "product_match_expert",
        "compliance_risk_officer",
        "manager_coordinator",
    )


def test_fixture_filename_generation_is_stable_per_request_name() -> None:
    assert (
        fixture_filename_for_request_name("user_profile_analyst")
        == "user_profile_analyst.json"
    )
    assert fixture_filename_for_request_name("market_intelligence") == "market_intelligence.json"
    assert fixture_filename_for_request_name("product_match_expert") == "product_match_expert.json"
    assert (
        fixture_filename_for_request_name("compliance_risk_officer")
        == "compliance_risk_officer.json"
    )
    assert fixture_filename_for_request_name("manager_coordinator") == "manager_coordinator.json"


def test_sanitize_captured_body_removes_unstable_metadata_and_preserves_nested_shape() -> None:
    raw_body = {
        "id": "msg_123",
        "created_at": "2026-01-01T00:00:00Z",
        "content": [
            {
                "type": "text",
                "text": "{\"summary_zh\":\"稳健\",\"summary_en\":\"Steady\"}",
                "id": "block_456",
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 8,
            "request_id": "req_789",
        },
        "nested": {"items": [{"created_at": "soon", "keep": "value"}]},
    }

    sanitized = sanitize_captured_body(raw_body)

    assert sanitized == {
        "content": [
            {
                "type": "text",
                "text": "{\"summary_zh\":\"稳健\",\"summary_en\":\"Steady\"}",
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 8,
        },
        "nested": {"items": [{"keep": "value"}]},
    }


def test_build_fixture_payload_keeps_request_name_phase_and_sanitized_body() -> None:
    payload = build_fixture_payload(
        request_name="market_intelligence",
        phase="structured",
        body={
            "id": "msg_123",
            "content": [{"type": "text", "text": "{\"summary_zh\":\"稳健\",\"summary_en\":\"Steady\"}"}],
        },
    )

    assert payload == {
        "request_name": "market_intelligence",
        "capture_phase": "structured",
        "body": {
            "content": [{"type": "text", "text": "{\"summary_zh\":\"稳健\",\"summary_en\":\"Steady\"}"}],
        },
    }


def test_capture_request_names_follow_provider_route_registry_source_of_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sample_capture_module.provider_module,
        "AGENT_MODEL_ROUTE_ENV_NAMES",
        {"alpha": "ALPHA", "beta": "BETA"},
    )

    assert capture_request_names() == ("alpha", "beta")


def test_capture_all_agents_returns_ordered_summary_and_writes_sanitized_fixtures_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_dir = tmp_path / "captures"
    fixtures_dir = tmp_path / "fixtures"
    capture_dir.mkdir(parents=True)
    for request_name in capture_request_names():
        _write_capture_file(capture_dir, request_name, f"new-{request_name}")

    fake_runtime = _FakeRuntime()
    monkeypatch.setattr(
        sample_capture_module,
        "_build_anthropic_provider_from_env",
        lambda: (object(), _runtime_config()),
    )
    monkeypatch.setattr(sample_capture_module.provider_module, "_build_env_values", lambda: {"x": "y"})
    monkeypatch.setattr(sample_capture_module.provider_module, "_is_raw_capture_enabled", lambda _: True)
    monkeypatch.setattr(sample_capture_module.provider_module, "_resolve_capture_dir", lambda _: capture_dir)
    monkeypatch.setattr(
        sample_capture_module,
        "AnthropicRecommendationAgentRuntime",
        lambda provider, runtime_config: fake_runtime,
    )

    summary = capture_all_agents(fixtures_dir=fixtures_dir)

    assert [item["request_name"] for item in summary] == list(capture_request_names())
    assert [item["phase"] for item in summary] == ["structured"] * len(summary)
    assert all(item["fixture_path"] is not None for item in summary)
    assert fake_runtime._run_order == list(capture_request_names())
    fixture_payload = json.loads(
        (fixtures_dir / "user_profile_analyst.json").read_text(encoding="utf-8")
    )
    assert fixture_payload["capture_phase"] == "structured"
    assert fixture_payload["body"]["content"][0]["text"] == "new-user_profile_analyst"
    assert "id" not in fixture_payload["body"]


def test_capture_cli_main_prints_summary_lines_with_default_fixtures_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_module = _load_capture_cli_module()
    monkeypatch.chdir(tmp_path)
    expected_fixtures_dir = (
        Path(cli_module.__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "anthropic_responses"
    )

    def _fake_capture_all_agents(*, risk_profile: str, fixtures_dir: Path) -> list[dict[str, str]]:
        assert risk_profile == "balanced"
        assert fixtures_dir == expected_fixtures_dir
        return [
            {
                "request_name": "user_profile_analyst",
                "phase": "structured",
                "fixture_path": "/tmp/user_profile_analyst.json",
                "error": None,
            },
            {
                "request_name": "manager_coordinator",
                "phase": "fallback",
                "fixture_path": "/tmp/manager_coordinator.json",
                "error": None,
            },
        ]

    monkeypatch.setattr(cli_module, "capture_all_agents", _fake_capture_all_agents)
    monkeypatch.setattr(sys, "argv", ["capture_anthropic_agent_responses.py"])

    result = cli_module.main()

    assert result is None
    assert capsys.readouterr().out.splitlines() == [
        "user_profile_analyst: phase=structured, fixture_path=/tmp/user_profile_analyst.json",
        "manager_coordinator: phase=fallback, fixture_path=/tmp/manager_coordinator.json",
    ]


def test_run_live_agent_smoke_uses_core_stage_sequence_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sample_capture_module, "_build_runtime_or_raise", lambda: object())
    monkeypatch.setattr(
        sample_capture_module,
        "_run_core_stage_sequence",
        lambda runtime, *, risk_profile: [
            (
                "user_profile_analyst",
                UserProfileAgentOutput(
                    risk_tier="R2",
                    liquidity_preference="high",
                    investment_horizon="one_year",
                    return_objective="capital_preservation",
                    drawdown_sensitivity="high",
                    profile_focus_zh="稳健",
                    profile_focus_en="steady",
                    derived_signals=[],
                ),
                "claude-test",
            ),
            (
                "manager_coordinator",
                ManagerCoordinatorAgentOutput(
                    recommendation_status="ready",
                    summary_zh="建议保持稳健配置。",
                    summary_en="Favor a resilient allocation.",
                    why_this_plan_zh=["理由一"],
                    why_this_plan_en=["Reason one"],
                ),
                "claude-test",
            ),
        ],
    )

    summary = run_live_agent_smoke()

    assert [item["request_name"] for item in summary] == [
        "user_profile_analyst",
        "manager_coordinator",
    ]
    assert [item["model_name"] for item in summary] == ["claude-test", "claude-test"]
    assert summary[0]["output_summary"].startswith("{\"derived_signals\":")


@pytest.mark.parametrize(
    ("risk_profile", "expected_categories"),
    [
        ("conservative", {"fund", "wealth_management"}),
        ("stable", {"fund", "wealth_management"}),
        ("balanced", {"fund", "wealth_management", "stock"}),
        ("growth", {"fund", "stock"}),
        ("aggressive", {"fund", "stock"}),
    ],
)
def test_live_sample_matrix_matches_profile_and_candidate_mix(
    risk_profile: str,
    expected_categories: set[str],
) -> None:
    candidates = sample_capture_module._build_live_candidates(risk_profile=risk_profile)
    request = sample_capture_module._build_live_request(risk_profile=risk_profile)

    assert request.riskAssessmentResult.finalProfile == risk_profile
    assert {candidate.category for candidate in candidates} == expected_categories

    if risk_profile in {"growth", "aggressive"}:
        assert any(candidate.category == "stock" for candidate in candidates)
        assert "收益" in request.userIntentText or "成长" in request.userIntentText


def test_capture_all_agents_continues_after_stage_failure_and_reports_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_dir = tmp_path / "captures"
    fixtures_dir = tmp_path / "fixtures"
    capture_dir.mkdir(parents=True)
    _write_capture_file(capture_dir, "user_profile_analyst", "user_profile_analyst")
    _write_capture_file(capture_dir, "market_intelligence", "market_intelligence")

    fake_runtime = _FakeRuntime(fail_market=True)
    monkeypatch.setattr(
        sample_capture_module,
        "_build_anthropic_provider_from_env",
        lambda: (object(), _runtime_config()),
    )
    monkeypatch.setattr(sample_capture_module.provider_module, "_build_env_values", lambda: {"x": "y"})
    monkeypatch.setattr(sample_capture_module.provider_module, "_is_raw_capture_enabled", lambda _: True)
    monkeypatch.setattr(sample_capture_module.provider_module, "_resolve_capture_dir", lambda _: capture_dir)
    monkeypatch.setattr(
        sample_capture_module,
        "AnthropicRecommendationAgentRuntime",
        lambda provider, runtime_config: fake_runtime,
    )

    with pytest.raises(CaptureRunError) as exc_info:
        capture_all_agents(fixtures_dir=fixtures_dir)

    summary = exc_info.value.summary
    assert [item["request_name"] for item in summary] == list(capture_request_names())
    assert summary[0]["error"] is None
    assert summary[1]["error"] == "market failed"
    assert summary[1]["fixture_path"] == str(fixtures_dir / "market_intelligence.json")
    assert summary[2]["error"] == "skipped because dependency market_intelligence failed"
    assert summary[2]["fixture_path"] is None
    assert summary[3]["error"] == "skipped because dependency product_match_expert failed"
    assert summary[3]["fixture_path"] is None
    assert summary[4]["error"] == "skipped because dependency market_intelligence failed"
    assert summary[4]["fixture_path"] is None


def test_latest_capture_for_request_name_ignores_unreadable_non_matching_files(tmp_path: Path) -> None:
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    (capture_dir / "broken.json").write_text("{", encoding="utf-8")
    target_path = capture_dir / "user_profile_analyst.json"
    target_path.write_text(
        json.dumps(
            {
                "request_name": "user_profile_analyst",
                "phase": "structured",
                "body": {"content": [{"type": "text", "text": "user_profile_analyst"}]},
            }
        ),
        encoding="utf-8",
    )

    path, payload = sample_capture_module._latest_capture_for_request_name(
        capture_dir,
        "user_profile_analyst",
    )

    assert path == target_path
    assert payload["request_name"] == "user_profile_analyst"
