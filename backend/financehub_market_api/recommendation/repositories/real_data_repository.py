from __future__ import annotations

from financehub_market_api.recommendation.repositories.candidate_repository import CandidateRepository
from financehub_market_api.recommendation.repositories.real_data_adapters import (
    BondFundCandidateAdapter,
    MoneyFundWealthProxyAdapter,
)
from financehub_market_api.recommendation.repositories.static_repository import StaticCandidateRepository
from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile


class RealDataCandidateRepository(CandidateRepository):
    def __init__(
        self,
        *,
        fund_adapter: BondFundCandidateAdapter | None = None,
        wealth_adapter: MoneyFundWealthProxyAdapter | None = None,
        fallback_repository: CandidateRepository | None = None,
    ) -> None:
        self._fund_adapter = fund_adapter or BondFundCandidateAdapter()
        self._wealth_adapter = wealth_adapter or MoneyFundWealthProxyAdapter()
        self._fallback_repository = fallback_repository or StaticCandidateRepository()

    def list_funds(self, user_profile: UserProfile) -> list[CandidateProduct]:
        try:
            candidates = self._fund_adapter.list_candidates(user_profile)
        except Exception:
            return self._fallback_repository.list_funds(user_profile)
        if not candidates:
            return self._fallback_repository.list_funds(user_profile)
        return candidates

    def list_wealth_management(self, user_profile: UserProfile) -> list[CandidateProduct]:
        try:
            candidates = self._wealth_adapter.list_candidates(user_profile)
        except Exception:
            return self._fallback_repository.list_wealth_management(user_profile)
        if not candidates:
            return self._fallback_repository.list_wealth_management(user_profile)
        return candidates

    def list_stocks(self, user_profile: UserProfile) -> list[CandidateProduct]:
        return self._fallback_repository.list_stocks(user_profile)
