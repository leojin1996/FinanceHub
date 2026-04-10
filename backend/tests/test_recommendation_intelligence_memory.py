from financehub_market_api.models import (
    IndexCard,
    IndicesResponse,
    LocalizedText,
    MarketOverviewResponse,
    MetricCard,
    OverviewStockSummary,
    TrendPoint,
)
from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService


class _SpyMemoryStore:
    def __init__(self) -> None:
        self.last_query: str | None = None
        self.last_limit: int | None = None

    def search(self, query: str, *, limit: int) -> list[str]:
        self.last_query = query
        self.last_limit = limit
        return [f"memory:{query}", "preference:short_horizon"][:limit]


class _FakeMarketDataService:
    def get_market_overview(self) -> MarketOverviewResponse:
        return MarketOverviewResponse(
            asOfDate="2026-04-02",
            stale=False,
            metrics=[
                MetricCard(
                    label="上证指数",
                    value="3,210.12",
                    delta="+0.8%",
                    changeValue=25.1,
                    changePercent=0.8,
                    tone="positive",
                ),
                MetricCard(
                    label="深证成指",
                    value="10,120.45",
                    delta="+0.3%",
                    changeValue=30.2,
                    changePercent=0.3,
                    tone="positive",
                ),
            ],
            chartLabel="上证指数",
            trendSeries=[
                TrendPoint(date="2026-03-27", value=3180.0),
                TrendPoint(date="2026-03-30", value=3192.0),
                TrendPoint(date="2026-03-31", value=3201.0),
                TrendPoint(date="2026-04-01", value=3205.0),
                TrendPoint(date="2026-04-02", value=3210.12),
            ],
            topGainers=[
                OverviewStockSummary(
                    code="300750",
                    name="宁德时代",
                    price="210.00",
                    priceValue=210.0,
                    change="+5.00",
                    changePercent=2.4,
                )
            ],
            topLosers=[
                OverviewStockSummary(
                    code="600519",
                    name="贵州茅台",
                    price="1500.00",
                    priceValue=1500.0,
                    change="-12.00",
                    changePercent=-0.8,
                )
            ],
        )

    def get_indices(self) -> IndicesResponse:
        return IndicesResponse(
            asOfDate="2026-04-02",
            stale=False,
            cards=[
                IndexCard(
                    name="上证指数",
                    code="000001",
                    market="SH",
                    description="上海证券交易所综合指数",
                    value="3,210.12",
                    valueNumber=3210.12,
                    changeValue=25.1,
                    changePercent=0.8,
                    tone="positive",
                    trendSeries=[
                        TrendPoint(date="2026-03-31", value=3201.0),
                        TrendPoint(date="2026-04-01", value=3205.0),
                        TrendPoint(date="2026-04-02", value=3210.12),
                    ],
                ),
                IndexCard(
                    name="深证成指",
                    code="399001",
                    market="SZ",
                    description="深圳证券交易所成份指数",
                    value="10,120.45",
                    valueNumber=10120.45,
                    changeValue=30.2,
                    changePercent=0.3,
                    tone="positive",
                    trendSeries=[
                        TrendPoint(date="2026-03-31", value=10050.0),
                        TrendPoint(date="2026-04-01", value=10090.0),
                        TrendPoint(date="2026-04-02", value=10120.45),
                    ],
                ),
                IndexCard(
                    name="创业板指",
                    code="399006",
                    market="SZ",
                    description="创业板指数",
                    value="2,150.00",
                    valueNumber=2150.0,
                    changeValue=-5.0,
                    changePercent=-0.2,
                    tone="negative",
                    trendSeries=[
                        TrendPoint(date="2026-03-31", value=2160.0),
                        TrendPoint(date="2026-04-01", value=2155.0),
                        TrendPoint(date="2026-04-02", value=2150.0),
                    ],
                ),
            ],
        )


class _NegativeMarketDataService:
    def get_market_overview(self) -> MarketOverviewResponse:
        return MarketOverviewResponse(
            asOfDate="2026-04-03",
            stale=False,
            metrics=[
                MetricCard(
                    label="上证指数",
                    value="3,180.12",
                    delta="-0.9%",
                    changeValue=-28.1,
                    changePercent=-0.9,
                    tone="negative",
                ),
                MetricCard(
                    label="深证成指",
                    value="9,980.45",
                    delta="-0.4%",
                    changeValue=-40.2,
                    changePercent=-0.4,
                    tone="negative",
                ),
            ],
            chartLabel="上证指数",
            trendSeries=[
                TrendPoint(date="2026-04-01", value=3230.0),
                TrendPoint(date="2026-04-02", value=3208.0),
                TrendPoint(date="2026-04-03", value=3180.12),
            ],
            topGainers=[],
            topLosers=[],
        )

    def get_indices(self) -> IndicesResponse:
        return IndicesResponse(
            asOfDate="2026-04-03",
            stale=False,
            cards=[
                IndexCard(
                    name="上证指数",
                    code="000001",
                    market="SH",
                    description="上海证券交易所综合指数",
                    value="3,180.12",
                    valueNumber=3180.12,
                    changeValue=-28.1,
                    changePercent=-0.9,
                    tone="negative",
                    trendSeries=[
                        TrendPoint(date="2026-04-02", value=3208.0),
                        TrendPoint(date="2026-04-03", value=3180.12),
                    ],
                ),
                IndexCard(
                    name="深证成指",
                    code="399001",
                    market="SZ",
                    description="深圳证券交易所成份指数",
                    value="9,980.45",
                    valueNumber=9980.45,
                    changeValue=-40.2,
                    changePercent=-0.4,
                    tone="negative",
                    trendSeries=[
                        TrendPoint(date="2026-04-02", value=10020.0),
                        TrendPoint(date="2026-04-03", value=9980.45),
                    ],
                ),
                IndexCard(
                    name="创业板指",
                    code="399006",
                    market="SZ",
                    description="创业板指数",
                    value="2,100.00",
                    valueNumber=2100.0,
                    changeValue=-12.0,
                    changePercent=-0.6,
                    tone="negative",
                    trendSeries=[
                        TrendPoint(date="2026-04-02", value=2112.0),
                        TrendPoint(date="2026-04-03", value=2100.0),
                    ],
                ),
            ],
        )


def test_market_intelligence_service_normalizes_live_and_fallback_sources() -> None:
    service = MarketIntelligenceService()

    snapshot = service.build_snapshot(
        market_overview_summary="市场震荡，债券偏强",
        macro_summary="降息预期升温",
        rate_summary="一年期存款利率下行",
        news_summaries=["债市资金面平稳", "权益板块分化"],
    )

    assert (
        snapshot.summary_zh
        == "市场概览：市场震荡，债券偏强；宏观环境：降息预期升温；利率观察：一年期存款利率下行；新闻要点：债市资金面平稳；权益板块分化"
    )
    assert (
        snapshot.summary_en
        == "Deterministic market snapshot built from overview, macro, rates, and news inputs."
    )
    assert snapshot.stance == "defensive"
    assert snapshot.sentiment == "neutral"
    assert snapshot.preferred_categories == ["wealth_management", "fund"]
    assert snapshot.avoided_categories == ["stock"]
    assert len(snapshot.evidence) >= 2
    assert all(isinstance(item.summary, LocalizedText) for item in snapshot.evidence)


def test_market_intelligence_service_builds_snapshot_from_market_data_models() -> None:
    service = MarketIntelligenceService(market_data_service=_FakeMarketDataService())

    snapshot = service.build_recommendation_snapshot()

    assert snapshot.sentiment == "positive"
    assert snapshot.stance == "offensive"
    assert snapshot.preferred_categories == ["fund", "stock"]
    assert snapshot.avoided_categories == []
    assert snapshot.summary_zh.startswith("市场概览（截至 2026-04-02）")
    assert "上证指数" in snapshot.summary_zh
    assert "宁德时代" in snapshot.summary_zh
    assert snapshot.summary_en.startswith("Market overview as of 2026-04-02")
    assert [item.source for item in snapshot.evidence] == [
        "market_overview",
        "indices",
        "market_leadership",
    ]
    assert all(item.asOf == "2026-04-02" for item in snapshot.evidence)


def test_market_intelligence_service_builds_negative_defensive_snapshot() -> None:
    service = MarketIntelligenceService(market_data_service=_NegativeMarketDataService())

    snapshot = service.build_recommendation_snapshot()

    assert snapshot.sentiment == "negative"
    assert snapshot.stance == "defensive"
    assert snapshot.preferred_categories == ["wealth_management", "fund"]
    assert snapshot.avoided_categories == ["stock"]


def test_memory_recall_service_returns_ranked_memories() -> None:
    store = _SpyMemoryStore()
    service = MemoryRecallService(store=store)

    memories = service.recall("一年期稳健理财", limit=2)

    assert memories == ["memory:一年期稳健理财", "preference:short_horizon"]
    assert store.last_query == "一年期稳健理财"
    assert store.last_limit == 2
