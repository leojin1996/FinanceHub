from __future__ import annotations

from dataclasses import dataclass

from financehub_market_api.recommendation.agents.anthropic_runtime import (
    ComplianceReviewRuntimeAgent,
    ManagerCoordinatorRuntimeAgent,
    MarketIntelligenceRuntimeAgent,
    ProductMatchRuntimeAgent,
    UserProfileRuntimeAgent,
)
from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    ManagerCoordinatorAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
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
)
from financehub_market_api.recommendation.schemas import (
    CandidateProduct,
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
        route = self._route_or_raise("user_profile_analyst")
        output, tool_calls = UserProfileRuntimeAgent(
            self._provider,
            route.model_name,
            self.request_timeout_seconds,
            "user_profile_analyst",
        ).run_with_trace(user_profile, prompt_context=prompt_context)
        return output, _metadata_for(route, tool_calls=tool_calls)

    def analyze_market_intelligence(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_facts: dict[str, object],
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
            user_profile_insights,
            market_facts,
            prompt_context=prompt_context,
        )
        return output, _metadata_for(route, tool_calls=tool_calls)

    def match_products(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ProductMatchAgentOutput, AgentInvocationMetadata]:
        route = self._route_or_raise("product_match_expert")
        output, tool_calls = ProductMatchRuntimeAgent(
            self._provider,
            route.model_name,
            self.request_timeout_seconds,
            "product_match_expert",
        ).run_with_trace(
            user_profile,
            user_profile_insights,
            market_intelligence,
            candidates,
            prompt_context=prompt_context,
        )
        return output, _metadata_for(route, tool_calls=tool_calls)

    def review_compliance(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        selected_candidates: list[CandidateProduct],
        compliance_facts: dict[str, object],
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ComplianceReviewAgentOutput, AgentInvocationMetadata]:
        route = self._route_or_raise("compliance_risk_officer")
        output, tool_calls = ComplianceReviewRuntimeAgent(
            self._provider,
            route.model_name,
            self.request_timeout_seconds,
            "compliance_risk_officer",
        ).run_with_trace(
            user_profile,
            user_profile_insights,
            selected_candidates,
            compliance_facts,
            prompt_context=prompt_context,
        )
        return output, _metadata_for(route, tool_calls=tool_calls)

    def coordinate_manager(
        self,
        user_profile: UserProfile,
        *,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        product_match: ProductMatchAgentOutput,
        compliance_review: ComplianceReviewAgentOutput,
        prompt_context: AgentPromptContext | None = None,
    ) -> tuple[ManagerCoordinatorAgentOutput, AgentInvocationMetadata]:
        route = self._route_or_raise("manager_coordinator")
        output, tool_calls = ManagerCoordinatorRuntimeAgent(
            self._provider,
            route.model_name,
            self.request_timeout_seconds,
            "manager_coordinator",
        ).run_with_trace(
            user_profile,
            user_profile_insights,
            market_intelligence,
            product_match,
            compliance_review,
            prompt_context=prompt_context,
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
