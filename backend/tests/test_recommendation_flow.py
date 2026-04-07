import httpx
import pytest

from financehub_market_api.recommendation_flow import (
    build_recommendation_context,
    run_recommendation_flow,
)

from financehub_market_api.recommendation.agents import OpenAIMultiAgentRuntime
from financehub_market_api.recommendation.agents.provider import (
    ANTHROPIC_PROVIDER_NAME,
    OPENAI_PROVIDER_NAME,
    AgentModelRoute,
)
from financehub_market_api.recommendation.orchestration import RecommendationOrchestrator
from financehub_market_api.recommendation.repositories import StaticCandidateRepository
from financehub_market_api.recommendation_types import RecommendationContext


def test_conservative_flow_limits_stock_items_and_tracks_applied_rules() -> None:
    context = build_recommendation_context("conservative")

    state = run_recommendation_flow(context)

    assert state.allocation.stock == 5
    assert len(state.stock_items) == 1
    assert state.stock_items[0].nameZh == "招商银行"
    assert state.review_status == "partial_pass"
    assert state.applied_rules == [
        "apply_base_plan",
        "attach_market_summary",
        "select_candidate_products",
        "limit_stock_exposure_for_low_risk",
        "derive_review_status",
        "derive_plan_rationale",
    ]
    assert state.decision_trace == [
        "base allocation seeded for conservative",
        "market summary attached for conservative",
        "candidate products selected: funds=2, wealth_management=2, stocks=2",
        "low-risk stock exposure limited to top 1 item",
        "review status set to partial_pass",
        "plan rationale generated for conservative",
    ]


def test_balanced_flow_keeps_full_stock_section_and_pass_review() -> None:
    context = build_recommendation_context("balanced")

    state = run_recommendation_flow(context)

    assert state.allocation.fund == 45
    assert state.allocation.wealthManagement == 35
    assert state.allocation.stock == 20
    assert len(state.stock_items) == 2
    assert state.review_status == "pass"
    assert any("平衡型" in reason for reason in state.why_this_plan_zh)
    assert state.decision_trace[-2:] == [
        "review status set to pass",
        "plan rationale generated for balanced",
    ]


def test_manual_context_labels_are_preserved_by_recommendation_flow() -> None:
    context = RecommendationContext(
        risk_profile="balanced",
        profile_label_zh="自定义平衡档",
        profile_label_en="Custom Balanced",
    )

    state = run_recommendation_flow(context)

    assert "自定义平衡档" in state.why_this_plan_zh[0]
    assert "Custom Balanced" in state.why_this_plan_en[0]


def test_orchestration_keeps_execution_trace_available_for_fallback_path() -> None:
    orchestrator = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=OpenAIMultiAgentRuntime(providers={}),
    )

    final_recommendation = orchestrator.generate("balanced")

    assert final_recommendation.execution_trace.path == "rules_fallback"
    assert final_recommendation.execution_trace.execution_mode == "rules_fallback"
    assert final_recommendation.execution_trace.applied_rules == [
        "apply_base_plan",
        "attach_market_summary",
        "select_candidate_products",
        "limit_stock_exposure_for_low_risk",
        "derive_review_status",
        "derive_plan_rationale",
    ]
    assert final_recommendation.execution_trace.decision_trace[0] == "base allocation seeded for balanced"


def test_orchestration_without_llm_config_keeps_safe_rule_fallback() -> None:
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=OpenAIMultiAgentRuntime(providers={})
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.execution_mode == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "llm_config_missing"


class _SequenceProvider:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self._index = 0
        self.calls: list[dict[str, object]] = []

    def chat_json(
        self,
        *,
        model_name: str,
        messages: list[dict[str, str]],
        response_schema: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "model_name": model_name,
                "messages": messages,
                "response_schema": response_schema,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self._index >= len(self._responses):
            raise AssertionError("unexpected provider call")
        response = self._responses[self._index]
        self._index += 1
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            return response
        raise TypeError("response must be dict or exception")


def test_provider_exception_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = OpenAIMultiAgentRuntime(
        provider=_SequenceProvider([httpx.TimeoutException("request timed out")]),
        model_name="gpt-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "provider_error"


def test_missing_anthropic_provider_downgrades_to_rule_fallback_with_warning() -> None:
    openai_provider = _SequenceProvider([])
    runtime = OpenAIMultiAgentRuntime(providers={OPENAI_PROVIDER_NAME: openai_provider})

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "agent_provider_missing"
    assert recommendation.execution_trace.warnings[0].stage == "market_intelligence"
    assert openai_provider.calls == []


def test_invalid_agent_route_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = OpenAIMultiAgentRuntime(
        providers={
            OPENAI_PROVIDER_NAME: _SequenceProvider([]),
            ANTHROPIC_PROVIDER_NAME: _SequenceProvider([]),
        },
        agent_routes={
            "market_intelligence": AgentModelRoute(provider_name="", model_name="claude-opus-4-6")
        },
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "agent_model_route_invalid"
    assert recommendation.execution_trace.warnings[0].stage == "market_intelligence"


def test_invalid_agent_payload_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = OpenAIMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
                {"summary_zh": "市场维持震荡", "summary_en": "Market is range-bound"},
                {"ranked_ids": "not-a-list"},
            ]
        ),
        model_name="gpt-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "invalid_agent_output"


def test_empty_ranked_ids_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = OpenAIMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
                {"summary_zh": "市场维持震荡", "summary_en": "Market is range-bound"},
                {"ranked_ids": []},
                {"ranked_ids": ["wm-001"]},
                {"ranked_ids": ["stock-001"]},
                {
                    "why_this_plan_zh": ["智能解释1", "智能解释2"],
                    "why_this_plan_en": ["Agent reason 1", "Agent reason 2"],
                },
            ]
        ),
        model_name="gpt-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "agent_ranking_unusable"


def test_ranked_ids_without_candidate_overlap_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = OpenAIMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
                {"summary_zh": "市场维持震荡", "summary_en": "Market is range-bound"},
                {"ranked_ids": ["unknown-fund-id"]},
                {"ranked_ids": ["wm-001"]},
                {"ranked_ids": ["stock-001"]},
                {
                    "why_this_plan_zh": ["智能解释1", "智能解释2"],
                    "why_this_plan_en": ["Agent reason 1", "Agent reason 2"],
                },
            ]
        ),
        model_name="gpt-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "agent_ranking_unusable"


def test_ranked_ids_with_partial_unknown_entries_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = OpenAIMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
                {"summary_zh": "市场维持震荡", "summary_en": "Market is range-bound"},
                {"ranked_ids": ["fund-001", "hallucinated-fund-id"]},
                {"ranked_ids": ["wm-001"]},
                {"ranked_ids": ["stock-001"]},
                {
                    "why_this_plan_zh": ["智能解释1", "智能解释2"],
                    "why_this_plan_en": ["Agent reason 1", "Agent reason 2"],
                },
            ]
        ),
        model_name="gpt-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "agent_ranking_unusable"


def test_agent_assisted_execution_is_tracked_separately_from_pure_rule_fallback() -> None:
    runtime = OpenAIMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                {"profile_focus_zh": "稳健增值", "profile_focus_en": "steady growth"},
                {"summary_zh": "智能摘要：配置需均衡", "summary_en": "Agent summary: keep diversified"},
                {"ranked_ids": ["fund-002", "fund-001"]},
                {"ranked_ids": ["wm-002", "wm-001"]},
                {"ranked_ids": ["stock-002", "stock-001"]},
                {
                    "why_this_plan_zh": ["智能解释1", "智能解释2", "智能解释3"],
                    "why_this_plan_en": ["Agent reason 1", "Agent reason 2", "Agent reason 3"],
                },
            ]
        ),
        model_name="gpt-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"
    assert recommendation.execution_trace.execution_mode == "agent_assisted"
    assert recommendation.execution_trace.degraded is False
    assert recommendation.execution_trace.warnings == []
    assert recommendation.market_context.summary_zh == "智能摘要：配置需均衡"
    assert recommendation.fund_items[0].id == "fund-002"
    assert recommendation.why_this_plan_en[0] == "Agent reason 1"


def test_agent_assisted_execution_routes_market_and_explanation_to_anthropic() -> None:
    openai_provider = _SequenceProvider(
        [
            {"profile_focus_zh": "稳健增值", "profile_focus_en": "steady growth"},
            {"ranked_ids": ["fund-002", "fund-001"]},
            {"ranked_ids": ["wm-002", "wm-001"]},
            {"ranked_ids": ["stock-002", "stock-001"]},
        ]
    )
    anthropic_provider = _SequenceProvider(
        [
            {"summary_zh": "Anthropic 市场摘要", "summary_en": "Anthropic market summary"},
            {
                "why_this_plan_zh": ["Anthropic 解释1", "Anthropic 解释2"],
                "why_this_plan_en": ["Anthropic reason 1", "Anthropic reason 2"],
            },
        ]
    )
    runtime = OpenAIMultiAgentRuntime(
        providers={
            OPENAI_PROVIDER_NAME: openai_provider,
            ANTHROPIC_PROVIDER_NAME: anthropic_provider,
        }
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"
    assert [call["model_name"] for call in openai_provider.calls] == ["gpt-5.4"] * 4
    assert [call["model_name"] for call in anthropic_provider.calls] == ["claude-opus-4-6"] * 2
    assert "UserProfileAgent" in openai_provider.calls[0]["messages"][0]["content"]
    assert "MarketIntelligenceAgent" in anthropic_provider.calls[0]["messages"][0]["content"]
    assert "ExplanationAgent" in anthropic_provider.calls[1]["messages"][0]["content"]
    assert recommendation.market_context.summary_zh == "Anthropic 市场摘要"
    assert recommendation.why_this_plan_en[0] == "Anthropic reason 1"


def test_invalid_anthropic_output_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = OpenAIMultiAgentRuntime(
        providers={
            OPENAI_PROVIDER_NAME: _SequenceProvider(
                [
                    {"profile_focus_zh": "稳健增值", "profile_focus_en": "steady growth"},
                ]
            ),
            ANTHROPIC_PROVIDER_NAME: _SequenceProvider(
                [
                    {"summary_zh": "Only one field"},
                ]
            ),
        }
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "invalid_agent_output"
