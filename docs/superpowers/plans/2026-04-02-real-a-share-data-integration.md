# Real A-Share Data Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the China market mock data with real end-of-day A-share data by adding a lightweight FastAPI backend, wiring the three China market pages to runtime API requests, and handling loading, error, and stale-data states safely.

**Architecture:** Add a small Python backend under `backend/` that exposes three stable `/api/*` endpoints. Use `investment_data` through DoltHub SQL for curated stock watchlist closes and percentage changes, and isolate the three benchmark indices behind a dedicated index adapter because the approved page labels (`上证指数`, `深证成指`, `创业板指`) are not clearly exposed by the public `investment_data` tables. Keep the React page structure intact, move data fetching into a shared front-end service module, and surface stale-data fallback through a reusable status notice.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, httpx, pytest, React, TypeScript, Vite, Vitest, Testing Library, existing FinanceHub CSS and i18n modules

---

## File Structure

- Create: `backend/pyproject.toml` - backend package metadata and Python dependencies
- Create: `backend/financehub_market_api/__init__.py` - package marker
- Create: `backend/financehub_market_api/models.py` - Pydantic response models shared by service and API
- Create: `backend/financehub_market_api/watchlist.py` - curated representative stock metadata for table rows and mover lists
- Create: `backend/financehub_market_api/upstreams/dolthub.py` - `investment_data` / DoltHub stock close adapter
- Create: `backend/financehub_market_api/upstreams/index_data.py` - benchmark-index adapter for `上证指数`, `深证成指`, `创业板指`
- Create: `backend/financehub_market_api/cache.py` - in-memory snapshot cache and stale fallback helpers
- Create: `backend/financehub_market_api/service.py` - data orchestration, normalization, ranking, and fallback behavior
- Create: `backend/financehub_market_api/main.py` - FastAPI app and `/api/*` endpoints
- Create: `backend/tests/test_stock_snapshot_service.py` - pure stock-row and ranking tests
- Create: `backend/tests/test_dolthub_client.py` - DoltHub query/parsing tests
- Create: `backend/tests/test_market_service.py` - stale fallback and query filtering tests
- Create: `backend/tests/test_api.py` - FastAPI endpoint tests
- Create: `src/services/chinaMarketApi.ts` - typed browser fetchers for the three endpoints
- Create: `src/components/DataStatusNotice.tsx` - reusable loading/error/stale notice component
- Modify: `vite.config.ts` - proxy `/api/*` to the FastAPI dev server
- Modify: `src/i18n/messages.ts` - add shared data-state copy and updated market-data labels
- Modify: `src/i18n/locales/zh-CN.ts` - update chart/title/badge copy and add data-state strings
- Modify: `src/i18n/locales/en-US.ts` - update chart/title/badge copy and add data-state strings
- Modify: `src/app/App.test.tsx` - switch shell assertions from mock badge text to API-backed badge text and mock fetches across routes
- Modify: `src/styles/app-shell.css` - add styles for the new data status notice
- Modify: `src/features/market-overview/MarketOverviewPage.tsx` - fetch overview data, show recent close trend, and show status notices
- Modify: `src/features/market-overview/MarketOverviewPage.test.tsx` - assert loading, success, and stale behavior with fetch mocks
- Modify: `src/features/chinese-indices/ChineseIndicesPage.tsx` - fetch benchmark index data and show status notices
- Modify: `src/features/chinese-indices/IndexComparisonPanel.tsx` - accept API-fed series props instead of importing local mock arrays
- Modify: `src/features/chinese-indices/ChineseIndicesPage.test.tsx` - assert API-backed chart rendering and error handling
- Modify: `src/features/chinese-stocks/ChineseStocksPage.tsx` - fetch stock rows from the API and preserve local text filtering
- Modify: `src/features/chinese-stocks/ChineseStocksPage.test.tsx` - assert API-backed stock rows and stale banner rendering
- Delete: `src/mock/marketOverview.ts` - no longer needed once the overview page is API-backed
- Delete: `src/mock/indices.ts` - no longer needed once the indices page is API-backed
- Delete: `src/mock/stocks.ts` - no longer needed once the stocks page is API-backed

## Task 1: Scaffold the backend package, shared models, and curated stock metadata

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/financehub_market_api/__init__.py`
- Create: `backend/financehub_market_api/models.py`
- Create: `backend/financehub_market_api/watchlist.py`

- [ ] **Step 1: Create the backend package manifest**

Create `backend/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "financehub-market-api"
version = "0.1.0"
description = "Lightweight API for FinanceHub China market pages"
requires-python = ">=3.11"
dependencies = [
  "akshare>=1.17,<2.0",
  "fastapi>=0.116,<1.0",
  "httpx>=0.28,<0.29",
  "pydantic>=2.11,<3.0",
  "uvicorn>=0.35,<0.36",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create typed API models and the representative stock watchlist**

Create `backend/financehub_market_api/models.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


Tone = Literal["positive", "negative", "neutral"]


class MetricCard(BaseModel):
    label: str
    value: str
    delta: str
    tone: Tone


class TrendPoint(BaseModel):
    date: str
    value: float


class RankingItem(BaseModel):
    name: str
    value: str


class MarketOverviewResponse(BaseModel):
    asOfDate: str
    stale: bool
    metrics: list[MetricCard]
    trendSeries: list[TrendPoint]
    topGainers: list[RankingItem]
    topLosers: list[RankingItem]


class IndexSeriesItem(BaseModel):
    name: str
    value: float


class IndicesResponse(BaseModel):
    asOfDate: str
    stale: bool
    series: list[IndexSeriesItem]


class StockRow(BaseModel):
    code: str
    name: str
    sector: str
    price: str
    change: str


class StocksResponse(BaseModel):
    asOfDate: str
    stale: bool
    rows: list[StockRow]
```

Create `backend/financehub_market_api/watchlist.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchlistEntry:
    code: str
    symbol: str
    name: str
    sector: str


WATCHLIST: tuple[WatchlistEntry, ...] = (
    WatchlistEntry(code="300750", symbol="SZ300750", name="宁德时代", sector="新能源"),
    WatchlistEntry(code="002594", symbol="SZ002594", name="比亚迪", sector="汽车"),
    WatchlistEntry(code="600519", symbol="SH600519", name="贵州茅台", sector="白酒"),
    WatchlistEntry(code="600036", symbol="SH600036", name="招商银行", sector="银行"),
    WatchlistEntry(code="601318", symbol="SH601318", name="中国平安", sector="保险"),
    WatchlistEntry(code="600900", symbol="SH600900", name="长江电力", sector="公用事业"),
    WatchlistEntry(code="000333", symbol="SZ000333", name="美的集团", sector="家电"),
    WatchlistEntry(code="300059", symbol="SZ300059", name="东方财富", sector="金融科技"),
)
```

Create `backend/financehub_market_api/__init__.py`:

```python
__all__ = []
```

- [ ] **Step 3: Install backend dependencies in editable mode**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pip install -e '.[dev]'
```

Expected: install completes successfully and registers `financehub-market-api` plus `pytest`, `fastapi`, and `httpx`.

- [ ] **Step 4: Commit the backend scaffold**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/pyproject.toml backend/financehub_market_api/__init__.py backend/financehub_market_api/models.py backend/financehub_market_api/watchlist.py
git commit -m "feat: scaffold financehub market api package"
```

## Task 2: Build pure stock-row formatting and mover ranking helpers

**Files:**
- Create: `backend/financehub_market_api/service.py`
- Create: `backend/tests/test_stock_snapshot_service.py`

- [ ] **Step 1: Write failing tests for stock-row formatting and gainers/losers ranking**

Create `backend/tests/test_stock_snapshot_service.py`:

```python
from financehub_market_api.service import build_stock_rows, split_rankings
from financehub_market_api.watchlist import WATCHLIST


def test_build_stock_rows_formats_prices_and_percentage_changes() -> None:
    latest_prices = {
        "SZ300750": 188.55,
        "SZ002594": 221.88,
        "SH600519": 1608.00,
    }
    previous_prices = {
        "SZ300750": 177.54,
        "SZ002594": 211.72,
        "SH600519": 1618.00,
    }

    rows = build_stock_rows(WATCHLIST[:3], latest_prices, previous_prices)

    assert [row.model_dump() for row in rows] == [
        {
            "code": "300750",
            "name": "宁德时代",
            "sector": "新能源",
            "price": "188.55",
            "change": "+6.2%",
        },
        {
            "code": "002594",
            "name": "比亚迪",
            "sector": "汽车",
            "price": "221.88",
            "change": "+4.8%",
        },
        {
            "code": "600519",
            "name": "贵州茅台",
            "sector": "白酒",
            "price": "1,608.00",
            "change": "-0.6%",
        },
    ]


def test_split_rankings_returns_top_and_bottom_movers() -> None:
    latest_prices = {
        "SZ300750": 188.55,
        "SZ002594": 221.88,
        "SH600519": 1608.00,
        "SH600036": 43.50,
    }
    previous_prices = {
        "SZ300750": 177.54,
        "SZ002594": 211.72,
        "SH600519": 1618.00,
        "SH600036": 45.10,
    }

    rows = build_stock_rows(WATCHLIST[:4], latest_prices, previous_prices)
    top_gainers, top_losers = split_rankings(rows, limit=2)

    assert [item.model_dump() for item in top_gainers] == [
        {"name": "宁德时代", "value": "+6.2%"},
        {"name": "比亚迪", "value": "+4.8%"},
    ]
    assert [item.model_dump() for item in top_losers] == [
        {"name": "招商银行", "value": "-3.5%"},
        {"name": "贵州茅台", "value": "-0.6%"},
    ]
```

- [ ] **Step 2: Run the stock-helper tests to verify they fail**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_stock_snapshot_service.py -q
```

Expected: FAIL because `financehub_market_api.service` does not exist yet.

- [ ] **Step 3: Implement the pure formatting and ranking helpers**

Create `backend/financehub_market_api/service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import RankingItem, StockRow
from .watchlist import WatchlistEntry


def _format_price(value: float) -> str:
    return f"{value:,.2f}"


def _format_change_percent(latest: float, previous: float) -> str:
    change = 0.0 if previous == 0 else ((latest - previous) / previous) * 100
    return f"{change:+.1f}%"


def _parse_change(change: str) -> float:
    return float(change.replace("%", ""))


def build_stock_rows(
    entries: Iterable[WatchlistEntry],
    latest_prices: dict[str, float],
    previous_prices: dict[str, float],
) -> list[StockRow]:
    rows: list[StockRow] = []

    for entry in entries:
        latest = latest_prices[entry.symbol]
        previous = previous_prices[entry.symbol]
        rows.append(
            StockRow(
                code=entry.code,
                name=entry.name,
                sector=entry.sector,
                price=_format_price(latest),
                change=_format_change_percent(latest, previous),
            )
        )

    return rows


def split_rankings(rows: list[StockRow], limit: int = 3) -> tuple[list[RankingItem], list[RankingItem]]:
    sorted_rows = sorted(rows, key=lambda row: _parse_change(row.change), reverse=True)
    gainers = [
        RankingItem(name=row.name, value=row.change)
        for row in sorted_rows[:limit]
    ]
    losers = [
        RankingItem(name=row.name, value=row.change)
        for row in sorted(rows, key=lambda row: _parse_change(row.change))[:limit]
    ]
    return gainers, losers
```

- [ ] **Step 4: Run the stock-helper tests to verify they pass**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_stock_snapshot_service.py -q
```

Expected: PASS with 2 passing tests.

- [ ] **Step 5: Commit the pure stock snapshot helpers**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/financehub_market_api/service.py backend/tests/test_stock_snapshot_service.py
git commit -m "feat: add stock snapshot formatting helpers"
```

## Task 3: Add the upstream adapters for watchlist closes and benchmark indices

**Files:**
- Create: `backend/financehub_market_api/upstreams/dolthub.py`
- Create: `backend/financehub_market_api/upstreams/index_data.py`
- Create: `backend/tests/test_dolthub_client.py`

- [ ] **Step 1: Write a failing DoltHub adapter test around the latest-two-trading-days query flow**

Create `backend/tests/test_dolthub_client.py`:

```python
from financehub_market_api.upstreams.dolthub import DoltHubClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeHttpClient:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads
        self.calls: list[dict] = []

    def get(self, url: str, params: dict[str, str], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self._payloads.pop(0))


def test_fetch_watchlist_prices_queries_latest_and_previous_trade_dates() -> None:
    client = FakeHttpClient(
        [
            {"rows": [{"tradedate": "2026-04-01"}]},
            {"rows": [{"tradedate": "2026-03-31"}]},
            {
                "rows": [
                    {"tradedate": "2026-04-01", "symbol": "SZ300750", "close": "188.55"},
                    {"tradedate": "2026-03-31", "symbol": "SZ300750", "close": "177.54"},
                    {"tradedate": "2026-04-01", "symbol": "SZ002594", "close": "221.88"},
                    {"tradedate": "2026-03-31", "symbol": "SZ002594", "close": "211.72"},
                ]
            },
        ]
    )

    adapter = DoltHubClient(http_client=client)
    snapshot = adapter.fetch_watchlist_prices(["SZ300750", "SZ002594"])

    assert snapshot.as_of_date == "2026-04-01"
    assert snapshot.latest_prices == {
        "SZ300750": 188.55,
        "SZ002594": 221.88,
    }
    assert snapshot.previous_prices == {
        "SZ300750": 177.54,
        "SZ002594": 211.72,
    }
    assert "SELECT MAX(tradedate)" in client.calls[0]["params"]["q"]
    assert "tradedate < '2026-04-01'" in client.calls[1]["params"]["q"]
    assert "symbol IN ('SZ300750','SZ002594')" in client.calls[2]["params"]["q"]
```

- [ ] **Step 2: Run the DoltHub adapter test to verify it fails**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_dolthub_client.py -q
```

Expected: FAIL because the `upstreams/dolthub.py` module does not exist yet.

- [ ] **Step 3: Implement the DoltHub stock adapter and benchmark index adapter**

Create `backend/financehub_market_api/upstreams/dolthub.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class StockPriceSnapshot:
    as_of_date: str
    latest_prices: dict[str, float]
    previous_prices: dict[str, float]


class DoltHubClient:
    BASE_URL = "https://www.dolthub.com/api/v1alpha1/chenditc/investment_data"

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client or httpx.Client()

    def _query(self, sql: str) -> dict:
        response = self._http_client.get(self.BASE_URL, params={"q": sql}, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
        return payload

    def fetch_watchlist_prices(self, symbols: list[str]) -> StockPriceSnapshot:
        quoted_symbols = ",".join(f"'{symbol}'" for symbol in symbols)

        latest_date_payload = self._query(
            f"SELECT MAX(tradedate) AS tradedate FROM final_a_stock_eod_price WHERE symbol IN ({quoted_symbols})"
        )
        latest_date = latest_date_payload["rows"][0]["tradedate"]

        previous_date_payload = self._query(
            "SELECT MAX(tradedate) AS tradedate "
            "FROM final_a_stock_eod_price "
            f"WHERE symbol IN ({quoted_symbols}) AND tradedate < '{latest_date}'"
        )
        previous_date = previous_date_payload["rows"][0]["tradedate"]

        prices_payload = self._query(
            "SELECT tradedate, symbol, close "
            "FROM final_a_stock_eod_price "
            f"WHERE symbol IN ({quoted_symbols}) AND tradedate IN ('{latest_date}','{previous_date}')"
        )

        latest_prices: dict[str, float] = {}
        previous_prices: dict[str, float] = {}
        for row in prices_payload["rows"]:
            close = float(row["close"])
            if row["tradedate"] == latest_date:
                latest_prices[row["symbol"]] = close
            else:
                previous_prices[row["symbol"]] = close

        return StockPriceSnapshot(
            as_of_date=latest_date,
            latest_prices=latest_prices,
            previous_prices=previous_prices,
        )
```

Create `backend/financehub_market_api/upstreams/index_data.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import akshare as ak


@dataclass(frozen=True)
class IndexSnapshot:
    name: str
    as_of_date: str
    closes: list[tuple[str, float]]


INDEX_CONFIG = {
    "上证指数": "000001.SS",
    "深证成指": "399001.SZ",
    "创业板指": "399006.SZ",
}


class IndexDataClient:
    def fetch_recent_closes(self, days: int = 5) -> dict[str, IndexSnapshot]:
        snapshots: dict[str, IndexSnapshot] = {}

        for name, symbol in INDEX_CONFIG.items():
            frame = ak.stock_zh_index_daily_em(symbol=symbol).tail(days).copy()
            normalized = [
                (
                    row["date"].strftime("%Y-%m-%d"),
                    float(row["close"]),
                )
                for _, row in frame.iterrows()
            ]
            snapshots[name] = IndexSnapshot(
                name=name,
                as_of_date=normalized[-1][0],
                closes=normalized,
            )

        return snapshots
```

Keep the index adapter isolated even if the concrete provider changes in the future. The rest of the backend should only depend on the adapter contract, not on `akshare` internals.

- [ ] **Step 4: Run the DoltHub adapter test again**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_dolthub_client.py -q
```

Expected: PASS with 1 passing test.

- [ ] **Step 5: Commit the upstream adapters**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/financehub_market_api/upstreams/dolthub.py backend/financehub_market_api/upstreams/index_data.py backend/tests/test_dolthub_client.py
git commit -m "feat: add market data upstream adapters"
```

## Task 4: Add snapshot caching, stale fallback, and market-data orchestration

**Files:**
- Create: `backend/financehub_market_api/cache.py`
- Modify: `backend/financehub_market_api/service.py`
- Create: `backend/tests/test_market_service.py`

- [ ] **Step 1: Write failing tests for stale fallback, overview composition, and stock query filtering**

Create `backend/tests/test_market_service.py`:

```python
from financehub_market_api.cache import SnapshotCache
from financehub_market_api.models import IndicesResponse, MarketOverviewResponse, StocksResponse
from financehub_market_api.service import DataUnavailableError, MarketDataService


class FakeStockClient:
    def __init__(self, snapshot=None, error: Exception | None = None) -> None:
        self._snapshot = snapshot
        self._error = error

    def fetch_watchlist_prices(self, symbols: list[str]):
        if self._error:
            raise self._error
        return self._snapshot


class FakeIndexClient:
    def __init__(self, snapshots=None, error: Exception | None = None) -> None:
        self._snapshots = snapshots
        self._error = error

    def fetch_recent_closes(self, days: int = 5):
        if self._error:
            raise self._error
        return self._snapshots


def build_service(stock_snapshot, index_snapshots, *, stock_error=None, index_error=None):
    return MarketDataService(
        stock_client=FakeStockClient(snapshot=stock_snapshot, error=stock_error),
        index_client=FakeIndexClient(snapshots=index_snapshots, error=index_error),
        cache=SnapshotCache(),
    )


def test_get_market_overview_returns_fresh_composed_payload() -> None:
    from financehub_market_api.upstreams.dolthub import StockPriceSnapshot
    from financehub_market_api.upstreams.index_data import IndexSnapshot

    service = build_service(
        StockPriceSnapshot(
            as_of_date="2026-04-01",
            latest_prices={"SZ300750": 188.55, "SZ002594": 221.88, "SH600519": 1608.00, "SH600036": 43.50},
            previous_prices={"SZ300750": 177.54, "SZ002594": 211.72, "SH600519": 1618.00, "SH600036": 45.10},
        ),
        {
            "上证指数": IndexSnapshot("上证指数", "2026-04-01", [("2026-03-26", 3200.2), ("2026-03-27", 3218.1), ("2026-03-28", 3226.4), ("2026-03-31", 3238.2), ("2026-04-01", 3245.5)]),
            "深证成指": IndexSnapshot("深证成指", "2026-04-01", [("2026-03-26", 10120.3), ("2026-03-27", 10190.6), ("2026-03-28", 10220.4), ("2026-03-31", 10311.2), ("2026-04-01", 10422.9)]),
            "创业板指": IndexSnapshot("创业板指", "2026-04-01", [("2026-03-26", 2078.1), ("2026-03-27", 2082.4), ("2026-03-28", 2085.2), ("2026-03-31", 2098.0), ("2026-04-01", 2094.4)]),
        },
    )

    overview = service.get_market_overview()
    indices = service.get_indices()
    stocks = service.get_stocks(query="宁德")

    assert isinstance(overview, MarketOverviewResponse)
    assert overview.stale is False
    assert overview.asOfDate == "2026-04-01"
    assert overview.metrics[0].label == "上证指数"
    assert overview.trendSeries[-1].value == 3245.5
    assert isinstance(indices, IndicesResponse)
    assert len(indices.series) == 3
    assert isinstance(stocks, StocksResponse)
    assert [row.name for row in stocks.rows] == ["宁德时代"]


def test_falls_back_to_stale_snapshot_after_a_successful_refresh() -> None:
    from financehub_market_api.upstreams.dolthub import StockPriceSnapshot
    from financehub_market_api.upstreams.index_data import IndexSnapshot

    cache = SnapshotCache()
    fresh_service = MarketDataService(
        stock_client=FakeStockClient(
            snapshot=StockPriceSnapshot(
                as_of_date="2026-04-01",
                latest_prices={"SZ300750": 188.55, "SZ002594": 221.88, "SH600519": 1608.00, "SH600036": 43.50},
                previous_prices={"SZ300750": 177.54, "SZ002594": 211.72, "SH600519": 1618.00, "SH600036": 45.10},
            )
        ),
        index_client=FakeIndexClient(
            snapshots={
                "上证指数": IndexSnapshot("上证指数", "2026-04-01", [("2026-03-28", 3226.4), ("2026-03-31", 3238.2), ("2026-04-01", 3245.5)]),
                "深证成指": IndexSnapshot("深证成指", "2026-04-01", [("2026-03-28", 10220.4), ("2026-03-31", 10311.2), ("2026-04-01", 10422.9)]),
                "创业板指": IndexSnapshot("创业板指", "2026-04-01", [("2026-03-28", 2085.2), ("2026-03-31", 2098.0), ("2026-04-01", 2094.4)]),
            }
        ),
        cache=cache,
    )
    failing_service = MarketDataService(
        stock_client=FakeStockClient(error=RuntimeError("dolt down")),
        index_client=FakeIndexClient(error=RuntimeError("index down")),
        cache=cache,
    )

    assert fresh_service.get_market_overview().stale is False
    stale = failing_service.get_market_overview()

    assert stale.stale is True
    assert stale.metrics[0].label == "上证指数"


def test_raises_when_no_snapshot_exists_and_refresh_fails() -> None:
    service = MarketDataService(
        stock_client=FakeStockClient(error=RuntimeError("dolt down")),
        index_client=FakeIndexClient(error=RuntimeError("index down")),
        cache=SnapshotCache(),
    )

    try:
        service.get_market_overview()
    except DataUnavailableError as exc:
        assert "market overview" in str(exc)
    else:
        raise AssertionError("expected DataUnavailableError")
```

- [ ] **Step 2: Run the market-service tests to verify they fail**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_market_service.py -q
```

Expected: FAIL because `SnapshotCache`, `MarketDataService`, and `DataUnavailableError` are not implemented yet.

- [ ] **Step 3: Implement the cache and market-data orchestration**

Create `backend/financehub_market_api/cache.py`:

```python
from __future__ import annotations

from typing import TypeVar


T = TypeVar("T")


class SnapshotCache:
    def __init__(self) -> None:
        self._items: dict[str, object] = {}

    def get(self, key: str) -> object | None:
        return self._items.get(key)

    def put(self, key: str, value: object) -> None:
        self._items[key] = value
```

Update `backend/financehub_market_api/service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from .cache import SnapshotCache
from .models import (
    IndexSeriesItem,
    IndicesResponse,
    MarketOverviewResponse,
    MetricCard,
    RankingItem,
    StocksResponse,
    TrendPoint,
)
from .watchlist import WATCHLIST


class DataUnavailableError(RuntimeError):
    pass


class MarketDataService:
    def __init__(self, stock_client, index_client, cache: SnapshotCache) -> None:
        self._stock_client = stock_client
        self._index_client = index_client
        self._cache = cache

    def _load_raw_inputs(self):
        stock_snapshot = self._stock_client.fetch_watchlist_prices([entry.symbol for entry in WATCHLIST])
        index_snapshots = self._index_client.fetch_recent_closes(days=5)
        return stock_snapshot, index_snapshots

    def get_market_overview(self) -> MarketOverviewResponse:
        cache_key = "market-overview"
        try:
            stock_snapshot, index_snapshots = self._load_raw_inputs()
            rows = build_stock_rows(WATCHLIST, stock_snapshot.latest_prices, stock_snapshot.previous_prices)
            gainers, losers = split_rankings(rows, limit=3)
            metrics = []
            trend_series = []
            for name in ("上证指数", "深证成指", "创业板指"):
                closes = index_snapshots[name].closes
                latest_value = closes[-1][1]
                previous_value = closes[-2][1]
                metrics.append(
                    MetricCard(
                        label=name,
                        value=f"{latest_value:,.2f}",
                        delta=_format_change_percent(latest_value, previous_value),
                        tone="positive" if latest_value > previous_value else "negative" if latest_value < previous_value else "neutral",
                    )
                )
                if name == "上证指数":
                    trend_series = [TrendPoint(date=date, value=value) for date, value in closes]

            payload = MarketOverviewResponse(
                asOfDate=stock_snapshot.as_of_date,
                stale=False,
                metrics=metrics,
                trendSeries=trend_series,
                topGainers=gainers,
                topLosers=losers,
            )
            self._cache.put(cache_key, payload)
            return payload
        except Exception as exc:
            cached = self._cache.get(cache_key)
            if cached is None:
                raise DataUnavailableError("market overview data is unavailable") from exc
            return cached.model_copy(update={"stale": True})

    def get_indices(self) -> IndicesResponse:
        cache_key = "indices"
        try:
            _, index_snapshots = self._load_raw_inputs()
            payload = IndicesResponse(
                asOfDate=index_snapshots["上证指数"].as_of_date,
                stale=False,
                series=[
                    IndexSeriesItem(name=name, value=snapshot.closes[-1][1])
                    for name, snapshot in index_snapshots.items()
                ],
            )
            self._cache.put(cache_key, payload)
            return payload
        except Exception as exc:
            cached = self._cache.get(cache_key)
            if cached is None:
                raise DataUnavailableError("indices data is unavailable") from exc
            return cached.model_copy(update={"stale": True})

    def get_stocks(self, query: str | None = None) -> StocksResponse:
        cache_key = "stocks"
        normalized_query = (query or "").strip().lower()
        try:
            stock_snapshot, _ = self._load_raw_inputs()
            rows = build_stock_rows(WATCHLIST, stock_snapshot.latest_prices, stock_snapshot.previous_prices)
            if normalized_query:
                rows = [
                    row
                    for row in rows
                    if normalized_query in row.code.lower() or normalized_query in row.name.lower()
                ]
            payload = StocksResponse(asOfDate=stock_snapshot.as_of_date, stale=False, rows=rows)
            self._cache.put(cache_key, payload)
            return payload
        except Exception as exc:
            cached = self._cache.get(cache_key)
            if cached is None:
                raise DataUnavailableError("stocks data is unavailable") from exc
            rows = cached.rows
            if normalized_query:
                rows = [
                    row
                    for row in rows
                    if normalized_query in row.code.lower() or normalized_query in row.name.lower()
                ]
            return cached.model_copy(update={"stale": True, "rows": rows})
```

- [ ] **Step 4: Run the market-service tests again**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_market_service.py -q
```

Expected: PASS with 3 passing tests.

- [ ] **Step 5: Commit the cache and orchestration layer**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/financehub_market_api/cache.py backend/financehub_market_api/service.py backend/tests/test_market_service.py
git commit -m "feat: add market data service fallback logic"
```

## Task 5: Expose the FastAPI endpoints and wire the Vite proxy

**Files:**
- Create: `backend/financehub_market_api/main.py`
- Create: `backend/tests/test_api.py`
- Modify: `vite.config.ts`

- [ ] **Step 1: Write failing API endpoint tests**

Create `backend/tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from financehub_market_api.main import app, get_market_data_service


class FakeService:
    def get_market_overview(self):
        return {
            "asOfDate": "2026-04-01",
            "stale": False,
            "metrics": [{"label": "上证指数", "value": "3,245.55", "delta": "+0.8%", "tone": "positive"}],
            "trendSeries": [{"date": "2026-03-31", "value": 3238.2}, {"date": "2026-04-01", "value": 3245.5}],
            "topGainers": [{"name": "宁德时代", "value": "+6.2%"}],
            "topLosers": [{"name": "招商银行", "value": "-3.5%"}],
        }

    def get_indices(self):
        return {
            "asOfDate": "2026-04-01",
            "stale": False,
            "series": [{"name": "上证指数", "value": 3245.5}],
        }

    def get_stocks(self, query: str | None = None):
        return {
            "asOfDate": "2026-04-01",
            "stale": False,
            "rows": [{"code": "300750", "name": "宁德时代", "sector": "新能源", "price": "188.55", "change": "+6.2%"}],
        }


def test_market_endpoints_return_json_payloads() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: FakeService()
    client = TestClient(app)

    overview = client.get("/api/market-overview")
    indices = client.get("/api/indices")
    stocks = client.get("/api/stocks", params={"query": "宁德"})

    assert overview.status_code == 200
    assert overview.json()["metrics"][0]["label"] == "上证指数"
    assert indices.status_code == 200
    assert indices.json()["series"][0]["name"] == "上证指数"
    assert stocks.status_code == 200
    assert stocks.json()["rows"][0]["name"] == "宁德时代"

    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_api.py -q
```

Expected: FAIL because `main.py` and dependency wiring do not exist yet.

- [ ] **Step 3: Implement the FastAPI app and Vite dev proxy**

Create `backend/financehub_market_api/main.py`:

```python
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query

from .cache import SnapshotCache
from .service import DataUnavailableError, MarketDataService
from .upstreams.dolthub import DoltHubClient
from .upstreams.index_data import IndexDataClient

app = FastAPI(title="FinanceHub Market API")
_cache = SnapshotCache()


def get_market_data_service() -> MarketDataService:
    return MarketDataService(
        stock_client=DoltHubClient(),
        index_client=IndexDataClient(),
        cache=_cache,
    )


@app.get("/api/market-overview")
def market_overview(service: MarketDataService = Depends(get_market_data_service)):
    try:
        return service.get_market_overview()
    except DataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/indices")
def indices(service: MarketDataService = Depends(get_market_data_service)):
    try:
        return service.get_indices()
    except DataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/stocks")
def stocks(
    query: str | None = Query(default=None),
    service: MarketDataService = Depends(get_market_data_service),
):
    try:
        return service.get_stocks(query=query)
    except DataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
```

Update `vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **Step 4: Run backend API tests after the endpoint implementation**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_api.py -q
```

Expected: PASS with 1 passing test.

- [ ] **Step 5: Commit the API layer**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/financehub_market_api/main.py backend/tests/test_api.py vite.config.ts
git commit -m "feat: expose financehub market api endpoints"
```

## Task 6: Add the front-end API client, shared status notice, and market overview integration

**Files:**
- Create: `src/services/chinaMarketApi.ts`
- Create: `src/components/DataStatusNotice.tsx`
- Modify: `src/i18n/messages.ts`
- Modify: `src/i18n/locales/zh-CN.ts`
- Modify: `src/i18n/locales/en-US.ts`
- Modify: `src/styles/app-shell.css`
- Modify: `src/features/market-overview/MarketOverviewPage.tsx`
- Modify: `src/features/market-overview/MarketOverviewPage.test.tsx`
- Modify: `src/app/App.test.tsx`

- [ ] **Step 1: Write failing front-end tests for API-backed overview content and shell copy**

Update `src/features/market-overview/MarketOverviewPage.test.tsx`:

```ts
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { AppStateProvider } from "../../app/state/AppStateProvider";
import { MarketOverviewPage } from "./MarketOverviewPage";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("MarketOverviewPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/market-overview")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: true,
            metrics: [
              { label: "上证指数", value: "3,245.55", delta: "+0.8%", tone: "positive" },
              { label: "深证成指", value: "10,422.88", delta: "+1.1%", tone: "positive" },
              { label: "创业板指", value: "2,094.41", delta: "-0.2%", tone: "negative" },
            ],
            trendSeries: [
              { date: "2026-03-31", value: 3238.2 },
              { date: "2026-04-01", value: 3245.5 },
            ],
            topGainers: [
              { name: "宁德时代", value: "+6.2%" },
              { name: "比亚迪", value: "+4.8%" },
            ],
            topLosers: [
              { name: "招商银行", value: "-3.5%" },
              { name: "贵州茅台", value: "-0.6%" },
            ],
          });
        }
        throw new Error(`Unhandled fetch for ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders API-backed overview data and a stale-data notice", async () => {
    render(
      <AppStateProvider>
        <MemoryRouter initialEntries={["/"]}>
          <MarketOverviewPage />
        </MemoryRouter>
      </AppStateProvider>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("正在加载市场数据");
    expect(await screen.findByText("上证指数")).toBeInTheDocument();
    expect(screen.getByText("最近可用收盘数据: 2026-04-01")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "近期收盘走势" })).toBeInTheDocument();
    expect(screen.getByText("招商银行")).toBeInTheDocument();
  });

  it("renders an error message when the overview request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ detail: "market overview data is unavailable" }, 503)));

    render(
      <AppStateProvider>
        <MemoryRouter initialEntries={["/"]}>
          <MarketOverviewPage />
        </MemoryRouter>
      </AppStateProvider>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("市场数据暂不可用");
  });
});
```

Update `src/app/App.test.tsx` to replace the shell badge assertions:

```ts
expect(screen.getByText("A股收盘数据")).toBeInTheDocument();
```

and in the English locale test:

```ts
expect(screen.getByText("A-Share EOD")).toBeInTheDocument();
```

Add the shared fetch mock in `src/app/App.test.tsx`:

```ts
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/market-overview")) {
        return jsonResponse({
          asOfDate: "2026-04-01",
          stale: false,
          metrics: [
            { label: "上证指数", value: "3,245.55", delta: "+0.8%", tone: "positive" },
            { label: "深证成指", value: "10,422.88", delta: "+1.1%", tone: "positive" },
            { label: "创业板指", value: "2,094.41", delta: "-0.2%", tone: "negative" },
          ],
          trendSeries: [
            { date: "2026-03-31", value: 3238.2 },
            { date: "2026-04-01", value: 3245.5 },
          ],
          topGainers: [{ name: "宁德时代", value: "+6.2%" }],
          topLosers: [{ name: "招商银行", value: "-3.5%" }],
        });
      }

      if (url.endsWith("/api/indices")) {
        return jsonResponse({
          asOfDate: "2026-04-01",
          stale: false,
          series: [
            { name: "上证指数", value: 3245.5 },
            { name: "深证成指", value: 10422.9 },
            { name: "创业板指", value: 2094.4 },
          ],
        });
      }

      if (url.endsWith("/api/stocks")) {
        return jsonResponse({
          asOfDate: "2026-04-01",
          stale: false,
          rows: [
            { code: "300750", name: "宁德时代", sector: "新能源", price: "188.55", change: "+6.2%" },
          ],
        });
      }

      throw new Error(`Unhandled fetch for ${url}`);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});
```

- [ ] **Step 2: Run the overview and shell tests to verify they fail**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/features/market-overview/MarketOverviewPage.test.tsx src/app/App.test.tsx
```

Expected: FAIL because the overview page still imports local mock arrays, there is no `DataStatusNotice`, and the shell badge still says mock data.

- [ ] **Step 3: Implement the shared fetch layer, status notice, i18n copy, and overview page**

Create `src/services/chinaMarketApi.ts`:

```ts
export interface MetricCardData {
  label: string;
  value: string;
  delta: string;
  tone: "positive" | "negative" | "neutral";
}

export interface TrendPoint {
  date: string;
  value: number;
}

export interface RankingItem {
  name: string;
  value: string;
}

export interface MarketOverviewResponse {
  asOfDate: string;
  stale: boolean;
  metrics: MetricCardData[];
  trendSeries: TrendPoint[];
  topGainers: RankingItem[];
  topLosers: RankingItem[];
}

export interface IndicesResponse {
  asOfDate: string;
  stale: boolean;
  series: { name: string; value: number }[];
}

export interface StockRowData {
  code: string;
  name: string;
  sector: string;
  price: string;
  change: string;
}

export interface StocksResponse {
  asOfDate: string;
  stale: boolean;
  rows: StockRowData[];
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = typeof payload?.detail === "string" ? payload.detail : "request failed";
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function fetchMarketOverview(): Promise<MarketOverviewResponse> {
  return fetch("/api/market-overview").then(readJson<MarketOverviewResponse>);
}

export function fetchIndices(): Promise<IndicesResponse> {
  return fetch("/api/indices").then(readJson<IndicesResponse>);
}

export function fetchStocks(query?: string): Promise<StocksResponse> {
  const url = query ? `/api/stocks?query=${encodeURIComponent(query)}` : "/api/stocks";
  return fetch(url).then(readJson<StocksResponse>);
}
```

Create `src/components/DataStatusNotice.tsx`:

```tsx
interface DataStatusNoticeProps {
  body?: string;
  title: string;
  tone: "info" | "warning" | "danger";
}

export function DataStatusNotice({ body, title, tone }: DataStatusNoticeProps) {
  const role = tone === "danger" ? "alert" : "status";

  return (
    <section className={`data-status-notice data-status-notice--${tone}`} role={role}>
      <strong>{title}</strong>
      {body ? <p>{body}</p> : null}
    </section>
  );
}
```

Update `src/i18n/messages.ts`:

```ts
export interface Messages {
  languageLabel: string;
  dataState: {
    errorBody: string;
    errorTitle: string;
    loading: string;
    staleLabel: string;
  };
  nav: Record<RouteKey, RouteMessages>;
  marketOverview: {
    chartTitle: string;
    insightBody: string;
    insightTitle: string;
    losersTitle: string;
    gainersTitle: string;
  };
  topStatus: {
    dataBadgeLabel: string;
    workspaceLabel: string;
  };
}
```

Update `src/i18n/locales/zh-CN.ts`:

```ts
dataState: {
  loading: "正在加载市场数据",
  errorTitle: "市场数据暂不可用",
  errorBody: "请稍后重试，或等待上一次成功快照恢复。",
  staleLabel: "最近可用收盘数据",
},
marketOverview: {
  chartTitle: "近期收盘走势",
  insightTitle: "盘面洞察",
  gainersTitle: "涨幅榜",
  losersTitle: "跌幅榜",
  insightBody: "重点关注代表性股票与核心指数的最新交易日收盘表现。",
},
topStatus: {
  workspaceLabel: "中国市场工作区",
  dataBadgeLabel: "A股收盘数据",
},
```

Update `src/i18n/locales/en-US.ts`:

```ts
dataState: {
  loading: "Loading market data",
  errorTitle: "Market data is temporarily unavailable",
  errorBody: "Please try again later or wait for the last successful snapshot to recover.",
  staleLabel: "Latest available close data",
},
marketOverview: {
  chartTitle: "Recent Close Trend",
  insightTitle: "Market Insights",
  gainersTitle: "Top Gainers",
  losersTitle: "Top Losers",
  insightBody: "Track representative stocks and benchmark closes from the latest trading day.",
},
topStatus: {
  workspaceLabel: "China Market Workspace",
  dataBadgeLabel: "A-Share EOD",
},
```

Update `src/features/market-overview/MarketOverviewPage.tsx` so it no longer imports `../../mock/marketOverview` and instead fetches API data:

```tsx
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AppShell } from "../../app/layout/AppShell";
import { useAppState } from "../../app/state/app-state";
import { ChartPanel } from "../../components/ChartPanel";
import { DataStatusNotice } from "../../components/DataStatusNotice";
import { InsightCard } from "../../components/InsightCard";
import { MetricCard } from "../../components/MetricCard";
import { RankingList } from "../../components/RankingList";
import { getMessages } from "../../i18n/messages";
import { fetchMarketOverview, type MarketOverviewResponse } from "../../services/chinaMarketApi";

export function MarketOverviewContent() {
  const { locale } = useAppState();
  const messages = getMessages(locale);
  const bodyCopy = messages.marketOverview;
  const [data, setData] = useState<MarketOverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchMarketOverview()
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      })
      .catch((fetchError: Error) => {
        if (!cancelled) {
          setError(fetchError.message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <DataStatusNotice
        body={messages.dataState.errorBody}
        title={messages.dataState.errorTitle}
        tone="danger"
      />
    );
  }

  if (!data) {
    return <DataStatusNotice title={messages.dataState.loading} tone="info" />;
  }

  return (
    <>
      {data.stale ? (
        <DataStatusNotice
          title={`${messages.dataState.staleLabel}: ${data.asOfDate}`}
          tone="warning"
        />
      ) : null}
      <section className="market-overview__metrics">
        {data.metrics.map((metric) => (
          <MetricCard
            delta={metric.delta}
            key={metric.label}
            label={metric.label}
            tone={metric.tone}
            value={metric.value}
          />
        ))}
      </section>

      <section className="market-overview__main">
        <ChartPanel title={bodyCopy.chartTitle}>
          <div className="market-overview__chart">
            <ResponsiveContainer height={260} width="100%">
              <AreaChart data={data.trendSeries}>
                <defs>
                  <linearGradient id="overviewTrendGradient" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="5%" stopColor="#4d8fff" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#4d8fff" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid opacity={0.4} stroke="var(--fh-border)" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="var(--fh-text-muted)" tickLine={false} />
                <YAxis stroke="var(--fh-text-muted)" tickLine={false} />
                <Tooltip />
                <Area
                  dataKey="value"
                  fill="url(#overviewTrendGradient)"
                  fillOpacity={1}
                  stroke="#4d8fff"
                  strokeWidth={2}
                  type="monotone"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </ChartPanel>

        <InsightCard title={bodyCopy.insightTitle}>
          <p>{bodyCopy.insightBody}</p>
        </InsightCard>
      </section>

      <section className="market-overview__lists">
        <RankingList items={data.topGainers} title={bodyCopy.gainersTitle} />
        <RankingList items={data.topLosers} title={bodyCopy.losersTitle} />
      </section>
    </>
  );
}
```

Update `src/styles/app-shell.css` with the shared notice styles:

```css
.data-status-notice {
  border: 1px solid var(--fh-border);
  border-radius: var(--fh-radius-md);
  background: linear-gradient(180deg, var(--fh-bg-elevated), var(--fh-bg-overlay));
  box-shadow: var(--fh-shadow);
  padding: 0.85rem 1rem;
}

.data-status-notice strong {
  display: block;
}

.data-status-notice p {
  color: var(--fh-text-muted);
  margin: 0.35rem 0 0;
}

.data-status-notice--warning {
  border-color: rgba(245, 158, 11, 0.45);
}

.data-status-notice--danger {
  border-color: rgba(239, 68, 68, 0.45);
}
```

- [ ] **Step 4: Run the updated overview and shell tests**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/features/market-overview/MarketOverviewPage.test.tsx src/app/App.test.tsx
```

Expected: PASS with the overview page loading from `/api/market-overview` and the shell badge reading `A股收盘数据` / `A-Share EOD`.

- [ ] **Step 5: Commit the overview integration**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add src/services/chinaMarketApi.ts src/components/DataStatusNotice.tsx src/i18n/messages.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/styles/app-shell.css src/features/market-overview/MarketOverviewPage.tsx src/features/market-overview/MarketOverviewPage.test.tsx src/app/App.test.tsx
git commit -m "feat: load market overview from api"
```

## Task 7: Convert the China indices and China stocks pages to runtime API data and remove the old mocks

**Files:**
- Modify: `src/features/chinese-indices/ChineseIndicesPage.tsx`
- Modify: `src/features/chinese-indices/IndexComparisonPanel.tsx`
- Modify: `src/features/chinese-indices/ChineseIndicesPage.test.tsx`
- Modify: `src/features/chinese-stocks/ChineseStocksPage.tsx`
- Modify: `src/features/chinese-stocks/ChineseStocksPage.test.tsx`
- Delete: `src/mock/indices.ts`
- Delete: `src/mock/stocks.ts`
- Delete: `src/mock/marketOverview.ts`

- [ ] **Step 1: Write failing tests for API-backed indices and stocks pages**

Update `src/features/chinese-indices/ChineseIndicesPage.test.tsx`:

```ts
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppStateProvider } from "../../app/state/AppStateProvider";
import { ChineseIndicesPage } from "./ChineseIndicesPage";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("ChineseIndicesPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/indices")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: false,
            series: [
              { name: "上证指数", value: 3245.5 },
              { name: "深证成指", value: 10422.9 },
              { name: "创业板指", value: 2094.4 },
            ],
          });
        }
        throw new Error(`Unhandled fetch for ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the index comparison panel with api data", async () => {
    render(
      <AppStateProvider>
        <MemoryRouter initialEntries={["/indices"]}>
          <ChineseIndicesPage />
        </MemoryRouter>
      </AppStateProvider>,
    );

    expect(await screen.findByRole("img", { name: "指数对比图" })).toBeInTheDocument();
    expect(screen.getByText("指数对比")).toBeInTheDocument();
  });
});
```

Update `src/features/chinese-stocks/ChineseStocksPage.test.tsx`:

```ts
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppStateProvider } from "../../app/state/AppStateProvider";
import { ChineseStocksPage } from "./ChineseStocksPage";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("ChineseStocksPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/stocks")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: true,
            rows: [
              { code: "300750", name: "宁德时代", sector: "新能源", price: "188.55", change: "+6.2%" },
              { code: "002594", name: "比亚迪", sector: "汽车", price: "221.88", change: "+4.8%" },
            ],
          });
        }
        throw new Error(`Unhandled fetch for ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders stock rows from the api and shows the stale-data banner", async () => {
    render(
      <AppStateProvider>
        <MemoryRouter initialEntries={["/stocks"]}>
          <ChineseStocksPage />
        </MemoryRouter>
      </AppStateProvider>,
    );

    expect(await screen.findByText("宁德时代")).toBeInTheDocument();
    expect(screen.getByText("最近可用收盘数据: 2026-04-01")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the indices and stocks tests to verify they fail**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/features/chinese-indices/ChineseIndicesPage.test.tsx src/features/chinese-stocks/ChineseStocksPage.test.tsx
```

Expected: FAIL because both pages still import local mock arrays.

- [ ] **Step 3: Implement API-backed indices and stocks pages and remove obsolete mock imports**

Update `src/features/chinese-indices/IndexComparisonPanel.tsx`:

```tsx
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface IndexComparisonPanelProps {
  ariaLabel: string;
  data: { name: string; value: number }[];
}

export function IndexComparisonPanel({ ariaLabel, data }: IndexComparisonPanelProps) {
  return (
    <div aria-label={ariaLabel} className="index-comparison-panel" role="img">
      <ResponsiveContainer height={280} width="100%">
        <BarChart data={data}>
          <CartesianGrid opacity={0.4} stroke="var(--fh-border)" strokeDasharray="3 3" />
          <XAxis dataKey="name" stroke="var(--fh-text-muted)" tickLine={false} />
          <YAxis stroke="var(--fh-text-muted)" tickLine={false} />
          <Tooltip />
          <Bar dataKey="value" fill="#4d8fff" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

Update `src/features/chinese-indices/ChineseIndicesPage.tsx`:

```tsx
import { useEffect, useState } from "react";

import { AppShell } from "../../app/layout/AppShell";
import { type Locale, useAppState } from "../../app/state/app-state";
import { ChartPanel } from "../../components/ChartPanel";
import { DataStatusNotice } from "../../components/DataStatusNotice";
import { InsightCard } from "../../components/InsightCard";
import { getMessages } from "../../i18n/messages";
import { fetchIndices, type IndicesResponse } from "../../services/chinaMarketApi";
import { IndexComparisonPanel } from "./IndexComparisonPanel";

export function ChineseIndicesPage() {
  const { locale } = useAppState();
  const routeCopy = getMessages(locale).nav.indices;
  const pageCopy = getPageCopy(locale);
  const dataStateCopy = getMessages(locale).dataState;
  const [data, setData] = useState<IndicesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchIndices()
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      })
      .catch((fetchError: Error) => {
        if (!cancelled) {
          setError(fetchError.message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppShell pageSubtitle={routeCopy.subtitle} pageTitle={routeCopy.title}>
      {error ? <DataStatusNotice body={dataStateCopy.errorBody} title={dataStateCopy.errorTitle} tone="danger" /> : null}
      {!data && !error ? <DataStatusNotice title={dataStateCopy.loading} tone="info" /> : null}
      {data?.stale ? <DataStatusNotice title={`${dataStateCopy.staleLabel}: ${data.asOfDate}`} tone="warning" /> : null}
      {data ? (
        <section className="chinese-indices__layout">
          <ChartPanel title={pageCopy.comparisonTitle}>
            <IndexComparisonPanel ariaLabel={pageCopy.comparisonAriaLabel} data={data.series} />
          </ChartPanel>

          <InsightCard title={pageCopy.insightTitle}>
            <p>{pageCopy.insightBody}</p>
          </InsightCard>
        </section>
      ) : null}
    </AppShell>
  );
}
```

Update `src/features/chinese-stocks/ChineseStocksPage.tsx`:

```tsx
import { useEffect, useState } from "react";

import { AppShell } from "../../app/layout/AppShell";
import { type Locale, useAppState } from "../../app/state/app-state";
import { DataTable, type DataTableColumn } from "../../components/DataTable";
import { DataStatusNotice } from "../../components/DataStatusNotice";
import { InsightCard } from "../../components/InsightCard";
import { getMessages } from "../../i18n/messages";
import { fetchStocks, type StockRowData, type StocksResponse } from "../../services/chinaMarketApi";
import { StockFilters } from "./StockFilters";

export function ChineseStocksPage() {
  const { locale } = useAppState();
  const routeCopy = getMessages(locale).nav.stocks;
  const pageCopy = getPageCopy(locale);
  const dataStateCopy = getMessages(locale).dataState;
  const [query, setQuery] = useState("");
  const [data, setData] = useState<StocksResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchStocks()
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      })
      .catch((fetchError: Error) => {
        if (!cancelled) {
          setError(fetchError.message);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const normalizedQuery = query.trim().toLowerCase();
  const visibleRows = (data?.rows ?? []).filter((row) => {
    if (!normalizedQuery) {
      return true;
    }

    return row.code.includes(normalizedQuery) || row.name.toLowerCase().includes(normalizedQuery);
  });

  const columns: DataTableColumn<StockRowData>[] = [
    { key: "code", label: pageCopy.columns.code },
    { key: "name", label: pageCopy.columns.name },
    { key: "sector", label: pageCopy.columns.sector },
    { key: "price", label: pageCopy.columns.price },
    { key: "change", label: pageCopy.columns.change },
  ];

  return (
    <AppShell pageSubtitle={routeCopy.subtitle} pageTitle={routeCopy.title}>
      <StockFilters
        label={pageCopy.filterLabel}
        onQueryChange={setQuery}
        placeholder={pageCopy.filterPlaceholder}
        query={query}
      />
      {error ? <DataStatusNotice body={dataStateCopy.errorBody} title={dataStateCopy.errorTitle} tone="danger" /> : null}
      {!data && !error ? <DataStatusNotice title={dataStateCopy.loading} tone="info" /> : null}
      {data?.stale ? <DataStatusNotice title={`${dataStateCopy.staleLabel}: ${data.asOfDate}`} tone="warning" /> : null}
      {data ? (
        <section className="chinese-stocks__layout">
          <div className="chinese-stocks__table">
            <DataTable columns={columns} rows={visibleRows} />
          </div>
          <InsightCard title={pageCopy.insightTitle}>
            <p>{pageCopy.insightBody}</p>
          </InsightCard>
        </section>
      ) : null}
    </AppShell>
  );
}
```

Delete the three obsolete mock files once no imports remain:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
rg "../../mock/(marketOverview|indices|stocks)" src
rm src/mock/marketOverview.ts src/mock/indices.ts src/mock/stocks.ts
```

The `rg` command should return no results before deletion.

- [ ] **Step 4: Run the indices/stocks tests, then the full front-end suite and build**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/features/chinese-indices/ChineseIndicesPage.test.tsx src/features/chinese-stocks/ChineseStocksPage.test.tsx
npx vitest run
npm run build
```

Expected:

- the targeted indices/stocks tests PASS
- the full Vitest suite PASS
- `npm run build` succeeds

- [ ] **Step 5: Commit the indices/stocks integration and mock cleanup**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add src/features/chinese-indices/ChineseIndicesPage.tsx src/features/chinese-indices/IndexComparisonPanel.tsx src/features/chinese-indices/ChineseIndicesPage.test.tsx src/features/chinese-stocks/ChineseStocksPage.tsx src/features/chinese-stocks/ChineseStocksPage.test.tsx src/mock/marketOverview.ts src/mock/indices.ts src/mock/stocks.ts
git commit -m "feat: switch china market pages to api data"
```

## Task 8: Run final backend and frontend verification and do a manual smoke check

**Files:**
- No code changes expected

- [ ] **Step 1: Run the full backend test suite**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest
```

Expected: all backend tests PASS.

- [ ] **Step 2: Start the backend locally and smoke-test the three endpoints**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m uvicorn financehub_market_api.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, run:

```bash
curl -I http://127.0.0.1:8000/api/market-overview
curl -I http://127.0.0.1:8000/api/indices
curl -I http://127.0.0.1:8000/api/stocks
```

Expected: each endpoint returns `HTTP/1.1 200 OK` or `HTTP/1.1 503 Service Unavailable` with a JSON body if the upstream is unavailable and no cache is present on first boot.

- [ ] **Step 3: Run the full front-end verification again against the final code**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run
npm run build
```

Expected: all front-end tests PASS and the production build succeeds.

- [ ] **Step 4: Start the Vite app with the backend running and manually confirm the three pages**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npm run dev -- --host 0.0.0.0
```

Manual checks:

- `/` shows metric cards, a recent close trend chart, and gainers/losers from the API
- `/indices` shows the benchmark comparison chart from the API
- `/stocks` shows watchlist rows from the API, still filters by code/name, and shows the stale banner when applicable

- [ ] **Step 5: Commit only if the verification steps required code fixes**

If Task 8 required extra code edits, use a final cleanup commit like:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend src vite.config.ts
git commit -m "fix: finalize market data integration verification"
```
