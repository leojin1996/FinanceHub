import logging

import httpx
import pytest

from financehub_market_api.recommendation.agents import anthropic_runtime as runtime_module
from financehub_market_api.recommendation_flow import (
    build_recommendation_context,
    run_recommendation_flow,
)
from financehub_market_api.recommendation.agents import AnthropicMultiAgentRuntime
from financehub_market_api.recommendation.agents.provider import (
    ANTHROPIC_PROVIDER_NAME,
    AgentModelRoute,
    LLMInvalidResponseError,
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
        multi_agent_runtime=AnthropicMultiAgentRuntime(providers={}),
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
        multi_agent_runtime=AnthropicMultiAgentRuntime(providers={}),
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
        request_name: str | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "model_name": model_name,
                "messages": messages,
                "response_schema": response_schema,
                "timeout_seconds": timeout_seconds,
                "request_name": request_name,
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
    runtime = AnthropicMultiAgentRuntime(
        provider=_SequenceProvider([httpx.TimeoutException("request timed out")]),
        model_name="claude-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "provider_error"


def test_user_profile_provider_error_uses_fallback_focus_and_keeps_agent_outputs() -> None:
    runtime = AnthropicMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                httpx.ReadTimeout("request timed out"),
                {"summary_zh": "智能市场摘要", "summary_en": "Agent market summary"},
                {"ranked_ids": ["fund-002", "fund-001"]},
                {"ranked_ids": ["wm-002", "wm-001"]},
                {"ranked_ids": ["stock-002", "stock-001"]},
                {"why_this_plan_zh": ["智能解释1"], "why_this_plan_en": ["Agent reason 1"]},
            ]
        ),
        model_name="claude-test",
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].stage == "user_profile"
    assert recommendation.execution_trace.warnings[0].code == "provider_error"
    assert recommendation.market_context.summary_zh == "智能市场摘要"
    assert recommendation.why_this_plan_en == ["Agent reason 1"]
    assert [product.id for product in recommendation.fund_items] == ["fund-002", "fund-001"]


def test_market_intelligence_provider_error_keeps_rule_summary_and_continues() -> None:
    runtime = AnthropicMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
                httpx.ReadTimeout("request timed out"),
                {"ranked_ids": ["fund-002", "fund-001"]},
                {"ranked_ids": ["wm-002", "wm-001"]},
                {"ranked_ids": ["stock-002", "stock-001"]},
                {"why_this_plan_zh": ["智能解释1"], "why_this_plan_en": ["Agent reason 1"]},
            ]
        ),
        model_name="claude-test",
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].stage == "market_intelligence"
    assert recommendation.execution_trace.warnings[0].code == "provider_error"
    assert recommendation.market_context.summary_zh == "当前市场更适合稳健资产与权益增强搭配，控制整体波动。"
    assert recommendation.why_this_plan_en == ["Agent reason 1"]
    assert [product.id for product in recommendation.fund_items] == ["fund-002", "fund-001"]


def test_explanation_provider_error_keeps_rule_rationale_and_agent_summary() -> None:
    runtime = AnthropicMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
                {"summary_zh": "智能市场摘要", "summary_en": "Agent market summary"},
                {"ranked_ids": ["fund-002", "fund-001"]},
                {"ranked_ids": ["wm-002", "wm-001"]},
                {"ranked_ids": ["stock-002", "stock-001"]},
                httpx.ReadTimeout("request timed out"),
            ]
        ),
        model_name="claude-test",
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].stage == "explanation"
    assert recommendation.execution_trace.warnings[0].code == "provider_error"
    assert recommendation.market_context.summary_zh == "智能市场摘要"
    assert recommendation.why_this_plan_en[0] == (
        "Your profile screens as Balanced, so the base plan prioritizes overall volatility control."
    )
    assert [product.id for product in recommendation.fund_items] == ["fund-002", "fund-001"]


@pytest.mark.parametrize(
    "provider_error_message",
    [
        "provider response has no content blocks",
        "provider response has no text content block",
    ],
)
def test_empty_provider_response_downgrades_to_rule_fallback_with_clear_warning(
    provider_error_message: str,
) -> None:
    runtime = AnthropicMultiAgentRuntime(
        provider=_SequenceProvider([LLMInvalidResponseError(provider_error_message)]),
        model_name="claude-test",
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].stage == "provider"
    assert recommendation.execution_trace.warnings[0].code == "provider_empty_response"
    assert "returned an empty structured response" in recommendation.execution_trace.warnings[0].message


def test_runtime_uses_configured_request_timeout_for_all_agents() -> None:
    provider = _SequenceProvider(
        [
            {"profile_focus_zh": "稳健", "profile_focus_en": "Stable"},
            {"summary_zh": "市场震荡", "summary_en": "Market is choppy"},
            {"ranked_ids": ["fund-001", "fund-002"]},
            {"ranked_ids": ["wm-001", "wm-002"]},
            {"ranked_ids": ["stock-001", "stock-002"]},
            {"why_this_plan_zh": ["理由一", "理由二"], "why_this_plan_en": ["Reason one", "Reason two"]},
        ]
    )
    runtime = AnthropicMultiAgentRuntime(
        provider=provider,
        model_name="claude-test",
        request_timeout_seconds=30.0,
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"
    assert [call["timeout_seconds"] for call in provider.calls] == [30.0] * 6


def test_runtime_threads_request_name_across_stages() -> None:
    provider = _SequenceProvider(
        [
            {"profile_focus_zh": "稳健", "profile_focus_en": "Stable"},
            {"summary_zh": "市场震荡", "summary_en": "Market is choppy"},
            {"ranked_ids": ["fund-001", "fund-002"]},
            {"ranked_ids": ["wm-001", "wm-002"]},
            {"ranked_ids": ["stock-001", "stock-002"]},
            {"why_this_plan_zh": ["理由一", "理由二"], "why_this_plan_en": ["Reason one", "Reason two"]},
        ]
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=AnthropicMultiAgentRuntime(
            provider=provider,
            model_name="claude-test",
        ),
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"
    assert [call["request_name"] for call in provider.calls] == [
        "user_profile",
        "market_intelligence",
        "fund_selection",
        "wealth_selection",
        "stock_selection",
        "explanation",
    ]


def test_agent_trace_logging_records_start_and_finish_with_response_summary(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _SequenceProvider(
        [
            {"profile_focus_zh": "稳健", "profile_focus_en": "Stable"},
            {"summary_zh": "市场震荡", "summary_en": "Market is choppy"},
            {"ranked_ids": ["fund-001", "fund-002"]},
            {"ranked_ids": ["wm-001", "wm-002"]},
            {"ranked_ids": ["stock-001", "stock-002"]},
            {"why_this_plan_zh": ["理由一", "理由二"], "why_this_plan_en": ["Reason one", "Reason two"]},
        ]
    )
    monkeypatch.setenv("FINANCEHUB_LLM_AGENT_TRACE_LOGS", "true")
    caplog.set_level(logging.INFO, logger=runtime_module.__name__)

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=AnthropicMultiAgentRuntime(
            provider=provider,
            model_name="claude-test",
        ),
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"

    event_messages = [
        record.message for record in caplog.records if record.message.startswith("agent_request_")
    ]
    assert any(message.startswith("agent_request_start") for message in event_messages)
    finish_messages = [message for message in event_messages if message.startswith("agent_request_finish")]
    assert finish_messages
    assert all("response_summary=" in message for message in finish_messages)


def test_agent_trace_logging_records_error_for_first_agent_provider_failure(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINANCEHUB_LLM_AGENT_TRACE_LOGS", "true")
    caplog.set_level(logging.INFO, logger=runtime_module.__name__)

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=AnthropicMultiAgentRuntime(
            provider=_SequenceProvider([httpx.ReadTimeout("boom")]),
            model_name="claude-test",
        ),
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    event_messages = [
        record.message for record in caplog.records if record.message.startswith("agent_request_")
    ]
    error_messages = [message for message in event_messages if message.startswith("agent_request_error")]
    assert any("request_name=user_profile" in message for message in error_messages)
    assert any(
        'error_message="structured-output provider request failed: boom"' in message
        for message in error_messages
    )


def test_runtime_rejects_non_anthropic_agent_route() -> None:
    runtime = AnthropicMultiAgentRuntime(
        providers={ANTHROPIC_PROVIDER_NAME: _SequenceProvider([])},
        agent_routes={
            "market_intelligence": AgentModelRoute(provider_name="openai", model_name="claude-opus-4-6")
        },
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "agent_provider_invalid"
    assert recommendation.execution_trace.warnings[0].stage == "market_intelligence"


def test_missing_anthropic_provider_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = AnthropicMultiAgentRuntime(providers={})

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "llm_config_missing"


def test_invalid_agent_payload_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = AnthropicMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
                {"summary_zh": "市场维持震荡", "summary_en": "Market is range-bound"},
                {"ranked_ids": "not-a-list"},
            ]
        ),
        model_name="claude-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "invalid_agent_output"


def test_empty_ranking_provider_responses_keep_agent_authored_summary_and_explanation() -> None:
    runtime = AnthropicMultiAgentRuntime(
        provider=_SequenceProvider(
            [
                {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
                {"summary_zh": "智能市场摘要", "summary_en": "Agent market summary"},
                LLMInvalidResponseError("provider response has no text content block"),
                LLMInvalidResponseError("provider response has no text content block"),
                LLMInvalidResponseError("provider response has no text content block"),
                {
                    "why_this_plan_zh": ["智能解释1", "智能解释2"],
                    "why_this_plan_en": ["Agent reason 1", "Agent reason 2"],
                },
            ]
        ),
        model_name="claude-test",
    )

    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"
    assert recommendation.execution_trace.execution_mode == "agent_assisted"
    assert recommendation.execution_trace.degraded is True
    assert [warning.code for warning in recommendation.execution_trace.warnings] == [
        "provider_empty_response",
        "provider_empty_response",
        "provider_empty_response",
    ]
    assert [warning.stage for warning in recommendation.execution_trace.warnings] == [
        "fund_selection",
        "wealth_selection",
        "stock_selection",
    ]
    assert recommendation.market_context.summary_zh == "智能市场摘要"
    assert recommendation.why_this_plan_en == ["Agent reason 1", "Agent reason 2"]
    assert [product.id for product in recommendation.fund_items] == ["fund-001", "fund-002"]


def test_empty_ranked_ids_keep_agent_assisted_mode_with_warning() -> None:
    runtime = AnthropicMultiAgentRuntime(
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
        model_name="claude-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "agent_assisted"
    assert recommendation.execution_trace.execution_mode == "agent_assisted"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "agent_ranking_unusable"
    assert recommendation.execution_trace.warnings[0].stage == "fund_selection"
    assert [product.id for product in recommendation.fund_items] == ["fund-001", "fund-002"]
    assert recommendation.market_context.summary_zh == "市场维持震荡"
    assert recommendation.why_this_plan_en == ["Agent reason 1", "Agent reason 2"]


def test_ranking_prompts_require_non_empty_output_and_original_order_fallback() -> None:
    provider = _SequenceProvider(
        [
            {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
            {"summary_zh": "市场维持震荡", "summary_en": "Market is range-bound"},
            {"ranked_ids": ["fund-001", "fund-002"]},
            {"ranked_ids": ["wm-001", "wm-002"]},
            {"ranked_ids": ["stock-001", "stock-002"]},
            {
                "why_this_plan_zh": ["智能解释1", "智能解释2"],
                "why_this_plan_en": ["Agent reason 1", "Agent reason 2"],
            },
        ]
    )
    RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=AnthropicMultiAgentRuntime(
            provider=provider,
            model_name="claude-test",
        ),
    ).generate("balanced")

    ranking_user_prompts = [
        call["messages"][1]["content"]
        for call in provider.calls[2:5]
    ]

    for prompt in ranking_user_prompts:
        assert "Never return an empty list." in prompt
        assert "If uncertain, return every candidate ID exactly once in the original order." in prompt


def test_ranking_prompts_include_richer_candidate_features() -> None:
    provider = _SequenceProvider(
        [
            {"profile_focus_zh": "稳健", "profile_focus_en": "stable"},
            {"summary_zh": "市场维持震荡", "summary_en": "Market is range-bound"},
            {"ranked_ids": ["fund-001", "fund-002"]},
            {"ranked_ids": ["wm-001", "wm-002"]},
            {"ranked_ids": ["stock-001", "stock-002"]},
            {
                "why_this_plan_zh": ["智能解释1", "智能解释2"],
                "why_this_plan_en": ["Agent reason 1", "Agent reason 2"],
            },
        ]
    )
    RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=AnthropicMultiAgentRuntime(
            provider=provider,
            model_name="claude-test",
        ),
    ).generate("balanced")

    fund_prompt = provider.calls[2]["messages"][1]["content"]
    wealth_prompt = provider.calls[3]["messages"][1]["content"]
    stock_prompt = provider.calls[4]["messages"][1]["content"]

    assert "tags_zh=低回撤, 债券底仓, 适合稳健增值" in fund_prompt
    assert "liquidity=T+1" in fund_prompt
    assert "rationale_zh=作为组合底仓，波动较低，更适合用来承接稳健增值目标。" in fund_prompt

    assert "tags_en=Short tenor, Liquidity-friendly, Stable base" in wealth_prompt
    assert "liquidity=90天" in wealth_prompt
    assert "rationale_en=Fits the role of a stable base allocation while preserving reasonable liquidity." in wealth_prompt

    assert "code=600036" in stock_prompt
    assert "tags_zh=高股息, 大盘蓝筹, 增强配置" in stock_prompt
    assert "rationale_en=As a satellite equity holding, it leans on earnings stability and dividend quality to keep volatility more contained." in stock_prompt


def test_ranked_ids_without_candidate_overlap_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = AnthropicMultiAgentRuntime(
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
        model_name="claude-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "agent_ranking_unusable"


def test_ranked_ids_with_partial_unknown_entries_downgrades_to_rule_fallback_with_warning() -> None:
    runtime = AnthropicMultiAgentRuntime(
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
        model_name="claude-test",
    )
    recommendation = RecommendationOrchestrator(
        candidate_repository=StaticCandidateRepository(),
        multi_agent_runtime=runtime,
    ).generate("balanced")

    assert recommendation.execution_trace.path == "rules_fallback"
    assert recommendation.execution_trace.degraded is True
    assert recommendation.execution_trace.warnings[0].code == "agent_ranking_unusable"


def test_agent_assisted_execution_is_tracked_separately_from_pure_rule_fallback() -> None:
    runtime = AnthropicMultiAgentRuntime(
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
        model_name="claude-test",
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
