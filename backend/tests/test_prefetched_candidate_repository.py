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


def test_prefetched_repository_prioritizes_equity_funds_for_aggressive_profiles() -> None:
    cache = CandidatePoolSnapshotCache(SnapshotCache(ttl_seconds=300))
    repository = PrefetchedCandidateRepository(cache=cache)
    cache.put_candidate_pool(
        "fund",
        CandidatePoolSnapshot(
            category="fund",
            generated_at="2026-04-09T12:00:00+00:00",
            fresh_until="2026-04-09T12:10:00+00:00",
            source="unit-test",
            fallback_used=False,
            warnings=[],
            stale=False,
            items=[
                CandidatePoolItem(
                    id="fund-bond-000001",
                    category="fund",
                    code="000001",
                    name_zh="稳健债券A",
                    name_en="Stable Bond A",
                    risk_level="R2",
                    liquidity="T+1",
                    tags_zh=["债券型公募", "稳健底仓"],
                    tags_en=["Public bond fund", "Stable core"],
                    rationale_zh="债券基金候选",
                    rationale_en="Bond fund candidate",
                    as_of_date="2026-04-09",
                    detail_route="/recommendations/products/fund-bond-000001",
                ),
                CandidatePoolItem(
                    id="fund-equity-161725",
                    category="fund",
                    code="161725",
                    name_zh="招商中证白酒指数A",
                    name_en="ChinaAMC Equity Fund",
                    risk_level="R4",
                    liquidity="T+1",
                    tags_zh=["股票型公募", "成长弹性"],
                    tags_en=["Public equity fund", "Growth-oriented"],
                    rationale_zh="股票型基金候选",
                    rationale_en="Equity fund candidate",
                    as_of_date="2026-04-09",
                    detail_route="/recommendations/products/fund-equity-161725",
                ),
            ],
        ),
    )

    products = repository.list_funds(map_user_profile("aggressive"))

    assert [product.id for product in products] == [
        "fund-equity-161725",
        "fund-bond-000001",
    ]
