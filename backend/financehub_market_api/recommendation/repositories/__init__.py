from financehub_market_api.recommendation.repositories.candidate_repository import CandidateRepository
from financehub_market_api.recommendation.repositories.prefetched_candidate_repository import (
    PrefetchedCandidateRepository,
)
from financehub_market_api.recommendation.repositories.real_data_repository import RealDataCandidateRepository
from financehub_market_api.recommendation.repositories.static_repository import StaticCandidateRepository

__all__ = [
    "CandidateRepository",
    "PrefetchedCandidateRepository",
    "RealDataCandidateRepository",
    "StaticCandidateRepository",
]
