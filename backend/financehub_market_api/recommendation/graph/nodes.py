from __future__ import annotations

from collections import deque

from pydantic import ValidationError

from financehub_market_api.recommendation.agents.contracts import (
    MarketIntelligenceAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.live_runtime import (
    AnthropicRecommendationAgentRuntime,
)
from financehub_market_api.recommendation.agents.runtime_context import (
    AgentPromptContext,
    AgentPromptSection,
    AgentToolCallRecord,
    SelectedPlanContext,
)
from financehub_market_api.recommendation.compliance import ComplianceReviewService
from financehub_market_api.recommendation.graph.routing import route_compliance_verdict
from financehub_market_api.recommendation.graph.state import (
    AgentMarketSummaryState,
    AgentProfileFocusState,
    ComplianceReviewState,
    FinalResponseState,
    ManagerBrief,
    MarketIntelligenceState,
    ProductStrategy,
    RecommendationGraphState,
    RetrievalContext,
    RetrievedCandidate,
    RuntimeCandidateSnapshot,
    UserIntelligence,
    append_agent_trace_event,
    append_warning,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.intelligence.service import (
    _DEFAULT_MACRO_SUMMARY,
    _DEFAULT_MARKET_OVERVIEW_SUMMARY,
    _DEFAULT_NEWS_SUMMARIES,
    _DEFAULT_RATE_SUMMARY,
)
from financehub_market_api.recommendation.manager_synthesis import (
    ManagerSynthesisService,
)
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.profile_intelligence import (
    ProfileIntelligenceService,
)
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.schemas import CandidateProduct
from financehub_market_api.recommendation.schemas.domain import MarketContext

_RISK_ORDER = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}
_CATEGORY_TO_RANKING_REQUEST = {
    "fund": "fund_selection",
    "wealth_management": "wealth_selection",
    "stock": "stock_selection",
}
_RANKING_STAGE_LABELS_ZH = {
    "fund_selection": "基金",
    "wealth_selection": "银行理财",
    "stock_selection": "股票",
}


def user_profile_analyst_node(
    state: RecommendationGraphState,
    *,
    profile_intelligence_service: ProfileIntelligenceService,
    agent_runtime: AnthropicRecommendationAgentRuntime | None = None,
) -> RecommendationGraphState:
    payload = state["request_context"].payload
    risk_profile = payload.riskAssessmentResult.finalProfile

    user_intelligence = profile_intelligence_service.build_user_intelligence(
        risk_profile=risk_profile,
        questionnaire_answers=list(payload.questionnaireAnswers),
        historical_holdings=list(payload.historicalHoldings),
        historical_transactions=list(payload.historicalTransactions),
        user_intent_text=state["request_context"].user_intent_text,
    )

    next_state = {
        **state,
        "user_intelligence": user_intelligence,
        "agent_profile_focus": None,
        "agent_market_summary": None,
    }
    provider_name: str | None = None
    model_name: str | None = None
    response_summary = f"risk_tier={user_intelligence.risk_tier}"
    trace_tool_calls: tuple[AgentToolCallRecord, ...] = ()
    trace_status = "finish"
    if agent_runtime is not None:
        try:
            metadata = agent_runtime.route_metadata("user_profile")
        except Exception:  # noqa: BLE001
            metadata = None
        else:
            provider_name = metadata.provider_name
            model_name = metadata.model_name
        try:
            profile_focus, metadata = agent_runtime.analyze_user_profile(
                map_user_profile(risk_profile),
                prompt_context=_build_user_profile_prompt_context(
                    state=state,
                    user_intelligence=user_intelligence,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            next_state = append_warning(
                next_state,
                stage="user_profile_analyst",
                code="agent_user_profile_failed",
                message=_format_runtime_error(exc),
            )
            trace_status = "error"
        else:
            provider_name = metadata.provider_name
            model_name = metadata.model_name
            trace_tool_calls = metadata.tool_calls
            next_state = {
                **next_state,
                "user_intelligence": user_intelligence.model_copy(
                    update={
                        "profile_summary_zh": (
                            f"{user_intelligence.profile_summary_zh} "
                            f"AI画像补充：{profile_focus.profile_focus_zh}"
                        ),
                        "profile_summary_en": (
                            f"{user_intelligence.profile_summary_en} "
                            f"AI focus: {profile_focus.profile_focus_en}"
                        ),
                    }
                ),
                "agent_profile_focus": AgentProfileFocusState(
                    profile_focus_zh=profile_focus.profile_focus_zh,
                    profile_focus_en=profile_focus.profile_focus_en,
                ),
            }
            response_summary = (
                f"risk_tier={user_intelligence.risk_tier}; agent_profile_focus=applied"
            )
    return append_agent_trace_event(
        next_state,
        node_name="user_profile_analyst",
        request_name="user_profile_analyst",
        status=trace_status,
        provider_name=provider_name,
        model_name=model_name,
        request_summary=f"risk_profile={risk_profile}",
        response_summary=response_summary,
        tool_calls=trace_tool_calls,
    )


def market_intelligence_node(
    state: RecommendationGraphState,
    *,
    market_intelligence_service: MarketIntelligenceService,
    agent_runtime: AnthropicRecommendationAgentRuntime | None = None,
) -> RecommendationGraphState:
    user_intelligence = state["user_intelligence"]
    if user_intelligence is None:
        raise ValueError(
            "user_intelligence must be present before market_intelligence_node"
        )

    next_state_base = state
    trace_status = "finish"
    try:
        snapshot = market_intelligence_service.build_recommendation_snapshot()
    except Exception as exc:  # noqa: BLE001
        snapshot = market_intelligence_service.build_snapshot(
            market_overview_summary=_DEFAULT_MARKET_OVERVIEW_SUMMARY,
            macro_summary=_DEFAULT_MACRO_SUMMARY,
            rate_summary=_DEFAULT_RATE_SUMMARY,
            news_summaries=list(_DEFAULT_NEWS_SUMMARIES),
        )
        next_state_base = append_warning(
            state,
            stage="market_intelligence",
            code="market_snapshot_fallback",
            message=_format_runtime_error(exc),
        )
        trace_status = "error"

    next_state = {
        **next_state_base,
        "market_intelligence": MarketIntelligenceState(
            sentiment=snapshot.sentiment,
            stance=snapshot.stance,
            preferred_categories=list(snapshot.preferred_categories),
            avoided_categories=list(snapshot.avoided_categories),
            summary_zh=snapshot.summary_zh,
            summary_en=snapshot.summary_en,
            evidence=snapshot.evidence,
        ),
    }
    provider_name: str | None = None
    model_name: str | None = None
    response_summary = f"stance={snapshot.stance}"
    trace_tool_calls: tuple[AgentToolCallRecord, ...] = ()
    profile_focus_state = state["agent_profile_focus"]
    if agent_runtime is not None and profile_focus_state is not None:
        try:
            metadata = agent_runtime.route_metadata("market_intelligence")
        except Exception:  # noqa: BLE001
            metadata = None
        else:
            provider_name = metadata.provider_name
            model_name = metadata.model_name
        try:
            market_output, metadata = agent_runtime.analyze_market_intelligence(
                map_user_profile(
                    state["request_context"].payload.riskAssessmentResult.finalProfile
                ),
                UserProfileAgentOutput(
                    profile_focus_zh=profile_focus_state.profile_focus_zh,
                    profile_focus_en=profile_focus_state.profile_focus_en,
                ),
                MarketContext(
                    summary_zh=snapshot.summary_zh,
                    summary_en=snapshot.summary_en,
                ),
                prompt_context=_build_market_intelligence_prompt_context(
                    state=state,
                    user_intelligence=user_intelligence,
                    profile_focus=profile_focus_state,
                    snapshot=snapshot,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            next_state = append_warning(
                next_state,
                stage="market_intelligence",
                code="agent_market_intelligence_failed",
                message=_format_runtime_error(exc),
            )
            trace_status = "error"
        else:
            provider_name = metadata.provider_name
            model_name = metadata.model_name
            trace_tool_calls = metadata.tool_calls
            next_state = {
                **next_state,
                "market_intelligence": next_state["market_intelligence"].model_copy(
                    update={
                        "summary_zh": market_output.summary_zh,
                        "summary_en": market_output.summary_en,
                    }
                ),
                "agent_market_summary": AgentMarketSummaryState(
                    summary_zh=market_output.summary_zh,
                    summary_en=market_output.summary_en,
                ),
            }
            response_summary = f"stance={snapshot.stance}; agent_market_summary=applied"
    return append_agent_trace_event(
        next_state,
        node_name="market_intelligence",
        request_name="market_intelligence",
        status=trace_status,
        provider_name=provider_name,
        model_name=model_name,
        request_summary=f"risk_tier={user_intelligence.risk_tier}",
        response_summary=response_summary,
        tool_calls=trace_tool_calls,
    )


def product_match_expert_node(
    state: RecommendationGraphState,
    *,
    product_retrieval_service: ProductRetrievalService,
    memory_recall_service: MemoryRecallService,
    product_candidates: list[CandidateProduct],
    agent_runtime: AnthropicRecommendationAgentRuntime | None = None,
) -> RecommendationGraphState:
    user_intelligence = state["user_intelligence"]
    market_intelligence = state["market_intelligence"]
    if user_intelligence is None or market_intelligence is None:
        raise ValueError(
            "user_intelligence and market_intelligence must be present before product_match_expert_node"
        )

    query_text = (
        state["request_context"].user_intent_text
        or user_intelligence.profile_summary_zh
    )
    recalled_memories = memory_recall_service.recall(query_text, limit=3)
    allowed_risk_levels = _allowed_risk_levels_for_tier(user_intelligence.risk_tier)
    preferred_categories = _preferred_categories_for_strategy(
        user_intelligence=user_intelligence,
        market_intelligence=market_intelligence,
    )
    blocked_categories = _blocked_categories_for_strategy(
        user_intelligence=user_intelligence,
        market_intelligence=market_intelligence,
    )
    retrieval_plan = product_retrieval_service.plan_retrieval(
        query_text=query_text,
        candidates=product_candidates,
        allowed_risk_levels=allowed_risk_levels,
        preferred_categories=set(preferred_categories),
        blocked_categories=blocked_categories,
        liquidity_preference=user_intelligence.liquidity_preference,
        limit=6,
    )
    ranked_candidates = list(retrieval_plan.candidates)
    next_state = dict(state)
    provider_name: str | None = None
    model_name: str | None = None
    applied_rank_stages: list[str] = []
    trace_tool_calls: list[AgentToolCallRecord] = []
    trace_status = "finish"
    profile_focus_state = state["agent_profile_focus"]
    if (
        agent_runtime is not None
        and profile_focus_state is not None
        and ranked_candidates
    ):
        category_rankings: dict[str, list[CandidateProduct]] = {}
        attempted_ranking_models: list[str] = []
        for category, request_name in _CATEGORY_TO_RANKING_REQUEST.items():
            category_candidates = [
                candidate
                for candidate in ranked_candidates
                if candidate.category == category
            ]
            if not category_candidates:
                continue
            try:
                route_metadata = agent_runtime.route_metadata(request_name)
            except Exception:  # noqa: BLE001
                route_metadata = None
            else:
                provider_name = route_metadata.provider_name
                attempted_ranking_models.append(
                    f"{request_name}:{route_metadata.model_name}"
                )
            try:
                ranking_output, metadata = agent_runtime.rank_candidates(
                    request_name,
                    map_user_profile(
                        state[
                            "request_context"
                        ].payload.riskAssessmentResult.finalProfile
                    ),
                    UserProfileAgentOutput(
                        profile_focus_zh=profile_focus_state.profile_focus_zh,
                        profile_focus_en=profile_focus_state.profile_focus_en,
                    ),
                    category_candidates,
                    prompt_context=_build_ranking_prompt_context(
                        state=state,
                        user_intelligence=user_intelligence,
                        market_intelligence=market_intelligence,
                        recalled_memories=recalled_memories,
                        request_name=request_name,
                        candidates=category_candidates,
                        allowed_risk_levels=allowed_risk_levels,
                        preferred_categories=_recommended_categories_for_prompt(
                            preferred_categories=preferred_categories,
                            blocked_categories=blocked_categories,
                        ),
                        blocked_categories=blocked_categories,
                        filtered_out_reasons=retrieval_plan.filtered_out_reasons,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                next_state = append_warning(
                    next_state,
                    stage="product_match_expert",
                    code=f"agent_{request_name}_failed",
                    message=_friendly_ranking_warning(request_name, exc),
                )
                trace_status = "error"
                continue
            provider_name = metadata.provider_name
            if route_metadata is None:
                attempted_ranking_models.append(f"{request_name}:{metadata.model_name}")
            applied_rank_stages.append(request_name)
            trace_tool_calls.extend(metadata.tool_calls)
            category_rankings[category] = _rank_candidates_with_agent_ids(
                category_candidates,
                ranking_output.ranked_ids,
            )

        if category_rankings:
            ranked_candidates = _apply_category_rankings(
                ranked_candidates,
                category_rankings,
            )
        if attempted_ranking_models:
            model_name = " | ".join(attempted_ranking_models)

    recommended_categories = [
        category
        for category in preferred_categories
        if category not in blocked_categories
    ]
    product_strategy = ProductStrategy(
        recommended_categories=recommended_categories,
        ranking_rationale_zh=(
            f"结合用户风险等级 {user_intelligence.risk_tier}、"
            f"流动性偏好 {user_intelligence.liquidity_preference} 和"
            f"市场立场 {market_intelligence.stance}，优先筛选 "
            f"{'、'.join(recommended_categories) or '合规候选'}。"
        ),
        ranking_rationale_en=(
            f"Ranking prioritizes categories aligned with risk tier {user_intelligence.risk_tier}, "
            f"{user_intelligence.liquidity_preference} liquidity needs, and a "
            f"{market_intelligence.stance} market stance."
        ),
    )

    retrieval_context = RetrievalContext(
        recalled_memories=recalled_memories,
        candidates=[
            RetrievedCandidate(
                product_id=candidate.id,
                category=candidate.category,
                score=max(0.01, 1.0 - index * 0.08),
                rationale=candidate.rationale_zh,
                runtime_candidate=RuntimeCandidateSnapshot(
                    id=candidate.id,
                    category=candidate.category,
                    code=candidate.code,
                    liquidity=candidate.liquidity,
                    as_of_date=candidate.as_of_date,
                    detail_route=candidate.detail_route,
                    name_zh=candidate.name_zh,
                    name_en=candidate.name_en,
                    rationale_zh=candidate.rationale_zh,
                    rationale_en=candidate.rationale_en,
                    risk_level=candidate.risk_level,
                    tags_zh=list(candidate.tags_zh),
                    tags_en=list(candidate.tags_en),
                ),
            )
            for index, candidate in enumerate(ranked_candidates)
        ],
        filtered_out_reasons=list(retrieval_plan.filtered_out_reasons),
    )

    next_state = {
        **next_state,
        "product_strategy": product_strategy,
        "retrieval_context": retrieval_context,
    }
    response_summary = f"retrieved={len(retrieval_context.candidates)}"
    if applied_rank_stages:
        response_summary = (
            f"{response_summary}; agent_ranked={','.join(applied_rank_stages)}"
        )
    return append_agent_trace_event(
        next_state,
        node_name="product_match_expert",
        request_name="product_match_expert",
        status=trace_status,
        provider_name=provider_name,
        model_name=model_name,
        request_summary=f"candidate_pool={len(product_candidates)}",
        response_summary=response_summary,
        tool_calls=trace_tool_calls,
    )


def compliance_risk_officer_node(
    state: RecommendationGraphState,
    *,
    compliance_review_service: ComplianceReviewService,
    product_candidates: list[CandidateProduct],
) -> RecommendationGraphState:
    user_intelligence = state["user_intelligence"]
    retrieval_context = state["retrieval_context"]
    if user_intelligence is None or retrieval_context is None:
        raise ValueError(
            "user_intelligence and retrieval_context are required for compliance"
        )

    candidates_by_id = {candidate.id: candidate for candidate in product_candidates}
    selected_candidates: list[CandidateProduct] = []
    selected_items: list[RetrievedCandidate] = []
    for item in retrieval_context.candidates:
        if item.runtime_candidate is not None:
            snapshot = item.runtime_candidate
            selected_candidates.append(
                CandidateProduct(
                    id=snapshot.id,
                    category=snapshot.category,
                    code=snapshot.code,
                    liquidity=snapshot.liquidity,
                    as_of_date=snapshot.as_of_date,
                    detail_route=snapshot.detail_route,
                    name_zh=snapshot.name_zh,
                    name_en=snapshot.name_en,
                    rationale_zh=snapshot.rationale_zh,
                    rationale_en=snapshot.rationale_en,
                    risk_level=snapshot.risk_level,
                    tags_zh=list(snapshot.tags_zh),
                    tags_en=list(snapshot.tags_en),
                )
            )
            selected_items.append(item)
            continue
        candidate = candidates_by_id.get(item.product_id)
        if candidate is not None:
            selected_candidates.append(candidate)
            selected_items.append(item)

    review_result = compliance_review_service.review(
        risk_tier=user_intelligence.risk_tier,
        liquidity_preference=user_intelligence.liquidity_preference,
        candidates=selected_candidates,
    )

    next_state: RecommendationGraphState = {
        **state,
        "compliance_review": ComplianceReviewState(
            verdict=review_result.verdict,
            reason_zh=review_result.reason_zh,
            reason_en=review_result.reason_en,
            disclosures_zh=review_result.disclosures_zh,
            disclosures_en=review_result.disclosures_en,
            suitability_notes_zh=review_result.suitability_notes_zh,
            suitability_notes_en=review_result.suitability_notes_en,
        ),
    }

    if review_result.verdict != "approve":
        allowed_risk_level = _RISK_ORDER.get(user_intelligence.risk_tier, 0)
        filtered_candidates: list[RetrievedCandidate] = []
        filtered_out_reasons = list(retrieval_context.filtered_out_reasons)
        for item, candidate in zip(selected_items, selected_candidates):
            candidate_risk_level = _RISK_ORDER.get(candidate.risk_level, 99)
            if candidate_risk_level <= allowed_risk_level:
                filtered_candidates.append(item)
            else:
                filtered_out_reasons.append(
                    f"{candidate.id} filtered: risk {candidate.risk_level} exceeds {user_intelligence.risk_tier}"
                )
        next_state = {
            **next_state,
            "retrieval_context": RetrievalContext(
                recalled_memories=list(retrieval_context.recalled_memories),
                candidates=filtered_candidates,
                filtered_out_reasons=filtered_out_reasons,
            ),
        }
        next_state = append_warning(
            next_state,
            stage="compliance_review",
            code="compliance_revise_required",
            message=review_result.reason_en,
        )

    return append_agent_trace_event(
        next_state,
        node_name="compliance_risk_officer",
        request_name="compliance_risk_officer",
        status="finish",
        request_summary=f"selected={len(selected_candidates)}",
        response_summary=f"verdict={review_result.verdict}",
    )


def manager_coordinator_node(
    state: RecommendationGraphState,
    *,
    manager_synthesis_service: ManagerSynthesisService,
    agent_runtime: AnthropicRecommendationAgentRuntime | None = None,
) -> RecommendationGraphState:
    route = route_compliance_verdict(state)
    user_intelligence = state["user_intelligence"]
    market_intelligence = state["market_intelligence"]
    if user_intelligence is None or market_intelligence is None:
        raise ValueError(
            "user_intelligence and market_intelligence are required for manager_coordinator_node"
        )
    manager_brief = manager_synthesis_service.build_manager_brief(
        route=route,
        user_intelligence=user_intelligence,
        market_intelligence=market_intelligence,
        product_strategy=state["product_strategy"],
        compliance_review=state["compliance_review"],
    )
    next_state = dict(state)
    provider_name: str | None = None
    model_name: str | None = None
    trace_tool_calls: tuple[AgentToolCallRecord, ...] = ()
    trace_status = "finish"
    profile_focus_state = state["agent_profile_focus"]
    market_summary_state = state["agent_market_summary"]
    selected_plan_context = _build_selected_plan_context(state)
    if agent_runtime is not None and profile_focus_state is not None:
        try:
            metadata = agent_runtime.route_metadata("explanation")
        except Exception:  # noqa: BLE001
            metadata = None
        else:
            provider_name = metadata.provider_name
            model_name = metadata.model_name
        market_summary = MarketIntelligenceAgentOutput(
            summary_zh=(
                market_intelligence.summary_zh
                if market_summary_state is None
                else market_summary_state.summary_zh
            ),
            summary_en=(
                market_intelligence.summary_en
                if market_summary_state is None
                else market_summary_state.summary_en
            ),
        )
        try:
            explanation_output, metadata = agent_runtime.explain_plan(
                map_user_profile(
                    state["request_context"].payload.riskAssessmentResult.finalProfile
                ),
                UserProfileAgentOutput(
                    profile_focus_zh=profile_focus_state.profile_focus_zh,
                    profile_focus_en=profile_focus_state.profile_focus_en,
                ),
                market_summary,
                prompt_context=_build_explanation_prompt_context(
                    state=state,
                    route=route,
                    manager_brief=manager_brief,
                    market_summary=market_summary,
                    selected_plan_context=selected_plan_context,
                ),
                selected_plan_context=selected_plan_context,
            )
        except Exception as exc:  # noqa: BLE001
            next_state = append_warning(
                next_state,
                stage="manager_coordinator",
                code="agent_explanation_failed",
                message=_format_runtime_error(exc),
            )
            trace_status = "error"
        else:
            provider_name = metadata.provider_name
            model_name = metadata.model_name
            trace_tool_calls = metadata.tool_calls
            manager_brief = manager_brief.model_copy(
                update={
                    "why_this_plan_zh": list(explanation_output.why_this_plan_zh),
                    "why_this_plan_en": list(explanation_output.why_this_plan_en),
                }
            )

    next_state = {
        **next_state,
        "manager_brief": manager_brief,
        "recommendation_draft": {
            "summary_zh": manager_brief.summary_zh,
            "summary_en": manager_brief.summary_en,
            "why_this_plan_zh": list(manager_brief.why_this_plan_zh),
            "why_this_plan_en": list(manager_brief.why_this_plan_en),
        },
        "final_response": FinalResponseState(
            recommendation_status=manager_brief.recommendation_status,
            summary_zh=manager_brief.summary_zh,
            summary_en=manager_brief.summary_en,
        ),
    }
    return append_agent_trace_event(
        next_state,
        node_name="manager_coordinator",
        request_name="manager_coordinator",
        status=trace_status,
        provider_name=provider_name,
        model_name=model_name,
        request_summary=f"route={route}",
        response_summary=f"status={manager_brief.recommendation_status}",
        tool_calls=trace_tool_calls,
    )


def _allowed_risk_levels_for_tier(risk_tier: str) -> set[str]:
    allowed_risk_level = _RISK_ORDER.get(risk_tier)
    if allowed_risk_level is None:
        return {"R1", "R2"}
    return {
        risk_level
        for risk_level, order in _RISK_ORDER.items()
        if order <= allowed_risk_level
    }


def _blocked_categories_for_strategy(
    *,
    user_intelligence: UserIntelligence,
    market_intelligence: MarketIntelligenceState,
) -> set[str]:
    del market_intelligence
    blocked_categories: set[str] = set()
    if user_intelligence.risk_tier in {"R1", "R2"}:
        blocked_categories.add("stock")
    if user_intelligence.drawdown_sensitivity == "high":
        blocked_categories.add("stock")
    return blocked_categories


def _preferred_categories_for_strategy(
    *,
    user_intelligence: UserIntelligence,
    market_intelligence: MarketIntelligenceState,
) -> list[str]:
    if user_intelligence.risk_tier in {"R1", "R2"}:
        return ["wealth_management", "fund"]
    if user_intelligence.drawdown_sensitivity == "high":
        return ["wealth_management", "fund"]
    return list(market_intelligence.preferred_categories)


def _rank_candidates_with_agent_ids(
    candidates: list[CandidateProduct],
    ranked_ids: list[str],
) -> list[CandidateProduct]:
    by_id = {candidate.id: candidate for candidate in candidates}
    ranked: list[CandidateProduct] = []
    seen: set[str] = set()
    for candidate_id in ranked_ids:
        candidate = by_id.get(candidate_id)
        if candidate is None or candidate_id in seen:
            continue
        ranked.append(candidate)
        seen.add(candidate_id)
    ranked.extend(candidate for candidate in candidates if candidate.id not in seen)
    return ranked


def _apply_category_rankings(
    candidates: list[CandidateProduct],
    category_rankings: dict[str, list[CandidateProduct]],
) -> list[CandidateProduct]:
    ranking_queues = {
        category: deque(ranked_candidates)
        for category, ranked_candidates in category_rankings.items()
    }
    merged: list[CandidateProduct] = []
    for candidate in candidates:
        queue = ranking_queues.get(candidate.category)
        if queue:
            merged.append(queue.popleft())
        else:
            merged.append(candidate)
    return merged


def _format_runtime_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def _friendly_ranking_warning(request_name: str, exc: Exception) -> str:
    label = _RANKING_STAGE_LABELS_ZH.get(request_name, request_name)
    if isinstance(exc, ValidationError):
        return f"{label}智能排序暂时不可用，已自动回退到默认候选顺序。"
    return f"{label}智能排序调用失败，已自动回退到默认候选顺序。"


def _build_user_profile_prompt_context(
    *,
    state: RecommendationGraphState,
    user_intelligence: UserIntelligence,
) -> AgentPromptContext:
    payload = state["request_context"].payload
    risk_result = payload.riskAssessmentResult
    return AgentPromptContext(
        task="Refine the user's investment profile focus using the provided request context.",
        sections=(
            AgentPromptSection(
                title="Risk assessment result",
                body=(
                    f"base_profile={risk_result.baseProfile}\n"
                    f"final_profile={risk_result.finalProfile}\n"
                    f"total_score={risk_result.totalScore}\n"
                    f"dimension_levels={risk_result.dimensionLevels.model_dump()}\n"
                    f"dimension_scores={risk_result.dimensionScores.model_dump()}"
                ),
            ),
            AgentPromptSection(
                title="Derived user_intelligence",
                body=user_intelligence.model_dump_json(indent=2),
            ),
            AgentPromptSection(
                title="Questionnaire answers",
                body=_render_items(payload.questionnaireAnswers),
            ),
            AgentPromptSection(
                title="User intent and conversation",
                body=_render_text_block(
                    [
                        f"user_intent={state['request_context'].user_intent_text or 'none'}",
                        f"conversation_messages={_render_items(payload.conversationMessages)}",
                    ]
                ),
            ),
            AgentPromptSection(
                title="Client context and history",
                body=_render_text_block(
                    [
                        (
                            f"client_context={payload.clientContext.model_dump()}"
                            if payload.clientContext is not None
                            else "client_context=none"
                        ),
                        f"historical_holdings={_render_items(payload.historicalHoldings)}",
                        f"historical_transactions={_render_items(payload.historicalTransactions)}",
                    ]
                ),
            ),
        ),
        instructions=(
            "Use the deterministic profile intelligence as grounding, not as something to contradict.",
            "Prioritize liquidity needs, drawdown sensitivity, and explicit user goals when they appear.",
        ),
    )


def _build_market_intelligence_prompt_context(
    *,
    state: RecommendationGraphState,
    user_intelligence: UserIntelligence,
    profile_focus: AgentProfileFocusState,
    snapshot: object,
) -> AgentPromptContext:
    payload = state["request_context"].payload
    return AgentPromptContext(
        task="Refine the market intelligence summary for this user using market evidence and user context.",
        sections=(
            AgentPromptSection(
                title="User context",
                body=_render_text_block(
                    [
                        f"final_profile={payload.riskAssessmentResult.finalProfile}",
                        f"user_intelligence={user_intelligence.model_dump_json(indent=2)}",
                        f"user_intent={state['request_context'].user_intent_text or 'none'}",
                    ]
                ),
            ),
            AgentPromptSection(
                title="Agent profile focus",
                body=_render_items([profile_focus.model_dump()]),
            ),
            AgentPromptSection(
                title="Market snapshot and evidence",
                body=_render_text_block(
                    [
                        f"snapshot_summary_zh={getattr(snapshot, 'summary_zh')}",
                        f"snapshot_summary_en={getattr(snapshot, 'summary_en')}",
                        f"preferred_categories={getattr(snapshot, 'preferred_categories')}",
                        f"avoided_categories={getattr(snapshot, 'avoided_categories')}",
                        f"evidence={_render_items(getattr(snapshot, 'evidence'))}",
                    ]
                ),
            ),
        ),
        instructions=(
            "Stay consistent with the supplied evidence.",
            "Explain the market in a way that is suitable for the user's risk profile and goals.",
        ),
    )


def _build_ranking_prompt_context(
    *,
    state: RecommendationGraphState,
    user_intelligence: UserIntelligence,
    market_intelligence: MarketIntelligenceState,
    recalled_memories: list[str],
    request_name: str,
    candidates: list[CandidateProduct],
    allowed_risk_levels: set[str],
    preferred_categories: list[str],
    blocked_categories: set[str],
    filtered_out_reasons: list[str],
) -> AgentPromptContext:
    payload = state["request_context"].payload
    return AgentPromptContext(
        task=f"Rank the candidate list for {request_name} using retrieval context and safety guardrails.",
        sections=(
            AgentPromptSection(
                title="User and market context",
                body=_render_text_block(
                    [
                        f"user_intelligence={user_intelligence.model_dump_json(indent=2)}",
                        f"market_intelligence={market_intelligence.model_dump_json(indent=2)}",
                        f"user_intent={state['request_context'].user_intent_text or 'none'}",
                        (
                            f"conversation_messages={_render_items(payload.conversationMessages)}"
                            if payload.conversationMessages
                            else "conversation_messages=none"
                        ),
                    ]
                ),
            ),
            AgentPromptSection(
                title="Memory recall context",
                body=_render_items(recalled_memories),
            ),
            AgentPromptSection(
                title="Candidate list context",
                body=_render_items(
                    [_serialize_candidate_for_prompt(candidate) for candidate in candidates]
                ),
            ),
            AgentPromptSection(
                title="Retrieval guardrails",
                body=_render_text_block(
                    [
                        f"allowed_risk_levels={sorted(allowed_risk_levels)}",
                        f"preferred_categories={preferred_categories}",
                        f"blocked_categories={sorted(blocked_categories)}",
                        f"filtered_out_reasons={filtered_out_reasons or ['none']}",
                    ]
                ),
            ),
        ),
        instructions=(
            "Do not introduce candidates outside the supplied list.",
            "Respect the retrieval guardrails and user suitability constraints.",
        ),
    )


def _build_explanation_prompt_context(
    *,
    state: RecommendationGraphState,
    route: str,
    manager_brief: ManagerBrief,
    market_summary: MarketIntelligenceAgentOutput,
    selected_plan_context: SelectedPlanContext,
) -> AgentPromptContext:
    payload = state["request_context"].payload
    sections = [
        AgentPromptSection(
            title="Recommendation route and summary",
            body=_render_text_block(
                [
                    f"route={route}",
                    f"recommendation_status={manager_brief.recommendation_status}",
                    f"summary_zh={manager_brief.summary_zh}",
                    f"summary_en={manager_brief.summary_en}",
                ]
            ),
        ),
        AgentPromptSection(
            title="Market context",
            body=_render_text_block(
                [
                    f"market_summary_zh={market_summary.summary_zh}",
                    f"market_summary_en={market_summary.summary_en}",
                ]
            ),
        ),
        AgentPromptSection(
            title="Selected plan context",
            body=_render_text_block(
                [
                    f"selected_plan={selected_plan_context.as_dict()}",
                    f"user_intent={state['request_context'].user_intent_text or 'none'}",
                    (
                        f"client_context={payload.clientContext.model_dump()}"
                        if payload.clientContext is not None
                        else "client_context=none"
                    ),
                ]
            ),
        ),
    ]
    if state["product_strategy"] is not None:
        sections.append(
            AgentPromptSection(
                title="Product strategy",
                body=state["product_strategy"].model_dump_json(indent=2),
            )
        )
    if state["compliance_review"] is not None:
        sections.append(
            AgentPromptSection(
                title="Compliance review",
                body=state["compliance_review"].model_dump_json(indent=2),
            )
        )
    return AgentPromptContext(
        task="Explain why the selected recommendation plan fits the user and the current market context.",
        sections=tuple(sections),
        instructions=(
            "Ground the explanation in the selected plan, manager brief, and market summary.",
            "Keep the rationale aligned with any compliance or suitability caveats.",
        ),
    )


def _build_selected_plan_context(
    state: RecommendationGraphState,
) -> SelectedPlanContext:
    retrieval_context = state["retrieval_context"]
    if retrieval_context is None:
        return SelectedPlanContext()

    funds: list[str] = []
    wealth_management: list[str] = []
    stocks: list[str] = []
    for item in retrieval_context.candidates:
        if item.category == "fund":
            funds.append(item.product_id)
        elif item.category == "wealth_management":
            wealth_management.append(item.product_id)
        elif item.category == "stock":
            stocks.append(item.product_id)
    return SelectedPlanContext(
        fund_ids=tuple(funds),
        wealth_management_ids=tuple(wealth_management),
        stock_ids=tuple(stocks),
    )


def _recommended_categories_for_prompt(
    *,
    preferred_categories: list[str],
    blocked_categories: set[str],
) -> list[str]:
    return [
        category
        for category in preferred_categories
        if category not in blocked_categories
    ]


def _render_items(items: object) -> str:
    if not items:
        return "none"
    if isinstance(items, list):
        rendered_items: list[str] = []
        for item in items:
            if hasattr(item, "model_dump"):
                rendered_items.append(str(item.model_dump()))
            else:
                rendered_items.append(str(item))
        return "\n".join(f"- {item}" for item in rendered_items)
    return str(items)


def _render_text_block(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)


def _serialize_candidate_for_prompt(candidate: CandidateProduct) -> dict[str, object]:
    return {
        "id": candidate.id,
        "category": candidate.category,
        "code": candidate.code,
        "liquidity": candidate.liquidity,
        "name_zh": candidate.name_zh,
        "name_en": candidate.name_en,
        "rationale_zh": candidate.rationale_zh,
        "rationale_en": candidate.rationale_en,
        "risk_level": candidate.risk_level,
        "tags_zh": list(candidate.tags_zh),
        "tags_en": list(candidate.tags_en),
    }
