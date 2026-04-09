from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from financehub_market_api.recommendation.candidate_pool.cache import (
    CandidatePoolSnapshotCache,
    ProductDetailSnapshotCache,
)
from financehub_market_api.recommendation.candidate_pool.schemas import (
    CandidatePoolSnapshot,
    ProductDetailSnapshot,
)
from financehub_market_api.recommendation.repositories.real_data_adapters import (
    BondFundDetailAdapter,
    MoneyFundWealthProxyDetailAdapter,
    PremiumStockDetailAdapter,
    PublicWealthManagementDetailAdapter,
)


class ProductDetailProvider(Protocol):
    def list_product_details(self) -> list[ProductDetailSnapshot]:
        ...


@dataclass(frozen=True)
class RefreshResult:
    status: str
    item_count: int
    error_message: str | None = None


def build_candidate_pool_snapshot(
    category: str,
    product_details: list[ProductDetailSnapshot],
) -> CandidatePoolSnapshot:
    if not product_details:
        raise ValueError(f"{category} provider returned no product details")

    first = product_details[0]
    return CandidatePoolSnapshot(
        category=first.category,
        generated_at=first.generated_at,
        fresh_until=first.fresh_until,
        source=first.source,
        fallback_used=False,
        warnings=[],
        stale=False,
        items=[detail.to_candidate_pool_item() for detail in product_details],
    )


class RecommendationCandidatePoolRefresher:
    def __init__(
        self,
        *,
        candidate_pool_cache: CandidatePoolSnapshotCache,
        product_detail_cache: ProductDetailSnapshotCache,
        fund_provider: ProductDetailProvider,
        wealth_provider: ProductDetailProvider,
        stock_provider: ProductDetailProvider,
    ) -> None:
        self._candidate_pool_cache = candidate_pool_cache
        self._product_detail_cache = product_detail_cache
        self._fund_provider = fund_provider
        self._wealth_provider = wealth_provider
        self._stock_provider = stock_provider

    def refresh_all(self) -> dict[str, RefreshResult]:
        return {
            "fund": self.refresh_category("fund"),
            "wealth_management": self.refresh_category("wealth_management"),
            "stock": self.refresh_category("stock"),
        }

    def refresh_category(self, category: str) -> RefreshResult:
        if category == "fund":
            return self._refresh_category("fund", self._fund_provider)
        if category == "wealth_management":
            return self._refresh_category("wealth_management", self._wealth_provider)
        if category == "stock":
            return self._refresh_category("stock", self._stock_provider)
        raise ValueError(f"unsupported recommendation category: {category}")

    @classmethod
    def with_default_providers(
        cls,
        *,
        candidate_pool_cache: CandidatePoolSnapshotCache,
        product_detail_cache: ProductDetailSnapshotCache,
    ) -> "RecommendationCandidatePoolRefresher":
        wealth_provider = _FallbackWealthManagementProvider(
            primary=PublicWealthManagementDetailAdapter(),
            fallback=MoneyFundWealthProxyDetailAdapter(),
        )
        return cls(
            candidate_pool_cache=candidate_pool_cache,
            product_detail_cache=product_detail_cache,
            fund_provider=BondFundDetailAdapter(),
            wealth_provider=wealth_provider,
            stock_provider=PremiumStockDetailAdapter(),
        )

    def _refresh_category(
        self,
        category: str,
        provider: ProductDetailProvider,
    ) -> RefreshResult:
        try:
            product_details = provider.list_product_details()
            snapshot = build_candidate_pool_snapshot(category, product_details)
        except Exception as exc:  # noqa: BLE001
            previous = self._candidate_pool_cache.peek_candidate_pool(category)
            previous_count = 0 if previous is None else len(previous.items)
            return RefreshResult(
                status="error",
                item_count=previous_count,
                error_message=str(exc),
            )

        self._candidate_pool_cache.put_candidate_pool(category, snapshot)
        self._product_detail_cache.put_many(product_details)
        return RefreshResult(status="fresh", item_count=len(snapshot.items))


class _FallbackWealthManagementProvider:
    def __init__(
        self,
        *,
        primary: ProductDetailProvider,
        fallback: ProductDetailProvider,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def list_product_details(self) -> list[ProductDetailSnapshot]:
        primary_details = self._primary.list_product_details()
        if primary_details:
            return primary_details
        return self._fallback.list_product_details()
