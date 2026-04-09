from __future__ import annotations

from financehub_market_api.recommendation.compliance import ComplianceReviewService
from financehub_market_api.recommendation.graph.routing import route_compliance_verdict
from financehub_market_api.recommendation.graph.state import (
    ComplianceReviewState,
    FinalResponseState,
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
from financehub_market_api.recommendation.manager_synthesis import ManagerSynthesisService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.profile_intelligence import ProfileIntelligenceService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.schemas import CandidateProduct

_RISK_ORDER = {"R1": 1, "R2": 2, "R3": 3, "R4": 4, "R5": 5}


def user_profile_analyst_node(
    state: RecommendationGraphState,
    *,
    profile_intelligence_service: ProfileIntelligenceService,
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
    }
    return append_agent_trace_event(
        next_state,
        node_name="user_profile_analyst",
        request_name="user_profile_analyst",
        status="finish",
        request_summary=f"risk_profile={risk_profile}",
        response_summary=f"risk_tier={user_intelligence.risk_tier}",
    )


def market_intelligence_node(
    state: RecommendationGraphState,
    *,
    market_intelligence_service: MarketIntelligenceService,
) -> RecommendationGraphState:
    user_intelligence = state["user_intelligence"]
    if user_intelligence is None:
        raise ValueError("user_intelligence must be present before market_intelligence_node")

    snapshot = market_intelligence_service.build_recommendation_snapshot()

    next_state = {
        **state,
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
    return append_agent_trace_event(
        next_state,
        node_name="market_intelligence",
        request_name="market_intelligence",
        status="finish",
        request_summary=f"risk_tier={user_intelligence.risk_tier}",
        response_summary=f"stance={snapshot.stance}",
    )


def product_match_expert_node(
    state: RecommendationGraphState,
    *,
    product_retrieval_service: ProductRetrievalService,
    memory_recall_service: MemoryRecallService,
    product_candidates: list[CandidateProduct],
) -> RecommendationGraphState:
    user_intelligence = state["user_intelligence"]
    market_intelligence = state["market_intelligence"]
    if user_intelligence is None or market_intelligence is None:
        raise ValueError(
            "user_intelligence and market_intelligence must be present before product_match_expert_node"
        )

    query_text = state["request_context"].user_intent_text or user_intelligence.profile_summary_zh
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
    recommended_categories = [
        category for category in preferred_categories if category not in blocked_categories
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
                    name_zh=candidate.name_zh,
                    name_en=candidate.name_en,
                    rationale_zh=candidate.rationale_zh,
                    rationale_en=candidate.rationale_en,
                    risk_level=candidate.risk_level,
                    tags_zh=list(candidate.tags_zh),
                    tags_en=list(candidate.tags_en),
                ),
            )
            for index, candidate in enumerate(retrieval_plan.candidates)
        ],
        filtered_out_reasons=list(retrieval_plan.filtered_out_reasons),
    )

    next_state = {
        **state,
        "product_strategy": product_strategy,
        "retrieval_context": retrieval_context,
    }
    return append_agent_trace_event(
        next_state,
        node_name="product_match_expert",
        request_name="product_match_expert",
        status="finish",
        request_summary=f"candidate_pool={len(product_candidates)}",
        response_summary=f"retrieved={len(retrieval_context.candidates)}",
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
        raise ValueError("user_intelligence and retrieval_context are required for compliance")

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
        request_summary=f"route={route}",
        response_summary=f"status={manager_brief.recommendation_status}",
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
    blocked_categories = set(market_intelligence.avoided_categories)
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
