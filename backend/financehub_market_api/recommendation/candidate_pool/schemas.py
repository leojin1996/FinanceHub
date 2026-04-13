from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from financehub_market_api.recommendation.schemas import CandidateProduct

CandidatePoolCategory = Literal["fund", "wealth_management", "stock"]


class CandidatePoolItem(BaseModel):
    id: str
    category: CandidatePoolCategory
    code: str | None = None
    name_zh: str
    name_en: str
    risk_level: str
    liquidity: str | None = None
    tags_zh: list[str] = Field(default_factory=list)
    tags_en: list[str] = Field(default_factory=list)
    rationale_zh: str
    rationale_en: str
    as_of_date: str
    detail_route: str

    def to_candidate_product(self) -> CandidateProduct:
        return CandidateProduct(
            id=self.id,
            category=self.category,
            code=self.code,
            liquidity=self.liquidity,
            as_of_date=self.as_of_date,
            detail_route=self.detail_route,
            name_zh=self.name_zh,
            name_en=self.name_en,
            risk_level=self.risk_level,
            tags_zh=list(self.tags_zh),
            tags_en=list(self.tags_en),
            rationale_zh=self.rationale_zh,
            rationale_en=self.rationale_en,
        )


class CandidatePoolSnapshot(BaseModel):
    category: CandidatePoolCategory
    generated_at: str
    fresh_until: str
    source: str
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    items: list[CandidatePoolItem] = Field(default_factory=list)


class ProductChartPoint(BaseModel):
    date: str
    value: float


class ProductDetailSnapshot(BaseModel):
    id: str
    category: CandidatePoolCategory
    code: str | None = None
    provider_name: str | None = None
    name_zh: str
    name_en: str
    as_of_date: str
    generated_at: str
    fresh_until: str
    source: str
    stale: bool = False
    risk_level: str
    liquidity: str | None = None
    tags_zh: list[str] = Field(default_factory=list)
    tags_en: list[str] = Field(default_factory=list)
    summary_zh: str
    summary_en: str
    recommendation_rationale_zh: str
    recommendation_rationale_en: str
    chart_label_zh: str
    chart_label_en: str
    chart: list[ProductChartPoint] = Field(default_factory=list)
    yield_metrics: dict[str, str] = Field(default_factory=dict)
    fees: dict[str, str] = Field(default_factory=dict)
    drawdown_or_volatility: dict[str, str] = Field(default_factory=dict)
    fit_for_profile_zh: str = ""
    fit_for_profile_en: str = ""

    def to_candidate_pool_item(self) -> CandidatePoolItem:
        return CandidatePoolItem(
            id=self.id,
            category=self.category,
            code=self.code,
            name_zh=self.name_zh,
            name_en=self.name_en,
            risk_level=self.risk_level,
            liquidity=self.liquidity,
            tags_zh=list(self.tags_zh),
            tags_en=list(self.tags_en),
            rationale_zh=self.recommendation_rationale_zh,
            rationale_en=self.recommendation_rationale_en,
            as_of_date=self.as_of_date,
            detail_route=f"/recommendations/products/{self.id}",
        )
