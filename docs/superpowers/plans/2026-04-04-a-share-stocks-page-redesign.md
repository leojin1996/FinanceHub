# A-Share Stocks Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the A-share stocks page into a reference-style full-width board, extend `/api/stocks` with volume, amount, and seven-day trend data, and keep filtering local and testable.

**Architecture:** Extend the existing FastAPI stocks contract instead of creating a new endpoint. Keep the current watchlist-driven backend flow, enrich the stock snapshot with latest `volume` and `amount` plus seven-day close history, and replace the page's generic `DataTable` usage with a stocks-page-specific table view that renders search, industry chips, change arrows, and sparklines.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, httpx, pytest, React, TypeScript, Vitest, Testing Library, existing FinanceHub i18n and CSS

---

## File Structure

- Modify: `backend/financehub_market_api/models.py` - expand the stock row schema with numeric display fields and seven-day trend points
- Modify: `backend/financehub_market_api/upstreams/dolthub.py` - fetch latest `close`, `volume`, `amount`, previous close, and seven-day series for the curated watchlist
- Modify: `backend/financehub_market_api/service.py` - build expanded stock rows, validate richer snapshots, and preserve stale fallback semantics
- Modify: `backend/tests/test_stock_snapshot_service.py` - add schema and stock-row helper coverage for the new fields
- Modify: `backend/tests/test_market_service.py` - cover expanded rows, trend completeness checks, and stale fallback behavior
- Modify: `backend/tests/test_api.py` - assert `/api/stocks` returns the expanded response model
- Modify: `src/services/chinaMarketApi.ts` - expand `StockRowData` types for raw numeric values and trend series
- Modify: `src/features/chinese-stocks/ChineseStocksPage.tsx` - replace generic table usage with a dedicated stocks board
- Modify: `src/features/chinese-stocks/ChineseStocksPage.test.tsx` - assert filter chips, stale state, and expanded cells
- Modify: `src/features/chinese-stocks/StockFilters.tsx` - support the new search-plus-industry layout or fold the logic into the page if that keeps the diff smaller
- Modify: `src/styles/app-shell.css` - add stocks-board-specific layout, chip, and table styles
- Modify: `src/i18n/locales/zh-CN.ts` - add localized column and filter labels if needed by the redesigned page
- Modify: `src/i18n/locales/en-US.ts` - add localized column and filter labels if needed by the redesigned page

## Task 1: Lock the backend contract with failing tests

**Files:**
- Modify: `backend/tests/test_stock_snapshot_service.py`
- Modify: `backend/tests/test_market_service.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Add a failing schema test for the expanded stock row**

Add to `backend/tests/test_stock_snapshot_service.py`:

```python
def test_stock_row_schema_includes_numeric_fields_and_trend() -> None:
    schema = StockRow.model_json_schema()
    properties = schema["properties"]

    assert "priceValue" in properties
    assert "changePercent" in properties
    assert "volumeValue" in properties
    assert "amountValue" in properties
    assert "trend7d" in properties
```

- [ ] **Step 2: Add a failing stock-row construction test**

Add to `backend/tests/test_stock_snapshot_service.py`:

```python
def test_build_stock_rows_includes_volume_amount_and_trend() -> None:
    snapshot = StockPriceSnapshot(
        as_of_date="2026-04-01",
        latest_prices={"SZ300750": 188.55},
        previous_prices={"SZ300750": 177.54},
        latest_volumes={"SZ300750": 123456789.0},
        latest_amounts={"SZ300750": 2345678901.0},
        recent_closes={"SZ300750": [
            ("2026-03-24", 176.0),
            ("2026-03-25", 177.1),
            ("2026-03-26", 178.4),
            ("2026-03-27", 179.0),
            ("2026-03-28", 180.5),
            ("2026-03-31", 182.0),
            ("2026-04-01", 188.55),
        ]},
    )

    rows = build_stock_rows(WATCHLIST[:1], snapshot)

    assert rows[0].code == "300750"
    assert rows[0].priceValue == 188.55
    assert rows[0].changePercent > 0
    assert rows[0].volumeValue == 123456789.0
    assert rows[0].amountValue == 2345678901.0
    assert [point.date for point in rows[0].trend7d] == [
        "2026-03-24",
        "2026-03-25",
        "2026-03-26",
        "2026-03-27",
        "2026-03-28",
        "2026-03-31",
        "2026-04-01",
    ]
```

- [ ] **Step 3: Add a failing refresh-validation test for incomplete trend data**

Add to `backend/tests/test_market_service.py`:

```python
def test_get_stocks_rejects_snapshot_with_incomplete_trend_series() -> None:
    broken_snapshot = _build_stock_snapshot()
    broken_snapshot.recent_closes["SZ300750"] = broken_snapshot.recent_closes["SZ300750"][:6]

    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=broken_snapshot),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=SnapshotCache(),
    )

    with pytest.raises(IndexError):
        service.get_stocks()
```

- [ ] **Step 4: Add a failing API-response test for the expanded payload**

Update `backend/tests/test_api.py` with a `StocksResponse` fixture row that includes:

```python
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
```

Then assert:

```python
assert payload["rows"][0]["amountValue"] == 2345678901.0
assert len(payload["rows"][0]["trend7d"]) == 7
```

- [ ] **Step 5: Run the targeted backend tests and confirm they fail for the right reason**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
pytest -q tests/test_stock_snapshot_service.py tests/test_market_service.py tests/test_api.py
```

Expected: failures referencing missing `priceValue`, `volumeValue`, `amountValue`, `trend7d`, or outdated `StockPriceSnapshot` fields.

## Task 2: Implement the expanded stock snapshot and response model

**Files:**
- Modify: `backend/financehub_market_api/models.py`
- Modify: `backend/financehub_market_api/upstreams/dolthub.py`
- Modify: `backend/financehub_market_api/service.py`

- [ ] **Step 1: Expand the backend models**

Update `backend/financehub_market_api/models.py` so `StockRow` becomes:

```python
class StockRow(BaseModel):
    code: str
    name: str
    sector: str
    price: str
    change: str
    priceValue: float
    changePercent: float
    volumeValue: float
    amountValue: float
    trend7d: list[TrendPoint]
    _raw_change: float = PrivateAttr(default=0.0)
```

- [ ] **Step 2: Expand the upstream stock snapshot**

Update `backend/financehub_market_api/upstreams/dolthub.py` so `StockPriceSnapshot` includes:

```python
@dataclass(frozen=True)
class StockPriceSnapshot:
    as_of_date: str
    latest_prices: dict[str, float]
    previous_prices: dict[str, float]
    latest_volumes: dict[str, float]
    latest_amounts: dict[str, float]
    recent_closes: dict[str, list[tuple[str, float]]]
```

Extend `fetch_watchlist_prices()` to query:

- latest trading date
- previous trading date
- latest row values for `close`, `volume`, and `amount`
- latest seven trading dates of `close` per symbol

Keep the return shape normalized by symbol and raise `ValueError` if any tracked symbol is missing latest, previous, volume, amount, or seven closes.

- [ ] **Step 3: Refactor stock-row construction to consume the richer snapshot**

Update `backend/financehub_market_api/service.py`:

```python
def build_stock_rows(
    entries: Iterable[WatchlistEntry],
    snapshot: StockPriceSnapshot,
) -> list[StockRow]:
    rows: list[StockRow] = []

    for entry in entries:
        latest = snapshot.latest_prices[entry.symbol]
        previous = snapshot.previous_prices[entry.symbol]
        raw_change = _raw_change_percent(latest, previous)
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
        rows.append(row)

    return rows
```

Also update:

- `_validate_stock_snapshot()` to require numeric `latest_volumes`, `latest_amounts`, and exactly seven `recent_closes` items per symbol
- `_build_stock_rows()` to call `build_stock_rows(WATCHLIST, stock_snapshot)`

- [ ] **Step 4: Run the targeted backend tests and confirm they pass**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
pytest -q tests/test_stock_snapshot_service.py tests/test_market_service.py tests/test_api.py
```

Expected: all targeted backend tests pass.

## Task 3: Lock the redesigned stocks page with failing front-end tests

**Files:**
- Modify: `src/features/chinese-stocks/ChineseStocksPage.test.tsx`
- Modify: `src/services/chinaMarketApi.ts`

- [ ] **Step 1: Expand the test payload shape**

Update the mocked `/api/stocks` payload in `src/features/chinese-stocks/ChineseStocksPage.test.tsx` so each row includes:

```ts
{
  code: "300750",
  name: "宁德时代",
  sector: "新能源",
  price: "188.55",
  change: "+6.2%",
  priceValue: 188.55,
  changePercent: 6.2,
  volumeValue: 123456789,
  amountValue: 2345678901,
  trend7d: [
    { date: "2026-03-24", value: 176.0 },
    { date: "2026-03-25", value: 177.1 },
    { date: "2026-03-26", value: 178.4 },
    { date: "2026-03-27", value: 179.0 },
    { date: "2026-03-28", value: 180.5 },
    { date: "2026-03-31", value: 182.0 },
    { date: "2026-04-01", value: 188.55 },
  ],
}
```

- [ ] **Step 2: Write a failing rendering-and-filter test**

Replace the current single-page assertion with tests like:

```ts
it("renders industry chips, expanded columns, and stale data", async () => {
  renderPage();

  expect(await screen.findByRole("columnheader", { name: "成交额" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "全部" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "新能源" })).toBeInTheDocument();
  expect(screen.getByText("最近可用收盘数据: 2026-04-01")).toBeInTheDocument();
});

it("filters rows by industry chip", async () => {
  const user = userEvent.setup();
  renderPage();

  await screen.findByText("宁德时代");
  await user.click(screen.getByRole("button", { name: "汽车" }));

  expect(screen.queryByText("宁德时代")).not.toBeInTheDocument();
  expect(screen.getByText("比亚迪")).toBeInTheDocument();
});
```

- [ ] **Step 3: Write a failing localized-number test**

Add:

```ts
it("formats volume and amount with Chinese units in zh-CN", async () => {
  renderPage();

  expect(await screen.findByText("1.23亿")).toBeInTheDocument();
  expect(screen.getByText("23.46亿")).toBeInTheDocument();
});
```

- [ ] **Step 4: Run the targeted front-end test and confirm it fails**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npm test -- ChineseStocksPage.test.tsx
```

Expected: failures because the current page still uses the generic table and does not render chips, amount, or localized units.

## Task 4: Implement the stocks-board UI and localized formatting

**Files:**
- Modify: `src/services/chinaMarketApi.ts`
- Modify: `src/features/chinese-stocks/ChineseStocksPage.tsx`
- Modify: `src/features/chinese-stocks/StockFilters.tsx`
- Modify: `src/styles/app-shell.css`
- Modify: `src/i18n/locales/zh-CN.ts`
- Modify: `src/i18n/locales/en-US.ts`

- [ ] **Step 1: Expand the front-end stock types**

Update `src/services/chinaMarketApi.ts`:

```ts
export interface StockRowData {
  code: string;
  name: string;
  sector: string;
  price: string;
  change: string;
  priceValue: number;
  changePercent: number;
  volumeValue: number;
  amountValue: number;
  trend7d: TrendPoint[];
}
```

- [ ] **Step 2: Add minimal formatting helpers and local filter state**

In `src/features/chinese-stocks/ChineseStocksPage.tsx`, add helpers for:

```ts
function formatChineseCompactNumber(value: number): string { /* 万 / 亿 */ }
function formatEnglishCompactNumber(value: number): string { /* K / M / B */ }
function formatMetric(locale: Locale, value: number): string { /* locale switch */ }
```

Track:

- `query`
- `selectedSector`

Derive:

- `availableSectors`
- `visibleRows`

- [ ] **Step 3: Replace the generic table with a page-specific board**

Render:

- search input on the left
- horizontally scrollable sector-chip rail on the right
- a full-width table with the columns from the approved spec
- non-interactive favorite markers
- sector pills
- inline SVG or CSS arrows for positive and negative change
- simple inline SVG sparklines derived from `trend7d`

Keep:

- existing `AppShell`
- existing `DataStatusNotice` loading, error, and stale states

Remove:

- the old right-side `InsightCard`
- the generic `DataTable` usage

- [ ] **Step 4: Add stocks-board-specific CSS**

Update `src/styles/app-shell.css` with styles for:

- `.stocks-board`
- `.stocks-board__filters`
- `.stocks-board__chip-rail`
- `.stocks-board__chip`
- `.stocks-board__table`
- `.stocks-board__change--positive`
- `.stocks-board__change--negative`
- `.stocks-board__sector-pill`
- `.stocks-board__sparkline`

The desktop layout should visually track the provided reference and preserve horizontal overflow on smaller screens.

- [ ] **Step 5: Run the targeted front-end test and confirm it passes**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npm test -- ChineseStocksPage.test.tsx
```

Expected: the stocks page test passes with the new board structure and filters.

## Task 5: Run focused verification and then broader regression checks

**Files:**
- Modify: `backend/tests/test_stock_snapshot_service.py`
- Modify: `backend/tests/test_market_service.py`
- Modify: `backend/tests/test_api.py`
- Modify: `src/features/chinese-stocks/ChineseStocksPage.test.tsx`
- Modify: any files touched above

- [ ] **Step 1: Run the focused backend suite**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend
pytest -q tests/test_stock_snapshot_service.py tests/test_market_service.py tests/test_api.py
```

Expected: PASS with zero failing tests.

- [ ] **Step 2: Run the focused front-end suite**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npm test -- ChineseStocksPage.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run a slightly broader front-end regression check**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npm test -- App.test.tsx
```

Expected: PASS, confirming the redesigned stocks page still integrates cleanly with app routing and shared shell behavior.

- [ ] **Step 4: Commit the implementation**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/financehub_market_api/models.py \
  backend/financehub_market_api/upstreams/dolthub.py \
  backend/financehub_market_api/service.py \
  backend/tests/test_stock_snapshot_service.py \
  backend/tests/test_market_service.py \
  backend/tests/test_api.py \
  src/services/chinaMarketApi.ts \
  src/features/chinese-stocks/ChineseStocksPage.tsx \
  src/features/chinese-stocks/ChineseStocksPage.test.tsx \
  src/features/chinese-stocks/StockFilters.tsx \
  src/styles/app-shell.css \
  src/i18n/locales/zh-CN.ts \
  src/i18n/locales/en-US.ts
git commit -m "Redesign A-share stocks page"
```
