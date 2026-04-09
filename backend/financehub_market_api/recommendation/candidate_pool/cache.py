from __future__ import annotations

from financehub_market_api.cache import SnapshotCache
from financehub_market_api.recommendation.candidate_pool.schemas import (
    CandidatePoolSnapshot,
    ProductDetailSnapshot,
)


class CandidatePoolSnapshotCache:
    def __init__(self, cache: SnapshotCache) -> None:
        self._cache = cache

    def get_candidate_pool(self, category: str) -> CandidatePoolSnapshot | None:
        payload = self._cache.get(self._candidate_pool_key(category))
        if payload is None:
            return None
        return CandidatePoolSnapshot.model_validate(payload)

    def peek_candidate_pool(self, category: str) -> CandidatePoolSnapshot | None:
        payload = self._cache.peek(self._candidate_pool_key(category))
        if payload is None:
            return None
        return CandidatePoolSnapshot.model_validate(payload)

    def put_candidate_pool(self, category: str, snapshot: CandidatePoolSnapshot) -> None:
        self._cache.put(self._candidate_pool_key(category), snapshot.model_dump(mode="json"))

    @staticmethod
    def _candidate_pool_key(category: str) -> str:
        return f"recommendation:candidate-pool:{category}"


class ProductDetailSnapshotCache:
    def __init__(self, cache: SnapshotCache) -> None:
        self._cache = cache

    def get_product_detail(self, product_id: str) -> ProductDetailSnapshot | None:
        payload = self._cache.get(self._detail_key(product_id))
        if payload is None:
            return None
        return ProductDetailSnapshot.model_validate(payload)

    def peek_product_detail(self, product_id: str) -> ProductDetailSnapshot | None:
        payload = self._cache.peek(self._detail_key(product_id))
        if payload is None:
            return None
        return ProductDetailSnapshot.model_validate(payload)

    def put_product_detail(self, product_id: str, snapshot: ProductDetailSnapshot) -> None:
        self._cache.put(self._detail_key(product_id), snapshot.model_dump(mode="json"))

    def put_many(self, snapshots: list[ProductDetailSnapshot]) -> None:
        for snapshot in snapshots:
            self.put_product_detail(snapshot.id, snapshot)

    @staticmethod
    def _detail_key(product_id: str) -> str:
        return f"recommendation:product-detail:{product_id}"
