from __future__ import annotations

from datetime import date

from financehub_market_api.recommendation.repositories.candidate_repository import CandidateRepository
from financehub_market_api.recommendation.rules.product_catalog import FUNDS, STOCKS, WEALTH_MANAGEMENT
from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile


class StaticCandidateRepository(CandidateRepository):
    def list_funds(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return [_with_catalog_metadata(product) for product in FUNDS]

    def list_wealth_management(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return [_with_catalog_metadata(product) for product in WEALTH_MANAGEMENT]

    def list_stocks(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return [_with_catalog_metadata(product) for product in STOCKS]


def _with_catalog_metadata(product: CandidateProduct) -> CandidateProduct:
    return CandidateProduct(
        id=product.id,
        category=product.category,
        code=product.code,
        liquidity=product.liquidity,
        as_of_date=product.as_of_date or date.today().isoformat(),
        detail_route=product.detail_route or f"/recommendations/products/{product.id}",
        name_zh=product.name_zh,
        name_en=product.name_en,
        risk_level=product.risk_level,
        tags_zh=list(product.tags_zh),
        tags_en=list(product.tags_en),
        rationale_zh=product.rationale_zh,
        rationale_en=product.rationale_en,
    )
