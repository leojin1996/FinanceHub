from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from financehub_market_api.recommendation.agents.contracts import (
    ExplanationAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductRankingAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.interfaces import StructuredOutputProvider
from financehub_market_api.recommendation.agents.provider import (
    ANTHROPIC_PROVIDER_NAME,
    AgentModelRoute,
    AgentRuntimeConfig,
    DEFAULT_AGENT_MODEL_ROUTES,
    LLMInvalidResponseError,
    LLMProviderError,
    _build_env_values,
    _is_agent_trace_logging_enabled,
    build_provider,
)
from financehub_market_api.recommendation.schemas import (
    CandidateProduct,
    DegradedWarning,
    MarketContext,
    RuleEvaluationState,
    UserProfile,
)

LOGGER = logging.getLogger(__name__)

_EMPTY_PROVIDER_RESPONSE_MARKERS = (
    "provider response has no content blocks",
    "provider response has no text content block",
)
_MAX_TRACE_STRING_LENGTH = 240
_MAX_TRACE_LIST_ITEMS = 8
_MAX_TRACE_OBJECT_KEYS = 16


def _trim_trace_value(value: object) -> object:
    if isinstance(value, str):
        if len(value) <= _MAX_TRACE_STRING_LENGTH:
            return value
        return f"{value[:_MAX_TRACE_STRING_LENGTH]}..."

    if isinstance(value, Mapping):
        trimmed: dict[str, object] = {}
        for index, (key, nested_value) in enumerate(value.items()):
            if index >= _MAX_TRACE_OBJECT_KEYS:
                break
            trimmed[str(key)] = _trim_trace_value(nested_value)
        return trimmed

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_trim_trace_value(item) for item in value[:_MAX_TRACE_LIST_ITEMS]]

    return value


def _response_summary(payload: Mapping[str, object]) -> str:
    return json.dumps(_trim_trace_value(payload), ensure_ascii=False, sort_keys=True)


def _render_candidates(candidates: list[CandidateProduct]) -> str:
    lines: list[str] = []
    for candidate in candidates:
        parts = [
            f"id={candidate.id}",
            f"name_zh={candidate.name_zh}",
            f"name_en={candidate.name_en}",
            f"category={candidate.category}",
            f"risk={candidate.risk_level}",
        ]
        if candidate.code is not None:
            parts.append(f"code={candidate.code}")
        if candidate.liquidity is not None:
            parts.append(f"liquidity={candidate.liquidity}")
        if candidate.tags_zh:
            parts.append(f"tags_zh={', '.join(candidate.tags_zh)}")
        if candidate.tags_en:
            parts.append(f"tags_en={', '.join(candidate.tags_en)}")
        parts.append(f"rationale_zh={candidate.rationale_zh}")
        parts.append(f"rationale_en={candidate.rationale_en}")
        lines.append(f"- {'; '.join(parts)}")
    return "\n".join(lines)


def _stable_reorder(candidates: list[CandidateProduct], ranked_ids: list[str]) -> list[CandidateProduct]:
    by_id = {candidate.id: candidate for candidate in candidates}
    ordered: list[CandidateProduct] = []
    seen: set[str] = set()
    for product_id in ranked_ids:
        candidate = by_id.get(product_id)
        if candidate is None or product_id in seen:
            continue
        ordered.append(candidate)
        seen.add(product_id)
    if not ordered:
        return list(candidates)
    ordered.extend(candidate for candidate in candidates if candidate.id not in seen)
    return ordered


def _ranking_validation_issue(candidates: list[CandidateProduct], ranked_ids: list[str]) -> str | None:
    if not ranked_ids:
        return "ranked_ids is empty"
    candidate_ids = {candidate.id for candidate in candidates}
    unknown_ids = sorted({ranked_id for ranked_id in ranked_ids if ranked_id not in candidate_ids})
    if unknown_ids:
        return f"ranked_ids contains unknown IDs: {', '.join(unknown_ids)}"
    return None


def _build_invalid_output_warning(exc: LLMInvalidResponseError | ValidationError) -> DegradedWarning:
    message = str(exc)
    if isinstance(exc, LLMInvalidResponseError) and message in _EMPTY_PROVIDER_RESPONSE_MARKERS:
        return DegradedWarning(
            stage="provider",
            code="provider_empty_response",
            message=(
                "The configured Anthropic provider returned an empty structured response, "
                "so the recommendation fell back to the rules engine."
            ),
        )
    return DegradedWarning(
        stage="agent",
        code="invalid_agent_output",
        message=message,
    )


def _is_empty_ranked_ids_validation_error(exc: ValidationError) -> bool:
    return any(
        error.get("loc") == ("ranked_ids",) and error.get("type") == "too_short"
        for error in exc.errors()
    )


def _override_warning_stage(warning: DegradedWarning, stage: str) -> DegradedWarning:
    return DegradedWarning(stage=stage, code=warning.code, message=warning.message)


def _build_provider_warning(stage: str, exc: LLMProviderError) -> DegradedWarning:
    return DegradedWarning(
        stage=stage,
        code="provider_error",
        message=str(exc),
    )


def _fallback_profile_focus(user_profile: UserProfile) -> UserProfileAgentOutput:
    return UserProfileAgentOutput(
        profile_focus_zh=f"围绕{user_profile.label_zh}目标，优先控制波动并兼顾稳步增值。",
        profile_focus_en=(
            f"Keep the allocation aligned with the {user_profile.label_en} profile by "
            "controlling volatility first and pursuing steady appreciation."
        ),
    )


class _BaseStructuredOutputAgent:
    def __init__(
        self,
        provider: StructuredOutputProvider,
        model_name: str,
        request_timeout_seconds: float,
        request_name: str,
    ) -> None:
        self._provider = provider
        self._model_name = model_name
        self._request_timeout_seconds = request_timeout_seconds
        self._request_name = request_name

    def _execute(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
    ) -> dict[str, object]:
        env_values = _build_env_values()
        trace_logs_enabled = _is_agent_trace_logging_enabled(env_values)
        started_at = time.perf_counter()
        if trace_logs_enabled:
            LOGGER.info(
                "agent_request_start request_name=%s model_name=%s",
                self._request_name,
                self._model_name,
            )
        try:
            payload = self._provider.chat_json(
                model_name=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_schema=response_schema,
                timeout_seconds=self._request_timeout_seconds,
                request_name=self._request_name,
            )
        except LLMInvalidResponseError as exc:
            if trace_logs_enabled:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                LOGGER.info(
                    "agent_request_error request_name=%s model_name=%s duration_ms=%s "
                    "error_type=%s error_message=%s",
                    self._request_name,
                    self._model_name,
                    duration_ms,
                    type(exc).__name__,
                    json.dumps(str(exc), ensure_ascii=False),
                )
            raise
        except Exception as exc:  # noqa: BLE001
            wrapped_error = LLMProviderError(f"structured-output provider request failed: {exc}")
            if trace_logs_enabled:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                LOGGER.info(
                    "agent_request_error request_name=%s model_name=%s duration_ms=%s "
                    "error_type=%s error_message=%s",
                    self._request_name,
                    self._model_name,
                    duration_ms,
                    type(wrapped_error).__name__,
                    json.dumps(str(wrapped_error), ensure_ascii=False),
                )
            raise wrapped_error from exc

        if trace_logs_enabled:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            LOGGER.info(
                "agent_request_finish request_name=%s model_name=%s duration_ms=%s response_summary=%s",
                self._request_name,
                self._model_name,
                duration_ms,
                _response_summary(payload),
            )
        return payload


class UserProfileRuntimeAgent(_BaseStructuredOutputAgent):
    def run(self, user_profile: UserProfile) -> UserProfileAgentOutput:
        payload = self._execute(
            system_prompt="You are UserProfileAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"label_zh={user_profile.label_zh}; label_en={user_profile.label_en}. "
                "Return two concise strings: profile_focus_zh and profile_focus_en."
            ),
            response_schema=UserProfileAgentOutput.model_json_schema(),
        )
        return UserProfileAgentOutput.model_validate(payload)


class MarketIntelligenceRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        fallback_context: MarketContext,
    ) -> MarketIntelligenceAgentOutput:
        payload = self._execute(
            system_prompt="You are MarketIntelligenceAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}; "
                f"fallback_summary_zh={fallback_context.summary_zh}; fallback_summary_en={fallback_context.summary_en}. "
                "Return summary_zh and summary_en suitable for investment recommendation context."
            ),
            response_schema=MarketIntelligenceAgentOutput.model_json_schema(),
        )
        return MarketIntelligenceAgentOutput.model_validate(payload)


class FundSelectionRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> ProductRankingAgentOutput:
        payload = self._execute(
            system_prompt="You are FundSelectionAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}. "
                f"Candidates:\n{_render_candidates(candidates)}\n"
                "Return ranked_ids as a prioritized list using only existing IDs. "
                "Never return an empty list. "
                "If uncertain, return every candidate ID exactly once in the original order."
            ),
            response_schema=ProductRankingAgentOutput.model_json_schema(),
        )
        return ProductRankingAgentOutput.model_validate(payload)


class WealthSelectionRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> ProductRankingAgentOutput:
        payload = self._execute(
            system_prompt="You are WealthSelectionAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}. "
                f"Candidates:\n{_render_candidates(candidates)}\n"
                "Return ranked_ids as a prioritized list using only existing IDs. "
                "Never return an empty list. "
                "If uncertain, return every candidate ID exactly once in the original order."
            ),
            response_schema=ProductRankingAgentOutput.model_json_schema(),
        )
        return ProductRankingAgentOutput.model_validate(payload)


class StockSelectionRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> ProductRankingAgentOutput:
        payload = self._execute(
            system_prompt="You are StockSelectionAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}. "
                f"Candidates:\n{_render_candidates(candidates)}\n"
                "Return ranked_ids as a prioritized list using only existing IDs. "
                "Never return an empty list. "
                "If uncertain, return every candidate ID exactly once in the original order."
            ),
            response_schema=ProductRankingAgentOutput.model_json_schema(),
        )
        return ProductRankingAgentOutput.model_validate(payload)


class ExplanationRuntimeAgent(_BaseStructuredOutputAgent):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
    ) -> ExplanationAgentOutput:
        payload = self._execute(
            system_prompt="You are ExplanationAgent. Return strict JSON only.",
            user_prompt=(
                f"model={self._model_name}; risk_profile={user_profile.risk_profile}; "
                f"profile_focus_zh={profile_focus.profile_focus_zh}; profile_focus_en={profile_focus.profile_focus_en}; "
                f"market_summary_zh={market_context.summary_zh}; market_summary_en={market_context.summary_en}. "
                "Return why_this_plan_zh and why_this_plan_en as concise bullet list items."
            ),
            response_schema=ExplanationAgentOutput.model_json_schema(),
        )
        return ExplanationAgentOutput.model_validate(payload)


@dataclass(frozen=True)
class MultiAgentRuntimeResult:
    assisted: bool
    warnings: list[DegradedWarning]


class AnthropicMultiAgentRuntime:
    def __init__(
        self,
        *,
        provider: StructuredOutputProvider | None = None,
        model_name: str | None = None,
        providers: Mapping[str, StructuredOutputProvider] | None = None,
        agent_routes: Mapping[str, AgentModelRoute] | None = None,
        request_timeout_seconds: float = 12.0,
    ) -> None:
        if provider is not None and providers is not None:
            raise ValueError("pass either provider/model_name or providers/agent_routes, not both")
        self._request_timeout_seconds = request_timeout_seconds

        if providers is None:
            legacy_model_name = model_name or "unconfigured"
            self._providers = {ANTHROPIC_PROVIDER_NAME: provider} if provider is not None else {}
            self._agent_routes = {
                agent_name: AgentModelRoute(
                    provider_name=ANTHROPIC_PROVIDER_NAME,
                    model_name=legacy_model_name,
                )
                for agent_name in DEFAULT_AGENT_MODEL_ROUTES
            }
            return

        self._providers = dict(providers)
        self._agent_routes = {
            agent_name: AgentModelRoute(
                provider_name=route.provider_name,
                model_name=route.model_name,
            )
            for agent_name, route in DEFAULT_AGENT_MODEL_ROUTES.items()
        }
        for agent_name, route in (agent_routes or {}).items():
            self._agent_routes[agent_name] = AgentModelRoute(
                provider_name=route.provider_name,
                model_name=route.model_name,
            )

    @classmethod
    def from_env(cls) -> AnthropicMultiAgentRuntime:
        runtime_config = AgentRuntimeConfig.from_env()
        providers: dict[str, StructuredOutputProvider] = {}
        for provider_name, provider_config in runtime_config.providers.items():
            try:
                providers[provider_name] = build_provider(provider_config)
            except ValueError:
                continue
        return cls(
            providers=providers,
            agent_routes=runtime_config.agent_routes,
            request_timeout_seconds=runtime_config.request_timeout_seconds,
        )

    def _missing_provider_warning(self) -> DegradedWarning | None:
        if ANTHROPIC_PROVIDER_NAME not in self._providers:
            return DegradedWarning(
                stage="runtime",
                code="llm_config_missing",
                message=(
                    "Anthropic agents are disabled because no Anthropic provider credentials were found. "
                    "Configure FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY/BASE_URL "
                    "(ANTHROPIC_AUTH_TOKEN/ANTHROPIC_BASE_URL also supported)."
                ),
            )

        for agent_name in DEFAULT_AGENT_MODEL_ROUTES:
            route = self._agent_routes.get(agent_name)
            if route is None or not route.model_name.strip():
                return DegradedWarning(
                    stage=agent_name,
                    code="agent_model_route_invalid",
                    message=f"{agent_name} route must include a model_name.",
                )
            if route.provider_name != ANTHROPIC_PROVIDER_NAME:
                return DegradedWarning(
                    stage=agent_name,
                    code="agent_provider_invalid",
                    message=f"{agent_name} must use provider '{ANTHROPIC_PROVIDER_NAME}'.",
                )
        return None

    def _build_agent(
        self,
        agent_name: str,
        agent_type: type[_BaseStructuredOutputAgent],
    ) -> _BaseStructuredOutputAgent:
        route = self._agent_routes[agent_name]
        provider = self._providers[ANTHROPIC_PROVIDER_NAME]
        return agent_type(provider, route.model_name, self._request_timeout_seconds, agent_name)

    def apply(self, user_profile: UserProfile, state: RuleEvaluationState) -> MultiAgentRuntimeResult:
        validation_warning = self._missing_provider_warning()
        if validation_warning is not None:
            return MultiAgentRuntimeResult(assisted=False, warnings=[validation_warning])

        if state.market_context is None:
            return MultiAgentRuntimeResult(
                assisted=False,
                warnings=[
                    DegradedWarning(
                        stage="runtime",
                        code="fallback_state_incomplete",
                        message="rule-based state is missing market context; agent assistance skipped.",
                    )
                ],
            )

        warnings: list[DegradedWarning] = []
        applied_agent_output = False

        try:
            profile_focus = self._build_agent("user_profile", UserProfileRuntimeAgent).run(user_profile)
        except (LLMInvalidResponseError, ValidationError) as exc:
            return MultiAgentRuntimeResult(
                assisted=False,
                warnings=[_build_invalid_output_warning(exc)],
            )
        except LLMProviderError as exc:
            warnings.append(_build_provider_warning("user_profile", exc))
            profile_focus = _fallback_profile_focus(user_profile)
        except Exception as exc:  # noqa: BLE001
            return MultiAgentRuntimeResult(
                assisted=False,
                warnings=[
                    DegradedWarning(
                        stage="runtime",
                        code="agent_runtime_error",
                        message=str(exc),
                    )
                ],
            )

        try:
            market_context = self._build_agent("market_intelligence", MarketIntelligenceRuntimeAgent).run(
                user_profile,
                profile_focus,
                state.market_context,
            )
        except (LLMInvalidResponseError, ValidationError) as exc:
            return MultiAgentRuntimeResult(
                assisted=False,
                warnings=[_build_invalid_output_warning(exc)],
            )
        except LLMProviderError as exc:
            warnings.append(_build_provider_warning("market_intelligence", exc))
            market_context = MarketIntelligenceAgentOutput(
                summary_zh=state.market_context.summary_zh,
                summary_en=state.market_context.summary_en,
            )
        except Exception as exc:  # noqa: BLE001
            return MultiAgentRuntimeResult(
                assisted=False,
                warnings=[
                    DegradedWarning(
                        stage="runtime",
                        code="agent_runtime_error",
                        message=str(exc),
                    )
                ],
            )

        ranking_steps = (
            ("fund_selection", FundSelectionRuntimeAgent, "fund_items"),
            ("wealth_selection", WealthSelectionRuntimeAgent, "wealth_management_items"),
            ("stock_selection", StockSelectionRuntimeAgent, "stock_items"),
        )
        ranking_outputs: dict[str, list[str]] = {}
        for stage, agent_type, state_attr in ranking_steps:
            candidates = getattr(state, state_attr)
            try:
                ranking = self._build_agent(stage, agent_type).run(
                    user_profile,
                    profile_focus,
                    candidates,
                )
            except LLMInvalidResponseError as exc:
                warning = _build_invalid_output_warning(exc)
                if warning.code == "provider_empty_response":
                    warnings.append(_override_warning_stage(warning, stage))
                    continue
                return MultiAgentRuntimeResult(
                    assisted=False,
                    warnings=[warning],
                )
            except LLMProviderError as exc:
                warnings.append(
                    DegradedWarning(
                        stage=stage,
                        code="provider_error",
                        message=str(exc),
                    )
                )
                continue
            except ValidationError as exc:
                if _is_empty_ranked_ids_validation_error(exc):
                    warnings.append(
                        DegradedWarning(
                            stage=stage,
                            code="agent_ranking_unusable",
                            message=f"{stage} ranking validation failed: ranked_ids is empty.",
                        )
                    )
                    continue
                return MultiAgentRuntimeResult(
                    assisted=False,
                    warnings=[_build_invalid_output_warning(exc)],
                )

            ranked_ids = ranking.ranked_ids
            validation_issue = _ranking_validation_issue(candidates, ranked_ids)
            if validation_issue is not None:
                if validation_issue == "ranked_ids is empty":
                    warnings.append(
                        DegradedWarning(
                            stage=stage,
                            code="agent_ranking_unusable",
                            message=f"{stage} ranking validation failed: {validation_issue}.",
                        )
                    )
                    continue
                return MultiAgentRuntimeResult(
                    assisted=False,
                    warnings=[
                        DegradedWarning(
                            stage=stage,
                            code="agent_ranking_unusable",
                            message=f"{stage} ranking validation failed: {validation_issue}.",
                        )
                    ],
                )
            ranking_outputs[state_attr] = ranked_ids
            applied_agent_output = True

        try:
            explanation = self._build_agent("explanation", ExplanationRuntimeAgent).run(
                user_profile,
                profile_focus,
                market_context,
            )
        except (LLMInvalidResponseError, ValidationError) as exc:
            return MultiAgentRuntimeResult(
                assisted=False,
                warnings=[_build_invalid_output_warning(exc)],
            )
        except LLMProviderError as exc:
            warnings.append(_build_provider_warning("explanation", exc))
            explanation = ExplanationAgentOutput(
                why_this_plan_zh=list(state.why_this_plan_zh),
                why_this_plan_en=list(state.why_this_plan_en),
            )

        if not any(warning.stage == "market_intelligence" for warning in warnings):
            state.market_context = MarketContext(
                summary_zh=market_context.summary_zh,
                summary_en=market_context.summary_en,
            )
            applied_agent_output = True
        for state_attr, ranked_ids in ranking_outputs.items():
            setattr(state, state_attr, _stable_reorder(getattr(state, state_attr), ranked_ids))
        if not any(warning.stage == "explanation" for warning in warnings):
            state.why_this_plan_zh = explanation.why_this_plan_zh
            state.why_this_plan_en = explanation.why_this_plan_en
            applied_agent_output = True
        if applied_agent_output:
            state.mark_applied("agent_runtime", "agent-assisted outputs applied")
        return MultiAgentRuntimeResult(assisted=applied_agent_output, warnings=warnings)
