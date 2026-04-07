from __future__ import annotations

from typing import Protocol

from financehub_market_api.recommendation.schemas import CandidateProduct, UserProfile


class CandidateRepository(Protocol):
    def list_funds(self, user_profile: UserProfile) -> list[CandidateProduct]:
        ...

    def list_wealth_management(self, user_profile: UserProfile) -> list[CandidateProduct]:
        ...

    def list_stocks(self, user_profile: UserProfile) -> list[CandidateProduct]:
        ...
