from __future__ import annotations

from dataclasses import dataclass, field

from financehub_market_api.models import AllocationDisplay, RecommendationProduct, ReviewStatus, RiskProfile


@dataclass(frozen=True)
class RecommendationContext:
    risk_profile: RiskProfile
    profile_label_zh: str
    profile_label_en: str


@dataclass
class RecommendationState:
    allocation: AllocationDisplay | None = None
    aggressive_allocation: AllocationDisplay | None = None
    fund_items: list[RecommendationProduct] = field(default_factory=list)
    wealth_management_items: list[RecommendationProduct] = field(default_factory=list)
    stock_items: list[RecommendationProduct] = field(default_factory=list)
    market_summary_zh: str = ""
    market_summary_en: str = ""
    review_status: ReviewStatus = "pass"
    why_this_plan_zh: list[str] = field(default_factory=list)
    why_this_plan_en: list[str] = field(default_factory=list)
    applied_rules: list[str] = field(default_factory=list)
    decision_trace: list[str] = field(default_factory=list)

    def mark_applied(self, rule_name: str, detail: str | None = None) -> None:
        self.applied_rules.append(rule_name)
        if detail is not None:
            self.decision_trace.append(detail)
