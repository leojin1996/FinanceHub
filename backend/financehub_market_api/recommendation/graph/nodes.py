from __future__ import annotations

from financehub_market_api.recommendation.compliance import ComplianceReviewService
from financehub_market_api.recommendation.graph.routing import route_compliance_verdict
from financehub_market_api.recommendation.graph.state import (
    ComplianceReviewState,
    FinalResponseState,
    MarketIntelligenceState,
    RecommendationGraphState,
    RetrievalContext,
    RetrievedCandidate,
    UserIntelligence,
    append_agent_trace_event,
    append_warning,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService
from financehub_market_api.recommendation.product_index import ProductRetrievalService
from financehub_market_api.recommendation.schemas import CandidateProduct

_RISK_PROFILE_TO_TIER = {
    "conservative": "R2",
    "stable": "R2",
    "balanced": "R3",
    "growth": "R4",
    "aggressive": "R5",
}

_PROFILE_LABELS_ZH = {
    "conservative": "保守型",
    "stable": "稳健型",
    "balanced": "平衡型",
    "growth": "成长型",
    "aggressive": "进取型",
}

_PROFILE_LABELS_EN = {
    "conservative": "Conservative",
    "stable": "Stable",
    "balanced": "Balanced",
    "growth": "Growth",
    "aggressive": "Aggressive",
}


def user_profile_analyst_node(state: RecommendationGraphState) -> RecommendationGraphState:
    payload = state["request_context"].payload
    risk_profile = payload.riskAssessmentResult.finalProfile
    dimension_levels = payload.riskAssessmentResult.dimensionLevels

    user_intelligence = UserIntelligence(
        risk_tier=_RISK_PROFILE_TO_TIER.get(risk_profile, "R2"),
        liquidity_preference="high" if risk_profile in {"conservative", "stable"} else "medium",
        investment_horizon=dimension_levels.investmentHorizon,
        return_objective=dimension_levels.returnObjective,
        drawdown_sensitivity=dimension_levels.riskTolerance,
        profile_summary_zh=(
            f"您的测评结果更接近{_PROFILE_LABELS_ZH[risk_profile]}，适合先控制回撤，再追求稳步增值。"
        ),
        profile_summary_en=(
            f"Your assessment aligns with a {_PROFILE_LABELS_EN[risk_profile]} profile, which calls for drawdown control before chasing extra upside."
        ),
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

    snapshot = market_intelligence_service.build_snapshot(
        market_overview_summary="A股宽基震荡，红利与固收风格相对占优。",
        macro_summary="宏观修复温和，政策基调保持稳增长。",
        rate_summary="一年期利率中枢下移，稳健资产仍具吸引力。",
        news_summaries=[
            "公募资金净申购延续，低波动产品关注度提升",
            "龙头权益估值分化，建议保持行业分散",
        ],
    )

    next_state = {
        **state,
        "market_intelligence": MarketIntelligenceState(
            sentiment=snapshot.sentiment,
            stance=snapshot.stance,
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
    if user_intelligence is None:
        raise ValueError("user_intelligence must be present before product_match_expert_node")

    query_text = state["request_context"].user_intent_text or user_intelligence.profile_summary_zh
    recalled_memories = memory_recall_service.recall(query_text, limit=3)
    retrieved = product_retrieval_service.retrieve(
        query_text=query_text,
        candidates=product_candidates,
        allowed_risk_levels={"R1", "R2", "R3", "R4", "R5"},
        limit=6,
    )

    retrieval_context = RetrievalContext(
        recalled_memories=recalled_memories,
        candidates=[
            RetrievedCandidate(
                product_id=candidate.id,
                category=candidate.category,
                score=max(0.01, 1.0 - index * 0.08),
                rationale=candidate.rationale_zh,
            )
            for index, candidate in enumerate(retrieved)
        ],
        filtered_out_reasons=[],
    )

    next_state = {
        **state,
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
    selected_candidates = [
        candidates_by_id[item.product_id]
        for item in retrieval_context.candidates
        if item.product_id in candidates_by_id
    ]

    review_result = compliance_review_service.review(
        risk_tier=user_intelligence.risk_tier,
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
        ),
    }

    if review_result.verdict != "approve":
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


def manager_coordinator_node(state: RecommendationGraphState) -> RecommendationGraphState:
    route = route_compliance_verdict(state)
    status_by_route = {
        "approved": "ready",
        "limited": "limited",
        "blocked": "blocked",
    }
    summary_by_route = {
        "approved": (
            "推荐结果已通过合规审阅，可直接查看主方案。",
            "Recommendation is compliance-approved and ready to present.",
        ),
        "limited": (
            "推荐结果需采用更稳健限制版本，请先查看合规提示。",
            "Recommendation is limited and revised conservatively; review compliance notes first.",
        ),
        "blocked": (
            "推荐结果暂不可下发，请联系投顾人工复核。",
            "Recommendation is blocked and requires manual advisor review.",
        ),
    }
    summary_zh, summary_en = summary_by_route[route]

    next_state = {
        **state,
        "final_response": FinalResponseState(
            recommendation_status=status_by_route[route],
            summary_zh=summary_zh,
            summary_en=summary_en,
        ),
    }
    return append_agent_trace_event(
        next_state,
        node_name="manager_coordinator",
        request_name="manager_coordinator",
        status="finish",
        request_summary=f"route={route}",
        response_summary=f"status={status_by_route[route]}",
    )
