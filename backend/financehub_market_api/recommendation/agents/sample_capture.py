from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Callable, TypedDict, TypeVar, cast

from financehub_market_api.models import RiskProfile
from financehub_market_api.recommendation.agents.anthropic_runtime import (
    ExplanationRuntimeAgent,
    FundSelectionRuntimeAgent,
    MarketIntelligenceRuntimeAgent,
    StockSelectionRuntimeAgent,
    UserProfileRuntimeAgent,
    WealthSelectionRuntimeAgent,
)
from financehub_market_api.recommendation.agents.interfaces import StructuredOutputProvider
from financehub_market_api.recommendation.agents import provider as provider_module
from financehub_market_api.recommendation.agents.provider import (
    ANTHROPIC_PROVIDER_NAME,
    AgentModelRoute,
    AgentRuntimeConfig,
    LLM_CAPTURE_RAW_RESPONSES_ENV,
    build_provider,
)
from financehub_market_api.recommendation.repositories import StaticCandidateRepository
from financehub_market_api.recommendation.rules import RuleBasedFallbackEngine, map_user_profile

_UNSTABLE_CAPTURE_KEYS = frozenset({"id", "created_at", "request_id"})


class CaptureSummary(TypedDict):
    request_name: str
    phase: str | None
    fixture_path: str | None
    error: str | None


class CaptureRunError(RuntimeError):
    def __init__(self, summary: list[CaptureSummary]) -> None:
        self.summary = summary
        failures = [
            f"{item['request_name']}: {item['error']}"
            for item in summary
            if item["error"] is not None
        ]
        super().__init__("Capture completed with failures: " + "; ".join(failures))


_T = TypeVar("_T")


def capture_request_names() -> tuple[str, ...]:
    return tuple(provider_module.AGENT_MODEL_ROUTE_ENV_NAMES)


def fixture_filename_for_request_name(request_name: str) -> str:
    if request_name not in capture_request_names():
        raise ValueError(f"unsupported request_name: {request_name}")
    return f"{request_name}.json"


def sanitize_captured_body(body: object) -> object:
    if isinstance(body, Mapping):
        return {
            key: sanitize_captured_body(value)
            for key, value in body.items()
            if key not in _UNSTABLE_CAPTURE_KEYS
        }
    if isinstance(body, list):
        return [sanitize_captured_body(item) for item in body]
    return body


def build_fixture_payload(*, request_name: str, phase: str, body: object) -> dict[str, object]:
    if request_name not in capture_request_names():
        raise ValueError(f"unsupported request_name: {request_name}")
    return {
        "request_name": request_name,
        "capture_phase": phase,
        "body": sanitize_captured_body(body),
    }


def _build_anthropic_provider_from_env() -> tuple[StructuredOutputProvider, AgentRuntimeConfig]:
    runtime_config = AgentRuntimeConfig.from_env()
    provider_config = runtime_config.providers.get(ANTHROPIC_PROVIDER_NAME)
    if provider_config is None:
        raise RuntimeError(
            "Anthropic provider config is missing. Set FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY "
            "and FINANCEHUB_LLM_PROVIDER_ANTHROPIC_BASE_URL (or compatible aliases)."
        )
    provider = build_provider(provider_config)
    return cast(StructuredOutputProvider, provider), runtime_config


def _agent_route_or_raise(routes: Mapping[str, AgentModelRoute], request_name: str) -> AgentModelRoute:
    route = routes.get(request_name)
    if route is None:
        raise RuntimeError(f"Missing model route for request_name={request_name}.")
    if route.provider_name != ANTHROPIC_PROVIDER_NAME:
        raise RuntimeError(
            f"Invalid provider for request_name={request_name}: {route.provider_name}. "
            f"Expected {ANTHROPIC_PROVIDER_NAME}."
        )
    if not route.model_name.strip():
        raise RuntimeError(f"Missing model_name for request_name={request_name}.")
    return route


def _load_capture_payload(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to read capture file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Capture file {path} must contain a top-level object.")
    return payload


def _path_may_match_request_name(path: Path, request_name: str) -> bool:
    return request_name in path.stem


def _latest_capture_for_request_name(capture_dir: Path, request_name: str) -> tuple[Path, dict[str, object]]:
    paths = sorted(
        capture_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for path in paths:
        try:
            payload = _load_capture_payload(path)
        except RuntimeError:
            if _path_may_match_request_name(path, request_name):
                raise
            continue
        if payload.get("request_name") != request_name:
            continue
        return path, payload
    raise RuntimeError(
        f"No raw capture found for request_name={request_name} in {capture_dir}. "
        f"Set {LLM_CAPTURE_RAW_RESPONSES_ENV}=true before running capture."
    )


def _write_fixture_payload(
    *,
    fixtures_dir: Path,
    request_name: str,
    phase: str,
    body: object,
) -> Path:
    fixture_path = fixtures_dir / fixture_filename_for_request_name(request_name)
    payload = build_fixture_payload(request_name=request_name, phase=phase, body=body)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return fixture_path


def capture_all_agents(
    *,
    risk_profile: RiskProfile = "balanced",
    fixtures_dir: str | Path | None = None,
) -> list[CaptureSummary]:
    env_values = provider_module._build_env_values()
    provider, runtime_config = _build_anthropic_provider_from_env()
    if not provider_module._is_raw_capture_enabled(env_values):
        raise RuntimeError(
            f"{LLM_CAPTURE_RAW_RESPONSES_ENV} must be set to a truthy value to capture raw responses."
        )

    user_profile = map_user_profile(risk_profile)
    state = RuleBasedFallbackEngine(StaticCandidateRepository()).run(user_profile)
    if state.market_context is None or state.allocation is None or state.aggressive_allocation is None:
        raise RuntimeError("Fallback state is incomplete; cannot run capture workflow.")

    timeout_seconds = runtime_config.request_timeout_seconds
    routes = runtime_config.agent_routes
    capture_dir = provider_module._resolve_capture_dir(env_values)
    fixtures_path = Path(fixtures_dir) if fixtures_dir is not None else None
    summary: list[CaptureSummary] = []
    stage_errors: dict[str, str] = {}

    def _format_error(exc: Exception) -> str:
        message = str(exc).strip()
        return message or exc.__class__.__name__

    def _record_summary(request_name: str, error: str | None, *, attempt_capture: bool) -> None:
        phase: str | None = None
        fixture_path_value: str | None = None
        summary_error = error

        if attempt_capture:
            try:
                _, capture_payload = _latest_capture_for_request_name(capture_dir, request_name)
            except RuntimeError as exc:
                capture_error = _format_error(exc)
                if summary_error is None:
                    summary_error = capture_error
                else:
                    summary_error = f"{summary_error}; {capture_error}"
            else:
                phase = str(capture_payload.get("phase", "unknown"))
                if fixtures_path is not None:
                    fixture_path = _write_fixture_payload(
                        fixtures_dir=fixtures_path,
                        request_name=request_name,
                        phase=phase,
                        body=capture_payload.get("body"),
                    )
                    fixture_path_value = str(fixture_path)

        summary.append(
            CaptureSummary(
                request_name=request_name,
                phase=phase,
                fixture_path=fixture_path_value,
                error=summary_error,
            )
        )
        if summary_error is not None:
            stage_errors[request_name] = summary_error

    def _run_stage(
        request_name: str,
        dependencies: tuple[str, ...],
        runner: Callable[[], _T],
    ) -> _T | None:
        for dependency in dependencies:
            if dependency in stage_errors:
                _record_summary(
                    request_name,
                    f"skipped: {dependency} failed",
                    attempt_capture=False,
                )
                return None

        try:
            result = runner()
        except Exception as exc:
            _record_summary(request_name, _format_error(exc), attempt_capture=True)
            return None

        _record_summary(request_name, None, attempt_capture=True)
        return result

    profile_focus = _run_stage(
        "user_profile",
        (),
        lambda: UserProfileRuntimeAgent(
            provider,
            _agent_route_or_raise(routes, "user_profile").model_name,
            timeout_seconds,
            "user_profile",
        ).run(user_profile),
    )
    market_context = _run_stage(
        "market_intelligence",
        ("user_profile",),
        lambda: MarketIntelligenceRuntimeAgent(
            provider,
            _agent_route_or_raise(routes, "market_intelligence").model_name,
            timeout_seconds,
            "market_intelligence",
        ).run(user_profile, profile_focus, state.market_context),
    )
    _run_stage(
        "fund_selection",
        ("user_profile",),
        lambda: FundSelectionRuntimeAgent(
            provider,
            _agent_route_or_raise(routes, "fund_selection").model_name,
            timeout_seconds,
            "fund_selection",
        ).run(user_profile, profile_focus, state.fund_items),
    )
    _run_stage(
        "wealth_selection",
        ("user_profile",),
        lambda: WealthSelectionRuntimeAgent(
            provider,
            _agent_route_or_raise(routes, "wealth_selection").model_name,
            timeout_seconds,
            "wealth_selection",
        ).run(user_profile, profile_focus, state.wealth_management_items),
    )
    _run_stage(
        "stock_selection",
        ("user_profile",),
        lambda: StockSelectionRuntimeAgent(
            provider,
            _agent_route_or_raise(routes, "stock_selection").model_name,
            timeout_seconds,
            "stock_selection",
        ).run(user_profile, profile_focus, state.stock_items),
    )
    _run_stage(
        "explanation",
        ("user_profile", "market_intelligence"),
        lambda: ExplanationRuntimeAgent(
            provider,
            _agent_route_or_raise(routes, "explanation").model_name,
            timeout_seconds,
            "explanation",
        ).run(user_profile, profile_focus, market_context),
    )

    if stage_errors:
        raise CaptureRunError(summary)
    return summary
