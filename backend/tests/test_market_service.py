import json
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from financehub_market_api.cache import SnapshotCache
from financehub_market_api.models import IndicesResponse, MarketOverviewResponse, StocksResponse
from financehub_market_api.service import DataUnavailableError, MarketDataService
from financehub_market_api.upstreams.dolthub import StockPriceSnapshot
from financehub_market_api.upstreams.index_data import IndexSnapshot
from financehub_market_api.watchlist import WATCHLIST


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value

    def advance(self, *, seconds: int) -> None:
        self._value += timedelta(seconds=seconds)


class FakeStockClient:
    def __init__(
        self,
        snapshot: StockPriceSnapshot | None = None,
        error: Exception | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._error = error
        self.calls = 0

    def fetch_watchlist_prices(self, symbols: list[str]) -> StockPriceSnapshot:
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._snapshot is None:
            raise AssertionError("snapshot must be provided")
        return self._snapshot


class FakeIndexClient:
    def __init__(
        self,
        snapshots: dict[str, IndexSnapshot] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._snapshots = snapshots
        self._error = error
        self.calls = 0

    def fetch_recent_closes(self, days: int = 5) -> dict[str, IndexSnapshot]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._snapshots is None:
            raise AssertionError("snapshots must be provided")
        return self._snapshots


def _build_stock_snapshot(as_of_date: str = "2026-04-01") -> StockPriceSnapshot:
    latest_prices = {
        entry.symbol: 100.0 + float(index)
        for index, entry in enumerate(WATCHLIST, start=1)
    }
    previous_prices = {
        symbol: price - 1.0 for symbol, price in latest_prices.items()
    }
    latest_prices.update({"SZ300750": 188.55, "SZ002594": 221.88, "SH600519": 1608.00})
    previous_prices.update({"SZ300750": 177.54, "SZ002594": 211.72, "SH600519": 1618.00})
    latest_volumes = {
        entry.symbol: float(index * 1_000_000)
        for index, entry in enumerate(WATCHLIST, start=1)
    }
    latest_amounts = {
        entry.symbol: float(index * 10_000_000)
        for index, entry in enumerate(WATCHLIST, start=1)
    }
    trend_dates = [
        "2026-03-24",
        "2026-03-25",
        "2026-03-26",
        "2026-03-27",
        "2026-03-28",
        "2026-03-31",
        as_of_date,
    ]
    recent_closes = {
        entry.symbol: [
            (trend_date, latest_prices[entry.symbol] - float(6 - index))
            for index, trend_date in enumerate(trend_dates)
        ]
        for entry in WATCHLIST
    }

    return StockPriceSnapshot(
        as_of_date=as_of_date,
        latest_prices=latest_prices,
        previous_prices=previous_prices,
        latest_volumes=latest_volumes,
        latest_amounts=latest_amounts,
        recent_closes=recent_closes,
    )


def _build_index_snapshots() -> dict[str, IndexSnapshot]:
    return {
        "上证指数": IndexSnapshot(
            name="上证指数",
            as_of_date="2026-04-01",
            closes=[
                ("2026-03-28", 3226.4),
                ("2026-03-31", 3238.2),
                ("2026-04-01", 3245.5),
            ],
        ),
        "深证成指": IndexSnapshot(
            name="深证成指",
            as_of_date="2026-04-01",
            closes=[
                ("2026-03-28", 10220.4),
                ("2026-03-31", 10311.2),
                ("2026-04-01", 10422.9),
            ],
        ),
        "创业板指": IndexSnapshot(
            name="创业板指",
            as_of_date="2026-04-01",
            closes=[
                ("2026-03-28", 2085.2),
                ("2026-03-31", 2098.0),
                ("2026-04-01", 2094.4),
            ],
        ),
        "科创50": IndexSnapshot(
            name="科创50",
            as_of_date="2026-04-01",
            closes=[
                ("2026-03-28", 986.4),
                ("2026-03-31", 995.1),
                ("2026-04-01", 1002.6),
            ],
        ),
    }


def test_get_endpoints_return_fresh_payloads() -> None:
    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=SnapshotCache(),
    )

    overview = service.get_market_overview()
    indices = service.get_indices()
    stocks = service.get_stocks(query="宁德")

    assert isinstance(overview, MarketOverviewResponse)
    assert overview.stale is False
    assert overview.asOfDate == "2026-04-01"
    assert overview.chartLabel == "上证指数"
    assert overview.metrics[0].label == "上证指数"
    assert overview.metrics[0].changeValue == pytest.approx(7.3)
    assert overview.metrics[0].changePercent == pytest.approx(0.2254, abs=1e-4)
    assert overview.trendSeries[-1].value == 3245.5
    assert overview.topGainers[0].code == "300750"
    assert overview.topGainers[0].name == "宁德时代"
    assert overview.topGainers[0].price == "188.55"
    assert overview.topGainers[0].priceValue == pytest.approx(188.55)
    assert overview.topGainers[0].change == "+11.01"
    assert overview.topGainers[0].changePercent == pytest.approx(6.2014, abs=1e-4)
    assert overview.topLosers[0].code == "600519"
    assert overview.topLosers[0].name == "贵州茅台"
    assert overview.topLosers[0].price == "1,608.00"
    assert overview.topLosers[0].priceValue == pytest.approx(1608.0)
    assert overview.topLosers[0].change == "-10.00"
    assert overview.topLosers[0].changePercent == pytest.approx(-0.618, abs=1e-3)
    assert isinstance(indices, IndicesResponse)
    assert indices.stale is False
    assert [card.name for card in indices.cards] == [
        "上证指数",
        "深证成指",
        "创业板指",
        "科创50",
    ]
    first_card = indices.cards[0]
    assert first_card.code == "000001.SH"
    assert first_card.market == "中国市场"
    assert first_card.description == "沪市核心宽基指数"
    assert first_card.value == "3,245.50"
    assert first_card.valueNumber == pytest.approx(3245.5)
    assert first_card.changeValue == pytest.approx(7.3)
    assert first_card.changePercent == pytest.approx(0.2254, abs=1e-4)
    assert first_card.tone == "positive"
    assert first_card.trendSeries[-1].date == "2026-04-01"
    assert isinstance(stocks, StocksResponse)
    assert stocks.stale is False
    assert [row.name for row in stocks.rows] == ["宁德时代"]


def test_get_stocks_covers_expanded_curated_watchlist() -> None:
    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=SnapshotCache(ttl_seconds=300),
    )

    stocks = service.get_stocks()
    china_stocks = service.get_stocks(query="中国")
    stock_names = [row.name for row in stocks.rows]

    assert len(stocks.rows) == len(WATCHLIST)
    assert len(stocks.rows) >= 20
    assert {"宁德时代", "贵州茅台", "中芯国际", "中国移动"}.issubset(stock_names)
    assert [row.name for row in china_stocks.rows] == [
        "中国平安",
        "中国移动",
        "中国石油",
        "中国神华",
    ]


def test_watchlist_curated_invariants() -> None:
    expected_entries = {
        ("300750", "SZ300750", "宁德时代", "新能源"),
        ("002594", "SZ002594", "比亚迪", "汽车"),
        ("600519", "SH600519", "贵州茅台", "白酒"),
        ("600036", "SH600036", "招商银行", "银行"),
        ("601318", "SH601318", "中国平安", "保险"),
        ("600900", "SH600900", "长江电力", "公用事业"),
        ("000333", "SZ000333", "美的集团", "家电"),
        ("300059", "SZ300059", "东方财富", "金融科技"),
        ("000858", "SZ000858", "五粮液", "白酒"),
        ("600887", "SH600887", "伊利股份", "食品饮料"),
        ("603288", "SH603288", "海天味业", "食品饮料"),
        ("600030", "SH600030", "中信证券", "券商"),
        ("000651", "SZ000651", "格力电器", "家电"),
        ("688981", "SH688981", "中芯国际", "半导体"),
        ("688041", "SH688041", "海光信息", "半导体"),
        ("002475", "SZ002475", "立讯精密", "电子"),
        ("600276", "SH600276", "恒瑞医药", "医药"),
        ("300760", "SZ300760", "迈瑞医疗", "医疗器械"),
        ("603259", "SH603259", "药明康德", "医药服务"),
        ("601138", "SH601138", "工业富联", "先进制造"),
        ("600941", "SH600941", "中国移动", "通信运营"),
        ("601857", "SH601857", "中国石油", "能源"),
        ("601088", "SH601088", "中国神华", "煤炭"),
        ("601899", "SH601899", "紫金矿业", "有色金属"),
    }
    entries = {(entry.code, entry.symbol, entry.name, entry.sector) for entry in WATCHLIST}
    codes = [entry.code for entry in WATCHLIST]
    symbols = [entry.symbol for entry in WATCHLIST]

    assert len(WATCHLIST) == 24
    assert entries == expected_entries
    assert len(set(codes)) == len(codes)
    assert len(set(symbols)) == len(symbols)
    assert all(entry.symbol[2:] == entry.code for entry in WATCHLIST)


def test_shared_raw_snapshots_are_reused_across_endpoints_within_ttl() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    stock_client = FakeStockClient(snapshot=_build_stock_snapshot())
    index_client = FakeIndexClient(snapshots=_build_index_snapshots())
    service = MarketDataService(
        stock_client=stock_client,
        index_client=index_client,
        cache=SnapshotCache(ttl_seconds=300, now=clock.now),
    )

    overview = service.get_market_overview()
    indices = service.get_indices()
    stocks = service.get_stocks()

    assert overview.stale is False
    assert indices.stale is False
    assert stocks.stale is False
    assert stock_client.calls == 1
    assert index_client.calls == 1


def test_expired_raw_snapshots_refresh_after_ttl() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    stock_client = FakeStockClient(snapshot=_build_stock_snapshot())
    index_client = FakeIndexClient(snapshots=_build_index_snapshots())
    service = MarketDataService(
        stock_client=stock_client,
        index_client=index_client,
        cache=SnapshotCache(ttl_seconds=60, now=clock.now),
    )

    service.get_market_overview()
    clock.advance(seconds=61)
    indices = service.get_indices()
    stocks = service.get_stocks()

    assert indices.stale is False
    assert stocks.stale is False
    assert stock_client.calls == 2
    assert index_client.calls == 2


def test_expired_raw_snapshot_uses_stale_cache_when_refresh_fails() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=60, now=clock.now)
    fresh_stock_client = FakeStockClient(snapshot=_build_stock_snapshot())
    fresh_index_client = FakeIndexClient(snapshots=_build_index_snapshots())
    fresh_service = MarketDataService(
        stock_client=fresh_stock_client,
        index_client=fresh_index_client,
        cache=cache,
    )
    failing_stock_client = FakeStockClient(error=RuntimeError("dolt down"))
    failing_index_client = FakeIndexClient(error=RuntimeError("index down"))
    failing_service = MarketDataService(
        stock_client=failing_stock_client,
        index_client=failing_index_client,
        cache=cache,
    )

    fresh_service.get_market_overview()
    clock.advance(seconds=61)

    stale_overview = failing_service.get_market_overview()
    stale_indices = failing_service.get_indices()
    stale_stocks = failing_service.get_stocks()

    assert stale_overview.stale is True
    assert stale_indices.stale is True
    assert stale_stocks.stale is True
    assert failing_stock_client.calls == 2
    assert failing_index_client.calls == 2


def test_market_overview_uses_oldest_as_of_date_when_sources_mixed_fresh_and_stale() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=60, now=clock.now)
    fresh_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot(as_of_date="2026-04-01")),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )
    mixed_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot(as_of_date="2026-04-02")),
        index_client=FakeIndexClient(error=RuntimeError("index down")),
        cache=cache,
    )

    fresh_service.get_market_overview()
    clock.advance(seconds=61)

    overview = mixed_service.get_market_overview()

    assert overview.stale is True
    assert overview.trendSeries[-1].date == "2026-04-01"
    assert overview.asOfDate == "2026-04-01"


def test_get_stocks_rejects_snapshot_with_incomplete_trend_series() -> None:
    latest_prices = {
        entry.symbol: 100.0 + float(index)
        for index, entry in enumerate(WATCHLIST, start=1)
    }
    previous_prices = {
        symbol: price - 1.0 for symbol, price in latest_prices.items()
    }
    latest_volumes = {entry.symbol: 1000000.0 for entry in WATCHLIST}
    latest_amounts = {entry.symbol: 2000000.0 for entry in WATCHLIST}
    recent_closes = {
        entry.symbol: [
            ("2026-03-24", 101.0),
            ("2026-03-25", 102.0),
            ("2026-03-26", 103.0),
            ("2026-03-27", 104.0),
            ("2026-03-28", 105.0),
            ("2026-03-31", 106.0),
            ("2026-04-01", 107.0),
        ]
        for entry in WATCHLIST
    }
    recent_closes["SZ300750"] = recent_closes["SZ300750"][:6]
    broken_snapshot = StockPriceSnapshot(
        as_of_date="2026-04-01",
        latest_prices=latest_prices,
        previous_prices=previous_prices,
        latest_volumes=latest_volumes,
        latest_amounts=latest_amounts,
        recent_closes=recent_closes,
    )

    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=cast(StockPriceSnapshot, broken_snapshot)),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=SnapshotCache(),
    )

    with pytest.raises(IndexError):
        service.get_stocks()


@pytest.mark.parametrize(
    ("trend_series", "expected_error"),
    [
        (
            [
                ("2026-04-01", 107.0),
                ("2026-03-31", 106.0),
                ("2026-03-28", 105.0),
                ("2026-03-27", 104.0),
                ("2026-03-26", 103.0),
                ("2026-03-25", 102.0),
                ("2026-03-24", 101.0),
            ],
            ValueError,
        ),
        (
            [
                ("2026-03-24", 101.0),
                ("2026-03-25", 102.0),
                ("2026-03-26", 103.0),
                ("2026-03-27", 104.0),
                ("2026-03-28", 105.0),
                ("2026-03-31", 106.0),
                ("2026-03-31", 107.0),
            ],
            ValueError,
        ),
    ],
)
def test_get_stocks_rejects_out_of_order_or_stale_trend_series(
    trend_series: list[tuple[str, float]],
    expected_error: type[Exception],
) -> None:
    broken_snapshot = _build_stock_snapshot()
    broken_snapshot.recent_closes["SZ300750"] = trend_series

    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=broken_snapshot),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=SnapshotCache(),
    )

    with pytest.raises(expected_error):
        service.get_stocks()


def test_get_indices_rejects_out_of_order_close_dates() -> None:
    snapshots = _build_index_snapshots()
    snapshots["上证指数"] = IndexSnapshot(
        name="上证指数",
        as_of_date="2026-04-01",
        closes=[
            ("2026-03-28", 3226.4),
            ("2026-04-01", 3245.5),
            ("2026-03-31", 3238.2),
        ],
    )
    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=snapshots),
        cache=SnapshotCache(),
    )

    with pytest.raises(ValueError, match="上证指数 close dates must be strictly ascending"):
        service.get_indices()


def test_get_indices_rejects_last_close_date_not_matching_as_of_date() -> None:
    snapshots = _build_index_snapshots()
    snapshots["深证成指"] = IndexSnapshot(
        name="深证成指",
        as_of_date="2026-04-01",
        closes=[
            ("2026-03-28", 10220.4),
            ("2026-03-30", 10311.2),
            ("2026-03-31", 10422.9),
        ],
    )
    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=snapshots),
        cache=SnapshotCache(),
    )

    with pytest.raises(ValueError, match="深证成指 last close date must match as_of_date"):
        service.get_indices()


def test_get_indices_rejects_mismatched_as_of_date_across_index_set() -> None:
    snapshots = _build_index_snapshots()
    snapshots["科创50"] = IndexSnapshot(
        name="科创50",
        as_of_date="2026-04-02",
        closes=[
            ("2026-03-28", 986.4),
            ("2026-03-31", 995.1),
            ("2026-04-02", 1002.6),
        ],
    )
    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=snapshots),
        cache=SnapshotCache(),
    )

    with pytest.raises(
        ValueError, match="index snapshots as_of_date must match across configured indices"
    ):
        service.get_indices()


def test_returns_stale_snapshot_when_refresh_fails_after_success() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=60, now=clock.now)
    fresh_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )
    failing_service = MarketDataService(
        stock_client=FakeStockClient(error=RuntimeError("dolt down")),
        index_client=FakeIndexClient(error=RuntimeError("index down")),
        cache=cache,
    )

    assert fresh_service.get_market_overview().stale is False
    assert fresh_service.get_indices().stale is False
    assert fresh_service.get_stocks().stale is False

    clock.advance(seconds=61)

    stale_overview = failing_service.get_market_overview()
    stale_indices = failing_service.get_indices()
    stale_filtered_stocks = failing_service.get_stocks(query="300750")

    assert stale_overview.stale is True
    assert stale_overview.metrics[0].label == "上证指数"
    assert stale_indices.stale is True
    assert stale_indices.cards[0].name in {"上证指数", "深证成指", "创业板指", "科创50"}
    assert stale_filtered_stocks.stale is True
    assert [row.code for row in stale_filtered_stocks.rows] == ["300750"]


def test_raises_when_refresh_fails_without_cached_snapshot() -> None:
    service = MarketDataService(
        stock_client=FakeStockClient(error=RuntimeError("dolt down")),
        index_client=FakeIndexClient(error=RuntimeError("index down")),
        cache=SnapshotCache(),
    )

    try:
        service.get_market_overview()
    except DataUnavailableError as exc:
        assert str(exc) == "market overview data is unavailable"
    else:
        raise AssertionError("expected DataUnavailableError")

    try:
        service.get_indices()
    except DataUnavailableError as exc:
        assert str(exc) == "indices data is unavailable"
    else:
        raise AssertionError("expected DataUnavailableError")

    try:
        service.get_stocks()
    except DataUnavailableError as exc:
        assert str(exc) == "stocks data is unavailable"
    else:
        raise AssertionError("expected DataUnavailableError")


def test_composition_errors_do_not_fall_back_to_stale_snapshot() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=60, now=clock.now)
    fresh_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )
    broken_index_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(
            snapshots={
                "上证指数": IndexSnapshot(
                    name="上证指数",
                    as_of_date="2026-04-01",
                    closes=[("2026-04-01", 3245.5)],
                ),
                "深证成指": _build_index_snapshots()["深证成指"],
                "创业板指": _build_index_snapshots()["创业板指"],
            }
        ),
        cache=cache,
    )
    broken_stock_snapshot = _build_stock_snapshot()
    broken_stock_snapshot.latest_prices.pop("SZ300750")
    broken_stock_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=broken_stock_snapshot),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )

    assert fresh_service.get_market_overview().stale is False
    assert fresh_service.get_stocks().stale is False

    clock.advance(seconds=61)

    with pytest.raises(IndexError):
        broken_index_service.get_market_overview()

    clock.advance(seconds=61)

    with pytest.raises(KeyError):
        broken_stock_service.get_stocks()


def test_stock_composition_error_does_not_poison_cache_for_next_healthy_request() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=300, now=clock.now)
    poisoned_snapshot = _build_stock_snapshot()
    poisoned_snapshot.latest_prices.pop("SZ300750")
    poisoned_client = FakeStockClient(snapshot=poisoned_snapshot)
    healthy_client = FakeStockClient(snapshot=_build_stock_snapshot())
    index_client = FakeIndexClient(snapshots=_build_index_snapshots())
    poisoned_service = MarketDataService(
        stock_client=poisoned_client,
        index_client=index_client,
        cache=cache,
    )
    healthy_service = MarketDataService(
        stock_client=healthy_client,
        index_client=index_client,
        cache=cache,
    )

    with pytest.raises(KeyError):
        poisoned_service.get_stocks()

    stocks = healthy_service.get_stocks()

    assert poisoned_client.calls == 1
    assert healthy_client.calls == 1
    assert stocks.stale is False
    assert len(stocks.rows) == len(WATCHLIST)


def test_overview_stock_composition_failure_keeps_cached_indices_for_stale_fallback() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=60, now=clock.now)
    warm_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )
    malformed_stock_snapshot = _build_stock_snapshot()
    malformed_stock_snapshot.latest_prices.pop("SZ300750")
    failing_refresh_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=malformed_stock_snapshot),
        index_client=FakeIndexClient(error=RuntimeError("index down")),
        cache=cache,
    )

    assert warm_service.get_market_overview().stale is False

    clock.advance(seconds=61)

    with pytest.raises(KeyError):
        failing_refresh_service.get_market_overview()

    indices = failing_refresh_service.get_indices()

    assert indices.stale is True
    assert len(indices.cards) == 4


def test_overview_malformed_stock_snapshot_does_not_evict_stale_index_cache() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=60, now=clock.now)
    warm_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )
    healthy_stock_snapshot = _build_stock_snapshot()
    malformed_stock_snapshot = StockPriceSnapshot(
        as_of_date=None,  # type: ignore[arg-type]
        latest_prices=healthy_stock_snapshot.latest_prices,
        previous_prices=healthy_stock_snapshot.previous_prices,
        latest_volumes=healthy_stock_snapshot.latest_volumes,
        latest_amounts=healthy_stock_snapshot.latest_amounts,
        recent_closes=healthy_stock_snapshot.recent_closes,
    )
    failing_refresh_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=malformed_stock_snapshot),
        index_client=FakeIndexClient(error=RuntimeError("index down")),
        cache=cache,
    )

    assert warm_service.get_market_overview().stale is False
    clock.advance(seconds=61)

    with pytest.raises(TypeError):
        failing_refresh_service.get_market_overview()

    indices = failing_refresh_service.get_indices()

    assert indices.stale is True
    assert len(indices.cards) == 4


def test_stock_refresh_value_error_surfaces_even_with_stale_cache() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=60, now=clock.now)
    warm_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )
    malformed_refresh_service = MarketDataService(
        stock_client=FakeStockClient(error=ValueError("missing latest closes")),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )

    assert warm_service.get_stocks().stale is False

    clock.advance(seconds=61)

    with pytest.raises(ValueError, match="missing latest closes"):
        malformed_refresh_service.get_stocks()


def test_string_stock_price_does_not_poison_future_healthy_requests() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=300, now=clock.now)
    poisoned_latest_prices = dict(_build_stock_snapshot().latest_prices)
    poisoned_latest_prices["SZ300750"] = "188.55"  # type: ignore[assignment]
    poisoned_snapshot = StockPriceSnapshot(
        as_of_date="2026-04-01",
        latest_prices=poisoned_latest_prices,
        previous_prices=_build_stock_snapshot().previous_prices,
        latest_volumes=_build_stock_snapshot().latest_volumes,
        latest_amounts=_build_stock_snapshot().latest_amounts,
        recent_closes=_build_stock_snapshot().recent_closes,
    )
    poisoned_client = FakeStockClient(snapshot=poisoned_snapshot)
    healthy_client = FakeStockClient(snapshot=_build_stock_snapshot())
    index_client = FakeIndexClient(snapshots=_build_index_snapshots())
    poisoned_service = MarketDataService(
        stock_client=poisoned_client,
        index_client=index_client,
        cache=cache,
    )
    healthy_service = MarketDataService(
        stock_client=healthy_client,
        index_client=index_client,
        cache=cache,
    )

    with pytest.raises(TypeError):
        poisoned_service.get_stocks()

    recovered = healthy_service.get_stocks()

    assert recovered.stale is False
    assert healthy_client.calls == 1
    assert len(recovered.rows) == len(WATCHLIST)


def test_stock_refresh_json_decode_error_uses_stale_cache() -> None:
    clock = MutableClock(datetime(2026, 4, 1, 9, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=60, now=clock.now)
    warm_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )
    decode_error_service = MarketDataService(
        stock_client=FakeStockClient(
            error=json.JSONDecodeError("Expecting value", "{}", 0)
        ),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )

    assert warm_service.get_stocks().stale is False
    clock.advance(seconds=61)

    stale_stocks = decode_error_service.get_stocks()

    assert stale_stocks.stale is True
    assert len(stale_stocks.rows) == len(WATCHLIST)
