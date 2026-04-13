from financehub_market_api.recommendation.candidate_pool.cache import ProductDetailSnapshotCache
from financehub_market_api.recommendation.services.product_detail_service import ProductDetailService


class _FakeRefresher:
    def __init__(self) -> None:
        self.categories: list[str] = []

    def refresh_category(self, category: str) -> None:
        self.categories.append(category)


def test_product_detail_service_refreshes_matching_category_for_product_id() -> None:
    refresher = _FakeRefresher()
    service = ProductDetailService(
        cache=ProductDetailSnapshotCache.__new__(ProductDetailSnapshotCache),
        refresher=refresher,
    )

    service.refresh_product_detail("fund-001")

    assert refresher.categories == ["fund"]
