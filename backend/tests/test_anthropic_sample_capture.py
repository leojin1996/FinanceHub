from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

import financehub_market_api.recommendation.agents.sample_capture as sample_capture_module
from financehub_market_api.recommendation.agents.contracts import (
    ExplanationAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductRankingAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.provider import AgentModelRoute, AgentRuntimeConfig
from financehub_market_api.recommendation.agents.sample_capture import (
    build_fixture_payload,
    capture_all_agents,
    capture_request_names,
    fixture_filename_for_request_name,
    sanitize_captured_body,
)
from financehub_market_api.recommendation.schemas import RuleEvaluationState


def _load_capture_cli_module() -> object:
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "capture_anthropic_agent_responses.py"
    )
    spec = importlib.util.spec_from_file_location("capture_anthropic_agent_responses_cli", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capture_request_names_covers_all_six_agent_stages() -> None:
    assert capture_request_names() == (
        "user_profile",
        "market_intelligence",
        "fund_selection",
        "wealth_selection",
        "stock_selection",
        "explanation",
    )


def test_fixture_filename_generation_is_stable_per_request_name() -> None:
    assert fixture_filename_for_request_name("user_profile") == "user_profile.json"
    assert fixture_filename_for_request_name("market_intelligence") == "market_intelligence.json"
    assert fixture_filename_for_request_name("fund_selection") == "fund_selection.json"
    assert fixture_filename_for_request_name("wealth_selection") == "wealth_selection.json"
    assert fixture_filename_for_request_name("stock_selection") == "stock_selection.json"
    assert fixture_filename_for_request_name("explanation") == "explanation.json"


def test_sanitize_captured_body_removes_unstable_metadata_and_preserves_nested_shape() -> None:
    raw_body = {
        "id": "msg_123",
        "created_at": "2026-01-01T00:00:00Z",
        "content": [
            {
                "type": "text",
                "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
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
                "text": '{"summary_zh":"稳健","summary_en":"Steady"}',
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 8,
        },
        "nested": {"items": [{"keep": "value"}]},
    }
    assert raw_body["id"] == "msg_123"
    assert raw_body["content"][0]["id"] == "block_456"
    assert raw_body["usage"]["request_id"] == "req_789"


def test_build_fixture_payload_keeps_request_name_phase_and_sanitized_body() -> None:
    payload = build_fixture_payload(
        request_name="market_intelligence",
        phase="structured",
        body={
            "id": "msg_123",
            "content": [{"type": "text", "text": '{"summary_zh":"稳健","summary_en":"Steady"}'}],
        },
    )

    assert payload == {
        "request_name": "market_intelligence",
        "capture_phase": "structured",
        "body": {
            "content": [{"type": "text", "text": '{"summary_zh":"稳健","summary_en":"Steady"}'}],
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

    request_names = capture_request_names()
    for index, request_name in enumerate(request_names):
        payload = {
            "request_name": request_name,
            "phase": "structured",
            "body": {
                "id": f"msg-{request_name}",
                "content": [{"type": "text", "text": f"new-{request_name}"}],
            },
        }
        capture_path = capture_dir / f"{index:02d}-{request_name}.json"
        capture_path.write_text(json.dumps(payload), encoding="utf-8")
        if request_name == "user_profile":
            old_payload = {
                "request_name": request_name,
                "phase": "structured",
                "body": {
                    "id": "old-user-profile",
                    "content": [{"type": "text", "text": "old-user_profile"}],
                },
            }
            old_path = capture_dir / "00-user_profile-old.json"
            old_path.write_text(json.dumps(old_payload), encoding="utf-8")
            old_mtime = capture_path.stat().st_mtime - 60
            old_path.touch()
            os.utime(old_path, (old_mtime, old_mtime))

    runtime_config = AgentRuntimeConfig(
        providers={},
        agent_routes={
            request_name: AgentModelRoute(provider_name="anthropic", model_name="claude-test")
            for request_name in request_names
        },
        request_timeout_seconds=7.5,
    )
    monkeypatch.setattr(
        sample_capture_module,
        "_build_anthropic_provider_from_env",
        lambda: (object(), runtime_config),
    )
    monkeypatch.setattr(sample_capture_module.provider_module, "_build_env_values", lambda: {"x": "y"})
    monkeypatch.setattr(sample_capture_module.provider_module, "_is_raw_capture_enabled", lambda _: True)
    monkeypatch.setattr(
        sample_capture_module.provider_module,
        "_resolve_capture_dir",
        lambda _: capture_dir,
    )
    monkeypatch.setattr(
        sample_capture_module.UserProfileRuntimeAgent,
        "run",
        lambda self, user_profile: UserProfileAgentOutput(
            profile_focus_zh="稳健",
            profile_focus_en="steady",
        ),
    )
    monkeypatch.setattr(
        sample_capture_module.MarketIntelligenceRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, fallback_context: MarketIntelligenceAgentOutput(
            summary_zh="市场平稳",
            summary_en="Market is steady",
        ),
    )
    monkeypatch.setattr(
        sample_capture_module.FundSelectionRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, candidates: ProductRankingAgentOutput(
            ranked_ids=[candidate.id for candidate in candidates]
        ),
    )
    monkeypatch.setattr(
        sample_capture_module.WealthSelectionRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, candidates: ProductRankingAgentOutput(
            ranked_ids=[candidate.id for candidate in candidates]
        ),
    )
    monkeypatch.setattr(
        sample_capture_module.StockSelectionRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, candidates: ProductRankingAgentOutput(
            ranked_ids=[candidate.id for candidate in candidates]
        ),
    )
    monkeypatch.setattr(
        sample_capture_module.ExplanationRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, market_context: ExplanationAgentOutput(
            why_this_plan_zh=["理由一"],
            why_this_plan_en=["Reason one"],
        ),
    )

    summary = capture_all_agents(fixtures_dir=fixtures_dir)

    assert [item["request_name"] for item in summary] == list(request_names)
    assert [item["phase"] for item in summary] == ["structured"] * len(request_names)
    assert all(item["fixture_path"] is not None for item in summary)
    user_profile_fixture = fixtures_dir / "user_profile.json"
    fixture_payload = json.loads(user_profile_fixture.read_text(encoding="utf-8"))
    assert fixture_payload["capture_phase"] == "structured"
    assert fixture_payload["body"]["content"][0]["text"] == "new-user_profile"
    assert "id" not in fixture_payload["body"]


def test_capture_all_agents_fails_when_fallback_state_is_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_config = AgentRuntimeConfig(
        providers={},
        agent_routes={
            request_name: AgentModelRoute(provider_name="anthropic", model_name="claude-test")
            for request_name in capture_request_names()
        },
        request_timeout_seconds=7.5,
    )
    monkeypatch.setattr(
        sample_capture_module,
        "_build_anthropic_provider_from_env",
        lambda: (object(), runtime_config),
    )
    monkeypatch.setattr(sample_capture_module.provider_module, "_build_env_values", lambda: {"x": "y"})
    monkeypatch.setattr(sample_capture_module.provider_module, "_is_raw_capture_enabled", lambda _: True)
    monkeypatch.setattr(
        sample_capture_module.provider_module,
        "_resolve_capture_dir",
        lambda _: tmp_path / "captures",
    )
    monkeypatch.setattr(
        sample_capture_module.RuleBasedFallbackEngine,
        "run",
        lambda self, user_profile: RuleEvaluationState(),
    )

    with pytest.raises(RuntimeError, match="Fallback state is incomplete"):
        capture_all_agents()


def test_capture_cli_main_prints_summary_lines_with_default_fixtures_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_module = _load_capture_cli_module()
    monkeypatch.chdir(tmp_path)
    expected_fixtures_dir = (
        Path(cli_module.__file__).resolve().parents[1] / "tests" / "fixtures" / "anthropic_responses"
    )

    def _fake_capture_all_agents(*, risk_profile: str, fixtures_dir: Path) -> list[dict[str, str]]:
        assert risk_profile == "balanced"
        assert fixtures_dir == expected_fixtures_dir
        return [
            {
                "request_name": "user_profile",
                "phase": "structured",
                "fixture_path": "/tmp/user_profile.json",
            },
            {
                "request_name": "explanation",
                "phase": "fallback",
                "fixture_path": "/tmp/explanation.json",
            },
        ]

    monkeypatch.setattr(cli_module, "capture_all_agents", _fake_capture_all_agents)
    monkeypatch.setattr(sys, "argv", ["capture_anthropic_agent_responses.py"])

    result = cli_module.main()

    assert result is None
    assert capsys.readouterr().out.splitlines() == [
        "user_profile: phase=structured, fixture_path=/tmp/user_profile.json",
        "explanation: phase=fallback, fixture_path=/tmp/explanation.json",
    ]


def test_capture_all_agents_executes_all_runtime_agents_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_names = capture_request_names()
    runtime_config = AgentRuntimeConfig(
        providers={},
        agent_routes={
            request_name: AgentModelRoute(provider_name="anthropic", model_name="claude-test")
            for request_name in request_names
        },
        request_timeout_seconds=7.5,
    )
    monkeypatch.setattr(
        sample_capture_module,
        "_build_anthropic_provider_from_env",
        lambda: (object(), runtime_config),
    )
    monkeypatch.setattr(sample_capture_module.provider_module, "_build_env_values", lambda: {"x": "y"})
    monkeypatch.setattr(sample_capture_module.provider_module, "_is_raw_capture_enabled", lambda _: True)
    monkeypatch.setattr(
        sample_capture_module.provider_module,
        "_resolve_capture_dir",
        lambda _: Path("/tmp/not-used"),
    )

    run_order: list[str] = []

    def _latest_capture_for_request_name(
        capture_dir: Path, request_name: str
    ) -> tuple[Path, dict[str, object]]:
        del capture_dir
        return Path(f"/tmp/{request_name}.json"), {
            "request_name": request_name,
            "phase": "structured",
            "body": {"content": [{"type": "text", "text": request_name}]},
        }

    monkeypatch.setattr(
        sample_capture_module,
        "_latest_capture_for_request_name",
        _latest_capture_for_request_name,
    )

    monkeypatch.setattr(
        sample_capture_module.UserProfileRuntimeAgent,
        "run",
        lambda self, user_profile: run_order.append("user_profile")
        or UserProfileAgentOutput(profile_focus_zh="稳健", profile_focus_en="steady"),
    )
    monkeypatch.setattr(
        sample_capture_module.MarketIntelligenceRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, fallback_context: run_order.append(
            "market_intelligence"
        )
        or MarketIntelligenceAgentOutput(summary_zh="市场平稳", summary_en="Market is steady"),
    )
    monkeypatch.setattr(
        sample_capture_module.FundSelectionRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, candidates: run_order.append("fund_selection")
        or ProductRankingAgentOutput(ranked_ids=[candidate.id for candidate in candidates]),
    )
    monkeypatch.setattr(
        sample_capture_module.WealthSelectionRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, candidates: run_order.append("wealth_selection")
        or ProductRankingAgentOutput(ranked_ids=[candidate.id for candidate in candidates]),
    )
    monkeypatch.setattr(
        sample_capture_module.StockSelectionRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, candidates: run_order.append("stock_selection")
        or ProductRankingAgentOutput(ranked_ids=[candidate.id for candidate in candidates]),
    )
    monkeypatch.setattr(
        sample_capture_module.ExplanationRuntimeAgent,
        "run",
        lambda self, user_profile, profile_focus, market_context: run_order.append("explanation")
        or ExplanationAgentOutput(why_this_plan_zh=["理由一"], why_this_plan_en=["Reason one"]),
    )

    summary = capture_all_agents()

    assert [item["request_name"] for item in summary] == list(request_names)
    assert run_order == list(request_names)


def test_capture_all_agents_surfaces_provider_config_missing_before_capture_toggle_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sample_capture_module.provider_module, "_build_env_values", lambda: {})
    monkeypatch.setattr(sample_capture_module.provider_module, "_is_raw_capture_enabled", lambda _: False)
    monkeypatch.setattr(
        sample_capture_module,
        "_build_anthropic_provider_from_env",
        lambda: (_ for _ in ()).throw(RuntimeError("Anthropic provider config is missing.")),
    )

    with pytest.raises(RuntimeError, match="Anthropic provider config is missing"):
        capture_all_agents()
