from financehub_market_api.cache import SnapshotCache
from financehub_market_api.recommendation.candidate_pool.cache import (
    CandidatePoolSnapshotCache,
    ProductDetailSnapshotCache,
)
from financehub_market_api.recommendation.candidate_pool.schemas import (
    CandidatePoolItem,
    CandidatePoolSnapshot,
    ProductChartPoint,
    ProductDetailSnapshot,
)


def test_candidate_pool_cache_round_trips_snapshot() -> None:
    cache = CandidatePoolSnapshotCache(SnapshotCache(ttl_seconds=300))
    snapshot = CandidatePoolSnapshot(
        category="stock",
        generated_at="2026-04-09T12:00:00+00:00",
        fresh_until="2026-04-09T12:10:00+00:00",
        source="premium_stock_refresh",
        fallback_used=False,
        warnings=[],
        stale=False,
        items=[
            CandidatePoolItem(
                id="stock-600036",
                category="stock",
                code="600036",
                name_zh="招商银行",
                name_en="China Merchants Bank",
                risk_level="R3",
                liquidity=None,
                tags_zh=["高股息"],
                tags_en=["Dividend quality"],
                rationale_zh="动态评分靠前。",
                rationale_en="Ranks highly on the dynamic score.",
                as_of_date="2026-04-09",
                detail_route="/recommendations/products/stock-600036",
            )
        ],
    )

    cache.put_candidate_pool("stock", snapshot)

    loaded = cache.get_candidate_pool("stock")

    assert loaded is not None
    assert loaded.items[0].detail_route == "/recommendations/products/stock-600036"


def test_product_detail_cache_peek_returns_stale_snapshot_after_expiry() -> None:
    cache = ProductDetailSnapshotCache(SnapshotCache(ttl_seconds=1))
    snapshot = ProductDetailSnapshot(
        id="stock-600036",
        category="stock",
        code="600036",
        provider_name="Premium stock refresh",
        name_zh="招商银行",
        name_en="China Merchants Bank",
        as_of_date="2026-04-09",
        generated_at="2026-04-09T12:00:00+00:00",
        fresh_until="2026-04-09T12:01:00+00:00",
        source="premium_stock_refresh",
        stale=False,
        risk_level="R3",
        liquidity=None,
        tags_zh=["高股息"],
        tags_en=["Dividend quality"],
        summary_zh="稳健龙头银行股。",
        summary_en="A stable leading bank stock.",
        recommendation_rationale_zh="动态评分靠前。",
        recommendation_rationale_en="Ranks highly on the dynamic score.",
        chart_label_zh="近5日走势",
        chart_label_en="5-day trend",
        chart=[ProductChartPoint(date="2026-04-09", value=42.5)],
    )

    cache.put_product_detail("stock-600036", snapshot)

    assert cache.get_product_detail("stock-600036") is not None
    assert cache.peek_product_detail("stock-600036") is not None
