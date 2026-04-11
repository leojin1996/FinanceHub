from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from financehub_market_api.models import MarketEvidenceItem
from financehub_market_api.recommendation.agents.contracts import (
    ComplianceReviewAgentOutput,
    MarketIntelligenceAgentOutput,
    ProductMatchAgentOutput,
    UserProfileAgentOutput,
)
from financehub_market_api.recommendation.agents.runtime_context import (
    AgentPromptContext,
    AgentPromptSection,
)
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
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.schemas import CandidateProduct

_BLOCKED_SUMMARY_ZH = "AI 多智能体评审未完成，建议人工复核后再下发推荐。"
_BLOCKED_SUMMARY_EN = (
    "AI multi-agent review did not complete. Route this recommendation for manual review."
)
_BLOCKED_REASON_ZH = "AI 多智能体评审未完成，当前推荐已阻断。"
_BLOCKED_REASON_EN = "The AI multi-agent review did not complete, so the recommendation was blocked."
_BLOCKED_DISCLOSURES_ZH = ["理财非存款，投资需谨慎。"]
_BLOCKED_DISCLOSURES_EN = ["Investing involves risk. Proceed prudently."]
_RISK_ORDER = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}


def user_profile_analyst_node(
    state: RecommendationGraphState,
    *,
    profile_intelligence_service: object | None,
    agent_runtime: object | None = None,
) -> RecommendationGraphState:
    del profile_intelligence_service
    if _is_blocked(state):
        return _append_skipped_trace(
            state,
            node_name="user_profile_analyst",
            request_name="user_profile_analyst",
            request_summary="skipped_after_prior_block",
        )

    payload = state["request_context"].payload
    user_profile = map_user_profile(payload.riskAssessmentResult.finalProfile)
    provider_name, model_name = _route_metadata_if_available(
        agent_runtime,
        "user_profile_analyst",
    )
    if agent_runtime is None:
        return _block_state_due_to_agent_failure(
            state,
            node_name="user_profile_analyst",
            request_name="user_profile_analyst",
            request_summary=f"risk_profile={user_profile.risk_profile}",
            code="agent_runtime_required",
            message="AI agent runtime is required for user_profile_analyst.",
            provider_name=provider_name,
            model_name=model_name,
        )

    try:
        profile_output, metadata = agent_runtime.analyze_user_profile(  # type: ignore[attr-defined]
            user_profile,
            prompt_context=_build_user_profile_prompt_context(state=state),
        )
    except Exception as exc:  # noqa: BLE001
        return _block_state_due_to_agent_failure(
            state,
            node_name="user_profile_analyst",
            request_name="user_profile_analyst",
            request_summary=f"risk_profile={user_profile.risk_profile}",
            code="agent_user_profile_failed",
            message=_format_runtime_error(exc),
            provider_name=provider_name,
            model_name=model_name,
        )

    next_state = {
        **state,
        "user_intelligence": UserIntelligence(
            risk_tier=profile_output.risk_tier,
            liquidity_preference=profile_output.liquidity_preference,
            investment_horizon=profile_output.investment_horizon,
            return_objective=profile_output.return_objective,
            drawdown_sensitivity=profile_output.drawdown_sensitivity,
            profile_summary_zh=profile_output.profile_focus_zh,
            profile_summary_en=profile_output.profile_focus_en,
            derived_signals=list(profile_output.derived_signals),
        ),
        "agent_profile_focus": AgentProfileFocusState(
            profile_focus_zh=profile_output.profile_focus_zh,
            profile_focus_en=profile_output.profile_focus_en,
        ),
    }
    return append_agent_trace_event(
        next_state,
        node_name="user_profile_analyst",
        request_name="user_profile_analyst",
        status="finish",
        provider_name=metadata.provider_name,
        model_name=metadata.model_name,
        request_summary=f"risk_profile={user_profile.risk_profile}",
        response_summary=f"risk_tier={profile_output.risk_tier}",
        tool_calls=metadata.tool_calls,
    )


def market_intelligence_node(
    state: RecommendationGraphState,
    *,
    market_intelligence_service: MarketIntelligenceService,
    agent_runtime: object | None = None,
) -> RecommendationGraphState:
    if _is_blocked(state):
        return _append_skipped_trace(
            state,
            node_name="market_intelligence",
            request_name="market_intelligence",
            request_summary="skipped_after_prior_block",
        )

    user_intelligence = state["user_intelligence"]
    if user_intelligence is None:
        raise ValueError("user_intelligence must be present before market_intelligence")

    provider_name, model_name = _route_metadata_if_available(
        agent_runtime,
        "market_intelligence",
    )
    if agent_runtime is None:
        return _block_state_due_to_agent_failure(
            state,
            node_name="market_intelligence",
            request_name="market_intelligence",
            request_summary=f"risk_tier={user_intelligence.risk_tier}",
            code="agent_runtime_required",
            message="AI agent runtime is required for market_intelligence.",
            provider_name=provider_name,
            model_name=model_name,
        )

    try:
        snapshot = market_intelligence_service.build_recommendation_snapshot()
    except Exception as exc:  # noqa: BLE001
        return _block_state_due_to_agent_failure(
            state,
            node_name="market_intelligence",
            request_name="market_intelligence",
            request_summary=f"risk_tier={user_intelligence.risk_tier}",
            code="market_facts_unavailable",
            message=_format_runtime_error(exc),
            provider_name=provider_name,
            model_name=model_name,
        )

    market_facts = _build_market_fact_payload(snapshot)
    try:
        market_output, metadata = agent_runtime.analyze_market_intelligence(  # type: ignore[attr-defined]
            map_user_profile(state["request_context"].payload.riskAssessmentResult.finalProfile),
            _user_profile_output_for_runtime(state),
            market_facts,
            prompt_context=_build_market_intelligence_prompt_context(
                state=state,
                market_facts=market_facts,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return _block_state_due_to_agent_failure(
            state,
            node_name="market_intelligence",
            request_name="market_intelligence",
            request_summary=f"risk_tier={user_intelligence.risk_tier}",
            code="agent_market_intelligence_failed",
            message=_format_runtime_error(exc),
            provider_name=provider_name,
            model_name=model_name,
        )

    selected_evidence = _select_market_evidence(
        evidence=snapshot.evidence,
        evidence_refs=market_output.evidence_refs,
    )
    next_state = {
        **state,
        "market_intelligence": MarketIntelligenceState(
            sentiment=market_output.sentiment,
            stance=market_output.stance,
            preferred_categories=list(market_output.preferred_categories),
            avoided_categories=list(market_output.avoided_categories),
            summary_zh=market_output.summary_zh,
            summary_en=market_output.summary_en,
            evidence=selected_evidence,
            evidence_refs=list(market_output.evidence_refs),
        ),
        "agent_market_summary": AgentMarketSummaryState(
            summary_zh=market_output.summary_zh,
            summary_en=market_output.summary_en,
        ),
    }
    return append_agent_trace_event(
        next_state,
        node_name="market_intelligence",
        request_name="market_intelligence",
        status="finish",
        provider_name=metadata.provider_name,
        model_name=metadata.model_name,
        request_summary=f"risk_tier={user_intelligence.risk_tier}",
        response_summary=f"stance={market_output.stance}",
        tool_calls=metadata.tool_calls,
    )


def product_match_expert_node(
    state: RecommendationGraphState,
    *,
    product_retrieval_service: ProductRetrievalService,
    memory_recall_service: MemoryRecallService,
    product_candidates: list[CandidateProduct],
    agent_runtime: object | None = None,
) -> RecommendationGraphState:
    if _is_blocked(state):
        return _append_skipped_trace(
            state,
            node_name="product_match_expert",
            request_name="product_match_expert",
            request_summary="skipped_after_prior_block",
        )

    user_intelligence = state["user_intelligence"]
    market_intelligence = state["market_intelligence"]
    if user_intelligence is None or market_intelligence is None:
        raise ValueError(
            "user_intelligence and market_intelligence must be present before product_match_expert"
        )

    provider_name, model_name = _route_metadata_if_available(
        agent_runtime,
        "product_match_expert",
    )
    if agent_runtime is None:
        return _block_state_due_to_agent_failure(
            state,
            node_name="product_match_expert",
            request_name="product_match_expert",
            request_summary=f"candidate_pool={len(product_candidates)}",
            code="agent_runtime_required",
            message="AI agent runtime is required for product_match_expert.",
            provider_name=provider_name,
            model_name=model_name,
        )

    query_text = state["request_context"].user_intent_text or user_intelligence.profile_summary_zh
    recalled_memories = memory_recall_service.recall(query_text, limit=3)
    retrieval_plan = product_retrieval_service.plan_retrieval(
        query_text=query_text,
        candidates=product_candidates,
        allowed_risk_levels=_allowed_risk_levels_for_tier(user_intelligence.risk_tier),
        preferred_categories=set(market_intelligence.preferred_categories),
        blocked_categories=set(market_intelligence.avoided_categories),
        liquidity_preference=user_intelligence.liquidity_preference,
        limit=max(6, len(product_candidates)),
    )

    try:
        product_match, metadata = agent_runtime.match_products(  # type: ignore[attr-defined]
            map_user_profile(state["request_context"].payload.riskAssessmentResult.finalProfile),
            user_profile_insights=_user_profile_output_for_runtime(state),
            market_intelligence=_market_output_for_runtime(state),
            candidates=list(retrieval_plan.candidates),
            prompt_context=_build_product_match_prompt_context(
                state=state,
                candidates=list(retrieval_plan.candidates),
                recalled_memories=recalled_memories,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return _block_state_due_to_agent_failure(
            state,
            node_name="product_match_expert",
            request_name="product_match_expert",
            request_summary=f"candidate_pool={len(product_candidates)}",
            code="agent_product_match_failed",
            message=_format_runtime_error(exc),
            provider_name=provider_name,
            model_name=model_name,
        )

    ordered_candidates, invalid_ids = _ordered_candidates_from_agent_selection(
        candidates=list(retrieval_plan.candidates),
        product_match=product_match,
    )
    if invalid_ids or not ordered_candidates:
        invalid_label = ",".join(invalid_ids) if invalid_ids else "empty_selection"
        return _block_state_due_to_agent_failure(
            state,
            node_name="product_match_expert",
            request_name="product_match_expert",
            request_summary=f"candidate_pool={len(product_candidates)}",
            code="agent_product_match_invalid_output",
            message=f"product_match_expert returned invalid candidate references: {invalid_label}",
            provider_name=metadata.provider_name,
            model_name=metadata.model_name,
        )

    retrieval_context = RetrievalContext(
        recalled_memories=list(recalled_memories),
        candidates=[
            RetrievedCandidate(
                product_id=candidate.id,
                category=candidate.category,
                score=max(0.01, 1.0 - index * 0.08),
                rationale=candidate.rationale_zh,
                runtime_candidate=_runtime_snapshot(candidate),
            )
            for index, candidate in enumerate(ordered_candidates)
        ],
        filtered_out_reasons=[
            *list(retrieval_plan.filtered_out_reasons),
            *list(product_match.filtered_out_reasons),
        ],
    )
    next_state = {
        **state,
        "product_strategy": ProductStrategy(
            recommended_categories=(
                list(product_match.recommended_categories)
                if product_match.recommended_categories
                else list(dict.fromkeys(candidate.category for candidate in ordered_candidates))
            ),
            ranking_rationale_zh=product_match.ranking_rationale_zh,
            ranking_rationale_en=product_match.ranking_rationale_en,
        ),
        "retrieval_context": retrieval_context,
    }
    return append_agent_trace_event(
        next_state,
        node_name="product_match_expert",
        request_name="product_match_expert",
        status="finish",
        provider_name=metadata.provider_name,
        model_name=metadata.model_name,
        request_summary=f"candidate_pool={len(product_candidates)}",
        response_summary=f"selected={len(ordered_candidates)}",
        tool_calls=metadata.tool_calls,
    )


def compliance_risk_officer_node(
    state: RecommendationGraphState,
    *,
    compliance_review_service: object | None,
    compliance_facts_service: object | None,
    product_candidates: list[CandidateProduct],
    agent_runtime: object | None = None,
) -> RecommendationGraphState:
    del compliance_review_service
    if _is_blocked(state):
        return _append_skipped_trace(
            state,
            node_name="compliance_risk_officer",
            request_name="compliance_risk_officer",
            request_summary="skipped_after_prior_block",
        )

    user_intelligence = state["user_intelligence"]
    retrieval_context = state["retrieval_context"]
    if user_intelligence is None or retrieval_context is None:
        raise ValueError(
            "user_intelligence and retrieval_context must be present before compliance_risk_officer"
        )

    provider_name, model_name = _route_metadata_if_available(
        agent_runtime,
        "compliance_risk_officer",
    )
    if agent_runtime is None:
        return _block_state_due_to_agent_failure(
            state,
            node_name="compliance_risk_officer",
            request_name="compliance_risk_officer",
            request_summary=f"selected={len(retrieval_context.candidates)}",
            code="agent_runtime_required",
            message="AI agent runtime is required for compliance_risk_officer.",
            provider_name=provider_name,
            model_name=model_name,
        )

    candidates_by_id = {candidate.id: candidate for candidate in product_candidates}
    selected_candidates = _selected_candidates_for_compliance(
        retrieval_context=retrieval_context,
        candidates_by_id=candidates_by_id,
    )
    if not selected_candidates:
        return _block_state_due_to_agent_failure(
            state,
            node_name="compliance_risk_officer",
            request_name="compliance_risk_officer",
            request_summary="selected=0",
            code="selected_candidates_missing",
            message="No valid selected candidates were available for compliance review.",
            provider_name=provider_name,
            model_name=model_name,
        )

    compliance_facts = (
        {
            "request_payload": state["request_context"].payload.model_dump(mode="json"),
            "selected_candidates": [
                {
                    "id": candidate.id,
                    "category": candidate.category,
                    "risk_level": candidate.risk_level,
                    "liquidity": candidate.liquidity,
                    "lockup_days": candidate.lockup_days,
                    "max_drawdown_percent": candidate.max_drawdown_percent,
                }
                for candidate in selected_candidates
            ],
            "rule_snapshot": {
                "available": False,
                "reason": "compliance_facts_service_missing",
            },
        }
        if compliance_facts_service is None
        else compliance_facts_service.build_review_facts(  # type: ignore[attr-defined]
            request_payload=state["request_context"].payload.model_dump(mode="json"),
            selected_candidates=selected_candidates,
        )
    )

    try:
        review_output, metadata = agent_runtime.review_compliance(  # type: ignore[attr-defined]
            map_user_profile(state["request_context"].payload.riskAssessmentResult.finalProfile),
            user_profile_insights=_user_profile_output_for_runtime(state),
            selected_candidates=selected_candidates,
            compliance_facts=compliance_facts,
            prompt_context=_build_compliance_prompt_context(
                state=state,
                selected_candidates=selected_candidates,
                compliance_facts=compliance_facts,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return _block_state_due_to_agent_failure(
            state,
            node_name="compliance_risk_officer",
            request_name="compliance_risk_officer",
            request_summary=f"selected={len(selected_candidates)}",
            code="agent_compliance_review_failed",
            message=_format_runtime_error(exc),
            provider_name=provider_name,
            model_name=model_name,
        )

    approved_ids = set(review_output.approved_ids)
    invalid_ids = [
        candidate_id
        for candidate_id in (*review_output.approved_ids, *review_output.rejected_ids)
        if candidate_id not in candidates_by_id
        and candidate_id not in {item.product_id for item in retrieval_context.candidates}
    ]
    if invalid_ids:
        return _block_state_due_to_agent_failure(
            state,
            node_name="compliance_risk_officer",
            request_name="compliance_risk_officer",
            request_summary=f"selected={len(selected_candidates)}",
            code="agent_compliance_invalid_output",
            message=(
                "compliance_risk_officer returned invalid candidate references: "
                + ",".join(invalid_ids)
            ),
            provider_name=metadata.provider_name,
            model_name=metadata.model_name,
        )

    next_state: RecommendationGraphState = {
        **state,
        "compliance_review": ComplianceReviewState(
            verdict=review_output.verdict,  # type: ignore[arg-type]
            reason_zh=review_output.reason_summary_zh,
            reason_en=review_output.reason_summary_en,
            disclosures_zh=list(review_output.required_disclosures_zh),
            disclosures_en=list(review_output.required_disclosures_en),
            suitability_notes_zh=list(review_output.suitability_notes_zh),
            suitability_notes_en=list(review_output.suitability_notes_en),
            applied_rule_ids=list(review_output.applied_rule_ids),
            blocking_reason_codes=list(review_output.blocking_reason_codes),
        ),
    }
    if review_output.verdict != "approve":
        next_state = {
            **next_state,
            "retrieval_context": RetrievalContext(
                recalled_memories=list(retrieval_context.recalled_memories),
                candidates=[
                    item
                    for item in retrieval_context.candidates
                    if item.product_id in approved_ids
                ],
                filtered_out_reasons=[
                    *list(retrieval_context.filtered_out_reasons),
                    *[
                        f"{candidate.id} filtered by compliance verdict {review_output.verdict}"
                        for candidate in selected_candidates
                        if candidate.id not in approved_ids
                    ],
                ],
            ),
        }

    return append_agent_trace_event(
        next_state,
        node_name="compliance_risk_officer",
        request_name="compliance_risk_officer",
        status="finish",
        provider_name=metadata.provider_name,
        model_name=metadata.model_name,
        request_summary=f"selected={len(selected_candidates)}",
        response_summary=f"verdict={review_output.verdict}",
        tool_calls=metadata.tool_calls,
    )


def manager_coordinator_node(
    state: RecommendationGraphState,
    *,
    manager_synthesis_service: object | None,
    agent_runtime: object | None = None,
) -> RecommendationGraphState:
    del manager_synthesis_service
    compliance_review = state["compliance_review"]
    if _is_blocked(state) or (
        compliance_review is not None and compliance_review.verdict == "block"
    ):
        skipped_state = _append_skipped_trace(
            state,
            node_name="manager_coordinator",
            request_name="manager_coordinator",
            request_summary=f"route={route_compliance_verdict(state)}",
        )
        return _finalize_blocked_response(skipped_state)

    user_intelligence = state["user_intelligence"]
    market_intelligence = state["market_intelligence"]
    product_strategy = state["product_strategy"]
    if (
        user_intelligence is None
        or market_intelligence is None
        or product_strategy is None
        or compliance_review is None
    ):
        raise ValueError(
            "user_intelligence, market_intelligence, product_strategy, and compliance_review are required before manager_coordinator"
        )

    provider_name, model_name = _route_metadata_if_available(
        agent_runtime,
        "manager_coordinator",
    )
    if agent_runtime is None:
        return _block_state_due_to_agent_failure(
            state,
            node_name="manager_coordinator",
            request_name="manager_coordinator",
            request_summary=f"route={route_compliance_verdict(state)}",
            code="agent_runtime_required",
            message="AI agent runtime is required for manager_coordinator.",
            provider_name=provider_name,
            model_name=model_name,
        )

    try:
        manager_output, metadata = agent_runtime.coordinate_manager(  # type: ignore[attr-defined]
            map_user_profile(state["request_context"].payload.riskAssessmentResult.finalProfile),
            user_profile_insights=_user_profile_output_for_runtime(state),
            market_intelligence=_market_output_for_runtime(state),
            product_match=_product_match_output_for_runtime(state),
            compliance_review=_compliance_output_for_runtime(state),
            prompt_context=_build_manager_prompt_context(state=state),
        )
    except Exception as exc:  # noqa: BLE001
        return _block_state_due_to_agent_failure(
            state,
            node_name="manager_coordinator",
            request_name="manager_coordinator",
            request_summary=f"route={route_compliance_verdict(state)}",
            code="agent_manager_coordinator_failed",
            message=_format_runtime_error(exc),
            provider_name=provider_name,
            model_name=model_name,
        )

    recommendation_status = _manager_status_for_verdict(
        verdict=compliance_review.verdict,
        requested_status=manager_output.recommendation_status,
    )
    manager_brief = ManagerBrief(
        recommendation_status=recommendation_status,  # type: ignore[arg-type]
        summary_zh=manager_output.summary_zh,
        summary_en=manager_output.summary_en,
        why_this_plan_zh=list(manager_output.why_this_plan_zh),
        why_this_plan_en=list(manager_output.why_this_plan_en),
    )
    next_state = {
        **state,
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
        status="finish",
        provider_name=metadata.provider_name,
        model_name=metadata.model_name,
        request_summary=f"route={route_compliance_verdict(state)}",
        response_summary=f"status={manager_brief.recommendation_status}",
        tool_calls=metadata.tool_calls,
    )


def _build_user_profile_prompt_context(
    *,
    state: RecommendationGraphState,
) -> AgentPromptContext:
    payload = state["request_context"].payload
    user_messages = [
        {
            "content": message.content,
            "occurred_at": message.occurredAt,
        }
        for message in payload.conversationMessages
        if message.role == "user"
    ]
    sections = [
        AgentPromptSection(
            title="Risk assessment result",
            body=_render_json(payload.riskAssessmentResult),
        ),
        AgentPromptSection(
            title="Questionnaire answers",
            body=_render_json(payload.questionnaireAnswers),
        ),
        AgentPromptSection(
            title="User intent text",
            body=payload.userIntentText or "none",
        ),
        AgentPromptSection(
            title="User conversation messages",
            body=_render_json(user_messages),
        ),
    ]
    if payload.clientContext is not None:
        sections.append(
            AgentPromptSection(
                title="Client context",
                body=_render_json(payload.clientContext),
            )
        )
    sections.append(
        AgentPromptSection(
            title="Historical holdings and transactions",
            body=_render_text_block(
                (
                    f"historical_holdings={_render_json(payload.historicalHoldings)}",
                    f"historical_transactions={_render_json(payload.historicalTransactions)}",
                )
            ),
        )
    )
    return AgentPromptContext(
        task=(
            "Analyze the user's questionnaire, intent text, conversation, holdings, and transactions. "
            "Return the structured investment profile fields and derived signals."
        ),
        sections=tuple(sections),
        instructions=(
            "Use the full context, not just the questionnaire score.",
            "Infer risk tier, liquidity needs, horizon, return objective, and drawdown sensitivity from the user's own words when possible.",
            "Return concise derived_signals that cite the grounding source.",
        ),
    )


def _build_market_intelligence_prompt_context(
    *,
    state: RecommendationGraphState,
    market_facts: Mapping[str, object],
) -> AgentPromptContext:
    return AgentPromptContext(
        task=(
            "Analyze the provided market facts for this user and return sentiment, stance, "
            "preferred categories, avoided categories, summary, and evidence refs."
        ),
        sections=(
            AgentPromptSection(
                title="User profile insights",
                body=_render_json(_user_profile_output_for_runtime(state)),
            ),
            AgentPromptSection(
                title="User intent text",
                body=state["request_context"].user_intent_text or "none",
            ),
            AgentPromptSection(
                title="Market facts",
                body=_render_json(market_facts),
            ),
        ),
        instructions=(
            "Base every judgment on the supplied facts and evidence references.",
            "Choose evidence_refs from the provided market evidence sources only.",
        ),
    )


def _build_product_match_prompt_context(
    *,
    state: RecommendationGraphState,
    candidates: list[CandidateProduct],
    recalled_memories: list[str],
) -> AgentPromptContext:
    return AgentPromptContext(
        task=(
            "Select the final candidate products for this user using the candidate pool, "
            "user profile insights, market intelligence, and recalled memory."
        ),
        sections=(
            AgentPromptSection(
                title="User profile insights",
                body=_render_json(_user_profile_output_for_runtime(state)),
            ),
            AgentPromptSection(
                title="Market intelligence",
                body=_render_json(_market_output_for_runtime(state)),
            ),
            AgentPromptSection(
                title="Candidate pool facts",
                body=_render_json([_candidate_fact(candidate) for candidate in candidates]),
            ),
            AgentPromptSection(
                title="Retrieved memories",
                body=_render_json(recalled_memories),
            ),
        ),
        instructions=(
            "Only return product ids that exist in the supplied candidate pool.",
            "Use selected_product_ids for the final ids and ranking_rationale_zh/ranking_rationale_en for the bilingual rationale.",
            "Use filtered_out_reasons to explain major exclusions.",
        ),
    )


def _build_compliance_prompt_context(
    *,
    state: RecommendationGraphState,
    selected_candidates: list[CandidateProduct],
    compliance_facts: Mapping[str, object],
) -> AgentPromptContext:
    return AgentPromptContext(
        task=(
            "Review the selected products against the supplied compliance facts and rule snapshot. "
            "Return approve, revise_conservative, or block together with disclosures and reason codes."
        ),
        sections=(
            AgentPromptSection(
                title="User profile insights",
                body=_render_json(_user_profile_output_for_runtime(state)),
            ),
            AgentPromptSection(
                title="Market intelligence",
                body=_render_json(_market_output_for_runtime(state)),
            ),
            AgentPromptSection(
                title="Product match",
                body=_render_json(_product_match_output_for_runtime(state)),
            ),
            AgentPromptSection(
                title="Selected candidate facts",
                body=_render_json([_candidate_fact(candidate) for candidate in selected_candidates]),
            ),
            AgentPromptSection(
                title="Compliance facts",
                body=_render_json(compliance_facts),
            ),
        ),
        instructions=(
            "Only reference candidate ids that exist in the selected candidate facts.",
            "Return approved_ids/rejected_ids plus reason_summary_zh/reason_summary_en and required_disclosures_zh/en using the exact field names.",
            "Use applied_rule_ids and blocking_reason_codes when the facts support them.",
        ),
    )


def _build_manager_prompt_context(
    *,
    state: RecommendationGraphState,
) -> AgentPromptContext:
    return AgentPromptContext(
        task=(
            "Write the final recommendation summary and why-this-plan bullets using the upstream "
            "user profile, market intelligence, product match, and compliance outputs."
        ),
        sections=(
            AgentPromptSection(
                title="User profile insights",
                body=_render_json(_user_profile_output_for_runtime(state)),
            ),
            AgentPromptSection(
                title="Market intelligence",
                body=_render_json(_market_output_for_runtime(state)),
            ),
            AgentPromptSection(
                title="Product match",
                body=_render_json(_product_match_output_for_runtime(state)),
            ),
            AgentPromptSection(
                title="Compliance review",
                body=_render_json(_compliance_output_for_runtime(state)),
            ),
        ),
        instructions=(
            "Do not contradict the compliance verdict.",
            "Keep the explanation warm, clear, and grounded in the upstream outputs.",
        ),
    )


def _build_market_fact_payload(snapshot: Any) -> dict[str, object]:
    return {
        "summary_zh": getattr(snapshot, "summary_zh"),
        "summary_en": getattr(snapshot, "summary_en"),
        "preferred_categories": list(getattr(snapshot, "preferred_categories", [])),
        "avoided_categories": list(getattr(snapshot, "avoided_categories", [])),
        "evidence": [
            evidence.model_dump(mode="json")
            if hasattr(evidence, "model_dump")
            else evidence
            for evidence in getattr(snapshot, "evidence", [])
        ],
    }


def _candidate_fact(candidate: CandidateProduct) -> dict[str, object]:
    return {
        "id": candidate.id,
        "category": candidate.category,
        "risk_level": candidate.risk_level,
        "liquidity": candidate.liquidity,
        "lockup_days": candidate.lockup_days,
        "max_drawdown_percent": candidate.max_drawdown_percent,
        "name_zh": candidate.name_zh,
        "name_en": candidate.name_en,
        "tags_zh": list(candidate.tags_zh),
        "tags_en": list(candidate.tags_en),
    }


def _runtime_snapshot(candidate: CandidateProduct) -> RuntimeCandidateSnapshot:
    return RuntimeCandidateSnapshot(
        id=candidate.id,
        category=candidate.category,
        code=candidate.code,
        liquidity=candidate.liquidity,
        lockup_days=candidate.lockup_days,
        max_drawdown_percent=candidate.max_drawdown_percent,
        as_of_date=candidate.as_of_date,
        detail_route=candidate.detail_route,
        name_zh=candidate.name_zh,
        name_en=candidate.name_en,
        rationale_zh=candidate.rationale_zh,
        rationale_en=candidate.rationale_en,
        risk_level=candidate.risk_level,
        tags_zh=list(candidate.tags_zh),
        tags_en=list(candidate.tags_en),
    )


def _selected_candidates_for_compliance(
    *,
    retrieval_context: RetrievalContext,
    candidates_by_id: Mapping[str, CandidateProduct],
) -> list[CandidateProduct]:
    selected_candidates: list[CandidateProduct] = []
    for item in retrieval_context.candidates:
        if item.runtime_candidate is not None:
            snapshot = item.runtime_candidate
            selected_candidates.append(
                CandidateProduct(
                    id=snapshot.id,
                    category=snapshot.category,
                    code=snapshot.code,
                    liquidity=snapshot.liquidity,
                    lockup_days=snapshot.lockup_days,
                    max_drawdown_percent=snapshot.max_drawdown_percent,
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
            continue
        candidate = candidates_by_id.get(item.product_id)
        if candidate is not None:
            selected_candidates.append(candidate)
    return selected_candidates


def _ordered_candidates_from_agent_selection(
    *,
    candidates: list[CandidateProduct],
    product_match: ProductMatchAgentOutput,
) -> tuple[list[CandidateProduct], list[str]]:
    by_id = {candidate.id: candidate for candidate in candidates}
    ordered_ids = [
        *product_match.selected_product_ids,
        *product_match.fund_ids,
        *product_match.wealth_management_ids,
        *product_match.stock_ids,
    ]
    ordered_candidates: list[CandidateProduct] = []
    invalid_ids: list[str] = []
    seen: set[str] = set()
    for candidate_id in ordered_ids:
        if candidate_id in seen:
            continue
        candidate = by_id.get(candidate_id)
        if candidate is None:
            invalid_ids.append(candidate_id)
            continue
        seen.add(candidate_id)
        ordered_candidates.append(candidate)
    return ordered_candidates, invalid_ids


def _select_market_evidence(
    *,
    evidence: Sequence[MarketEvidenceItem],
    evidence_refs: Sequence[str],
) -> list[MarketEvidenceItem]:
    if not evidence_refs:
        return []
    evidence_by_source = {item.source: item for item in evidence}
    return [
        evidence_by_source[source]
        for source in evidence_refs
        if source in evidence_by_source
    ]


def _user_profile_output_for_runtime(
    state: RecommendationGraphState,
) -> UserProfileAgentOutput:
    user_intelligence = state["user_intelligence"]
    if user_intelligence is None:
        raise ValueError("user_intelligence must be present")
    return UserProfileAgentOutput(
        risk_tier=user_intelligence.risk_tier,
        liquidity_preference=user_intelligence.liquidity_preference,
        investment_horizon=user_intelligence.investment_horizon,
        return_objective=user_intelligence.return_objective,
        drawdown_sensitivity=user_intelligence.drawdown_sensitivity,
        profile_focus_zh=user_intelligence.profile_summary_zh,
        profile_focus_en=user_intelligence.profile_summary_en,
        derived_signals=list(user_intelligence.derived_signals),
    )


def _market_output_for_runtime(
    state: RecommendationGraphState,
) -> MarketIntelligenceAgentOutput:
    market_intelligence = state["market_intelligence"]
    if market_intelligence is None:
        raise ValueError("market_intelligence must be present")
    return MarketIntelligenceAgentOutput(
        sentiment=market_intelligence.sentiment,
        stance=market_intelligence.stance,
        preferred_categories=list(market_intelligence.preferred_categories),
        avoided_categories=list(market_intelligence.avoided_categories),
        summary_zh=market_intelligence.summary_zh,
        summary_en=market_intelligence.summary_en,
        evidence_refs=list(market_intelligence.evidence_refs),
    )


def _product_match_output_for_runtime(
    state: RecommendationGraphState,
) -> ProductMatchAgentOutput:
    product_strategy = state["product_strategy"]
    retrieval_context = state["retrieval_context"]
    if product_strategy is None or retrieval_context is None:
        raise ValueError("product_strategy and retrieval_context must be present")
    return ProductMatchAgentOutput(
        recommended_categories=list(product_strategy.recommended_categories),
        selected_product_ids=[item.product_id for item in retrieval_context.candidates],
        fund_ids=[
            item.product_id for item in retrieval_context.candidates if item.category == "fund"
        ],
        wealth_management_ids=[
            item.product_id
            for item in retrieval_context.candidates
            if item.category == "wealth_management"
        ],
        stock_ids=[
            item.product_id for item in retrieval_context.candidates if item.category == "stock"
        ],
        ranking_rationale_zh=product_strategy.ranking_rationale_zh,
        ranking_rationale_en=product_strategy.ranking_rationale_en,
        filtered_out_reasons=list(retrieval_context.filtered_out_reasons),
    )


def _compliance_output_for_runtime(
    state: RecommendationGraphState,
) -> ComplianceReviewAgentOutput:
    compliance_review = state["compliance_review"]
    retrieval_context = state["retrieval_context"]
    if compliance_review is None:
        raise ValueError("compliance_review must be present")
    selected_ids = (
        []
        if retrieval_context is None
        else [item.product_id for item in retrieval_context.candidates]
    )
    return ComplianceReviewAgentOutput(
        verdict=compliance_review.verdict,
        approved_ids=selected_ids,
        rejected_ids=[],
        reason_summary_zh=compliance_review.reason_zh,
        reason_summary_en=compliance_review.reason_en,
        required_disclosures_zh=list(compliance_review.disclosures_zh),
        required_disclosures_en=list(compliance_review.disclosures_en),
        suitability_notes_zh=list(compliance_review.suitability_notes_zh),
        suitability_notes_en=list(compliance_review.suitability_notes_en),
        applied_rule_ids=list(compliance_review.applied_rule_ids),
        blocking_reason_codes=list(compliance_review.blocking_reason_codes),
    )


def _route_metadata_if_available(
    agent_runtime: object | None,
    request_name: str,
) -> tuple[str | None, str | None]:
    if agent_runtime is None:
        return None, None
    route_metadata = getattr(agent_runtime, "route_metadata", None)
    if route_metadata is None:
        return None, None
    try:
        metadata = route_metadata(request_name)
    except Exception:  # noqa: BLE001
        return None, None
    return (
        getattr(metadata, "provider_name", None),
        getattr(metadata, "model_name", None),
    )


def _block_state_due_to_agent_failure(
    state: RecommendationGraphState,
    *,
    node_name: str,
    request_name: str,
    request_summary: str,
    code: str,
    message: str,
    provider_name: str | None = None,
    model_name: str | None = None,
) -> RecommendationGraphState:
    blocked_state = append_warning(
        state,
        stage=node_name,
        code=code,
        message=message,
    )
    blocked_state = {
        **blocked_state,
        "compliance_review": ComplianceReviewState(
            verdict="block",
            reason_zh=_BLOCKED_REASON_ZH,
            reason_en=_BLOCKED_REASON_EN,
            disclosures_zh=list(_BLOCKED_DISCLOSURES_ZH),
            disclosures_en=list(_BLOCKED_DISCLOSURES_EN),
            suitability_notes_zh=[message],
            suitability_notes_en=[message],
            applied_rule_ids=[],
            blocking_reason_codes=[code],
        ),
        "final_response": FinalResponseState(
            recommendation_status="blocked",
            summary_zh=_BLOCKED_SUMMARY_ZH,
            summary_en=_BLOCKED_SUMMARY_EN,
        ),
        "recommendation_draft": {
            "summary_zh": _BLOCKED_SUMMARY_ZH,
            "summary_en": _BLOCKED_SUMMARY_EN,
            "why_this_plan_zh": [_BLOCKED_REASON_ZH],
            "why_this_plan_en": [_BLOCKED_REASON_EN],
        },
    }
    return append_agent_trace_event(
        blocked_state,
        node_name=node_name,
        request_name=request_name,
        status="error",
        provider_name=provider_name,
        model_name=model_name,
        request_summary=request_summary,
        response_summary=code,
        tool_calls=(),
    )


def _append_skipped_trace(
    state: RecommendationGraphState,
    *,
    node_name: str,
    request_name: str,
    request_summary: str,
) -> RecommendationGraphState:
    return append_agent_trace_event(
        state,
        node_name=node_name,
        request_name=request_name,
        status="transition",
        request_summary=request_summary,
        response_summary="skipped",
        tool_calls=(),
    )


def _finalize_blocked_response(
    state: RecommendationGraphState,
) -> RecommendationGraphState:
    if state["final_response"] is not None:
        return state
    return {
        **state,
        "final_response": FinalResponseState(
            recommendation_status="blocked",
            summary_zh=_BLOCKED_SUMMARY_ZH,
            summary_en=_BLOCKED_SUMMARY_EN,
        ),
    }


def _is_blocked(state: RecommendationGraphState) -> bool:
    final_response = state["final_response"]
    if final_response is not None and final_response.recommendation_status == "blocked":
        return True
    compliance_review = state["compliance_review"]
    return compliance_review is not None and compliance_review.verdict == "block"


def _manager_status_for_verdict(
    *,
    verdict: str,
    requested_status: str,
) -> str:
    if verdict == "approve":
        return requested_status if requested_status in {"ready", "limited"} else "ready"
    if verdict == "revise_conservative":
        return "limited"
    return "blocked"


def _format_runtime_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def _allowed_risk_levels_for_tier(risk_tier: str) -> set[str]:
    normalized_tier = risk_tier.strip().upper()
    max_allowed = _RISK_ORDER.get(normalized_tier, _RISK_ORDER["R2"])
    return {
        level
        for level, order in _RISK_ORDER.items()
        if order <= max_allowed
    }


def _render_json(value: object) -> str:
    normalized = _normalize_json_value(value)
    return json.dumps(normalized, ensure_ascii=False, indent=2)


def _render_text_block(lines: Sequence[str]) -> str:
    non_empty = [line for line in lines if line]
    if not non_empty:
        return "none"
    return "\n".join(non_empty)


def _normalize_json_value(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_json_value(item) for item in value]
    return value
