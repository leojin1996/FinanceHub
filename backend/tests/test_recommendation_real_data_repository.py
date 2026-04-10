from __future__ import annotations

import threading
import time
from dataclasses import replace

from financehub_market_api.recommendation.repositories.real_data_adapters import (
    BondFundDetailAdapter,
    BondFundCandidateAdapter,
    MoneyFundWealthProxyDetailAdapter,
    MoneyFundWealthProxyAdapter,
    PremiumStockDetailAdapter,
)
from financehub_market_api.recommendation.repositories.real_data_repository import (
    RealDataCandidateRepository,
)
from financehub_market_api.recommendation.graph.runtime import (
    RecommendationGraphRuntime,
)
from financehub_market_api.recommendation.rules import map_user_profile
from financehub_market_api.recommendation.rules.product_catalog import (
    FUNDS,
    STOCKS,
    WEALTH_MANAGEMENT,
)
from financehub_market_api.recommendation.services import RecommendationService
from financehub_market_api.upstreams.dolthub import StockPriceSnapshot


class FakeFrame:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def iterrows(self):
        for index, row in enumerate(self._rows):
            yield index, row


def _strip_detail_metadata(products):
    return [
        replace(product, as_of_date=None, detail_route=None) for product in products
    ]


def _build_stock_snapshot(symbols: list[str]) -> StockPriceSnapshot:
    latest_prices = {symbol: 10.0 + index for index, symbol in enumerate(symbols)}
    previous_prices = {symbol: 9.5 + index for index, symbol in enumerate(symbols)}
    latest_amounts = {
        symbol: 100_000_000.0 + index for index, symbol in enumerate(symbols)
    }
    recent_closes = {
        symbol: [(f"2026-04-0{day}", 9.0 + index + day * 0.1) for day in range(1, 8)]
        for index, symbol in enumerate(symbols)
    }
    return StockPriceSnapshot(
        as_of_date="2026-04-09",
        latest_prices=latest_prices,
        previous_prices=previous_prices,
        latest_volumes={
            symbol: 1_000_000.0 + index for index, symbol in enumerate(symbols)
        },
        latest_amounts=latest_amounts,
        recent_closes=recent_closes,
    )


def _build_stock_snapshot_with_series(
    series_by_symbol: dict[str, dict[str, object]],
) -> StockPriceSnapshot:
    return StockPriceSnapshot(
        as_of_date="2026-04-09",
        latest_prices={
            symbol: float(payload["latest_price"])
            for symbol, payload in series_by_symbol.items()
        },
        previous_prices={
            symbol: float(payload["previous_price"])
            for symbol, payload in series_by_symbol.items()
        },
        latest_volumes={
            symbol: float(payload.get("latest_volume", 1_000_000.0))
            for symbol, payload in series_by_symbol.items()
        },
        latest_amounts={
            symbol: float(payload.get("latest_amount", 100_000_000.0))
            for symbol, payload in series_by_symbol.items()
        },
        recent_closes={
            symbol: list(payload["recent_closes"])
            for symbol, payload in series_by_symbol.items()
        },
    )


def test_bond_fund_adapter_maps_public_rows_into_candidate_products() -> None:
    adapter = BondFundCandidateAdapter(
        fetcher=lambda: FakeFrame(
            [
                {
                    "基金代码": "000001",
                    "基金简称": "稳健债券A",
                    "日期": "2026-04-02",
                    "单位净值": "1.1234",
                    "手续费": "0.15%",
                }
            ]
        )
    )

    user_profile = map_user_profile("balanced")
    candidates = adapter.list_candidates(user_profile)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == "fund"
    assert candidate.id == "fund-001"
    assert candidate.code == "000001"
    assert candidate.name_zh == "稳健债券A"
    assert candidate.name_en == "稳健债券A"
    assert candidate.risk_level == "R2"


def test_money_fund_proxy_adapter_maps_public_rows_into_candidate_products() -> None:
    adapter = MoneyFundWealthProxyAdapter(
        fetcher=lambda: FakeFrame(
            [
                {
                    "基金代码": "511990",
                    "基金简称": "华宝添益",
                    "日期": "2026-04-02",
                    "年化收益率7日": "1.88%",
                    "手续费": "0.00%",
                }
            ]
        )
    )

    user_profile = map_user_profile("balanced")
    candidates = adapter.list_candidates(user_profile)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == "wealth_management"
    assert candidate.id == "wm-001"
    assert candidate.code == "511990"
    assert candidate.name_zh == "华宝添益"
    assert candidate.name_en == "华宝添益"
    assert candidate.risk_level == "R1"


def test_money_fund_proxy_adapter_accepts_daily_fallback_columns() -> None:
    adapter = MoneyFundWealthProxyAdapter(
        fetcher=lambda: FakeFrame(
            [
                {
                    "基金代码": "001078",
                    "基金简称": "华夏现金宝货币B",
                    "2026-04-08-7日年化%": "1.7500%",
                    "手续费": "0费率",
                    "成立日期": "2013-01-22",
                }
            ]
        )
    )

    user_profile = map_user_profile("balanced")
    candidates = adapter.list_candidates(user_profile)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.category == "wealth_management"
    assert candidate.code == "001078"
    assert candidate.name_zh == "华夏现金宝货币B"


def test_bond_fund_detail_adapter_populates_chart_and_yield_metrics() -> None:
    candidate_adapter = BondFundCandidateAdapter(
        fetcher=lambda: FakeFrame(
            [
                {
                    "基金代码": "000001",
                    "基金简称": "稳健债券A",
                    "日期": "2026-04-02",
                    "单位净值": "1.1234",
                    "手续费": "0.15%",
                }
            ]
        )
    )

    detail_adapter = BondFundDetailAdapter(
        adapter=candidate_adapter,
        trend_fetcher=lambda symbol: (
            FakeFrame(
                [
                    {"日期": "2026-04-01", "累计收益率": "0.12"},
                    {"日期": "2026-04-08", "累计收益率": "1.08"},
                    {"日期": "2026-04-09", "累计收益率": "1.56"},
                ]
            )
            if symbol == "000001"
            else FakeFrame([])
        ),
    )

    details = detail_adapter.list_product_details()

    assert len(details) == 1
    detail = details[0]
    assert detail.chart_label_zh == "近1月累计收益率"
    assert detail.yield_metrics["changePercent"] == "1.56%"
    assert [point.date for point in detail.chart] == [
        "2026-04-01",
        "2026-04-08",
        "2026-04-09",
    ]
    assert detail.chart[-1].value == 1.56


def test_money_fund_detail_adapter_populates_annualized_return_and_chart() -> None:
    candidate_adapter = MoneyFundWealthProxyAdapter(
        fetcher=lambda: FakeFrame(
            [
                {
                    "基金代码": "511990",
                    "基金简称": "华宝添益",
                    "日期": "2026-04-02",
                    "年化收益率7日": "1.88%",
                    "手续费": "0.00%",
                }
            ]
        )
    )

    detail_adapter = MoneyFundWealthProxyDetailAdapter(
        adapter=candidate_adapter,
        history_fetcher=lambda symbol: (
            FakeFrame(
                [
                    {
                        "净值日期": "2026-04-01",
                        "每万份收益": "0.5521",
                        "7日年化收益率": "1.71",
                    },
                    {
                        "净值日期": "2026-04-08",
                        "每万份收益": "0.5578",
                        "7日年化收益率": "1.82",
                    },
                    {
                        "净值日期": "2026-04-09",
                        "每万份收益": "0.5612",
                        "7日年化收益率": "1.88",
                    },
                ]
            )
            if symbol == "511990"
            else FakeFrame([])
        ),
    )

    details = detail_adapter.list_product_details()

    assert len(details) == 1
    detail = details[0]
    assert detail.yield_metrics["annualizedReturn"] == "1.88%"
    assert [point.date for point in detail.chart] == [
        "2026-04-01",
        "2026-04-08",
        "2026-04-09",
    ]
    assert detail.chart[-1].value == 1.88


def test_premium_stock_detail_adapter_batches_large_snapshot_requests() -> None:
    rows = [
        {"代码": f"{600000 + index}", "名称": f"股票{index:03d}"}
        for index in range(120)
    ]
    requested_batch_sizes: list[int] = []

    def fake_price_snapshot_fetcher(symbols: list[str]) -> StockPriceSnapshot:
        requested_batch_sizes.append(len(symbols))
        if len(symbols) > 8:
            raise TimeoutError("oversized stock snapshot batch")
        return _build_stock_snapshot(symbols)

    adapter = PremiumStockDetailAdapter(
        constituent_fetchers=(("CSI300", lambda: FakeFrame(rows)),),
        price_snapshot_fetcher=fake_price_snapshot_fetcher,
        max_universe_size=120,
        max_items=5,
    )

    details = adapter.list_product_details()

    assert len(details) == 5
    assert requested_batch_sizes == [8] * 15
    assert details[0].source == "premium_stock_refresh"


def test_premium_stock_detail_adapter_keeps_broader_default_stock_pool() -> None:
    rows = [
        {"代码": f"{600000 + index}", "名称": f"股票{index:03d}"}
        for index in range(90)
    ]
    adapter = PremiumStockDetailAdapter(
        constituent_fetchers=(("CSI300", lambda: FakeFrame(rows)),),
        price_snapshot_fetcher=_build_stock_snapshot,
        max_universe_size=90,
    )

    details = adapter.list_product_details()

    assert len(details) == 60


def test_premium_stock_detail_adapter_assigns_stock_risk_levels_from_volatility() -> None:
    rows = [
        {"代码": "600001", "名称": "稳健股票"},
        {"代码": "600002", "名称": "均衡股票"},
        {"代码": "600003", "名称": "高波股票"},
    ]

    def fake_price_snapshot_fetcher(symbols: list[str]) -> StockPriceSnapshot:
        assert symbols == ["SH600001", "SH600002", "SH600003"]
        return _build_stock_snapshot_with_series(
            {
                "SH600001": {
                    "latest_price": 10.2,
                    "previous_price": 10.0,
                    "recent_closes": [
                        ("2026-04-01", 9.9),
                        ("2026-04-02", 10.0),
                        ("2026-04-03", 10.1),
                        ("2026-04-04", 10.0),
                        ("2026-04-07", 10.1),
                        ("2026-04-08", 10.2),
                        ("2026-04-09", 10.2),
                    ],
                    "latest_amount": 500_000_000.0,
                },
                "SH600002": {
                    "latest_price": 10.6,
                    "previous_price": 10.1,
                    "recent_closes": [
                        ("2026-04-01", 9.7),
                        ("2026-04-02", 10.0),
                        ("2026-04-03", 10.4),
                        ("2026-04-04", 10.2),
                        ("2026-04-07", 10.5),
                        ("2026-04-08", 10.3),
                        ("2026-04-09", 10.6),
                    ],
                    "latest_amount": 400_000_000.0,
                },
                "SH600003": {
                    "latest_price": 11.8,
                    "previous_price": 10.7,
                    "recent_closes": [
                        ("2026-04-01", 8.6),
                        ("2026-04-02", 9.2),
                        ("2026-04-03", 10.4),
                        ("2026-04-04", 9.8),
                        ("2026-04-07", 11.2),
                        ("2026-04-08", 10.9),
                        ("2026-04-09", 11.8),
                    ],
                    "latest_amount": 300_000_000.0,
                },
            }
        )

    adapter = PremiumStockDetailAdapter(
        constituent_fetchers=(("CSI300", lambda: FakeFrame(rows)),),
        price_snapshot_fetcher=fake_price_snapshot_fetcher,
        max_universe_size=3,
        max_items=3,
        price_snapshot_batch_size=8,
    )

    details = adapter.list_product_details()
    risk_by_code = {detail.code: detail.risk_level for detail in details}

    assert risk_by_code == {
        "600001": "R3",
        "600002": "R4",
        "600003": "R5",
    }


def test_premium_stock_detail_adapter_fetches_batches_concurrently() -> None:
    rows = [
        {"代码": f"{600000 + index}", "名称": f"股票{index:03d}"}
        for index in range(24)
    ]
    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0

    def fake_price_snapshot_fetcher(symbols: list[str]) -> StockPriceSnapshot:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        try:
            time.sleep(0.05)
            return _build_stock_snapshot(symbols)
        finally:
            with lock:
                in_flight -= 1

    adapter = PremiumStockDetailAdapter(
        constituent_fetchers=(("CSI300", lambda: FakeFrame(rows)),),
        price_snapshot_fetcher=fake_price_snapshot_fetcher,
        max_universe_size=24,
        max_items=5,
    )

    details = adapter.list_product_details()

    assert len(details) == 5
    assert max_in_flight >= 2


def test_real_repository_falls_back_to_static_funds_on_adapter_failure() -> None:
    repository = RealDataCandidateRepository(
        fund_adapter=BondFundCandidateAdapter(
            fetcher=lambda: (_ for _ in ()).throw(RuntimeError("fund upstream down"))
        )
    )

    user_profile = map_user_profile("balanced")
    candidates = repository.list_funds(user_profile)

    assert _strip_detail_metadata(candidates) == FUNDS
    assert all(candidate.as_of_date for candidate in candidates)
    assert all(candidate.detail_route for candidate in candidates)


def test_real_repository_falls_back_to_static_wealth_on_adapter_failure() -> None:
    repository = RealDataCandidateRepository(
        wealth_adapter=MoneyFundWealthProxyAdapter(
            fetcher=lambda: (_ for _ in ()).throw(
                RuntimeError("money fund upstream down")
            )
        )
    )

    user_profile = map_user_profile("balanced")
    candidates = repository.list_wealth_management(user_profile)

    assert _strip_detail_metadata(candidates) == WEALTH_MANAGEMENT
    assert all(candidate.as_of_date for candidate in candidates)
    assert all(candidate.detail_route for candidate in candidates)


def test_real_repository_keeps_stock_candidate_selection_unchanged() -> None:
    repository = RealDataCandidateRepository()

    user_profile = map_user_profile("balanced")
    candidates = repository.list_stocks(user_profile)

    assert _strip_detail_metadata(candidates) == STOCKS
    assert all(candidate.as_of_date for candidate in candidates)
    assert all(candidate.detail_route for candidate in candidates)


def test_domain_recommendation_service_keeps_api_compatible_payload_with_explicit_real_repository(
    monkeypatch,
) -> None:
    from financehub_market_api.recommendation.repositories import real_data_adapters

    monkeypatch.setattr(
        real_data_adapters.ak,
        "fund_open_fund_rank_em",
        lambda symbol: FakeFrame(
            [
                {
                    "基金代码": "000001",
                    "基金简称": "稳健债券A",
                    "日期": "2026-04-02",
                    "单位净值": "1.1234",
                    "手续费": "0.15%",
                },
                {
                    "基金代码": "000002",
                    "基金简称": "稳健债券B",
                    "日期": "2026-04-02",
                    "单位净值": "1.0555",
                    "手续费": "0.20%",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        real_data_adapters.ak,
        "fund_money_rank_em",
        lambda: FakeFrame(
            [
                {
                    "基金代码": "511990",
                    "基金简称": "华宝添益",
                    "日期": "2026-04-02",
                    "年化收益率7日": "1.88%",
                    "手续费": "0.00%",
                },
                {
                    "基金代码": "000009",
                    "基金简称": "现金管理A",
                    "日期": "2026-04-02",
                    "年化收益率7日": "1.75%",
                    "手续费": "0.00%",
                },
            ]
        ),
    )

    response = RecommendationService(
        graph_runtime=RecommendationGraphRuntime.with_default_services(
            repository=RealDataCandidateRepository()
        )
    ).get_recommendation("balanced")

    assert response.allocationDisplay.model_dump() == {
        "fund": 45,
        "wealthManagement": 35,
        "stock": 20,
    }
    assert response.sections.funds.titleZh == "基金推荐"
    assert response.sections.wealthManagement.titleZh == "银行理财推荐"
    assert response.executionMode == "agent_assisted"
    assert response.sections.funds.items[0].nameZh == "稳健债券A"
    assert response.sections.wealthManagement.items[0].nameZh == "华宝添益"
