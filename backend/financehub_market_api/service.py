from __future__ import annotations

from collections.abc import Callable, Iterable
from numbers import Real
from typing import Protocol, TypeVar, cast

from .cache import SnapshotCache
from .models import (
    IndexCard,
    IndicesResponse,
    MarketOverviewResponse,
    MetricCard,
    OverviewStockSummary,
    StockRow,
    StocksResponse,
    TrendPoint,
)
from .upstreams.dolthub import StockPriceSnapshot
from .upstreams.index_data import INDEX_METADATA, INDEX_ORDER, IndexSnapshot
from .watchlist import WATCHLIST, WatchlistEntry


def _format_price(value: float) -> str:
    return f"{value:,.2f}"


def _format_change_value(value: float) -> str:
    return f"{value:+.2f}"


def _format_change_percent(latest: float, previous: float) -> str:
    return f"{_raw_change_percent(latest, previous):+.1f}%"


def _raw_change_percent(latest: float, previous: float) -> float:
    return 0.0 if previous == 0 else ((latest - previous) / previous) * 100


def _set_raw_change(row: StockRow, raw_change: float) -> None:
    row._raw_change = raw_change


def _get_raw_change(row: StockRow) -> float:
    return row._raw_change


def _set_raw_change_value(row: StockRow, raw_change_value: float) -> None:
    row._raw_change_value = raw_change_value


def _get_raw_change_value(row: StockRow) -> float:
    return row._raw_change_value


def build_stock_rows(
    entries: Iterable[WatchlistEntry],
    snapshot: StockPriceSnapshot,
) -> list[StockRow]:
    rows: list[StockRow] = []

    for entry in entries:
        latest = snapshot.latest_prices[entry.symbol]
        previous = snapshot.previous_prices[entry.symbol]
        raw_change = _raw_change_percent(latest, previous)
        raw_change_value = latest - previous
        trend_points = [
            TrendPoint(date=trend_date, value=trend_value)
            for trend_date, trend_value in snapshot.recent_closes[entry.symbol]
        ]
        row = StockRow(
            code=entry.code,
            name=entry.name,
            sector=entry.sector,
            price=_format_price(latest),
            change=_format_change_percent(latest, previous),
            priceValue=latest,
            changePercent=raw_change,
            volumeValue=snapshot.latest_volumes[entry.symbol],
            amountValue=snapshot.latest_amounts[entry.symbol],
            trend7d=trend_points,
        )
        _set_raw_change(row, raw_change)
        _set_raw_change_value(row, raw_change_value)
        rows.append(row)

    return rows


def split_rankings(
    rows: list[StockRow], limit: int = 3
) -> tuple[list[OverviewStockSummary], list[OverviewStockSummary]]:
    sorted_rows = sorted(
        (row for row in rows if _get_raw_change(row) > 0),
        key=_get_raw_change,
        reverse=True,
    )
    gainers = [
        OverviewStockSummary(
            code=row.code,
            name=row.name,
            price=row.price,
            priceValue=row.priceValue,
            change=_format_change_value(_get_raw_change_value(row)),
            changePercent=row.changePercent,
        )
        for row in sorted_rows[:limit]
    ]
    losers = [
        OverviewStockSummary(
            code=row.code,
            name=row.name,
            price=row.price,
            priceValue=row.priceValue,
            change=_format_change_value(_get_raw_change_value(row)),
            changePercent=row.changePercent,
        )
        for row in sorted(
            (row for row in rows if _get_raw_change(row) < 0),
            key=_get_raw_change,
        )[:limit]
    ]
    return gainers, losers


class StockClient(Protocol):
    def fetch_watchlist_prices(self, symbols: list[str]) -> StockPriceSnapshot: ...


class IndexClient(Protocol):
    def fetch_recent_closes(self, days: int = 5) -> dict[str, IndexSnapshot]: ...


class DataUnavailableError(RuntimeError):
    pass


SnapshotT = TypeVar("SnapshotT")
_REFRESH_DATA_ERRORS: frozenset[type[Exception]] = frozenset(
    (ValueError, TypeError, KeyError, IndexError)
)


class _SnapshotRefreshError(RuntimeError):
    pass


def _validate_stock_snapshot(snapshot: StockPriceSnapshot) -> None:
    if not isinstance(snapshot.as_of_date, str) or not snapshot.as_of_date:
        raise TypeError("stock snapshot as_of_date must be a non-empty string")
    for entry in WATCHLIST:
        if entry.symbol not in snapshot.latest_prices:
            raise KeyError(entry.symbol)
        if entry.symbol not in snapshot.previous_prices:
            raise KeyError(entry.symbol)
        latest_price = snapshot.latest_prices[entry.symbol]
        previous_price = snapshot.previous_prices[entry.symbol]
        latest_volume = snapshot.latest_volumes[entry.symbol]
        latest_amount = snapshot.latest_amounts[entry.symbol]
        recent_closes = snapshot.recent_closes[entry.symbol]
        if isinstance(latest_price, bool) or not isinstance(latest_price, Real):
            raise TypeError(f"{entry.symbol} latest price must be numeric")
        if isinstance(previous_price, bool) or not isinstance(previous_price, Real):
            raise TypeError(f"{entry.symbol} previous price must be numeric")
        if isinstance(latest_volume, bool) or not isinstance(latest_volume, Real):
            raise TypeError(f"{entry.symbol} latest volume must be numeric")
        if isinstance(latest_amount, bool) or not isinstance(latest_amount, Real):
            raise TypeError(f"{entry.symbol} latest amount must be numeric")
        if len(recent_closes) != 7:
            raise IndexError(f"{entry.symbol} recent closes requires exactly seven items")
        previous_close_date: str | None = None
        for close_item in recent_closes:
            if len(close_item) != 2:
                raise TypeError(f"{entry.symbol} close item must contain date and value")
            close_date, close_value = close_item
            if not isinstance(close_date, str) or not close_date:
                raise TypeError(f"{entry.symbol} close date must be a non-empty string")
            if isinstance(close_value, bool) or not isinstance(close_value, Real):
                raise TypeError(f"{entry.symbol} close value must be numeric")
            if previous_close_date is not None and close_date <= previous_close_date:
                raise ValueError(f"{entry.symbol} close dates must be strictly ascending")
            previous_close_date = close_date
        if recent_closes[-1][0] != snapshot.as_of_date:
            raise ValueError(f"{entry.symbol} last close date must match as_of_date")


def _validate_index_snapshots(snapshots: dict[str, IndexSnapshot]) -> None:
    common_as_of_date: str | None = None
    for index_name in INDEX_ORDER:
        if index_name not in snapshots:
            raise KeyError(index_name)
        snapshot = snapshots[index_name]
        if not isinstance(snapshot.as_of_date, str) or not snapshot.as_of_date:
            raise TypeError(f"{index_name} as_of_date must be a non-empty string")
        if common_as_of_date is None:
            common_as_of_date = snapshot.as_of_date
        elif snapshot.as_of_date != common_as_of_date:
            raise ValueError(
                "index snapshots as_of_date must match across configured indices"
            )
        if len(snapshot.closes) < 2:
            raise IndexError(f"{index_name} closes requires at least two items")
        previous_close_date: str | None = None
        for close_item in snapshot.closes:
            if len(close_item) != 2:
                raise TypeError(f"{index_name} close item must contain date and value")
            close_date, close_value = close_item
            if not isinstance(close_date, str) or not close_date:
                raise TypeError(f"{index_name} close date must be a non-empty string")
            if isinstance(close_value, bool) or not isinstance(close_value, Real):
                raise TypeError(f"{index_name} close value must be numeric")
            if previous_close_date is not None and close_date <= previous_close_date:
                raise ValueError(f"{index_name} close dates must be strictly ascending")
            previous_close_date = close_date
        if snapshot.closes[-1][0] != snapshot.as_of_date:
            raise ValueError(f"{index_name} last close date must match as_of_date")


class MarketDataService:
    def __init__(
        self,
        stock_client: StockClient,
        index_client: IndexClient,
        cache: SnapshotCache,
    ) -> None:
        self._stock_client = stock_client
        self._index_client = index_client
        self._cache = cache

    def _refresh_stock_snapshot(self) -> StockPriceSnapshot:
        return self._stock_client.fetch_watchlist_prices(
            [entry.symbol for entry in WATCHLIST]
        )

    def _refresh_index_snapshots(self) -> dict[str, IndexSnapshot]:
        return self._index_client.fetch_recent_closes(days=5)

    def _filter_stock_rows(self, rows: list[StockRow], query: str | None) -> list[StockRow]:
        normalized_query = (query or "").strip().lower()
        if not normalized_query:
            return rows
        return [
            row
            for row in rows
            if normalized_query in row.code.lower() or normalized_query in row.name.lower()
        ]

    def _build_stock_rows(self, stock_snapshot: StockPriceSnapshot) -> list[StockRow]:
        return build_stock_rows(WATCHLIST, stock_snapshot)

    def _load_cached_snapshot(
        self,
        cache_key: str,
        refresh: Callable[[], SnapshotT],
        validate: Callable[[SnapshotT], None],
    ) -> tuple[SnapshotT, bool]:
        cached = cast(SnapshotT | None, self._cache.get(cache_key))
        if cached is not None:
            try:
                validate(cached)
            except Exception:
                self._cache.delete(cache_key)
            else:
                return cached, False

        stale_cached = cast(SnapshotT | None, self._cache.peek(cache_key))
        if stale_cached is not None:
            try:
                validate(stale_cached)
            except Exception:
                self._cache.delete(cache_key)
                stale_cached = None

        try:
            fresh_snapshot = refresh()
        except Exception as exc:
            if type(exc) in _REFRESH_DATA_ERRORS:
                raise
            if stale_cached is not None:
                return stale_cached, True
            raise _SnapshotRefreshError(cache_key) from exc

        validate(fresh_snapshot)
        self._cache.put(cache_key, fresh_snapshot)
        return fresh_snapshot, False

    def _overview_metrics(
        self, index_snapshots: dict[str, IndexSnapshot]
    ) -> tuple[list[MetricCard], list[TrendPoint]]:
        metrics: list[MetricCard] = []
        trend_series: list[TrendPoint] = []
        for index_name in ("上证指数", "深证成指", "创业板指"):
            closes = index_snapshots[index_name].closes
            latest = closes[-1][1]
            previous = closes[-2][1]
            metrics.append(
                MetricCard(
                    label=index_name,
                    value=f"{latest:,.2f}",
                    delta=_format_change_percent(latest, previous),
                    changeValue=latest - previous,
                    changePercent=_raw_change_percent(latest, previous),
                    tone=(
                        "positive"
                        if latest > previous
                        else "negative" if latest < previous else "neutral"
                    ),
                )
            )
            if index_name == "上证指数":
                trend_series = [TrendPoint(date=date, value=value) for date, value in closes]
        return metrics, trend_series

    def get_market_overview(self) -> MarketOverviewResponse:
        try:
            stock_snapshot, stock_stale = self._load_cached_snapshot(
                "stock-snapshot",
                self._refresh_stock_snapshot,
                _validate_stock_snapshot,
            )
            index_snapshots, index_stale = self._load_cached_snapshot(
                "index-snapshots",
                self._refresh_index_snapshots,
                _validate_index_snapshots,
            )
        except _SnapshotRefreshError as exc:
            raise DataUnavailableError("market overview data is unavailable") from exc
        rows = self._build_stock_rows(stock_snapshot)
        top_gainers, top_losers = split_rankings(rows, limit=3)
        metrics, trend_series = self._overview_metrics(index_snapshots)
        overview_as_of_date = min(
            [stock_snapshot.as_of_date, *(snapshot.as_of_date for snapshot in index_snapshots.values())]
        )
        return MarketOverviewResponse(
            asOfDate=overview_as_of_date,
            stale=stock_stale or index_stale,
            metrics=metrics,
            chartLabel="上证指数",
            trendSeries=trend_series,
            topGainers=top_gainers,
            topLosers=top_losers,
        )

    def get_indices(self) -> IndicesResponse:
        try:
            index_snapshots, stale = self._load_cached_snapshot(
                "index-snapshots",
                self._refresh_index_snapshots,
                _validate_index_snapshots,
            )
        except _SnapshotRefreshError as exc:
            raise DataUnavailableError("indices data is unavailable") from exc
        return IndicesResponse(
            asOfDate=index_snapshots["上证指数"].as_of_date,
            stale=stale,
            cards=[
                IndexCard(
                    name=index_name,
                    code=INDEX_METADATA[index_name].code,
                    market=INDEX_METADATA[index_name].market,
                    description=INDEX_METADATA[index_name].description,
                    value=f"{index_snapshots[index_name].closes[-1][1]:,.2f}",
                    valueNumber=index_snapshots[index_name].closes[-1][1],
                    changeValue=(
                        index_snapshots[index_name].closes[-1][1]
                        - index_snapshots[index_name].closes[-2][1]
                    ),
                    changePercent=_raw_change_percent(
                        index_snapshots[index_name].closes[-1][1],
                        index_snapshots[index_name].closes[-2][1],
                    ),
                    tone=(
                        "positive"
                        if index_snapshots[index_name].closes[-1][1]
                        > index_snapshots[index_name].closes[-2][1]
                        else (
                            "negative"
                            if index_snapshots[index_name].closes[-1][1]
                            < index_snapshots[index_name].closes[-2][1]
                            else "neutral"
                        )
                    ),
                    trendSeries=[
                        TrendPoint(date=close_date, value=close_value)
                        for close_date, close_value in index_snapshots[index_name].closes
                    ],
                )
                for index_name in INDEX_ORDER
            ],
        )

    def get_stocks(self, query: str | None = None) -> StocksResponse:
        try:
            stock_snapshot, stale = self._load_cached_snapshot(
                "stock-snapshot",
                self._refresh_stock_snapshot,
                _validate_stock_snapshot,
            )
        except _SnapshotRefreshError as exc:
            raise DataUnavailableError("stocks data is unavailable") from exc
        all_rows = self._build_stock_rows(stock_snapshot)
        payload = StocksResponse(
            asOfDate=stock_snapshot.as_of_date,
            stale=stale,
            rows=all_rows,
        )
        return payload.model_copy(
            update={"rows": self._filter_stock_rows(payload.rows, query)}
        )
