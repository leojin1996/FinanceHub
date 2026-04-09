from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from financehub_market_api.models import (
    IndexCard,
    IndicesResponse,
    MarketOverviewResponse,
    MetricCard,
    OverviewStockSummary,
    RecommendationGenerationRequest,
    RecommendationResponse,
    StockRow,
    StocksResponse,
    TrendPoint,
)
from financehub_market_api.service import DataUnavailableError


class FakeMarketDataService:
    def __init__(
        self,
        *,
        overview: MarketOverviewResponse | None = None,
        indices: IndicesResponse | None = None,
        stocks: StocksResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self._overview = overview
        self._indices = indices
        self._stocks = stocks
        self._error = error
        self.last_query: str | None = None

    def get_market_overview(self) -> MarketOverviewResponse:
        if self._error is not None:
            raise self._error
        if self._overview is None:
            raise AssertionError("overview payload must be provided")
        return self._overview

    def get_indices(self) -> IndicesResponse:
        if self._error is not None:
            raise self._error
        if self._indices is None:
            raise AssertionError("indices payload must be provided")
        return self._indices

    def get_stocks(self, query: str | None = None) -> StocksResponse:
        self.last_query = query
        if self._error is not None:
            raise self._error
        if self._stocks is None:
            raise AssertionError("stocks payload must be provided")
        return self._stocks


class FakeRecommendationService:
    def __init__(self, response: RecommendationResponse) -> None:
        self._response = response
        self.last_generation_request: RecommendationGenerationRequest | None = None
        self.last_risk_profile: str | None = None

    def generate_recommendation(
        self, payload: RecommendationGenerationRequest
    ) -> RecommendationResponse:
        self.last_generation_request = payload
        return self._response

    def get_recommendation(self, risk_profile: str) -> RecommendationResponse:
        self.last_risk_profile = risk_profile
        return self._response


def _build_overview() -> MarketOverviewResponse:
    return MarketOverviewResponse(
        asOfDate="2026-04-01",
        stale=False,
        metrics=[
            MetricCard(
                label="上证指数",
                value="3,245.50",
                delta="+0.2%",
                tone="positive",
                changeValue=7.3,
                changePercent=0.2254,
            )
        ],
        chartLabel="上证指数",
        trendSeries=[TrendPoint(date="2026-04-01", value=3245.5)],
        topGainers=[
            OverviewStockSummary(
                code="300750",
                name="宁德时代",
                price="188.55",
                priceValue=188.55,
                change="+11.01",
                changePercent=6.2,
            )
        ],
        topLosers=[
            OverviewStockSummary(
                code="600519",
                name="贵州茅台",
                price="1,608.00",
                priceValue=1608.0,
                change="-10.00",
                changePercent=-0.618,
            )
        ],
    )


def _build_indices() -> IndicesResponse:
    return IndicesResponse(
        asOfDate="2026-04-01",
        stale=False,
        cards=[
            IndexCard(
                name="上证指数",
                code="000001.SH",
                market="中国市场",
                description="沪市核心宽基指数",
                value="3,245.50",
                valueNumber=3245.5,
                changeValue=7.3,
                changePercent=0.2254,
                tone="positive",
                trendSeries=[
                    TrendPoint(date="2026-03-28", value=3226.4),
                    TrendPoint(date="2026-03-31", value=3238.2),
                    TrendPoint(date="2026-04-01", value=3245.5),
                ],
            ),
            IndexCard(
                name="深证成指",
                code="399001.SZ",
                market="中国市场",
                description="深市代表性综合指数",
                value="10,422.90",
                valueNumber=10422.9,
                changeValue=111.7,
                changePercent=1.0833,
                tone="positive",
                trendSeries=[
                    TrendPoint(date="2026-03-28", value=10220.4),
                    TrendPoint(date="2026-03-31", value=10311.2),
                    TrendPoint(date="2026-04-01", value=10422.9),
                ],
            ),
            IndexCard(
                name="创业板指",
                code="399006.SZ",
                market="中国市场",
                description="成长风格代表指数",
                value="2,094.40",
                valueNumber=2094.4,
                changeValue=-3.6,
                changePercent=-0.1716,
                tone="negative",
                trendSeries=[
                    TrendPoint(date="2026-03-28", value=2085.2),
                    TrendPoint(date="2026-03-31", value=2098.0),
                    TrendPoint(date="2026-04-01", value=2094.4),
                ],
            ),
            IndexCard(
                name="科创50",
                code="000688.SH",
                market="中国市场",
                description="科创板核心龙头指数",
                value="1,002.60",
                valueNumber=1002.6,
                changeValue=7.5,
                changePercent=0.7537,
                tone="positive",
                trendSeries=[
                    TrendPoint(date="2026-03-28", value=986.4),
                    TrendPoint(date="2026-03-31", value=995.1),
                    TrendPoint(date="2026-04-01", value=1002.6),
                ],
            ),
        ],
    )


def _build_stocks() -> StocksResponse:
    return StocksResponse(
        asOfDate="2026-04-01",
        stale=False,
        rows=[
            StockRow(
                code="300750",
                name="宁德时代",
                sector="新能源",
                price="188.55",
                change="+6.2%",
                priceValue=188.55,
                changePercent=6.2,
                volumeValue=123456789.0,
                amountValue=2345678901.0,
                trend7d=[
                    TrendPoint(date="2026-03-24", value=176.0),
                    TrendPoint(date="2026-03-25", value=177.1),
                    TrendPoint(date="2026-03-26", value=178.4),
                    TrendPoint(date="2026-03-27", value=179.0),
                    TrendPoint(date="2026-03-28", value=180.5),
                    TrendPoint(date="2026-03-31", value=182.0),
                    TrendPoint(date="2026-04-01", value=188.55),
                ],
            )
        ],
    )


def _build_recommendation_response() -> RecommendationResponse:
    from financehub_market_api.recommendations import RecommendationService
    from financehub_market_api.recommendation.graph.runtime import RecommendationGraphRuntime
    from financehub_market_api.recommendation.repositories import StaticCandidateRepository

    return RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_default_services(
            repository=StaticCandidateRepository()
        )
    ).get_recommendation("balanced")


def _install_override(
    service: FakeMarketDataService,
    recommendation_service: FakeRecommendationService | None = None,
) -> tuple[TestClient, Callable[[], None]]:
    from financehub_market_api.main import (
        app,
        get_market_data_service,
        get_recommendation_service,
    )

    app.dependency_overrides[get_market_data_service] = lambda: service
    if recommendation_service is not None:
        app.dependency_overrides[get_recommendation_service] = lambda: recommendation_service
    client = TestClient(app)

    def _clear() -> None:
        app.dependency_overrides.clear()

    return client, _clear


def test_get_market_overview_returns_service_payload() -> None:
    service = FakeMarketDataService(overview=_build_overview())
    client, clear = _install_override(service)
    try:
        response = client.get("/api/market-overview")
    finally:
        clear()

    assert response.status_code == 200
    assert response.json()["asOfDate"] == "2026-04-01"
    assert response.json()["metrics"][0]["label"] == "上证指数"
    assert response.json()["metrics"][0]["changeValue"] == 7.3
    assert response.json()["metrics"][0]["changePercent"] == 0.2254
    assert response.json()["chartLabel"] == "上证指数"
    assert response.json()["topGainers"][0]["code"] == "300750"
    assert response.json()["topGainers"][0]["priceValue"] == 188.55
    assert response.json()["topGainers"][0]["change"] == "+11.01"
    assert response.json()["topLosers"][0]["code"] == "600519"
    assert response.json()["topLosers"][0]["change"] == "-10.00"


def test_get_indices_returns_service_payload() -> None:
    service = FakeMarketDataService(indices=_build_indices())
    client, clear = _install_override(service)
    try:
        response = client.get("/api/indices")
    finally:
        clear()

    assert response.status_code == 200
    payload = response.json()
    assert [card["name"] for card in payload["cards"]] == [
        "上证指数",
        "深证成指",
        "创业板指",
        "科创50",
    ]
    first_card = payload["cards"][0]
    assert first_card["code"] == "000001.SH"
    assert first_card["market"] == "中国市场"
    assert first_card["description"] == "沪市核心宽基指数"
    assert first_card["value"] == "3,245.50"
    assert first_card["valueNumber"] == pytest.approx(3245.5)
    assert first_card["changeValue"] == pytest.approx(7.3)
    assert first_card["changePercent"] == pytest.approx(0.2254, abs=1e-4)
    assert first_card["tone"] == "positive"
    assert first_card["trendSeries"][-1]["date"] == "2026-04-01"
    assert payload["cards"][3]["code"] == "000688.SH"
    assert payload["cards"][3]["description"] == "科创板核心龙头指数"
    assert payload["cards"][3]["trendSeries"][-1]["date"] == "2026-04-01"


def test_get_stocks_passes_query_and_returns_payload() -> None:
    service = FakeMarketDataService(stocks=_build_stocks())
    client, clear = _install_override(service)
    try:
        response = client.get("/api/stocks", params={"query": "宁德"})
    finally:
        clear()

    assert response.status_code == 200
    assert service.last_query == "宁德"
    payload = response.json()
    row = payload["rows"][0]
    assert row["code"] == "300750"
    assert row["priceValue"] == 188.55
    assert row["changePercent"] == 6.2
    assert row["volumeValue"] == 123456789.0
    assert row["amountValue"] == 2345678901.0
    assert len(row["trend7d"]) == 7


def test_post_recommendations_passes_risk_profile_and_returns_payload() -> None:
    recommendation_service = FakeRecommendationService(_build_recommendation_response())
    client, clear = _install_override(
        FakeMarketDataService(overview=_build_overview()),
        recommendation_service,
    )
    try:
        response = client.post(
            "/api/recommendations/generate",
            json={
                "historicalHoldings": [],
                "historicalTransactions": [],
                "includeAggressiveOption": True,
                "questionnaireAnswers": [],
                "riskAssessmentResult": {
                    "baseProfile": "stable",
                    "dimensionLevels": {
                        "capitalStability": "medium",
                        "investmentExperience": "medium",
                        "investmentHorizon": "mediumHigh",
                        "returnObjective": "medium",
                        "riskTolerance": "medium",
                    },
                    "dimensionScores": {
                        "capitalStability": 12,
                        "investmentExperience": 11,
                        "investmentHorizon": 14,
                        "returnObjective": 13,
                        "riskTolerance": 12,
                    },
                    "finalProfile": "balanced",
                    "totalScore": 62,
                },
            },
        )
    finally:
        clear()

    assert response.status_code == 200
    assert recommendation_service.last_generation_request is not None
    assert recommendation_service.last_generation_request.riskAssessmentResult.finalProfile == "balanced"
    assert recommendation_service.last_generation_request.includeAggressiveOption is True
    assert response.json()["allocationDisplay"] == {
        "fund": 45,
        "wealthManagement": 35,
        "stock": 20,
    }
    assert response.json()["sections"]["funds"]["titleZh"] == "基金推荐"
    assert response.json()["profileSummary"]["zh"].startswith("用户风险等级")
    assert response.json()["marketSummary"]["en"]
    assert response.json()["executionMode"] == "agent_assisted"
    assert isinstance(response.json()["warnings"], list)


def test_generate_recommendations_accepts_extended_request_payload() -> None:
    recommendation_service = FakeRecommendationService(_build_recommendation_response())
    client, clear = _install_override(
        FakeMarketDataService(overview=_build_overview()),
        recommendation_service,
    )
    try:
        response = client.post(
            "/api/recommendations/generate",
            json={
                "userIntentText": "稳健理财",
                "conversationMessages": [
                    {
                        "role": "user",
                        "content": "稳健理财",
                        "occurredAt": "2026-04-08T10:00:00Z",
                    }
                ],
                "clientContext": {"channel": "web", "locale": "zh-CN"},
                "historicalHoldings": [],
                "historicalTransactions": [],
                "includeAggressiveOption": True,
                "questionnaireAnswers": [],
                "riskAssessmentResult": {
                    "baseProfile": "stable",
                    "dimensionLevels": {
                        "capitalStability": "medium",
                        "investmentExperience": "medium",
                        "investmentHorizon": "mediumHigh",
                        "returnObjective": "medium",
                        "riskTolerance": "medium",
                    },
                    "dimensionScores": {
                        "capitalStability": 12,
                        "investmentExperience": 11,
                        "investmentHorizon": 14,
                        "returnObjective": 13,
                        "riskTolerance": 12,
                    },
                    "finalProfile": "balanced",
                    "totalScore": 62,
                },
            },
        )
    finally:
        clear()

    assert response.status_code == 200
    assert recommendation_service.last_generation_request is not None
    assert recommendation_service.last_generation_request.userIntentText == "稳健理财"


def test_post_recommendations_alias_accepts_legacy_payload() -> None:
    recommendation_service = FakeRecommendationService(_build_recommendation_response())
    client, clear = _install_override(
        FakeMarketDataService(overview=_build_overview()),
        recommendation_service,
    )
    try:
        response = client.post("/api/recommendations", json={"riskProfile": "balanced"})
    finally:
        clear()

    assert response.status_code == 200
    assert recommendation_service.last_risk_profile == "balanced"
    assert response.json()["allocationDisplay"] == {
        "fund": 45,
        "wealthManagement": 35,
        "stock": 20,
    }


def test_post_recommendations_alias_accepts_new_payload() -> None:
    recommendation_service = FakeRecommendationService(_build_recommendation_response())
    client, clear = _install_override(
        FakeMarketDataService(overview=_build_overview()),
        recommendation_service,
    )
    try:
        response = client.post(
            "/api/recommendations",
            json={
                "historicalHoldings": [],
                "historicalTransactions": [],
                "includeAggressiveOption": False,
                "questionnaireAnswers": [],
                "riskAssessmentResult": {
                    "baseProfile": "stable",
                    "dimensionLevels": {
                        "capitalStability": "medium",
                        "investmentExperience": "medium",
                        "investmentHorizon": "mediumHigh",
                        "returnObjective": "medium",
                        "riskTolerance": "medium",
                    },
                    "dimensionScores": {
                        "capitalStability": 12,
                        "investmentExperience": 11,
                        "investmentHorizon": 14,
                        "returnObjective": 13,
                        "riskTolerance": 12,
                    },
                    "finalProfile": "balanced",
                    "totalScore": 62,
                },
            },
        )
    finally:
        clear()

    assert response.status_code == 200
    assert recommendation_service.last_generation_request is not None
    assert recommendation_service.last_generation_request.includeAggressiveOption is False
    assert recommendation_service.last_generation_request.riskAssessmentResult.finalProfile == "balanced"


@pytest.mark.parametrize(
    "path",
    ["/api/market-overview", "/api/indices", "/api/stocks"],
)
def test_data_unavailable_error_is_translated_to_http_503(path: str) -> None:
    service = FakeMarketDataService(error=DataUnavailableError("upstream unavailable"))
    client, clear = _install_override(service)
    try:
        response = client.get(path)
    finally:
        clear()

    assert response.status_code == 503
    body: dict[str, Any] = response.json()
    assert body == {"detail": "upstream unavailable"}


def test_default_recommendation_dependency_uses_graph_runtime_backed_service() -> None:
    from financehub_market_api.main import get_recommendation_service

    get_recommendation_service.cache_clear()
    service = get_recommendation_service()

    assert getattr(service, "_orchestrator", None) is None
    assert getattr(service, "_graph_runtime", None) is not None


def test_generate_recommendations_raises_when_graph_runtime_fails() -> None:
    from financehub_market_api.recommendations import RecommendationService

    class _FailingGraphRuntime:
        def run(self, payload: object) -> object:
            del payload
            raise RuntimeError("graph runtime crashed")

    recommendation_service = RecommendationService(graph_runtime=_FailingGraphRuntime())
    client, clear = _install_override(
        FakeMarketDataService(overview=_build_overview()),
        recommendation_service,
    )
    try:
        with pytest.raises(RuntimeError, match="graph runtime crashed"):
            client.post(
                "/api/recommendations/generate",
                json={
                    "historicalHoldings": [],
                    "historicalTransactions": [],
                    "includeAggressiveOption": True,
                    "questionnaireAnswers": [],
                    "riskAssessmentResult": {
                        "baseProfile": "stable",
                        "dimensionLevels": {
                            "capitalStability": "medium",
                            "investmentExperience": "medium",
                            "investmentHorizon": "mediumHigh",
                            "returnObjective": "medium",
                            "riskTolerance": "medium",
                        },
                        "dimensionScores": {
                            "capitalStability": 12,
                            "investmentExperience": 11,
                            "investmentHorizon": 14,
                            "returnObjective": 13,
                            "riskTolerance": 12,
                        },
                        "finalProfile": "balanced",
                        "totalScore": 62,
                    },
                },
            )
    finally:
        clear()
