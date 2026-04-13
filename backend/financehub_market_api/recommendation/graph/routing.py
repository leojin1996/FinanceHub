from __future__ import annotations

from financehub_market_api.recommendation.graph.state import RecommendationGraphState


def route_compliance_verdict(state: RecommendationGraphState) -> str:
    compliance_review = state["compliance_review"]
    if compliance_review is None:
        return "blocked"
    if compliance_review.verdict == "approve":
        return "approved"
    if compliance_review.verdict == "revise_conservative":
        return "limited"
    return "blocked"
