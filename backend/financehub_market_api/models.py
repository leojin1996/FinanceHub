from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr


Tone = Literal["positive", "negative", "neutral"]
RiskProfile = Literal["conservative", "stable", "balanced", "growth", "aggressive"]
RecommendationCategory = Literal["fund", "wealth_management", "stock"]
ReviewStatus = Literal["pass", "partial_pass"]
DimensionLevel = Literal["low", "mediumLow", "medium", "mediumHigh", "high"]
ExecutionMode = Literal["agent_assisted", "rules_fallback"]
RecommendationStatus = Literal["ready", "limited", "blocked"]


class MetricCard(BaseModel):
    label: str
    value: str
    delta: str
    changeValue: float
    changePercent: float
    tone: Tone


class TrendPoint(BaseModel):
    date: str
    value: float


class RankingItem(BaseModel):
    name: str
    value: str


class OverviewStockSummary(BaseModel):
    code: str
    name: str
    price: str
    priceValue: float
    change: str
    changePercent: float


class MarketOverviewResponse(BaseModel):
    asOfDate: str
    stale: bool
    metrics: list[MetricCard]
    chartLabel: str
    trendSeries: list[TrendPoint]
    topGainers: list[OverviewStockSummary]
    topLosers: list[OverviewStockSummary]


class IndexSeriesItem(BaseModel):
    name: str
    value: float


class IndexCard(BaseModel):
    name: str
    code: str
    market: str
    description: str
    value: str
    valueNumber: float
    changeValue: float
    changePercent: float
    tone: Tone
    trendSeries: list[TrendPoint]


class IndicesResponse(BaseModel):
    asOfDate: str
    stale: bool
    cards: list[IndexCard]


class StockRow(BaseModel):
    code: str
    name: str
    sector: str
    price: str
    change: str
    priceValue: float
    changePercent: float
    volumeValue: float
    amountValue: float
    trend7d: list[TrendPoint]
    _raw_change: float = PrivateAttr(default=0.0)
    _raw_change_value: float = PrivateAttr(default=0.0)


class StocksResponse(BaseModel):
    asOfDate: str
    stale: bool
    rows: list[StockRow]


class RecommendationRequest(BaseModel):
    riskProfile: RiskProfile


class RiskAssessmentDimensionLevels(BaseModel):
    riskTolerance: DimensionLevel
    investmentHorizon: DimensionLevel
    capitalStability: DimensionLevel
    investmentExperience: DimensionLevel
    returnObjective: DimensionLevel


class RiskAssessmentDimensionScores(BaseModel):
    riskTolerance: int
    investmentHorizon: int
    capitalStability: int
    investmentExperience: int
    returnObjective: int


class RiskAssessmentResultPayload(BaseModel):
    baseProfile: RiskProfile
    dimensionLevels: RiskAssessmentDimensionLevels
    dimensionScores: RiskAssessmentDimensionScores
    finalProfile: RiskProfile
    totalScore: int


class QuestionnaireAnswer(BaseModel):
    questionId: str | None = None
    answerId: str | None = None
    dimension: str | None = None
    score: int | None = None


class HistoricalHolding(BaseModel):
    symbol: str | None = None
    category: str | None = None
    quantity: float | None = None
    marketValue: float | None = None


class HistoricalTransaction(BaseModel):
    symbol: str | None = None
    action: str | None = None
    category: str | None = None
    amount: float | None = None
    occurredAt: str | None = None


class ConversationMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)
    occurredAt: str | None = None


class RecommendationClientContext(BaseModel):
    channel: str | None = None
    locale: str | None = None


class RecommendationGenerationRequest(BaseModel):
    riskAssessmentResult: RiskAssessmentResultPayload
    includeAggressiveOption: bool = True
    questionnaireAnswers: list[QuestionnaireAnswer] = Field(default_factory=list)
    historicalHoldings: list[HistoricalHolding] = Field(default_factory=list)
    historicalTransactions: list[HistoricalTransaction] = Field(default_factory=list)
    userIntentText: str | None = None
    conversationMessages: list[ConversationMessage] = Field(default_factory=list)
    clientContext: RecommendationClientContext | None = None


class AllocationDisplay(BaseModel):
    fund: int
    wealthManagement: int
    stock: int


class RecommendationProduct(BaseModel):
    id: str
    category: RecommendationCategory
    code: str | None = None
    liquidity: str | None = None
    nameEn: str
    nameZh: str
    rationaleEn: str
    rationaleZh: str
    riskLevel: str
    tagsEn: list[str]
    tagsZh: list[str]


class RecommendationSection(BaseModel):
    items: list[RecommendationProduct]
    titleEn: str
    titleZh: str


class RecommendationSections(BaseModel):
    funds: RecommendationSection
    wealthManagement: RecommendationSection
    stocks: RecommendationSection


class RecommendationSummary(BaseModel):
    subtitleEn: str
    subtitleZh: str
    titleEn: str
    titleZh: str


class LocalizedText(BaseModel):
    en: str
    zh: str


class LocalizedTextList(BaseModel):
    en: list[str]
    zh: list[str]


class RecommendationOption(BaseModel):
    allocation: AllocationDisplay
    subtitleEn: str
    subtitleZh: str
    titleEn: str
    titleZh: str


class RecommendationWarning(BaseModel):
    stage: str
    code: str
    message: str


class ComplianceReviewPayload(BaseModel):
    verdict: Literal["approve", "revise_conservative", "block"]
    reasonSummary: LocalizedText
    requiredDisclosures: LocalizedTextList
    suitabilityNotes: LocalizedTextList


class MarketEvidenceItem(BaseModel):
    source: str
    asOf: str
    summary: LocalizedText


class AgentTraceEvent(BaseModel):
    nodeName: str
    requestName: str
    status: Literal["start", "finish", "error", "transition"]
    providerName: str | None = None
    modelName: str | None = None
    durationMs: int | None = None
    requestSummary: str | None = None
    responseSummary: str | None = None


class RecommendationResponse(BaseModel):
    aggressiveOption: RecommendationOption | None
    allocationDisplay: AllocationDisplay
    executionMode: ExecutionMode
    marketSummary: LocalizedText
    profileSummary: LocalizedText
    reviewStatus: ReviewStatus
    riskNotice: LocalizedTextList
    sections: RecommendationSections
    summary: RecommendationSummary
    warnings: list[RecommendationWarning] = Field(default_factory=list)
    whyThisPlan: LocalizedTextList
    recommendationStatus: RecommendationStatus = "ready"
    complianceReview: ComplianceReviewPayload | None = None
    marketEvidence: list[MarketEvidenceItem] = Field(default_factory=list)
    agentTrace: list[AgentTraceEvent] = Field(default_factory=list)
