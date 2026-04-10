import pytest
from pydantic import ValidationError

from financehub_market_api.recommendation.agents.contracts import (
    MarketIntelligenceAgentOutput,
    ProductRankingAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.live_runtime import (
    AnthropicRecommendationAgentRuntime,
)
from financehub_market_api.recommendation.agents.provider import (
    AGENT_MODEL_ROUTE_ENV_NAMES,
    ANTHROPIC_PROVIDER_NAME,
    AgentModelRoute,
    AgentRuntimeConfig,
)
from financehub_market_api.recommendation.schemas import (
    CandidateProduct,
    MarketContext,
    UserProfile,
)


class _QueuedProvider:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
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
        if not self._responses:
            raise AssertionError("unexpected provider call")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if not isinstance(response, dict):
            raise AssertionError("test provider responses must be dicts or exceptions")
        return response


def _build_runtime(provider: _QueuedProvider) -> AnthropicRecommendationAgentRuntime:
    return AnthropicRecommendationAgentRuntime(
        provider=provider,
        runtime_config=AgentRuntimeConfig(
            providers={},
            agent_routes={
                request_name: AgentModelRoute(
                    provider_name=ANTHROPIC_PROVIDER_NAME,
                    model_name=f"test-model-{request_name}",
                )
                for request_name in AGENT_MODEL_ROUTE_ENV_NAMES
            },
            request_timeout_seconds=5.0,
        ),
    )


def _user_profile() -> UserProfile:
    return UserProfile(
        risk_profile="balanced",
        label_zh="平衡型",
        label_en="Balanced",
    )


def _profile_focus() -> UserProfileAgentOutput:
    return UserProfileAgentOutput(
        profile_focus_zh="偏好稳健底仓与良好流动性。",
        profile_focus_en="Prefers a resilient core and solid liquidity.",
    )


def _market_context() -> MarketIntelligenceAgentOutput:
    return MarketIntelligenceAgentOutput(
        summary_zh="当前市场处于震荡区间，适合控制回撤并逐步配置。",
        summary_en="Markets are range-bound, favoring drawdown control and gradual allocation.",
    )


def _fallback_market_context() -> MarketContext:
    return MarketContext(
        summary_zh="规则引擎市场摘要。",
        summary_en="Rules-based market summary.",
    )


def _fund_candidates() -> list[CandidateProduct]:
    return [
        CandidateProduct(
            id="fund-001",
            category="fund",
            code="000001",
            liquidity="T+1",
            name_zh="稳健债券增强A",
            name_en="Steady Bond Plus A",
            rationale_zh="主打回撤控制。",
            rationale_en="Focused on drawdown control.",
            risk_level="R2",
            tags_zh=["稳健", "债券"],
            tags_en=["steady", "bond"],
        ),
        CandidateProduct(
            id="fund-002",
            category="fund",
            code="000002",
            liquidity="T+1",
            name_zh="红利低波精选A",
            name_en="Dividend Low Vol A",
            rationale_zh="兼顾分红质量与波动控制。",
            rationale_en="Balances dividend quality and volatility control.",
            risk_level="R3",
            tags_zh=["红利", "低波"],
            tags_en=["dividend", "low-vol"],
        ),
    ]


def test_rank_candidates_runs_tool_loop_and_records_tool_trace() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "tool_call",
                "tool_name": "get_ranking_guardrails",
                "tool_arguments": {},
            },
            {
                "action": "tool_call",
                "tool_name": "get_candidate_detail",
                "tool_arguments": {"candidate_id": "fund-002"},
            },
            {
                "action": "final",
                "final_payload": {"ranked_ids": ["fund-002", "fund-001"]},
            },
        ]
    )
    runtime = _build_runtime(provider)

    output, metadata = runtime.rank_candidates(
        "fund_selection",
        _user_profile(),
        _profile_focus(),
        _fund_candidates(),
    )

    assert output == ProductRankingAgentOutput(ranked_ids=["fund-002", "fund-001"])
    assert [call.tool_name for call in metadata.tool_calls] == [
        "get_ranking_guardrails",
        "get_candidate_detail",
    ]
    assert metadata.tool_calls[1].arguments == {"candidate_id": "fund-002"}
    assert metadata.tool_calls[1].result["candidate"]["id"] == "fund-002"

    initial_user_prompt = provider.calls[0]["messages"][1]["content"]
    assert "Task" in initial_user_prompt
    assert "Candidate list context" in initial_user_prompt
    assert "Available tools" in initial_user_prompt


def test_rank_candidates_accepts_tool_alias_payload_shape() -> None:
    provider = _QueuedProvider(
        [
            {
                "tool": "get_ranking_guardrails",
                "parameters": {},
            },
            {
                "tool": "get_candidate_detail",
                "parameters": {"candidate_id": "fund-002"},
            },
            {
                "final_payload": {"ranked_ids": ["fund-002", "fund-001"]},
            },
        ]
    )
    runtime = _build_runtime(provider)

    output, metadata = runtime.rank_candidates(
        "fund_selection",
        _user_profile(),
        _profile_focus(),
        _fund_candidates(),
    )

    assert output == ProductRankingAgentOutput(ranked_ids=["fund-002", "fund-001"])
    assert [call.tool_name for call in metadata.tool_calls] == [
        "get_ranking_guardrails",
        "get_candidate_detail",
    ]
    assert metadata.tool_calls[1].arguments == {"candidate_id": "fund-002"}


def test_explain_plan_supports_selected_plan_tool_context() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "tool_call",
                "tool_name": "get_selected_plan",
                "tool_arguments": {},
            },
            {
                "action": "final",
                "final_payload": {
                    "why_this_plan_zh": [
                        "优先使用稳健底仓，帮助平衡波动与流动性。",
                    ],
                    "why_this_plan_en": [
                        "A resilient core balances volatility and liquidity needs.",
                    ],
                },
            },
        ]
    )
    runtime = _build_runtime(provider)

    output, metadata = runtime.explain_plan(
        _user_profile(),
        _profile_focus(),
        _market_context(),
        selected_plan_context={
            "fund_ids": ["fund-002"],
            "wealth_management_ids": ["wm-001"],
            "stock_ids": [],
        },
    )

    assert output.why_this_plan_zh == ["优先使用稳健底仓，帮助平衡波动与流动性。"]
    assert [call.tool_name for call in metadata.tool_calls] == ["get_selected_plan"]
    assert list(metadata.tool_calls[0].result["selected_plan"]["fund_ids"]) == [
        "fund-002"
    ]

    initial_user_prompt = provider.calls[0]["messages"][1]["content"]
    assert "Selected plan context" in initial_user_prompt
    assert "Available tools" in initial_user_prompt


def test_runtime_raises_clean_error_for_invalid_tool_request() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "tool_call",
                "tool_name": "missing_tool",
                "tool_arguments": {},
            }
        ]
    )
    runtime = _build_runtime(provider)

    with pytest.raises(RuntimeError, match="invalid tool request"):
        runtime.analyze_market_intelligence(
            _user_profile(),
            _profile_focus(),
            _fallback_market_context(),
        )


def test_runtime_raises_clean_error_for_malformed_tool_request() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "tool_call",
                "tool_arguments": {},
            },
            {
                "action": "tool_call",
                "tool_arguments": {},
            },
        ]
    )
    runtime = _build_runtime(provider)

    with pytest.raises(RuntimeError, match="invalid tool request"):
        runtime.analyze_market_intelligence(
            _user_profile(),
            _profile_focus(),
            _fallback_market_context(),
        )
    assert len(provider.calls) == 2


def test_runtime_raises_clean_error_for_tool_request_with_unexpected_arguments() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "tool_call",
                "tool_name": "get_candidate_detail",
                "tool_arguments": {
                    "candidate_id": "fund-001",
                    "unexpected": "value",
                },
            }
        ]
    )
    runtime = _build_runtime(provider)

    with pytest.raises(RuntimeError, match="invalid tool request: get_candidate_detail"):
        runtime.rank_candidates(
            "fund_selection",
            _user_profile(),
            _profile_focus(),
            _fund_candidates(),
        )


def test_runtime_raises_clean_error_for_malformed_final_response() -> None:
    provider = _QueuedProvider([{"action": "final"}, {"action": "final"}])
    runtime = _build_runtime(provider)

    with pytest.raises(RuntimeError, match="invalid final payload"):
        runtime.analyze_market_intelligence(
            _user_profile(),
            _profile_focus(),
            _fallback_market_context(),
        )
    assert len(provider.calls) == 2


def test_runtime_retries_invalid_final_payload_once_before_surfacing_error() -> None:
    provider = _QueuedProvider(
        [
            {"action": "final", "final_payload": {"ranked_ids": []}},
            {"action": "final", "final_payload": {"ranked_ids": []}},
        ]
    )
    runtime = _build_runtime(provider)

    with pytest.raises(ValidationError, match="ProductRankingAgentOutput"):
        runtime.rank_candidates(
            "fund_selection",
            _user_profile(),
            _profile_focus(),
            _fund_candidates(),
        )
    assert len(provider.calls) == 2


def test_runtime_recovers_after_invalid_direct_ranking_output() -> None:
    provider = _QueuedProvider(
        [
            {"ranked_ids": []},
            {"ranked_ids": ["fund-001", "fund-002"]},
        ]
    )
    runtime = _build_runtime(provider)

    output, metadata = runtime.rank_candidates(
        "fund_selection",
        _user_profile(),
        _profile_focus(),
        _fund_candidates(),
    )

    assert output == ProductRankingAgentOutput(ranked_ids=["fund-001", "fund-002"])
    assert metadata.tool_calls == ()
    assert len(provider.calls) == 2


def test_runtime_raises_clean_error_when_tool_loop_is_exhausted() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "tool_call",
                "tool_name": "get_user_profile_context",
                "tool_arguments": {},
            },
            {
                "action": "tool_call",
                "tool_name": "get_user_profile_context",
                "tool_arguments": {},
            },
            {
                "action": "tool_call",
                "tool_name": "get_user_profile_context",
                "tool_arguments": {},
            },
        ]
    )
    runtime = _build_runtime(provider)

    with pytest.raises(RuntimeError, match="tool loop exhausted"):
        runtime.analyze_market_intelligence(
            _user_profile(),
            _profile_focus(),
            _fallback_market_context(),
        )


def test_runtime_accepts_direct_output_without_requiring_tool_loop_action() -> None:
    provider = _QueuedProvider(
        [
            {
                "profile_focus_zh": "平衡风险与收益，追求稳健增长。",
                "profile_focus_en": "Balance risk and return for steady growth.",
            },
        ]
    )
    runtime = _build_runtime(provider)

    output, metadata = runtime.analyze_user_profile(_user_profile())

    assert output == UserProfileAgentOutput(
        profile_focus_zh="平衡风险与收益，追求稳健增长。",
        profile_focus_en="Balance risk and return for steady growth.",
    )
    assert metadata.tool_calls == ()
    assert len(provider.calls) == 1
    assert provider.calls[0]["response_schema"].get("required") in (None, [])
