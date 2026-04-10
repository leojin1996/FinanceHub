from __future__ import annotations

from typing import Protocol

from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    ExplanationAgentOutput,
    ManagerCoordinatorAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
    ProductRankingAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.runtime_context import (
    AgentPromptContext,
    SelectedPlanContext,
)
from financehub_market_api.recommendation.schemas import CandidateProduct, MarketContext, UserProfile


class StructuredOutputProvider(Protocol):
    def chat_json(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        response_schema: dict[str, object],
        timeout_seconds: float,
        request_name: str | None = None,
    ) -> dict[str, object]:
        """Execute one structured-output chat request and parse JSON content."""


class AnthropicProvider(StructuredOutputProvider, Protocol):
    """Anthropic structured-output provider interface."""


class UserProfileAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> UserProfileAgentOutput:
        """Return structured user profile focus fields."""


class MarketIntelligenceAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        fallback_context: MarketContext,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> MarketIntelligenceAgentOutput:
        """Return structured market summary fields."""


class ProductMatchAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ProductMatchAgentOutput:
        """Return structured candidate selection and ranking output."""


class FundSelectionAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ProductRankingAgentOutput:
        """Return ranked fund product IDs only."""


class WealthSelectionAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ProductRankingAgentOutput:
        """Return ranked wealth-management product IDs only."""


class StockSelectionAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ProductRankingAgentOutput:
        """Return ranked stock product IDs only."""


class ExplanationAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
        selected_plan_context: SelectedPlanContext | None = None,
    ) -> ExplanationAgentOutput:
        """Return bilingual rationale bullet lists."""


class ComplianceReviewAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        selected_candidates: list[CandidateProduct],
        compliance_facts: dict[str, object],
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ComplianceReviewAgentOutput:
        """Return the structured compliance verdict."""


class ManagerCoordinatorAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        user_profile_insights: UserProfileAgentOutput,
        market_intelligence: MarketIntelligenceAgentOutput,
        product_match: ProductMatchAgentOutput,
        compliance_review: ComplianceReviewAgentOutput,
        *,
        prompt_context: AgentPromptContext | None = None,
    ) -> ManagerCoordinatorAgentOutput:
        """Return final recommendation summary and rationale."""
