from financehub_market_api.cache import SnapshotCache
from financehub_market_api.recommendation.candidate_pool.cache import (
    CandidatePoolSnapshotCache,
    ProductDetailSnapshotCache,
)
from financehub_market_api.recommendation.candidate_pool.refresh import (
    RecommendationCandidatePoolRefresher,
)
from financehub_market_api.recommendation.candidate_pool.schemas import (
    ProductChartPoint,
    ProductDetailSnapshot,
)


def _detail_snapshot(product_id: str, category: str) -> ProductDetailSnapshot:
    return ProductDetailSnapshot(
        id=product_id,
        category=category,
        code=product_id.split("-")[-1] if category == "stock" else None,
        provider_name="test-provider",
        name_zh=f"{product_id}-zh",
        name_en=f"{product_id}-en",
        as_of_date="2026-04-09",
        generated_at="2026-04-09T12:00:00+00:00",
        fresh_until="2026-04-09T12:10:00+00:00",
        source="unit-test",
        stale=False,
        risk_level="R2" if category != "stock" else "R3",
        liquidity="T+1" if category != "stock" else None,
        tags_zh=["标签"],
        tags_en=["Tag"],
        summary_zh="摘要",
        summary_en="Summary",
        recommendation_rationale_zh="推荐理由",
        recommendation_rationale_en="Recommendation rationale",
        chart_label_zh="近5日走势",
        chart_label_en="5-day trend",
        chart=[ProductChartPoint(date="2026-04-09", value=1.0)],
        yield_metrics={"daily": "1.0%"},
        fees={"management": "0.10%"},
        drawdown_or_volatility={"volatility": "low"},
        fit_for_profile_zh="适合稳健用户",
        fit_for_profile_en="Fits steady users",
    )


class _StaticProvider:
    def __init__(self, snapshots: list[ProductDetailSnapshot]) -> None:
        self._snapshots = snapshots

    def list_product_details(self) -> list[ProductDetailSnapshot]:
        return list(self._snapshots)


class _FailingProvider:
    def list_product_details(self) -> list[ProductDetailSnapshot]:
        raise RuntimeError("upstream failed")


def test_refresh_writes_independent_category_snapshots() -> None:
    cache = SnapshotCache(ttl_seconds=300)
    refresher = RecommendationCandidatePoolRefresher(
        candidate_pool_cache=CandidatePoolSnapshotCache(cache),
        product_detail_cache=ProductDetailSnapshotCache(cache),
        fund_provider=_StaticProvider([_detail_snapshot("fund-001", "fund")]),
        wealth_provider=_StaticProvider([_detail_snapshot("wm-001", "wealth_management")]),
        stock_provider=_StaticProvider([_detail_snapshot("stock-600036", "stock")]),
    )

    result = refresher.refresh_all()

    assert result["fund"].status == "fresh"
    assert result["wealth_management"].status == "fresh"
    assert result["stock"].status == "fresh"
    assert refresher._candidate_pool_cache.get_candidate_pool("stock") is not None


def test_refresh_keeps_previous_snapshot_when_one_category_fails() -> None:
    cache = SnapshotCache(ttl_seconds=300)
    candidate_pool_cache = CandidatePoolSnapshotCache(cache)
    product_detail_cache = ProductDetailSnapshotCache(cache)
    bootstrap_refresher = RecommendationCandidatePoolRefresher(
        candidate_pool_cache=candidate_pool_cache,
        product_detail_cache=product_detail_cache,
        fund_provider=_StaticProvider([_detail_snapshot("fund-001", "fund")]),
        wealth_provider=_StaticProvider([_detail_snapshot("wm-001", "wealth_management")]),
        stock_provider=_StaticProvider([_detail_snapshot("stock-600036", "stock")]),
    )
    bootstrap_refresher.refresh_all()

    refresher = RecommendationCandidatePoolRefresher(
        candidate_pool_cache=candidate_pool_cache,
        product_detail_cache=product_detail_cache,
        fund_provider=_StaticProvider([_detail_snapshot("fund-002", "fund")]),
        wealth_provider=_FailingProvider(),
        stock_provider=_StaticProvider([_detail_snapshot("stock-601318", "stock")]),
    )

    result = refresher.refresh_all()

    wealth_snapshot = candidate_pool_cache.peek_candidate_pool("wealth_management")

    assert result["wealth_management"].status == "error"
    assert wealth_snapshot is not None
    assert [item.id for item in wealth_snapshot.items] == ["wm-001"]


def test_refresh_category_updates_only_requested_category() -> None:
    cache = SnapshotCache(ttl_seconds=300)
    candidate_pool_cache = CandidatePoolSnapshotCache(cache)
    product_detail_cache = ProductDetailSnapshotCache(cache)
    refresher = RecommendationCandidatePoolRefresher(
        candidate_pool_cache=candidate_pool_cache,
        product_detail_cache=product_detail_cache,
        fund_provider=_StaticProvider([_detail_snapshot("fund-001", "fund")]),
        wealth_provider=_StaticProvider([_detail_snapshot("wm-001", "wealth_management")]),
        stock_provider=_StaticProvider([_detail_snapshot("stock-600036", "stock")]),
    )

    result = refresher.refresh_category("stock")

    assert result.status == "fresh"
    assert candidate_pool_cache.get_candidate_pool("stock") is not None
    assert candidate_pool_cache.get_candidate_pool("fund") is None
    assert candidate_pool_cache.get_candidate_pool("wealth_management") is None
