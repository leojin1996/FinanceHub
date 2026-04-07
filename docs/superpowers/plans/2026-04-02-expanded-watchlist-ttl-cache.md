# Expanded Watchlist And TTL Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the curated A-share stock universe to roughly 24 representative names and add a 5-minute backend TTL cache for shared raw market snapshots so repeated page visits do not keep hitting upstreams.

**Architecture:** Keep the product contract unchanged: the backend still serves the same three `/api/*` response models, and the frontend keeps consuming them as-is. Move cache responsibility down to raw stock and index snapshots by upgrading `SnapshotCache` to track expiry metadata and refactoring `MarketDataService` to reuse those cached snapshots across `get_market_overview()`, `get_indices()`, and `get_stocks()`, while still surfacing stale data only when an expired refresh fails and an older snapshot exists.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest, existing in-memory backend service under `backend/financehub_market_api`

---

## File Structure

- Create: `backend/tests/test_cache.py` - focused TTL cache tests for fresh reads, expiry, and stale peek behavior
- Modify: `backend/financehub_market_api/cache.py:1-12` - replace plain key-value storage with TTL-aware cache entries and stale peek support
- Modify: `backend/financehub_market_api/service.py:3-229` - cache raw snapshots under shared keys and derive endpoint payloads from fresh or stale cached inputs
- Modify: `backend/tests/test_market_service.py:1-221` - add call counters, clock-driven TTL tests, and broader stock coverage assertions
- Modify: `backend/financehub_market_api/watchlist.py:14-23` - expand the curated watchlist from 8 names to about 24 names while keeping the existing initial entries stable
- Modify: `backend/tests/test_package_smoke.py:1-8` - tighten smoke coverage so the expanded curated universe is asserted explicitly

## Task 1: Add TTL-aware snapshot cache primitives

**Files:**
- Create: `backend/tests/test_cache.py`
- Modify: `backend/financehub_market_api/cache.py:1-12`

- [ ] **Step 1: Write the failing cache tests**

Create `backend/tests/test_cache.py`:

```python
from datetime import UTC, datetime, timedelta

from financehub_market_api.cache import SnapshotCache


class MutableClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def test_get_returns_cached_value_before_expiry() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 9, 30, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=300, now=clock.now)

    cache.put("stock-snapshot", {"rows": 24})

    assert cache.get("stock-snapshot") == {"rows": 24}
    assert cache.peek("stock-snapshot") == {"rows": 24}


def test_get_returns_none_after_expiry_but_peek_keeps_last_value() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 9, 30, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=300, now=clock.now)
    cache.put("index-snapshots", {"series": 3})

    clock.advance(seconds=301)

    assert cache.get("index-snapshots") is None
    assert cache.peek("index-snapshots") == {"series": 3}


def test_put_replaces_existing_value_and_resets_expiry_window() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 9, 30, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=300, now=clock.now)
    cache.put("stocks", {"version": 1})

    clock.advance(seconds=299)
    cache.put("stocks", {"version": 2})
    clock.advance(seconds=299)

    assert cache.get("stocks") == {"version": 2}
```

- [ ] **Step 2: Run the new cache tests to confirm they fail against the current plain cache**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_cache.py -q
```

Expected: FAIL with errors showing that `SnapshotCache` does not accept `ttl_seconds` / `now` and does not expose `peek()`.

- [ ] **Step 3: Implement TTL-aware cache entries with stale peek support**

Modify `backend/financehub_market_api/cache.py` to:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable


@dataclass(frozen=True)
class CacheEntry:
    value: object
    stored_at: datetime
    expires_at: datetime


class SnapshotCache:
    def __init__(
        self,
        ttl_seconds: int = 300,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._items: dict[str, CacheEntry] = {}

    def get(self, key: str) -> object | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self._now():
            return None
        return entry.value

    def peek(self, key: str) -> object | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        return entry.value

    def put(self, key: str, value: object) -> None:
        stored_at = self._now()
        self._items[key] = CacheEntry(
            value=value,
            stored_at=stored_at,
            expires_at=stored_at + timedelta(seconds=self._ttl_seconds),
        )
```

- [ ] **Step 4: Run the cache tests again**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_cache.py -q
```

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the cache primitive change**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/financehub_market_api/cache.py backend/tests/test_cache.py
git commit -m "feat: add ttl-aware snapshot cache"
```

## Task 2: Refactor the service to share raw stock and index snapshots across endpoints

**Files:**
- Modify: `backend/financehub_market_api/service.py:3-229`
- Modify: `backend/tests/test_market_service.py:1-221`

- [ ] **Step 1: Write the failing service tests for shared raw-snapshot caching**

Update `backend/tests/test_market_service.py` with call-counting fakes, a controllable clock, and TTL-aware tests:

```python
from datetime import UTC, datetime, timedelta

import pytest

from financehub_market_api.cache import SnapshotCache
from financehub_market_api.models import IndicesResponse, MarketOverviewResponse, StocksResponse
from financehub_market_api.service import DataUnavailableError, MarketDataService
from financehub_market_api.upstreams.dolthub import StockPriceSnapshot
from financehub_market_api.upstreams.index_data import IndexSnapshot
from financehub_market_api.watchlist import WATCHLIST


class MutableClock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


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
        assert symbols == [entry.symbol for entry in WATCHLIST]
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
        assert days == 5
        return self._snapshots


def _build_stock_snapshot() -> StockPriceSnapshot:
    latest_prices: dict[str, float] = {}
    previous_prices: dict[str, float] = {}
    for index, entry in enumerate(WATCHLIST, start=1):
        previous_prices[entry.symbol] = 100.0 + index
        latest_prices[entry.symbol] = 101.0 + index

    latest_prices["SZ300750"] = 188.55
    previous_prices["SZ300750"] = 177.54
    latest_prices["SZ002594"] = 221.88
    previous_prices["SZ002594"] = 211.72
    latest_prices["SH600519"] = 1608.00
    previous_prices["SH600519"] = 1618.00
    latest_prices["SH600036"] = 43.50
    previous_prices["SH600036"] = 45.10

    return StockPriceSnapshot(
        as_of_date="2026-04-01",
        latest_prices=latest_prices,
        previous_prices=previous_prices,
    )


def test_shared_raw_snapshots_are_reused_across_endpoints_within_ttl() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 9, 30, tzinfo=UTC))
    stock_client = FakeStockClient(snapshot=_build_stock_snapshot())
    index_client = FakeIndexClient(snapshots=_build_index_snapshots())
    service = MarketDataService(
        stock_client=stock_client,
        index_client=index_client,
        cache=SnapshotCache(ttl_seconds=300, now=clock.now),
    )

    assert service.get_market_overview().stale is False
    assert service.get_stocks().stale is False
    assert service.get_indices().stale is False

    assert stock_client.calls == 1
    assert index_client.calls == 1


def test_expired_snapshots_refresh_after_ttl() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 9, 30, tzinfo=UTC))
    stock_client = FakeStockClient(snapshot=_build_stock_snapshot())
    index_client = FakeIndexClient(snapshots=_build_index_snapshots())
    service = MarketDataService(
        stock_client=stock_client,
        index_client=index_client,
        cache=SnapshotCache(ttl_seconds=300, now=clock.now),
    )

    assert service.get_market_overview().stale is False
    clock.advance(seconds=301)
    assert service.get_market_overview().stale is False

    assert stock_client.calls == 2
    assert index_client.calls == 2


def test_expired_snapshot_uses_stale_cached_data_when_refresh_fails() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 9, 30, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=300, now=clock.now)
    fresh_service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=cache,
    )

    assert fresh_service.get_market_overview().stale is False
    clock.advance(seconds=301)

    failing_service = MarketDataService(
        stock_client=FakeStockClient(error=RuntimeError("dolt down")),
        index_client=FakeIndexClient(error=RuntimeError("index down")),
        cache=cache,
    )

    stale_overview = failing_service.get_market_overview()
    stale_indices = failing_service.get_indices()
    stale_filtered_stocks = failing_service.get_stocks(query="300750")

    assert stale_overview.stale is True
    assert stale_indices.stale is True
    assert stale_filtered_stocks.stale is True
    assert [row.code for row in stale_filtered_stocks.rows] == ["300750"]
```

- [ ] **Step 2: Run the market service tests to confirm the current endpoint-shaped cache is insufficient**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_market_service.py -q
```

Expected: FAIL because the current service still refreshes upstreams on every request and caches only endpoint payloads under `market-overview`, `indices`, and `stocks`.

- [ ] **Step 3: Refactor `MarketDataService` to cache and reuse raw snapshots**

Modify `backend/financehub_market_api/service.py` around the current cache handling:

```python
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, TypeVar, cast

from .cache import SnapshotCache
from .models import (
    IndexSeriesItem,
    IndicesResponse,
    MarketOverviewResponse,
    MetricCard,
    RankingItem,
    StockRow,
    StocksResponse,
    TrendPoint,
)
from .upstreams.dolthub import StockPriceSnapshot
from .upstreams.index_data import IndexSnapshot
from .watchlist import WATCHLIST, WatchlistEntry


SnapshotT = TypeVar("SnapshotT")

STOCK_SNAPSHOT_CACHE_KEY = "stock-snapshot"
INDEX_SNAPSHOTS_CACHE_KEY = "index-snapshots"


class MarketDataService:
    ...

    def _load_snapshot(
        self,
        cache_key: str,
        refresh: Callable[[], SnapshotT],
    ) -> tuple[SnapshotT, bool]:
        fresh_value = cast(SnapshotT | None, self._cache.get(cache_key))
        if fresh_value is not None:
            return fresh_value, False

        stale_value = cast(SnapshotT | None, self._cache.peek(cache_key))
        try:
            snapshot = refresh()
        except Exception:
            if stale_value is not None:
                return stale_value, True
            raise

        self._cache.put(cache_key, snapshot)
        return snapshot, False

    def get_market_overview(self) -> MarketOverviewResponse:
        try:
            stock_snapshot, stock_stale = self._load_snapshot(
                STOCK_SNAPSHOT_CACHE_KEY,
                self._refresh_stock_snapshot,
            )
            index_snapshots, index_stale = self._load_snapshot(
                INDEX_SNAPSHOTS_CACHE_KEY,
                self._refresh_index_snapshots,
            )
        except Exception as exc:
            raise DataUnavailableError("market overview data is unavailable") from exc

        rows = self._build_stock_rows(stock_snapshot)
        top_gainers, top_losers = split_rankings(rows, limit=3)
        metrics, trend_series = self._overview_metrics(index_snapshots)
        return MarketOverviewResponse(
            asOfDate=stock_snapshot.as_of_date,
            stale=stock_stale or index_stale,
            metrics=metrics,
            trendSeries=trend_series,
            topGainers=top_gainers,
            topLosers=top_losers,
        )

    def get_indices(self) -> IndicesResponse:
        try:
            index_snapshots, stale = self._load_snapshot(
                INDEX_SNAPSHOTS_CACHE_KEY,
                self._refresh_index_snapshots,
            )
        except Exception as exc:
            raise DataUnavailableError("indices data is unavailable") from exc

        return IndicesResponse(
            asOfDate=index_snapshots["上证指数"].as_of_date,
            stale=stale,
            series=[
                IndexSeriesItem(
                    name=index_name,
                    value=index_snapshots[index_name].closes[-1][1],
                )
                for index_name in ("上证指数", "深证成指", "创业板指")
            ],
        )

    def get_stocks(self, query: str | None = None) -> StocksResponse:
        try:
            stock_snapshot, stale = self._load_snapshot(
                STOCK_SNAPSHOT_CACHE_KEY,
                self._refresh_stock_snapshot,
            )
        except Exception as exc:
            raise DataUnavailableError("stocks data is unavailable") from exc

        rows = self._filter_stock_rows(self._build_stock_rows(stock_snapshot), query)
        return StocksResponse(
            asOfDate=stock_snapshot.as_of_date,
            stale=stale,
            rows=rows,
        )
```

Keep the current composition behavior intentionally narrow: only upstream refresh failures may fall back to stale cached data; formatting or composition errors after a snapshot is loaded should still propagate.

- [ ] **Step 4: Run the service tests again**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_market_service.py -q
```

Expected: PASS with the existing failure tests still green and the new TTL/call-count tests passing.

- [ ] **Step 5: Commit the shared raw-snapshot service refactor**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/financehub_market_api/service.py backend/tests/test_market_service.py
git commit -m "feat: share raw market snapshots across endpoints"
```

## Task 3: Expand the curated watchlist and assert broader stock coverage

**Files:**
- Modify: `backend/financehub_market_api/watchlist.py:14-23`
- Modify: `backend/tests/test_market_service.py:1-221`
- Modify: `backend/tests/test_package_smoke.py:1-8`

- [ ] **Step 1: Write the failing coverage tests for the expanded stock pool**

Extend `backend/tests/test_market_service.py` with a coverage assertion that uses the already generalized `_build_stock_snapshot()` helper:

```python
def test_get_stocks_returns_full_watchlist_and_filters_multiple_china_names() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 9, 30, tzinfo=UTC))
    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=SnapshotCache(ttl_seconds=300, now=clock.now),
    )

    stocks = service.get_stocks()
    filtered = service.get_stocks(query="中国")

    assert len(stocks.rows) == len(WATCHLIST)
    assert len(stocks.rows) >= 20
    assert {"宁德时代", "贵州茅台", "中芯国际", "中国移动"} <= {
        row.name for row in stocks.rows
    }
    assert [row.name for row in filtered.rows] == [
        "中国平安",
        "中国移动",
        "中国石油",
        "中国神华",
    ]
```

Tighten `backend/tests/test_package_smoke.py` to assert the expanded curated universe directly:

```python
from financehub_market_api.models import MetricCard
from financehub_market_api.watchlist import WATCHLIST


def test_backend_package_smoke_imports() -> None:
    card = MetricCard(label="test", value="1", delta="+0%", tone="neutral")

    assert card.label == "test"
    assert len(WATCHLIST) >= 20
    assert WATCHLIST[0].name == "宁德时代"
    assert any(entry.name == "中国移动" for entry in WATCHLIST)
```

- [ ] **Step 2: Run the targeted coverage tests and confirm the current 8-name list fails**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_market_service.py tests/test_package_smoke.py -q
```

Expected: FAIL on assertions such as `assert len(WATCHLIST) >= 20`.

- [ ] **Step 3: Expand `WATCHLIST` to the approved representative set**

Modify `backend/financehub_market_api/watchlist.py` to keep the existing first eight entries in place and append the new names:

```python
WATCHLIST: tuple[WatchlistEntry, ...] = (
    WatchlistEntry(code="300750", symbol="SZ300750", name="宁德时代", sector="新能源"),
    WatchlistEntry(code="002594", symbol="SZ002594", name="比亚迪", sector="汽车"),
    WatchlistEntry(code="600519", symbol="SH600519", name="贵州茅台", sector="白酒"),
    WatchlistEntry(code="600036", symbol="SH600036", name="招商银行", sector="银行"),
    WatchlistEntry(code="601318", symbol="SH601318", name="中国平安", sector="保险"),
    WatchlistEntry(code="600900", symbol="SH600900", name="长江电力", sector="公用事业"),
    WatchlistEntry(code="000333", symbol="SZ000333", name="美的集团", sector="家电"),
    WatchlistEntry(code="300059", symbol="SZ300059", name="东方财富", sector="金融科技"),
    WatchlistEntry(code="000858", symbol="SZ000858", name="五粮液", sector="白酒"),
    WatchlistEntry(code="600887", symbol="SH600887", name="伊利股份", sector="食品饮料"),
    WatchlistEntry(code="603288", symbol="SH603288", name="海天味业", sector="食品饮料"),
    WatchlistEntry(code="600030", symbol="SH600030", name="中信证券", sector="券商"),
    WatchlistEntry(code="000651", symbol="SZ000651", name="格力电器", sector="家电"),
    WatchlistEntry(code="688981", symbol="SH688981", name="中芯国际", sector="半导体"),
    WatchlistEntry(code="688041", symbol="SH688041", name="海光信息", sector="半导体"),
    WatchlistEntry(code="002475", symbol="SZ002475", name="立讯精密", sector="电子"),
    WatchlistEntry(code="600276", symbol="SH600276", name="恒瑞医药", sector="医药"),
    WatchlistEntry(code="300760", symbol="SZ300760", name="迈瑞医疗", sector="医疗器械"),
    WatchlistEntry(code="603259", symbol="SH603259", name="药明康德", sector="医药服务"),
    WatchlistEntry(code="601138", symbol="SH601138", name="工业富联", sector="先进制造"),
    WatchlistEntry(code="600941", symbol="SH600941", name="中国移动", sector="通信运营"),
    WatchlistEntry(code="601857", symbol="SH601857", name="中国石油", sector="能源"),
    WatchlistEntry(code="601088", symbol="SH601088", name="中国神华", sector="煤炭"),
    WatchlistEntry(code="601899", symbol="SH601899", name="紫金矿业", sector="有色金属"),
)
```

- [ ] **Step 4: Run the watchlist-focused verification**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest tests/test_package_smoke.py tests/test_stock_snapshot_service.py tests/test_market_service.py -q
```

Expected: PASS, with stock-row formatting tests unchanged and the new coverage assertions green.

- [ ] **Step 5: Commit the expanded watchlist**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/financehub_market_api/watchlist.py backend/tests/test_market_service.py backend/tests/test_package_smoke.py
git commit -m "feat: expand curated china stock watchlist"
```

## Task 4: Run full backend verification and capture the final state

**Files:**
- No code changes

- [ ] **Step 1: Run the full backend test suite**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
python3 -m pytest -q
```

Expected: PASS for the full backend suite, including `test_api.py`, `test_dolthub_client.py`, `test_index_data_client.py`, `test_stock_snapshot_service.py`, `test_cache.py`, and `test_market_service.py`.

- [ ] **Step 2: Inspect the working tree before handing off**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git status --short
```

Expected: no unexpected modified files outside the backend cache/watchlist/service/test scope.
