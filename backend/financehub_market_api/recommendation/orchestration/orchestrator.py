from __future__ import annotations

from financehub_market_api.models import RiskProfile
from financehub_market_api.recommendation.agents import AnthropicMultiAgentRuntime
from financehub_market_api.recommendation.repositories import CandidateRepository, RealDataCandidateRepository
from financehub_market_api.recommendation.rules import RuleBasedFallbackEngine, map_user_profile
from financehub_market_api.recommendation.schemas import FinalRecommendation


class RecommendationOrchestrator:
    def __init__(
        self,
        *,
        candidate_repository: CandidateRepository | None = None,
        multi_agent_runtime: AnthropicMultiAgentRuntime | None = None,
    ) -> None:
        repository = candidate_repository or RealDataCandidateRepository()
        self._fallback_engine = RuleBasedFallbackEngine(repository)
        self._multi_agent_runtime = multi_agent_runtime or AnthropicMultiAgentRuntime.from_env()

    def generate(self, risk_profile: RiskProfile) -> FinalRecommendation:
        user_profile = map_user_profile(risk_profile)
        state = self._fallback_engine.run(user_profile)
        if state.allocation is None or state.aggressive_allocation is None or state.market_context is None:
            raise ValueError("recommendation fallback state is incomplete")
        runtime_result = self._multi_agent_runtime.apply(user_profile, state)
        state.execution_trace.warnings.extend(runtime_result.warnings)
        state.execution_trace.degraded = bool(runtime_result.warnings)
        if runtime_result.assisted:
            state.execution_trace.path = "agent_assisted"
            state.execution_trace.execution_mode = "agent_assisted"
        else:
            state.execution_trace.path = "rules_fallback"
            state.execution_trace.execution_mode = "rules_fallback"

        return FinalRecommendation(
            user_profile=user_profile,
            market_context=state.market_context,
            allocation_plan=state.allocation,
            aggressive_allocation_plan=state.aggressive_allocation,
            fund_items=state.fund_items,
            wealth_management_items=state.wealth_management_items,
            stock_items=state.stock_items,
            risk_review_result=state.review_result,
            why_this_plan_zh=state.why_this_plan_zh,
            why_this_plan_en=state.why_this_plan_en,
            execution_trace=state.execution_trace,
        )
