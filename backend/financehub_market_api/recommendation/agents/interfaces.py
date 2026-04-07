from __future__ import annotations

from typing import Protocol

from financehub_market_api.recommendation.agents.contracts import (
    ExplanationAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductRankingAgentOutput,
    UserProfileAgentOutput,
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
    ) -> dict[str, object]:
        """Execute one structured-output chat request and parse JSON content."""


class OpenAICompatibleProvider(StructuredOutputProvider, Protocol):
    """Backward-compatible alias for existing single-provider runtime tests."""


class UserProfileAgent(Protocol):
    def run(self, user_profile: UserProfile) -> UserProfileAgentOutput:
        """Return structured user profile focus fields."""


class MarketIntelligenceAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        fallback_context: MarketContext,
    ) -> MarketIntelligenceAgentOutput:
        """Return structured market summary fields."""


class FundSelectionAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> ProductRankingAgentOutput:
        """Return ranked fund product IDs only."""


class WealthSelectionAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> ProductRankingAgentOutput:
        """Return ranked wealth-management product IDs only."""


class StockSelectionAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        candidates: list[CandidateProduct],
    ) -> ProductRankingAgentOutput:
        """Return ranked stock product IDs only."""


class ExplanationAgent(Protocol):
    def run(
        self,
        user_profile: UserProfile,
        profile_focus: UserProfileAgentOutput,
        market_context: MarketIntelligenceAgentOutput,
    ) -> ExplanationAgentOutput:
        """Return bilingual rationale bullet lists."""
