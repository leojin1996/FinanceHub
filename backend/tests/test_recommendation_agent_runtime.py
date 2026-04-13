import pytest

from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    ManagerCoordinatorAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.live_runtime import (
    RecommendationAgentRuntime,
)
from financehub_market_api.recommendation.agents.provider import (
    AGENT_MODEL_ROUTE_ENV_NAMES,
    OPENAI_PROVIDER_NAME,
    AgentModelRoute,
    AgentRuntimeConfig,
)
from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile


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


def _build_runtime(provider: _QueuedProvider) -> RecommendationAgentRuntime:
    return RecommendationAgentRuntime(
        provider=provider,
        runtime_config=AgentRuntimeConfig(
            providers={},
            agent_routes={
                request_name: AgentModelRoute(
                    provider_name=OPENAI_PROVIDER_NAME,
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


def _profile_insights() -> UserProfileAgentOutput:
    return UserProfileAgentOutput(
        risk_tier="R3",
        liquidity_preference="medium",
        investment_horizon="medium",
        return_objective="balanced_growth",
        drawdown_sensitivity="medium",
        profile_focus_zh="偏好稳健底仓与良好流动性。",
        profile_focus_en="Prefers a resilient core and solid liquidity.",
        derived_signals=["intent:steady_growth"],
    )


def _market_output() -> MarketIntelligenceAgentOutput:
    return MarketIntelligenceAgentOutput(
        sentiment="positive",
        stance="balanced",
        preferred_categories=["fund", "stock"],
        avoided_categories=[],
        summary_zh="当前市场相对均衡。",
        summary_en="Current market conditions are broadly balanced.",
        evidence_refs=["market_overview"],
    )


def _candidates() -> list[CandidateProduct]:
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
            id="stock-001",
            category="stock",
            code="600000",
            liquidity="T+1",
            name_zh="龙头科技股",
            name_en="Leading Tech Equity",
            rationale_zh="提供权益弹性。",
            rationale_en="Provides upside optionality.",
            risk_level="R3",
            tags_zh=["科技"],
            tags_en=["technology"],
        ),
    ]


def test_analyze_user_profile_accepts_direct_structured_output() -> None:
    provider = _QueuedProvider(
        [
            {
                "risk_tier": "R2",
                "liquidity_preference": "high",
                "investment_horizon": "one_year",
                "return_objective": "capital_preservation",
                "drawdown_sensitivity": "high",
                "profile_focus_zh": "强调保本和流动性。",
                "profile_focus_en": "Prioritize principal protection and liquidity.",
                "derived_signals": ["intent:保本"],
            }
        ]
    )
    runtime = _build_runtime(provider)

    output, metadata = runtime.analyze_user_profile(_user_profile())

    assert output == UserProfileAgentOutput(
        risk_tier="R2",
        liquidity_preference="high",
        investment_horizon="one_year",
        return_objective="capital_preservation",
        drawdown_sensitivity="high",
        profile_focus_zh="强调保本和流动性。",
        profile_focus_en="Prioritize principal protection and liquidity.",
        derived_signals=["intent:保本"],
    )
    assert metadata.provider_name == "openai"
    assert metadata.model_name == "test-model-user_profile_analyst"


def test_analyze_market_intelligence_raises_clean_error_for_invalid_tool_request() -> None:
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
            _profile_insights(),
            {"summary_zh": "测试市场事实"},
        )


def test_match_products_runs_tool_loop_and_records_tool_trace() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "tool_call",
                "tool_name": "list_candidate_products",
                "tool_arguments": {},
            },
            {
                "action": "final",
                "final_payload": {
                    "recommended_categories": ["fund", "stock"],
                    "fund_ids": ["fund-001"],
                    "wealth_management_ids": [],
                    "stock_ids": ["stock-001"],
                    "ranking_rationale_zh": "保留稳健底仓，并配置少量权益增强。",
                    "ranking_rationale_en": "Keep a resilient core with limited equity exposure.",
                    "filtered_out_reasons": [],
                },
            },
        ]
    )
    runtime = _build_runtime(provider)

    output, metadata = runtime.match_products(
        _user_profile(),
        user_profile_insights=_profile_insights(),
        market_intelligence=_market_output(),
        candidates=_candidates(),
    )

    assert output == ProductMatchAgentOutput(
        recommended_categories=["fund", "stock"],
        fund_ids=["fund-001"],
        wealth_management_ids=[],
        stock_ids=["stock-001"],
        ranking_rationale_zh="保留稳健底仓，并配置少量权益增强。",
        ranking_rationale_en="Keep a resilient core with limited equity exposure.",
        filtered_out_reasons=[],
    )
    assert [call.tool_name for call in metadata.tool_calls] == ["list_candidate_products"]


def test_review_compliance_retries_invalid_payload_once_before_surfacing_error() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "final",
                "final_payload": {"verdict": "approve"},
            },
            {
                "action": "final",
                "final_payload": {"verdict": "approve"},
            },
        ]
    )
    runtime = _build_runtime(provider)

    with pytest.raises(Exception):
        runtime.review_compliance(
            _user_profile(),
            user_profile_insights=_profile_insights(),
            selected_candidates=_candidates()[:1],
            compliance_facts={"rule_snapshot": {"version": "test"}},
        )


def test_coordinate_manager_returns_structured_summary() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "final",
                "final_payload": {
                    "recommendation_status": "ready",
                    "summary_zh": "建议以稳健资产为主。",
                    "summary_en": "Favor resilient assets.",
                    "why_this_plan_zh": ["匹配当前风险承受能力。"],
                    "why_this_plan_en": ["Matches the current risk profile."],
                },
            }
        ]
    )
    runtime = _build_runtime(provider)

    output, _ = runtime.coordinate_manager(
        _user_profile(),
        user_profile_insights=_profile_insights(),
        market_intelligence=_market_output(),
        product_match=ProductMatchAgentOutput(
            recommended_categories=["fund", "stock"],
            fund_ids=["fund-001"],
            wealth_management_ids=[],
            stock_ids=["stock-001"],
            ranking_rationale_zh="测试排序。",
            ranking_rationale_en="Test ranking.",
            filtered_out_reasons=[],
        ),
        compliance_review=ComplianceReviewAgentOutput(
            verdict="approve",
            approved_ids=["fund-001", "stock-001"],
            rejected_ids=[],
            reason_summary_zh="通过审核。",
            reason_summary_en="Approved.",
            required_disclosures_zh=["理财非存款，投资需谨慎。"],
            required_disclosures_en=["Investing involves risk. Proceed prudently."],
            suitability_notes_zh=["适配通过。"],
            suitability_notes_en=["Approved."],
            applied_rule_ids=["test-rule"],
            blocking_reason_codes=[],
        ),
    )

    assert output == ManagerCoordinatorAgentOutput(
        recommendation_status="ready",
        summary_zh="建议以稳健资产为主。",
        summary_en="Favor resilient assets.",
        why_this_plan_zh=["匹配当前风险承受能力。"],
        why_this_plan_en=["Matches the current risk profile."],
    )


def test_provider_protocol_has_chat_with_tools() -> None:
    from financehub_market_api.recommendation.agents.interfaces import StructuredOutputProvider

    assert hasattr(StructuredOutputProvider, "chat_with_tools")
