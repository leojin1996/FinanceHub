from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query

from .cache import build_snapshot_cache
from .chat.router import chat_router
from .models import (
    IndicesResponse,
    MarketOverviewResponse,
    RecommendationGenerationRequest,
    RecommendationProductDetailResponse,
    RecommendationRequest,
    RecommendationResponse,
    StocksResponse,
)
from .recommendation.graph.runtime import RecommendationGraphRuntime
from .recommendation.services import ProductDetailService
from .recommendations import RecommendationService
from .service import DataUnavailableError, MarketDataService
from .upstreams.dolthub import DoltHubClient
from .upstreams.index_data import IndexDataClient

app = FastAPI(title="FinanceHub Market API")

app.include_router(chat_router)


@lru_cache(maxsize=1)
def get_market_data_service() -> MarketDataService:
    return MarketDataService(
        stock_client=DoltHubClient(),
        index_client=IndexDataClient(),
        cache=build_snapshot_cache(),
    )


@lru_cache(maxsize=1)
def get_recommendation_service() -> RecommendationService:
    return RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_default_services(
            use_ai_agents=True
        )
    )


@lru_cache(maxsize=1)
def get_product_detail_service() -> ProductDetailService:
    return ProductDetailService.with_default_cache()


def _normalize_recommendation_payload(
    payload: RecommendationRequest | RecommendationGenerationRequest,
) -> RecommendationGenerationRequest:
    if isinstance(payload, RecommendationGenerationRequest):
        return payload

    return RecommendationGenerationRequest.model_validate(
        {
            "historicalHoldings": [],
            "historicalTransactions": [],
            "includeAggressiveOption": True,
            "questionnaireAnswers": [],
            "riskAssessmentResult": {
                "baseProfile": payload.riskProfile,
                "dimensionLevels": {
                    "capitalStability": "medium",
                    "investmentExperience": "medium",
                    "investmentHorizon": "medium",
                    "returnObjective": "medium",
                    "riskTolerance": "medium",
                },
                "dimensionScores": {
                    "capitalStability": 12,
                    "investmentExperience": 12,
                    "investmentHorizon": 12,
                    "returnObjective": 12,
                    "riskTolerance": 12,
                },
                "finalProfile": payload.riskProfile,
                "totalScore": 60,
            },
        }
    )


@app.get("/api/market-overview", response_model=MarketOverviewResponse)
def get_market_overview(
    service: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> MarketOverviewResponse:
    try:
        return service.get_market_overview()
    except DataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/indices", response_model=IndicesResponse)
def get_indices(
    service: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> IndicesResponse:
    try:
        return service.get_indices()
    except DataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/stocks", response_model=StocksResponse)
def get_stocks(
    service: Annotated[MarketDataService, Depends(get_market_data_service)],
    query: str | None = Query(default=None),
) -> StocksResponse:
    try:
        return service.get_stocks(query=query)
    except DataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/recommendations/generate", response_model=RecommendationResponse)
def generate_recommendations(
    payload: RecommendationGenerationRequest,
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> RecommendationResponse:
    return service.generate_recommendation(payload)


@app.post("/api/recommendations", response_model=RecommendationResponse)
def get_recommendations(
    payload: RecommendationRequest | RecommendationGenerationRequest,
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> RecommendationResponse:
    if isinstance(payload, RecommendationRequest):
        return service.get_recommendation(payload.riskProfile)
    return service.generate_recommendation(_normalize_recommendation_payload(payload))


@app.get(
    "/api/recommendations/products/{product_id}",
    response_model=RecommendationProductDetailResponse,
)
def get_recommendation_product_detail(
    product_id: str,
    background_tasks: BackgroundTasks,
    service: Annotated[ProductDetailService, Depends(get_product_detail_service)],
) -> RecommendationProductDetailResponse:
    detail = service.get_product_detail(product_id)
    if detail is None:
        raise HTTPException(
            status_code=404, detail=f"recommendation product {product_id} not found"
        )
    if detail.stale:
        background_tasks.add_task(service.refresh_product_detail, product_id)
    return detail
