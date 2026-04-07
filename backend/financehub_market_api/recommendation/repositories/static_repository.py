from __future__ import annotations

from financehub_market_api.recommendation.repositories.candidate_repository import CandidateRepository
from financehub_market_api.recommendation.rules.product_catalog import FUNDS, STOCKS, WEALTH_MANAGEMENT
from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile


class StaticCandidateRepository(CandidateRepository):
    def list_funds(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return list(FUNDS)

    def list_wealth_management(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return list(WEALTH_MANAGEMENT)

    def list_stocks(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return list(STOCKS)
