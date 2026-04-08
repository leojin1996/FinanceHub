from financehub_market_api.recommendation.intelligence import MarketIntelligenceService
from financehub_market_api.recommendation.memory import MemoryRecallService


class _StaticMemoryStore:
    def search(self, query: str, *, limit: int) -> list[str]:
        return [f"memory:{query}", "preference:short_horizon"][:limit]


def test_market_intelligence_service_normalizes_live_and_fallback_sources() -> None:
    service = MarketIntelligenceService()

    snapshot = service.build_snapshot(
        market_overview_summary="市场震荡，债券偏强",
        macro_summary="降息预期升温",
        rate_summary="一年期存款利率下行",
        news_summaries=["债市资金面平稳", "权益板块分化"],
    )

    assert snapshot.summary_zh
    assert snapshot.stance in {"defensive", "balanced", "offensive"}
    assert snapshot.evidence


def test_memory_recall_service_returns_ranked_memories() -> None:
    service = MemoryRecallService(store=_StaticMemoryStore())

    memories = service.recall("一年期稳健理财", limit=2)

    assert memories == ["memory:一年期稳健理财", "preference:short_horizon"]
