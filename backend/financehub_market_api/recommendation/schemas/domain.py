from __future__ import annotations

from dataclasses import dataclass, field

from financehub_market_api.models import AllocationDisplay, RecommendationProduct, ReviewStatus, RiskProfile


@dataclass(frozen=True)
class UserProfile:
    risk_profile: RiskProfile
    label_zh: str
    label_en: str


@dataclass(frozen=True)
class MarketContext:
    summary_zh: str
    summary_en: str


@dataclass(frozen=True)
class AllocationPlan:
    fund: int
    wealth_management: int
    stock: int

    def to_display(self) -> AllocationDisplay:
        return AllocationDisplay(
            fund=self.fund,
            wealthManagement=self.wealth_management,
            stock=self.stock,
        )


@dataclass(frozen=True)
class CandidateProduct:
    id: str
    category: str
    name_zh: str
    name_en: str
    risk_level: str
    tags_zh: list[str]
    tags_en: list[str]
    rationale_zh: str
    rationale_en: str
    code: str | None = None
    liquidity: str | None = None
    as_of_date: str | None = None
    detail_route: str | None = None

    def to_api_model(self) -> RecommendationProduct:
        return RecommendationProduct(
            id=self.id,
            category=self.category,
            nameZh=self.name_zh,
            nameEn=self.name_en,
            riskLevel=self.risk_level,
            tagsZh=list(self.tags_zh),
            tagsEn=list(self.tags_en),
            rationaleZh=self.rationale_zh,
            rationaleEn=self.rationale_en,
            code=self.code,
            liquidity=self.liquidity,
            asOfDate=self.as_of_date,
            detailRoute=self.detail_route,
        )


@dataclass(frozen=True)
class RiskReviewResult:
    review_status: ReviewStatus


@dataclass
class DegradedWarning:
    stage: str
    code: str
    message: str


@dataclass
class ExecutionTrace:
    path: str = "rules_fallback"
    execution_mode: str = "rules_fallback"
    degraded: bool = False
    warnings: list[DegradedWarning] = field(default_factory=list)
    applied_rules: list[str] = field(default_factory=list)
    decision_trace: list[str] = field(default_factory=list)


@dataclass
class RuleEvaluationState:
    market_context: MarketContext | None = None
    allocation: AllocationPlan | None = None
    aggressive_allocation: AllocationPlan | None = None
    fund_items: list[CandidateProduct] = field(default_factory=list)
    wealth_management_items: list[CandidateProduct] = field(default_factory=list)
    stock_items: list[CandidateProduct] = field(default_factory=list)
    review_result: RiskReviewResult = field(default_factory=lambda: RiskReviewResult(review_status="pass"))
    why_this_plan_zh: list[str] = field(default_factory=list)
    why_this_plan_en: list[str] = field(default_factory=list)
    execution_trace: ExecutionTrace = field(default_factory=ExecutionTrace)

    def mark_applied(self, rule_name: str, detail: str | None = None) -> None:
        self.execution_trace.applied_rules.append(rule_name)
        if detail is not None:
            self.execution_trace.decision_trace.append(detail)


@dataclass(frozen=True)
class FinalRecommendation:
    user_profile: UserProfile
    market_context: MarketContext
    allocation_plan: AllocationPlan
    aggressive_allocation_plan: AllocationPlan
    fund_items: list[CandidateProduct]
    wealth_management_items: list[CandidateProduct]
    stock_items: list[CandidateProduct]
    risk_review_result: RiskReviewResult
    why_this_plan_zh: list[str]
    why_this_plan_en: list[str]
    execution_trace: ExecutionTrace
