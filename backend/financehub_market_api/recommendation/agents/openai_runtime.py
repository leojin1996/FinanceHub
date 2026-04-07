from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pydantic import ValidationError

from financehub_market_api.recommendation.agents.contracts import (
    ExplanationAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductRankingAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.interfaces import StructuredOutputProvider
from financehub_market_api.recommendation.agents.provider import (
    OPENAI_PROVIDER_NAME,
    AgentModelRoute,
    AgentRuntimeConfig,
    DEFAULT_AGENT_MODEL_ROUTES,
    LLMInvalidResponseError,
    LLMProviderError,
    build_provider,
)
from financehub_market_api.recommendation.schemas import (
    CandidateProduct,
    DegradedWarning,
    MarketContext,
    RuleEvaluationState,
    UserProfile,
)


def _render_candidates(candidates: list[CandidateProduct]) -> str:
    return "\n".join(
        f"- id={candidate.id}; name_zh={candidate.name_zh}; name_en={candidate.name_en}; risk={candidate.risk_level}"
        for candidate in candidates
    )


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


class _BaseStructuredOutputAgent:
    def __init__(self, provider: StructuredOutputProvider, model_name: str) -> None:
        self._provider = provider
        self._model_name = model_name

    def _execute(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, object],
        timeout_seconds: float = 12.0,
    ) -> dict[str, object]:
        try:
            return self._provider.chat_json(
                model_name=self._model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_schema=response_schema,
                timeout_seconds=timeout_seconds,
            )
        except LLMInvalidResponseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LLMProviderError(f"structured-output provider request failed: {exc}") from exc


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
                "Return ranked_ids as a prioritized list using only existing IDs."
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
                "Return ranked_ids as a prioritized list using only existing IDs."
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
                "Return ranked_ids as a prioritized list using only existing IDs."
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


class OpenAIMultiAgentRuntime:
    def __init__(
        self,
        *,
        provider: StructuredOutputProvider | None = None,
        model_name: str | None = None,
        providers: Mapping[str, StructuredOutputProvider] | None = None,
        agent_routes: Mapping[str, AgentModelRoute] | None = None,
    ) -> None:
        if provider is not None and providers is not None:
            raise ValueError("pass either provider/model_name or providers/agent_routes, not both")

        if providers is None:
            legacy_model_name = model_name or "unconfigured"
            self._providers = {OPENAI_PROVIDER_NAME: provider} if provider is not None else {}
            self._agent_routes = {
                agent_name: AgentModelRoute(
                    provider_name=OPENAI_PROVIDER_NAME,
                    model_name=legacy_model_name,
                )
                for agent_name in DEFAULT_AGENT_MODEL_ROUTES
            }
        else:
            self._providers = dict(providers)
            self._agent_routes = {
                agent_name: AgentModelRoute(
                    provider_name=route.provider_name,
                    model_name=route.model_name,
                )
                for agent_name, route in DEFAULT_AGENT_MODEL_ROUTES.items()
            }
            for agent_name, route in (agent_routes or {}).items():
                self._agent_routes[agent_name] = route

    @classmethod
    def from_env(cls) -> OpenAIMultiAgentRuntime:
        runtime_config = AgentRuntimeConfig.from_env()
        providers: dict[str, StructuredOutputProvider] = {}
        for provider_name, provider_config in runtime_config.providers.items():
            try:
                providers[provider_name] = build_provider(provider_config)
            except ValueError:
                continue
        return cls(providers=providers, agent_routes=runtime_config.agent_routes)

    def _missing_provider_warning(self) -> DegradedWarning | None:
        if not self._providers:
            return DegradedWarning(
                stage="runtime",
                code="llm_config_missing",
                message=(
                    "LLM providers are disabled because no provider credentials were found. "
                    "Configure either FINANCEHUB_LLM_PROVIDER_OPENAI_API_KEY/BASE_URL, "
                    "legacy FINANCEHUB_LLM_API_KEY/BASE_URL, or "
                    "FINANCEHUB_LLM_PROVIDER_ANTHROPIC_API_KEY/BASE_URL "
                    "(ANTHROPIC_AUTH_TOKEN/ANTHROPIC_BASE_URL also supported)."
                ),
            )

        for agent_name in DEFAULT_AGENT_MODEL_ROUTES:
            route = self._agent_routes.get(agent_name)
            if route is None or not route.provider_name.strip() or not route.model_name.strip():
                return DegradedWarning(
                    stage=agent_name,
                    code="agent_model_route_invalid",
                    message=f"{agent_name} route must include both provider_name and model_name.",
                )
            if route.provider_name not in self._providers:
                return DegradedWarning(
                    stage=agent_name,
                    code="agent_provider_missing",
                    message=(
                        f"{agent_name} requires provider '{route.provider_name}', but that provider "
                        "is not configured."
                    ),
                )
        return None

    def _build_agent(
        self,
        agent_name: str,
        agent_type: type[_BaseStructuredOutputAgent],
    ) -> _BaseStructuredOutputAgent:
        route = self._agent_routes[agent_name]
        provider = self._providers[route.provider_name]
        return agent_type(provider, route.model_name)

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

        try:
            profile_focus = self._build_agent("user_profile", UserProfileRuntimeAgent).run(user_profile)
            market_context = self._build_agent("market_intelligence", MarketIntelligenceRuntimeAgent).run(
                user_profile,
                profile_focus,
                state.market_context,
            )
            fund_ranking = self._build_agent("fund_selection", FundSelectionRuntimeAgent).run(
                user_profile,
                profile_focus,
                state.fund_items,
            )
            wealth_ranking = self._build_agent("wealth_selection", WealthSelectionRuntimeAgent).run(
                user_profile,
                profile_focus,
                state.wealth_management_items,
            )
            stock_ranking = self._build_agent("stock_selection", StockSelectionRuntimeAgent).run(
                user_profile,
                profile_focus,
                state.stock_items,
            )
            explanation = self._build_agent("explanation", ExplanationRuntimeAgent).run(
                user_profile,
                profile_focus,
                market_context,
            )
        except (LLMInvalidResponseError, ValidationError) as exc:
            return MultiAgentRuntimeResult(
                assisted=False,
                warnings=[
                    DegradedWarning(
                        stage="agent",
                        code="invalid_agent_output",
                        message=str(exc),
                    )
                ],
            )
        except LLMProviderError as exc:
            return MultiAgentRuntimeResult(
                assisted=False,
                warnings=[
                    DegradedWarning(
                        stage="provider",
                        code="provider_error",
                        message=str(exc),
                    )
                ],
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

        ranking_checks = (
            ("fund_selection", state.fund_items, fund_ranking.ranked_ids),
            ("wealth_selection", state.wealth_management_items, wealth_ranking.ranked_ids),
            ("stock_selection", state.stock_items, stock_ranking.ranked_ids),
        )
        for stage, candidates, ranked_ids in ranking_checks:
            validation_issue = _ranking_validation_issue(candidates, ranked_ids)
            if validation_issue is not None:
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

        state.market_context = MarketContext(
            summary_zh=market_context.summary_zh,
            summary_en=market_context.summary_en,
        )
        state.fund_items = _stable_reorder(state.fund_items, fund_ranking.ranked_ids)
        state.wealth_management_items = _stable_reorder(
            state.wealth_management_items, wealth_ranking.ranked_ids
        )
        state.stock_items = _stable_reorder(state.stock_items, stock_ranking.ranked_ids)
        state.why_this_plan_zh = explanation.why_this_plan_zh
        state.why_this_plan_en = explanation.why_this_plan_en
        state.mark_applied("agent_runtime", "agent-assisted outputs applied")
        return MultiAgentRuntimeResult(assisted=True, warnings=[])
