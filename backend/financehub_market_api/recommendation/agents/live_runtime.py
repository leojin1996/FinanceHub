from __future__ import annotations

from dataclasses import dataclass

from financehub_market_api.recommendation.agents.anthropic_runtime import (
    ExplanationRuntimeAgent,
    FundSelectionRuntimeAgent,
    MarketIntelligenceRuntimeAgent,
    StockSelectionRuntimeAgent,
    UserProfileRuntimeAgent,
    WealthSelectionRuntimeAgent,
)
from financehub_market_api.recommendation.agents.contracts import (
    ExplanationAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductRankingAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.interfaces import (
    StructuredOutputProvider,
)
from financehub_market_api.recommendation.agents.provider import (
    ANTHROPIC_PROVIDER_NAME,
    AgentModelRoute,
    AgentRuntimeConfig,
    build_provider,
)
from financehub_market_api.recommendation.agents.runtime_context import (
    AgentPromptContext,
    AgentToolCallRecord,
    SelectedPlanContext,
    coerce_selected_plan_context,
)
from financehub_market_api.recommendation.schemas import (
    CandidateProduct,
    MarketContext,
    UserProfile,
)


@dataclass(frozen=True)
class AgentInvocationMetadata:
    provider_name: str
    model_name: str
    tool_calls: tuple[AgentToolCallRecord, ...] = ()


class AnthropicRecommendationAgentRuntime:
    def __init__(
        self,
        *,
        provider: StructuredOutputProvider,
        runtime_config: AgentRuntimeConfig,
    ) -> None:
        self._provider = provider
        self._runtime_config = runtime_config

    @property
    def request_timeout_seconds(self) -> float:
        return self._runtime_config.request_timeout_seconds

    @classmethod
    def from_env(cls) -> AnthropicRecommendationAgentRuntime | None:
        runtime_config = AgentRuntimeConfig.from_env()
        provider_config = runtime_config.providers.get(ANTHROPIC_PROVIDER_NAME)
        if provider_config is None:
            return None
        provider = build_provider(provider_config)
        return cls(provider=provider, runtime_config=runtime_config)

    def analyze_user_profile(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[UserProfileAgentOutput, AgentInvocationMetadata]:
        route = self._route_or_raise("user_profile")
        output, tool_calls = UserProfileRuntimeAgent(
            self._provider,
            route.model_name,
            self.request_timeout_seconds,
            "user_profile",
        ).run_with_trace(user_profile, prompt_context=prompt_context)
        return output, _metadata_for(route, tool_calls=tool_calls)

    def analyze_market_intelligence(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        fallback_context: MarketContext,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[MarketIntelligenceAgentOutput, AgentInvocationMetadata]:
        route = self._route_or_raise("market_intelligence")
        output, tool_calls = MarketIntelligenceRuntimeAgent(
            self._provider,
            route.model_name,
            self.request_timeout_seconds,
            "market_intelligence",
        ).run_with_trace(
            user_profile,
            profile_focus,
            fallback_context,
            prompt_context=prompt_context,
        )
        return output, _metadata_for(route, tool_calls=tool_calls)

    def rank_candidates(
        self,
        request_name: str,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductRankingAgentOutput, AgentInvocationMetadata]:
        route = self._route_or_raise(request_name)
        ranking_agent: (
            FundSelectionRuntimeAgent
            | WealthSelectionRuntimeAgent
            | StockSelectionRuntimeAgent
        )
        if request_name == "fund_selection":
            ranking_agent = FundSelectionRuntimeAgent(
                self._provider,
                route.model_name,
                self.request_timeout_seconds,
                request_name,
            )
        elif request_name == "wealth_selection":
            ranking_agent = WealthSelectionRuntimeAgent(
                self._provider,
                route.model_name,
                self.request_timeout_seconds,
                request_name,
            )
        elif request_name == "stock_selection":
            ranking_agent = StockSelectionRuntimeAgent(
                self._provider,
                route.model_name,
                self.request_timeout_seconds,
                request_name,
            )
        else:
            raise ValueError(f"unsupported ranking request_name: {request_name}")

        output, tool_calls = ranking_agent.run_with_trace(
            user_profile,
            profile_focus,
            candidates,
            prompt_context=prompt_context,
        )
        return output, _metadata_for(route, tool_calls=tool_calls)

    def explain_plan(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
        selected_plan_context: SelectedPlanContext | dict[str, object] | None = None,
    ) -> tuple[ExplanationAgentOutput, AgentInvocationMetadata]:
        route = self._route_or_raise("explanation")
        output, tool_calls = ExplanationRuntimeAgent(
            self._provider,
            route.model_name,
            self.request_timeout_seconds,
            "explanation",
        ).run_with_trace(
            user_profile,
            profile_focus,
            market_context,
            prompt_context=prompt_context,
            selected_plan_context=coerce_selected_plan_context(selected_plan_context),
        )
        return output, _metadata_for(route, tool_calls=tool_calls)

    def route_metadata(self, request_name: str) -> AgentInvocationMetadata:
        return _metadata_for(self._route_or_raise(request_name))

    def _route_or_raise(self, request_name: str) -> AgentModelRoute:
        route = self._runtime_config.agent_routes.get(request_name)
        if route is None:
            raise RuntimeError(f"missing model route for request_name={request_name}")
        if route.provider_name != ANTHROPIC_PROVIDER_NAME:
            raise RuntimeError(
                f"unsupported provider={route.provider_name} for request_name={request_name}"
            )
        model_name = route.model_name.strip()
        if not model_name:
            raise RuntimeError(f"missing model_name for request_name={request_name}")
        return AgentModelRoute(
            provider_name=route.provider_name,
            model_name=model_name,
        )


def _metadata_for(
    route: AgentModelRoute,
    *,
    tool_calls: tuple[AgentToolCallRecord, ...] = (),
) -> AgentInvocationMetadata:
    return AgentInvocationMetadata(
        provider_name=route.provider_name,
        model_name=route.model_name,
        tool_calls=tool_calls,
    )
