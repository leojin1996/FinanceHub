"""Recommendation domain package.

Avoid eager imports here: ``chat.recall_service`` loads
``recommendation.product_knowledge.embedding_client``; importing ``RecommendationService`` at
package import time would pull ``graph.runtime`` and create a circular import.
"""

from __future__ import annotations

__all__ = ["RecommendationService"]


def __getattr__(name: str):
    if name == "RecommendationService":
        from financehub_market_api.recommendation.services.recommendation_service import (
            RecommendationService,
        )

        return RecommendationService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
