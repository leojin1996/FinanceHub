import type { RiskAssessmentResult } from "../features/risk-assessment/risk-scoring";

export interface MetricCardData {
  label: string;
  value: string;
  delta: string;
  changeValue: number;
  changePercent: number;
  tone: "positive" | "negative" | "neutral";
}

export interface TrendPoint {
  date: string;
  value: number;
}

export interface RankingItem {
  code: string;
  name: string;
  price: string;
  priceValue: number;
  change: string;
  changePercent: number;
}

export interface MarketOverviewResponse {
  asOfDate: string;
  chartLabel: string;
  stale: boolean;
  metrics: MetricCardData[];
  trendSeries: TrendPoint[];
  topGainers: RankingItem[];
  topLosers: RankingItem[];
}

export interface IndicesResponse {
  asOfDate: string;
  stale: boolean;
  cards: IndexCardData[];
}

export interface IndexCardData {
  name: string;
  code: string;
  market: string;
  description: string;
  value: string;
  valueNumber: number;
  changeValue: number;
  changePercent: number;
  tone: "positive" | "negative" | "neutral";
  trendSeries: TrendPoint[];
}

export interface StockRowData {
  code: string;
  name: string;
  sector: string;
  price: string;
  change: string;
  priceValue: number;
  changePercent: number;
  volumeValue: number;
  amountValue: number;
  trend7d: TrendPoint[];
}

export interface StocksResponse {
  asOfDate: string;
  stale: boolean;
  rows: StockRowData[];
}

export interface AllocationDisplay {
  fund: number;
  wealthManagement: number;
  stock: number;
}

export interface RecommendationProduct {
  id: string;
  category: "fund" | "wealth_management" | "stock";
  code?: string | null;
  liquidity?: string | null;
  nameEn: string;
  nameZh: string;
  rationaleEn: string;
  rationaleZh: string;
  riskLevel: string;
  tagsEn: string[];
  tagsZh: string[];
}

export interface RecommendationSection {
  items: RecommendationProduct[];
  titleEn: string;
  titleZh: string;
}

export interface LocalizedText {
  en: string;
  zh: string;
}

export interface LocalizedTextList {
  en: string[];
  zh: string[];
}

export interface RecommendationWarning {
  code: string;
  message: string;
  stage: string;
}

export interface RecommendationResponse {
  aggressiveOption: {
    allocation: AllocationDisplay;
    subtitleEn: string;
    subtitleZh: string;
    titleEn: string;
    titleZh: string;
  } | null;
  allocationDisplay: AllocationDisplay;
  executionMode: "agent_assisted" | "rules_fallback";
  marketSummary: LocalizedText;
  profileSummary: LocalizedText;
  reviewStatus: "pass" | "partial_pass";
  riskNotice: LocalizedTextList;
  sections: {
    funds: RecommendationSection;
    wealthManagement: RecommendationSection;
    stocks: RecommendationSection;
  };
  summary: {
    subtitleEn: string;
    subtitleZh: string;
    titleEn: string;
    titleZh: string;
  };
  warnings: RecommendationWarning[];
  whyThisPlan: LocalizedTextList;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const message = typeof payload?.detail === "string" ? payload.detail : "request failed";
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function fetchMarketOverview(): Promise<MarketOverviewResponse> {
  return fetch("/api/market-overview").then(readJson<MarketOverviewResponse>);
}

export function fetchIndices(): Promise<IndicesResponse> {
  return fetch("/api/indices").then(readJson<IndicesResponse>);
}

export function fetchStocks(query?: string): Promise<StocksResponse> {
  const url = query ? `/api/stocks?query=${encodeURIComponent(query)}` : "/api/stocks";
  return fetch(url).then(readJson<StocksResponse>);
}

export function fetchRecommendations(
  riskAssessmentResult: RiskAssessmentResult,
): Promise<RecommendationResponse> {
  return fetch("/api/recommendations/generate", {
    body: JSON.stringify({
      historicalHoldings: [],
      historicalTransactions: [],
      includeAggressiveOption: true,
      questionnaireAnswers: [],
      riskAssessmentResult,
    }),
    headers: { "Content-Type": "application/json" },
    method: "POST",
  }).then(readJson<RecommendationResponse>);
}
