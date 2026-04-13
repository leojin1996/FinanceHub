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
        response = self._responses.pop(0)
        if not isinstance(response, dict):
            raise AssertionError("test response must be a dict")
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


def _candidate(product_id: str, *, category: str, risk_level: str) -> CandidateProduct:
    return CandidateProduct(
        id=product_id,
        category=category,
        code=product_id.upper(),
        liquidity="T+1",
        name_zh=f"{product_id}-zh",
        name_en=f"{product_id}-en",
        rationale_zh="候选理由",
        rationale_en="candidate rationale",
        risk_level=risk_level,
        tags_zh=["tag"],
        tags_en=["tag"],
    )


def test_agent_routes_use_the_five_core_graph_nodes() -> None:
    assert AGENT_MODEL_ROUTE_ENV_NAMES == {
        "user_profile_analyst": "USER_PROFILE_ANALYST",
        "market_intelligence": "MARKET_INTELLIGENCE",
        "product_match_expert": "PRODUCT_MATCH_EXPERT",
        "compliance_risk_officer": "COMPLIANCE_RISK_OFFICER",
        "manager_coordinator": "MANAGER_COORDINATOR",
    }


def test_match_products_supports_tool_grounded_structured_output() -> None:
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
                    "recommended_categories": ["wealth_management", "fund"],
                    "fund_ids": ["fund-001"],
                    "wealth_management_ids": ["wm-001"],
                    "stock_ids": [],
                    "ranking_rationale_zh": "优先保留稳健候选。",
                    "ranking_rationale_en": "Prefer resilient candidates.",
                    "filtered_out_reasons": ["stock-001 filtered by AI suitability analysis"],
                },
            },
        ]
    )
    runtime = _build_runtime(provider)

    output, metadata = runtime.match_products(
        _user_profile(),
        user_profile_insights=UserProfileAgentOutput(
            risk_tier="R2",
            liquidity_preference="high",
            investment_horizon="one_year",
            return_objective="capital_preservation",
            drawdown_sensitivity="high",
            profile_focus_zh="强调保本和流动性。",
            profile_focus_en="Prioritize principal protection and liquidity.",
            derived_signals=["intent:保本", "conversation:高流动性"],
        ),
        market_intelligence=MarketIntelligenceAgentOutput(
            sentiment="negative",
            stance="defensive",
            preferred_categories=["wealth_management", "fund"],
            avoided_categories=["stock"],
            summary_zh="防守优先。",
            summary_en="Favor defense.",
            evidence_refs=["market_overview", "macro_and_rates"],
        ),
        candidates=[
            _candidate("fund-001", category="fund", risk_level="R2"),
            _candidate("wm-001", category="wealth_management", risk_level="R1"),
        ],
    )

    assert output == ProductMatchAgentOutput(
        recommended_categories=["wealth_management", "fund"],
        fund_ids=["fund-001"],
        wealth_management_ids=["wm-001"],
        stock_ids=[],
        ranking_rationale_zh="优先保留稳健候选。",
        ranking_rationale_en="Prefer resilient candidates.",
        filtered_out_reasons=["stock-001 filtered by AI suitability analysis"],
    )
    assert [call.tool_name for call in metadata.tool_calls] == ["list_candidate_products"]
    initial_prompt = provider.calls[0]["messages"][-1]["content"]
    assert "Candidate pool facts" in initial_prompt
    assert '"candidate_count": 2' in initial_prompt
    assert '"candidate_ids": [' in initial_prompt
    assert '"fund-001"' in initial_prompt
    assert '"wm-001"' in initial_prompt
    assert "Tool outputs so far" in initial_prompt
    assert "1. list_candidate_products" in initial_prompt
    assert '"candidates": [' in initial_prompt


def test_match_products_retries_when_model_returns_empty_selection() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "final",
                "final_payload": {
                    "recommended_categories": [],
                    "fund_ids": [],
                    "wealth_management_ids": [],
                    "stock_ids": [],
                    "ranking_rationale_zh": "先给出排序理由，但遗漏了选中 ID。",
                    "ranking_rationale_en": "Returned ranking rationale but omitted selected IDs.",
                    "filtered_out_reasons": [],
                },
            },
            {
                "action": "final",
                "final_payload": {
                    "recommended_categories": ["wealth_management", "fund"],
                    "fund_ids": ["fund-001"],
                    "wealth_management_ids": ["wm-001"],
                    "stock_ids": [],
                    "ranking_rationale_zh": "修正后返回完整候选。",
                    "ranking_rationale_en": "Return the full candidate selection after correction.",
                    "filtered_out_reasons": [],
                },
            },
        ]
    )
    runtime = _build_runtime(provider)

    output, _ = runtime.match_products(
        _user_profile(),
        user_profile_insights=UserProfileAgentOutput(
            risk_tier="R2",
            liquidity_preference="high",
            investment_horizon="one_year",
            return_objective="capital_preservation",
            drawdown_sensitivity="high",
            profile_focus_zh="强调保本和流动性。",
            profile_focus_en="Prioritize principal protection and liquidity.",
            derived_signals=["intent:保本", "conversation:高流动性"],
        ),
        market_intelligence=MarketIntelligenceAgentOutput(
            sentiment="negative",
            stance="defensive",
            preferred_categories=["wealth_management", "fund"],
            avoided_categories=["stock"],
            summary_zh="防守优先。",
            summary_en="Favor defense.",
            evidence_refs=["market_overview", "macro_and_rates"],
        ),
        candidates=[
            _candidate("fund-001", category="fund", risk_level="R2"),
            _candidate("wm-001", category="wealth_management", risk_level="R1"),
        ],
    )

    assert output.fund_ids == ["fund-001"]
    assert output.wealth_management_ids == ["wm-001"]
    assert len(provider.calls) == 2
    assert "Previous response was invalid" in provider.calls[-1]["messages"][-1]["content"]
    assert "Candidate pool is not empty" in provider.calls[-1]["messages"][-1]["content"]
    assert "Valid supplied candidate ids" in provider.calls[-1]["messages"][-1]["content"]
    assert "fund-001" in provider.calls[-1]["messages"][-1]["content"]
    assert "wm-001" in provider.calls[-1]["messages"][-1]["content"]


def test_match_products_accepts_return_decision_with_top_level_selected_product_ids() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "return_decision",
                "selected_product_ids": ["wm-001", "fund-001"],
                "primary_recommendation_id": "wm-001",
                "rationale_zh": "返回顶层决策字段。",
                "rationale_en": "Return decision fields at the top level.",
                "filtered_out_reasons": [],
            }
        ]
    )
    runtime = _build_runtime(provider)

    output, _ = runtime.match_products(
        _user_profile(),
        user_profile_insights=UserProfileAgentOutput(
            risk_tier="R2",
            liquidity_preference="high",
            investment_horizon="one_year",
            return_objective="capital_preservation",
            drawdown_sensitivity="high",
            profile_focus_zh="强调保本和流动性。",
            profile_focus_en="Prioritize principal protection and liquidity.",
            derived_signals=["intent:保本", "conversation:高流动性"],
        ),
        market_intelligence=MarketIntelligenceAgentOutput(
            sentiment="negative",
            stance="defensive",
            preferred_categories=["wealth_management", "fund"],
            avoided_categories=["stock"],
            summary_zh="防守优先。",
            summary_en="Favor defense.",
            evidence_refs=["market_overview", "macro_and_rates"],
        ),
        candidates=[
            _candidate("fund-001", category="fund", risk_level="R2"),
            _candidate("wm-001", category="wealth_management", risk_level="R1"),
        ],
    )

    assert output.selected_product_ids == ["wm-001", "fund-001"]
    assert output.ranking_rationale_zh == "返回顶层决策字段。"
    assert output.ranking_rationale_en == "Return decision fields at the top level."


def test_match_products_accepts_selected_candidate_ids_and_selection_rationale_aliases() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "return_decision",
                "selected_candidate_ids": ["fund-001", "wm-001"],
                "primary_recommendation_id": "wm-001",
                "selection_rationale_zh": "候选兼顾稳健底仓与流动性。",
                "selection_rationale_en": "The picks balance resilience and liquidity.",
                "filtered_out_reasons": [],
            }
        ]
    )
    runtime = _build_runtime(provider)

    output, _ = runtime.match_products(
        _user_profile(),
        user_profile_insights=UserProfileAgentOutput(
            risk_tier="R2",
            liquidity_preference="high",
            investment_horizon="one_year",
            return_objective="capital_preservation",
            drawdown_sensitivity="high",
            profile_focus_zh="强调保本和流动性。",
            profile_focus_en="Prioritize principal protection and liquidity.",
            derived_signals=["intent:保本", "conversation:高流动性"],
        ),
        market_intelligence=MarketIntelligenceAgentOutput(
            sentiment="negative",
            stance="defensive",
            preferred_categories=["wealth_management", "fund"],
            avoided_categories=["stock"],
            summary_zh="防守优先。",
            summary_en="Favor defense.",
            evidence_refs=["market_overview", "macro_and_rates"],
        ),
        candidates=[
            _candidate("fund-001", category="fund", risk_level="R2"),
            _candidate("wm-001", category="wealth_management", risk_level="R1"),
        ],
    )

    assert output.selected_product_ids == ["wm-001", "fund-001"]
    assert output.ranking_rationale_zh == "候选兼顾稳健底仓与流动性。"
    assert output.ranking_rationale_en == "The picks balance resilience and liquidity."


def test_product_match_output_normalizes_selected_ids_by_category() -> None:
    output = ProductMatchAgentOutput.model_validate(
        {
            "recommended_categories": ["fund", "wealth_management"],
            "selected_ids": {
                "fund": ["fund-001"],
                "wealth_management": ["wm-001"],
                "stock": [],
            },
            "ranking_rationale_zh": "优先配置稳健候选。",
            "ranking_rationale_en": "Prefer resilient candidates.",
            "filtered_out": {
                "stock-001": "filtered by AI suitability analysis",
            },
        }
    )

    assert output == ProductMatchAgentOutput(
        recommended_categories=["fund", "wealth_management"],
        fund_ids=["fund-001"],
        wealth_management_ids=["wm-001"],
        stock_ids=[],
        ranking_rationale_zh="优先配置稳健候选。",
        ranking_rationale_en="Prefer resilient candidates.",
        filtered_out_reasons=["stock-001: filtered by AI suitability analysis"],
    )


def test_product_match_output_normalizes_nested_selected_products_shape() -> None:
    output = ProductMatchAgentOutput.model_validate(
        {
            "recommended_categories": ["fund", "wealth_management"],
            "selected_products": {
                "fund": ["fund-001"],
                "wealth_management": ["wm-001"],
            },
            "ranking_rationale": {
                "zh": "候选同时兼顾稳健性与流动性。",
                "en": "The selected products balance resilience and liquidity.",
            },
            "filtered_out": {
                "reasons": {
                    "zh": "无产品被过滤。",
                    "en": "No products were filtered out.",
                }
            },
        }
    )

    assert output == ProductMatchAgentOutput(
        recommended_categories=["fund", "wealth_management"],
        selected_product_ids=["fund-001", "wm-001"],
        fund_ids=["fund-001"],
        wealth_management_ids=["wm-001"],
        stock_ids=[],
        ranking_rationale_zh="候选同时兼顾稳健性与流动性。",
        ranking_rationale_en="The selected products balance resilience and liquidity.",
        filtered_out_reasons=["无产品被过滤。", "No products were filtered out."],
    )


def test_product_match_output_normalizes_dict_filtered_out_reasons() -> None:
    output = ProductMatchAgentOutput.model_validate(
        {
            "selected_product_ids": ["wm-001"],
            "ranking_rationale_zh": "优先选择现金管理。",
            "ranking_rationale_en": "Prioritize cash management.",
            "filtered_out_reasons": {},
        }
    )

    assert output.selected_product_ids == ["wm-001"]
    assert output.filtered_out_reasons == []


def test_product_match_output_normalizes_grouped_selected_product_ids_shape() -> None:
    output = ProductMatchAgentOutput.model_validate(
        {
            "recommended_categories": ["fund", "stock"],
            "selected_product_ids": {
                "fund": ["fund-301"],
                "stock": ["stock-301"],
            },
            "ranking_rationale_zh": "候选兼顾底仓与权益增强。",
            "ranking_rationale_en": "The picks balance a core holding with equity upside.",
            "filtered_out_reasons": ["wm-301 was filtered out."],
        }
    )

    assert output == ProductMatchAgentOutput(
        recommended_categories=["fund", "stock"],
        selected_product_ids=["fund-301", "stock-301"],
        fund_ids=["fund-301"],
        wealth_management_ids=[],
        stock_ids=["stock-301"],
        ranking_rationale_zh="候选兼顾底仓与权益增强。",
        ranking_rationale_en="The picks balance a core holding with equity upside.",
        filtered_out_reasons=["wm-301 was filtered out."],
    )


def test_product_match_output_normalizes_rationale_lists_into_strings() -> None:
    output = ProductMatchAgentOutput.model_validate(
        {
            "selected_product_ids": ["fund-301", "stock-301"],
            "ranking_rationale_zh": [
                "fund-301：适合作为底仓。",
                "stock-301：适合作为增强收益配置。",
            ],
            "ranking_rationale_en": [
                "fund-301: suitable as the core position.",
                "stock-301: suitable as the equity enhancer.",
            ],
            "filtered_out_reasons": [],
        }
    )

    assert output.ranking_rationale_zh == "fund-301：适合作为底仓。\nstock-301：适合作为增强收益配置。"
    assert (
        output.ranking_rationale_en
        == "fund-301: suitable as the core position.\nstock-301: suitable as the equity enhancer."
    )


def test_user_profile_output_normalizes_object_derived_signals() -> None:
    output = UserProfileAgentOutput.model_validate(
        {
            "risk_tier": "R2",
            "liquidity_preference": "high",
            "investment_horizon": "one_year",
            "return_objective": "capital_preservation",
            "drawdown_sensitivity": "high",
            "profile_focus_zh": "强调保本和流动性。",
            "profile_focus_en": "Prioritize principal protection and liquidity.",
            "derived_signals": [
                {
                    "signal": "capital_preservation",
                    "rationale": "用户明确表示不想亏本",
                },
                {
                    "source": "conversation",
                    "reason": "用户强调流动性",
                },
            ],
        }
    )

    assert output.derived_signals == [
        "capital_preservation: 用户明确表示不想亏本",
        "conversation: 用户强调流动性",
    ]


def test_user_profile_output_normalizes_mapping_derived_signals() -> None:
    output = UserProfileAgentOutput.model_validate(
        {
            "risk_tier": "R3",
            "liquidity_preference": "medium",
            "investment_horizon": "medium",
            "return_objective": "balanced_growth",
            "drawdown_sensitivity": "medium",
            "profile_focus_zh": "兼顾收益和波动承受能力。",
            "profile_focus_en": "Balance upside with drawdown tolerance.",
            "derived_signals": {
                "risk_tolerance_level": "medium_high",
                "capital_stability": "12/20",
                "returnObjective": "16/20",
            },
        }
    )

    assert output.derived_signals == [
        "risk_tolerance_level: medium_high",
        "capital_stability: 12/20",
        "returnObjective: 16/20",
    ]


def test_user_profile_output_normalizes_profile_alias_risk_tier() -> None:
    output = UserProfileAgentOutput.model_validate(
        {
            "risk_tier": "conservative",
            "liquidity_preference": "high",
            "investment_horizon": "one_year",
            "return_objective": "capital_preservation",
            "drawdown_sensitivity": "high",
            "profile_focus_zh": "强调保本和流动性。",
            "profile_focus_en": "Prioritize principal protection and liquidity.",
            "derived_signals": [],
        }
    )

    assert output.risk_tier == "R2"


@pytest.mark.parametrize(
    "raw_stance",
    [
        "bullish",
        "opportunistic",
        "pro-growth risk-on",
        "pro-risk growth",
        "aggressive_growth",
        "lean_growth",
        "lean_growth_risk_on",
    ],
)
def test_market_intelligence_output_normalizes_stance_aliases(raw_stance: str) -> None:
    output = MarketIntelligenceAgentOutput.model_validate(
        {
            "sentiment": "positive",
            "stance": raw_stance,
            "preferred_categories": ["stock", "fund"],
            "avoided_categories": [],
            "summary_zh": "市场偏强，适合进攻。",
            "summary_en": "Markets are strong enough for offense.",
            "evidence_refs": ["market_overview"],
        }
    )

    assert output.stance == "offensive"


def test_review_compliance_returns_block_capable_payload() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "final",
                "final_payload": {
                    "verdict": "block",
                    "approved_ids": [],
                    "rejected_ids": ["wm-001"],
                    "reason_summary_zh": "规则快照要求人工复核。",
                    "reason_summary_en": "Rules require manual review.",
                    "required_disclosures_zh": ["理财非存款，投资需谨慎。"],
                    "required_disclosures_en": ["Investing involves risk. Proceed prudently."],
                    "suitability_notes_zh": ["候选缺少关键回撤指标。"],
                    "suitability_notes_en": ["The candidate is missing a required drawdown metric."],
                    "applied_rule_ids": ["cn-suitability-r2"],
                    "blocking_reason_codes": ["missing_required_metric"],
                },
            }
        ]
    )
    runtime = _build_runtime(provider)

    output, _ = runtime.review_compliance(
        _user_profile(),
        user_profile_insights=UserProfileAgentOutput(
            risk_tier="R2",
            liquidity_preference="high",
            investment_horizon="one_year",
            return_objective="capital_preservation",
            drawdown_sensitivity="high",
            profile_focus_zh="强调保本和流动性。",
            profile_focus_en="Prioritize principal protection and liquidity.",
            derived_signals=["intent:保本"],
        ),
        selected_candidates=[_candidate("wm-001", category="wealth_management", risk_level="R2")],
        compliance_facts={
            "rule_snapshot": {
                "version": "2026-04-10",
                "risk_tiers": {"R2": {"max_risk_level": "R2", "max_lockup_days": 90}},
            }
        },
    )

    assert output == ComplianceReviewAgentOutput(
        verdict="block",
        approved_ids=[],
        rejected_ids=["wm-001"],
        reason_summary_zh="规则快照要求人工复核。",
        reason_summary_en="Rules require manual review.",
        required_disclosures_zh=["理财非存款，投资需谨慎。"],
        required_disclosures_en=["Investing involves risk. Proceed prudently."],
        suitability_notes_zh=["候选缺少关键回撤指标。"],
        suitability_notes_en=["The candidate is missing a required drawdown metric."],
        applied_rule_ids=["cn-suitability-r2"],
        blocking_reason_codes=["missing_required_metric"],
    )


def test_review_compliance_accepts_return_decision_and_real_world_aliases() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "return_decision",
                "decision": {
                    "verdict": "approve",
                    "approved_candidate_ids": ["wm-001"],
                    "rejected_candidate_ids": [],
                    "reason_zh": "候选通过审核。",
                    "reason_en": "The candidate passed review.",
                    "disclosures": ["理财非存款，投资需谨慎。"],
                    "suitability_notes": "候选与当前画像一致。",
                    "applied_rule_ids": ["cn-suitability-r2"],
                    "blocking_reason_codes": [],
                },
            }
        ]
    )
    runtime = _build_runtime(provider)

    output, _ = runtime.review_compliance(
        _user_profile(),
        user_profile_insights=UserProfileAgentOutput(
            risk_tier="R2",
            liquidity_preference="high",
            investment_horizon="one_year",
            return_objective="capital_preservation",
            drawdown_sensitivity="high",
            profile_focus_zh="强调保本和流动性。",
            profile_focus_en="Prioritize principal protection and liquidity.",
            derived_signals=["intent:保本"],
        ),
        selected_candidates=[_candidate("wm-001", category="wealth_management", risk_level="R2")],
        compliance_facts={"rule_snapshot": {"version": "2026-04-10"}},
    )

    assert output == ComplianceReviewAgentOutput(
        verdict="approve",
        approved_ids=["wm-001"],
        rejected_ids=[],
        reason_summary_zh="候选通过审核。",
        reason_summary_en="The candidate passed review.",
        required_disclosures_zh=["理财非存款，投资需谨慎。"],
        required_disclosures_en=["理财非存款，投资需谨慎。"],
        suitability_notes_zh=["候选与当前画像一致。"],
        suitability_notes_en=["候选与当前画像一致。"],
        applied_rule_ids=["cn-suitability-r2"],
        blocking_reason_codes=[],
    )


def test_compliance_output_normalizes_string_suitability_note_fields() -> None:
    output = ComplianceReviewAgentOutput.model_validate(
        {
            "verdict": "approve",
            "approved_ids": ["wm-001"],
            "rejected_ids": [],
            "reason_summary_zh": "候选通过审核。",
            "reason_summary_en": "The candidate passed review.",
            "required_disclosures_zh": ["理财非存款，投资需谨慎。"],
            "required_disclosures_en": ["Investing involves risk. Proceed prudently."],
            "suitability_notes_zh": "中文适配说明。",
            "suitability_notes_en": "English suitability note.",
            "applied_rule_ids": ["cn-suitability-r2"],
            "blocking_reason_codes": [],
        }
    )

    assert output.suitability_notes_zh == ["中文适配说明。"]
    assert output.suitability_notes_en == ["English suitability note."]


def test_compliance_output_normalizes_structured_disclosure_objects() -> None:
    output = ComplianceReviewAgentOutput.model_validate(
        {
            "verdict": "approve",
            "approved_ids": ["fund-001", "wm-001"],
            "rejected_ids": [],
            "reason_summary_zh": "候选通过审核。",
            "reason_summary_en": "The candidates passed review.",
            "required_disclosures_zh": [
                {
                    "disclosure_zh": "fund-001 为短债基金，净值可能小幅波动。",
                    "severity": "info",
                },
                {
                    "disclosure_zh": "wm-001 为现金管理产品，赎回规则需确认。",
                    "severity": "info",
                },
            ],
            "required_disclosures_en": [
                {
                    "disclosure_en": "fund-001 is a short-duration bond fund and may see small NAV moves.",
                    "severity": "info",
                },
                {
                    "disclosure_en": "wm-001 is a cash management product and redemption rules should be confirmed.",
                    "severity": "info",
                },
            ],
            "suitability_notes_zh": ["候选与当前画像一致。"],
            "suitability_notes_en": ["The candidates align with the current profile."],
            "applied_rule_ids": ["cn-suitability-r2"],
            "blocking_reason_codes": [],
        }
    )

    assert output.required_disclosures_zh == [
        "fund-001 为短债基金，净值可能小幅波动。",
        "wm-001 为现金管理产品，赎回规则需确认。",
    ]
    assert output.required_disclosures_en == [
        "fund-001 is a short-duration bond fund and may see small NAV moves.",
        "wm-001 is a cash management product and redemption rules should be confirmed.",
    ]


def test_compliance_output_normalizes_product_id_and_disclosure_aliases() -> None:
    output = ComplianceReviewAgentOutput.model_validate(
        {
            "verdict": "revise_conservative",
            "approved_product_ids": ["fund-005", "stock-000100"],
            "blocked_product_ids": ["stock-600030"],
            "blocking_reason_codes": ["RISK_LEVEL_EXCEEDS_PROFILE"],
            "applied_rule_ids": [],
            "disclosures_zh": [
                "用户风险等级为R3（平衡型），中信证券（stock-600030）风险等级为R4，超出用户风险承受能力，已从推荐中移除。",
                "其余候选符合当前配置需求。",
            ],
            "disclosures_en": [
                "User risk tier is R3 (Balanced). CITIC Securities (stock-600030) exceeds user risk tolerance and has been removed.",
                "The remaining candidates fit the current allocation need.",
            ],
        }
    )

    assert output.approved_ids == ["fund-005", "stock-000100"]
    assert output.rejected_ids == ["stock-600030"]
    assert output.reason_summary_zh == "用户风险等级为R3（平衡型），中信证券（stock-600030）风险等级为R4，超出用户风险承受能力，已从推荐中移除。"
    assert output.reason_summary_en == "User risk tier is R3 (Balanced). CITIC Securities (stock-600030) exceeds user risk tolerance and has been removed."
    assert output.required_disclosures_zh == [
        "用户风险等级为R3（平衡型），中信证券（stock-600030）风险等级为R4，超出用户风险承受能力，已从推荐中移除。",
        "其余候选符合当前配置需求。",
    ]
    assert output.required_disclosures_en == [
        "User risk tier is R3 (Balanced). CITIC Securities (stock-600030) exceeds user risk tolerance and has been removed.",
        "The remaining candidates fit the current allocation need.",
    ]


def test_coordinate_manager_returns_summary_and_rationale_lists() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "final",
                "final_payload": {
                    "recommendation_status": "ready",
                    "summary_zh": "建议以高流动性稳健资产为主。",
                    "summary_en": "Favor high-liquidity resilient assets.",
                    "why_this_plan_zh": ["匹配 R2 稳健需求。"],
                    "why_this_plan_en": ["Matches R2 resilience needs."],
                },
            }
        ]
    )
    runtime = _build_runtime(provider)

    output, _ = runtime.coordinate_manager(
        _user_profile(),
        user_profile_insights=UserProfileAgentOutput(
            risk_tier="R2",
            liquidity_preference="high",
            investment_horizon="one_year",
            return_objective="capital_preservation",
            drawdown_sensitivity="high",
            profile_focus_zh="强调保本和流动性。",
            profile_focus_en="Prioritize principal protection and liquidity.",
            derived_signals=["intent:保本"],
        ),
        market_intelligence=MarketIntelligenceAgentOutput(
            sentiment="negative",
            stance="defensive",
            preferred_categories=["wealth_management", "fund"],
            avoided_categories=["stock"],
            summary_zh="防守优先。",
            summary_en="Favor defense.",
            evidence_refs=["market_overview"],
        ),
        product_match=ProductMatchAgentOutput(
            recommended_categories=["wealth_management", "fund"],
            fund_ids=["fund-001"],
            wealth_management_ids=["wm-001"],
            stock_ids=[],
            ranking_rationale_zh="优先稳健候选。",
            ranking_rationale_en="Prefer resilient candidates.",
            filtered_out_reasons=[],
        ),
        compliance_review=ComplianceReviewAgentOutput(
            verdict="approve",
            approved_ids=["fund-001", "wm-001"],
            rejected_ids=[],
            reason_summary_zh="适配通过。",
            reason_summary_en="Approved.",
            required_disclosures_zh=["理财非存款，投资需谨慎。"],
            required_disclosures_en=["Investing involves risk. Proceed prudently."],
            suitability_notes_zh=["风险等级与流动性匹配。"],
            suitability_notes_en=["Risk and liquidity fit the user profile."],
            applied_rule_ids=["cn-suitability-r2"],
            blocking_reason_codes=[],
        ),
    )

    assert output == ManagerCoordinatorAgentOutput(
        recommendation_status="ready",
        summary_zh="建议以高流动性稳健资产为主。",
        summary_en="Favor high-liquidity resilient assets.",
        why_this_plan_zh=["匹配 R2 稳健需求。"],
        why_this_plan_en=["Matches R2 resilience needs."],
    )


def test_coordinate_manager_normalizes_summary_and_why_plan_aliases() -> None:
    provider = _QueuedProvider(
        [
            {
                "action": "final",
                "final_payload": {
                    "recommendation_status": "approved_with_revisions",
                    "recommendation_summary_zh": "建议保持稳健底仓，并保留充足流动性。",
                    "recommendation_summary_en": "Keep a resilient core allocation with ample liquidity.",
                    "why_this_plan_bullets_zh": [
                        "保留高流动性资产以覆盖短期资金需求。"
                    ],
                    "why_this_plan_bullets_en": [
                        "Retain high-liquidity assets for near-term cash needs."
                    ],
                },
            },
            {
                "action": "final",
                "final_payload": {
                    "recommendation_status": "approved_with_revisions",
                    "recommendation_summary_zh": "建议保持稳健底仓，并保留充足流动性。",
                    "recommendation_summary_en": "Keep a resilient core allocation with ample liquidity.",
                    "why_this_plan_bullets_zh": [
                        "保留高流动性资产以覆盖短期资金需求。"
                    ],
                    "why_this_plan_bullets_en": [
                        "Retain high-liquidity assets for near-term cash needs."
                    ],
                },
            },
        ]
    )
    runtime = _build_runtime(provider)

    output, _ = runtime.coordinate_manager(
        _user_profile(),
        user_profile_insights=UserProfileAgentOutput(
            risk_tier="R2",
            liquidity_preference="high",
            investment_horizon="one_year",
            return_objective="capital_preservation",
            drawdown_sensitivity="high",
            profile_focus_zh="强调保本和流动性。",
            profile_focus_en="Prioritize principal protection and liquidity.",
            derived_signals=["intent:保本"],
        ),
        market_intelligence=MarketIntelligenceAgentOutput(
            sentiment="negative",
            stance="defensive",
            preferred_categories=["wealth_management", "fund"],
            avoided_categories=["stock"],
            summary_zh="防守优先。",
            summary_en="Favor defense.",
            evidence_refs=["market_overview"],
        ),
        product_match=ProductMatchAgentOutput(
            recommended_categories=["wealth_management", "fund"],
            fund_ids=["fund-001"],
            wealth_management_ids=["wm-001"],
            stock_ids=[],
            ranking_rationale_zh="优先稳健候选。",
            ranking_rationale_en="Prefer resilient candidates.",
            filtered_out_reasons=[],
        ),
        compliance_review=ComplianceReviewAgentOutput(
            verdict="revise_conservative",
            approved_ids=["fund-001", "wm-001"],
            rejected_ids=[],
            reason_summary_zh="建议保守修订。",
            reason_summary_en="Revise conservatively.",
            required_disclosures_zh=["理财非存款，投资需谨慎。"],
            required_disclosures_en=["Investing involves risk. Proceed prudently."],
            suitability_notes_zh=["建议以高流动性稳健配置为主。"],
            suitability_notes_en=["Favor liquid and resilient allocations."],
            applied_rule_ids=["cn-suitability-r2"],
            blocking_reason_codes=[],
        ),
    )

    assert output == ManagerCoordinatorAgentOutput(
        recommendation_status="approved_with_revisions",
        summary_zh="建议保持稳健底仓，并保留充足流动性。",
        summary_en="Keep a resilient core allocation with ample liquidity.",
        why_this_plan_zh=["保留高流动性资产以覆盖短期资金需求。"],
        why_this_plan_en=["Retain high-liquidity assets for near-term cash needs."],
    )


def test_manager_output_sanitizes_internal_statuses_and_mixed_language_in_zh_fields() -> None:
    output = ManagerCoordinatorAgentOutput.model_validate(
        {
            "recommendation_status": "limited",
            "summary_zh": "当前方案保持 revise_conservative 口径。",
            "summary_en": "Keep the conservative revision posture.",
            "why_this_plan_zh": [
                "在规则快照缺失、且缺少历史持仓与交易行为数据的情况下，方案仍保留必要的审慎约束。",
                "结合 defensive 市场立场，优先保留 fund 与 stock。",
            ],
            "why_this_plan_en": [
                "The plan keeps a conservative revision posture.",
                "A defensive stance favors funds and stocks.",
            ],
        }
    )

    assert output.summary_zh == "当前方案保持偏谨慎调整口径。"
    assert output.why_this_plan_zh == [
        "当前方案主要依据风险测评结果、市场信息与已筛选候选生成，并保留必要的审慎约束。",
        "结合防守市场立场，优先保留基金与股票。",
    ]


def test_runtime_allows_up_to_four_tool_calls_before_exhaustion() -> None:
    provider = _QueuedProvider(
        [
            {"action": "tool_call", "tool_name": "list_candidate_products", "tool_arguments": {}},
            {"action": "tool_call", "tool_name": "list_candidate_products", "tool_arguments": {}},
            {"action": "tool_call", "tool_name": "list_candidate_products", "tool_arguments": {}},
            {"action": "tool_call", "tool_name": "list_candidate_products", "tool_arguments": {}},
            {"action": "tool_call", "tool_name": "list_candidate_products", "tool_arguments": {}},
        ]
    )
    runtime = _build_runtime(provider)

    with pytest.raises(RuntimeError, match="tool loop exhausted"):
        runtime.match_products(
            _user_profile(),
            user_profile_insights=UserProfileAgentOutput(
                risk_tier="R2",
                liquidity_preference="high",
                investment_horizon="one_year",
                return_objective="capital_preservation",
                drawdown_sensitivity="high",
                profile_focus_zh="强调保本和流动性。",
                profile_focus_en="Prioritize principal protection and liquidity.",
                derived_signals=["intent:保本"],
            ),
            market_intelligence=MarketIntelligenceAgentOutput(
                sentiment="negative",
                stance="defensive",
                preferred_categories=["wealth_management", "fund"],
                avoided_categories=["stock"],
                summary_zh="防守优先。",
                summary_en="Favor defense.",
                evidence_refs=["market_overview"],
            ),
            candidates=[_candidate("fund-001", category="fund", risk_level="R2")],
        )
