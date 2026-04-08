from financehub_market_api.models import LocalizedText
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
    assert len(snapshot.evidence) >= 2
    assert all(isinstance(item.summary, LocalizedText) for item in snapshot.evidence)


def test_memory_recall_service_returns_ranked_memories() -> None:
    store = _SpyMemoryStore()
    service = MemoryRecallService(store=store)

    memories = service.recall("一年期稳健理财", limit=2)

    assert memories == ["memory:一年期稳健理财", "preference:short_horizon"]
    assert store.last_query == "一年期稳健理财"
    assert store.last_limit == 2
