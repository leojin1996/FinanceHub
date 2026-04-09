from __future__ import annotations

from financehub_market_api.cache import SnapshotCache, build_snapshot_cache
from financehub_market_api.recommendation.candidate_pool.cache import CandidatePoolSnapshotCache
from financehub_market_api.recommendation.repositories.candidate_repository import CandidateRepository
from financehub_market_api.recommendation.repositories.static_repository import StaticCandidateRepository
from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile


class PrefetchedCandidateRepository(CandidateRepository):
    def __init__(
        self,
        *,
        cache: CandidatePoolSnapshotCache,
        fallback_repository: CandidateRepository | None = None,
    ) -> None:
        self._cache = cache
        self._fallback_repository = fallback_repository or StaticCandidateRepository()

    @classmethod
    def with_default_cache(
        cls,
        *,
        snapshot_cache: SnapshotCache | None = None,
        fallback_repository: CandidateRepository | None = None,
    ) -> "PrefetchedCandidateRepository":
        cache = snapshot_cache or build_snapshot_cache()
        return cls(
            cache=CandidatePoolSnapshotCache(cache),
            fallback_repository=fallback_repository,
        )

    def list_funds(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return self._list_category("fund", user_profile)

    def list_wealth_management(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return self._list_category("wealth_management", user_profile)

    def list_stocks(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return self._list_category("stock", user_profile)

    def _list_category(
        self,
        category: str,
        user_profile: UserProfile,
    ) -> list[CandidateProduct]:
        fresh_snapshot = self._cache.get_candidate_pool(category)
        if fresh_snapshot is not None and fresh_snapshot.items:
            return [item.to_candidate_product() for item in fresh_snapshot.items]

        stale_snapshot = self._cache.peek_candidate_pool(category)
        if stale_snapshot is not None and stale_snapshot.items:
            return [item.to_candidate_product() for item in stale_snapshot.items]

        return self._fallback_list(category, user_profile)

    def _fallback_list(
        self,
        category: str,
        user_profile: UserProfile,
    ) -> list[CandidateProduct]:
        if category == "fund":
            return self._fallback_repository.list_funds(user_profile)
        if category == "wealth_management":
            return self._fallback_repository.list_wealth_management(user_profile)
        return self._fallback_repository.list_stocks(user_profile)
