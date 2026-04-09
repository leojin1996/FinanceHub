from financehub_market_api.cache import SnapshotCache
from financehub_market_api.recommendation.candidate_pool.cache import CandidatePoolSnapshotCache
from financehub_market_api.recommendation.candidate_pool.schemas import (
    CandidatePoolItem,
    CandidatePoolSnapshot,
)
from financehub_market_api.recommendation.repositories.prefetched_candidate_repository import (
    PrefetchedCandidateRepository,
)
from financehub_market_api.recommendation.rules import map_user_profile


def _make_snapshot(category: str, product_ids: list[str]) -> CandidatePoolSnapshot:
    return CandidatePoolSnapshot(
        category=category,
        generated_at="2026-04-09T12:00:00+00:00",
        fresh_until="2026-04-09T12:10:00+00:00",
        source="unit-test",
        fallback_used=False,
        warnings=[],
        stale=False,
        items=[
            CandidatePoolItem(
                id=product_id,
                category=category,  # type: ignore[arg-type]
                code=product_id.split("-")[-1] if category == "stock" else None,
                name_zh=f"{product_id}-zh",
                name_en=f"{product_id}-en",
                risk_level="R2" if category != "stock" else "R3",
                liquidity="T+1" if category != "stock" else None,
                tags_zh=["标签"],
                tags_en=["Tag"],
                rationale_zh="推荐理由",
                rationale_en="Recommendation rationale",
                as_of_date="2026-04-09",
                detail_route=f"/recommendations/products/{product_id}",
            )
            for product_id in product_ids
        ],
    )


def test_prefetched_repository_prefers_fresh_snapshot_over_static_catalog() -> None:
    cache = CandidatePoolSnapshotCache(SnapshotCache(ttl_seconds=300))
    repository = PrefetchedCandidateRepository(cache=cache)
    cache.put_candidate_pool("fund", _make_snapshot("fund", ["fund-live-001"]))

    products = repository.list_funds(map_user_profile("balanced"))

    assert [product.id for product in products] == ["fund-live-001"]


def test_prefetched_repository_falls_back_to_static_catalog_when_snapshot_missing() -> None:
    repository = PrefetchedCandidateRepository(cache=CandidatePoolSnapshotCache(SnapshotCache(ttl_seconds=300)))

    products = repository.list_stocks(map_user_profile("balanced"))

    assert products
    assert products[0].id == "stock-001"
