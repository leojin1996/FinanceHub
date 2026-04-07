# China Indices Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current China indices comparison page with a four-card reference-style indices grid backed by an expanded `/api/indices` contract that includes `科创50` and real recent-close sparkline data.

**Architecture:** Expand the backend index snapshot metadata and `/api/indices` response so the service returns four card-ready index objects in fixed order. Then rebuild the `ChineseIndicesPage` as an indices-specific 2x2 card grid that consumes `cards[]` directly, renders per-card area charts, and keeps the shared shell, loading/error/stale notices, and nav behavior intact.

**Tech Stack:** FastAPI, Pydantic, AkShare, pytest, React, TypeScript, Vitest, Testing Library, Recharts, app-shell CSS

---

### Task 1: Expand the backend indices contract and cover it with tests

**Files:**
- Modify: `backend/financehub_market_api/models.py`
- Modify: `backend/financehub_market_api/service.py`
- Modify: `backend/financehub_market_api/upstreams/index_data.py`
- Test: `backend/tests/test_market_service.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write the failing backend tests for the new `cards[]` response**

Add assertions that `get_indices()` and `GET /api/indices` return four fixed-order cards with `科创50`, metadata, signed change values, tone, and trend series. Replace the old `series` expectations with card-based ones.

```python
def test_get_endpoints_return_fresh_payloads() -> None:
    service = MarketDataService(
        stock_client=FakeStockClient(snapshot=_build_stock_snapshot()),
        index_client=FakeIndexClient(snapshots=_build_index_snapshots()),
        cache=SnapshotCache(),
    )

    indices = service.get_indices()

    assert isinstance(indices, IndicesResponse)
    assert indices.stale is False
    assert [card.name for card in indices.cards] == [
        "上证指数",
        "深证成指",
        "创业板指",
        "科创50",
    ]
    assert indices.cards[0].code == "000001.SH"
    assert indices.cards[0].market == "中国市场"
    assert indices.cards[0].description == "沪市核心宽基指数"
    assert indices.cards[0].value == "3,245.50"
    assert indices.cards[0].valueNumber == pytest.approx(3245.5)
    assert indices.cards[0].changeValue == pytest.approx(7.3)
    assert indices.cards[0].changePercent == pytest.approx(0.2254, abs=1e-4)
    assert indices.cards[0].tone == "positive"
    assert indices.cards[0].trendSeries[-1].date == "2026-04-01"
```

```python
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
    assert payload["cards"][3]["code"] == "000688.SH"
    assert payload["cards"][3]["description"] == "科创板核心龙头指数"
    assert payload["cards"][3]["trendSeries"][-1]["date"] == "2026-04-01"
```

- [ ] **Step 2: Run the narrow backend tests and verify they fail for the right reason**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend && pytest -q tests/test_market_service.py tests/test_api.py -k "indices or endpoints"`

Expected: FAIL because `IndicesResponse` still exposes `series` instead of `cards`, and `科创50` is not yet part of the snapshot set.

- [ ] **Step 3: Implement the minimal backend contract changes**

Add new models for an index card payload, extend the index metadata table to include `科创50`, and update `MarketDataService.get_indices()` to build four cards in fixed order from recent closes.

```python
class IndexCard(BaseModel):
    name: str
    code: str
    market: str
    description: str
    value: str
    valueNumber: float
    changeValue: float
    changePercent: float
    tone: Tone
    trendSeries: list[TrendPoint]


class IndicesResponse(BaseModel):
    asOfDate: str
    stale: bool
    cards: list[IndexCard]
```

```python
INDEX_CONFIG = {
    "上证指数": {"ak_symbol": "sh000001", "code": "000001.SH", "description": "沪市核心宽基指数"},
    "深证成指": {"ak_symbol": "sz399001", "code": "399001.SZ", "description": "深市代表性综合指数"},
    "创业板指": {"ak_symbol": "sz399006", "code": "399006.SZ", "description": "成长风格代表指数"},
    "科创50": {"ak_symbol": "sh000688", "code": "000688.SH", "description": "科创板核心龙头指数"},
}
```

```python
def get_indices(self) -> IndicesResponse:
    try:
        index_snapshots, stale = self._load_cached_snapshot(
            "index-snapshots",
            self._refresh_index_snapshots,
            _validate_index_snapshots,
        )
    except _SnapshotRefreshError as exc:
        raise DataUnavailableError("indices data is unavailable") from exc

    cards = []
    for index_name in ("上证指数", "深证成指", "创业板指", "科创50"):
        closes = index_snapshots[index_name].closes
        latest = closes[-1][1]
        previous = closes[-2][1]
        meta = INDEX_CONFIG[index_name]
        cards.append(
            IndexCard(
                name=index_name,
                code=meta.code,
                market="中国市场",
                description=meta.description,
                value=f"{latest:,.2f}",
                valueNumber=latest,
                changeValue=latest - previous,
                changePercent=_raw_change_percent(latest, previous),
                tone="positive" if latest > previous else "negative" if latest < previous else "neutral",
                trendSeries=[TrendPoint(date=date, value=value) for date, value in closes],
            )
        )

    return IndicesResponse(
        asOfDate=index_snapshots["上证指数"].as_of_date,
        stale=stale,
        cards=cards,
    )
```

- [ ] **Step 4: Run the same backend tests and verify they pass**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend && pytest -q tests/test_market_service.py tests/test_api.py -k "indices or endpoints"`

Expected: PASS with the new card-based response and four configured indices.

- [ ] **Step 5: Commit the backend contract change**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/financehub_market_api/models.py \
  backend/financehub_market_api/service.py \
  backend/financehub_market_api/upstreams/index_data.py \
  backend/tests/test_market_service.py \
  backend/tests/test_api.py
git commit -m "feat(indices): expand indices cards payload"
```

### Task 2: Rebuild the front-end indices page as a four-card grid with TDD

**Files:**
- Modify: `src/services/chinaMarketApi.ts`
- Modify: `src/features/chinese-indices/ChineseIndicesPage.tsx`
- Modify: `src/features/chinese-indices/ChineseIndicesPage.test.tsx`
- Modify: `src/styles/app-shell.css`
- Optionally delete or stop using: `src/features/chinese-indices/IndexComparisonPanel.tsx`

- [ ] **Step 1: Write the failing page tests for four cards and the new layout**

Replace the old comparison-panel assertions with tests that expect four cards, the fixed index order, positive/negative styling, and no old comparison/insight content.

```tsx
it("renders four index cards with per-card charts", async () => {
  render(
    <AppStateProvider>
      <MemoryRouter initialEntries={["/indices"]}>
        <ChineseIndicesPage />
      </MemoryRouter>
    </AppStateProvider>,
  );

  expect(screen.getByRole("status")).toHaveTextContent("正在加载市场数据");
  expect(await screen.findByRole("heading", { name: "上证指数" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "深证成指" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "创业板指" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "科创50" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "指数对比" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "指数洞察" })).not.toBeInTheDocument();
  expect(screen.getAllByTestId("indices-card-chart")).toHaveLength(4);
});
```

```tsx
it("renders signed move styling from tone data", async () => {
  render(
    <AppStateProvider>
      <MemoryRouter initialEntries={["/indices"]}>
        <ChineseIndicesPage />
      </MemoryRouter>
    </AppStateProvider>,
  );

  const positiveMove = await screen.findByText(/^\+7\.30 \(\+0\.23%\)$/);
  const negativeMove = screen.getByText(/^-3\.60 \(-0\.17%\)$/);

  expect(positiveMove.className).toContain("indices-card__change--positive");
  expect(negativeMove.className).toContain("indices-card__change--negative");
});
```

- [ ] **Step 2: Run the indices page test and verify it fails**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && npm test -- src/features/chinese-indices/ChineseIndicesPage.test.tsx --run`

Expected: FAIL because the client still expects `series` and the page still renders the old comparison/insight layout.

- [ ] **Step 3: Implement the minimal front-end API and page changes**

Extend the front-end API types to `cards[]`, add page-local helpers for signed change text and chart domain, and rebuild the page into a dedicated 2x2 card grid with per-card area charts.

```ts
export interface IndexCardData {
  name: string;
  code: string;
  market: string;
  description: string;
  value: string;
  valueNumber: number;
  changeValue: number;
  changePercent: number;
  tone: "positive" | "negative" | "neutral";
  trendSeries: TrendPoint[];
}

export interface IndicesResponse {
  asOfDate: string;
  stale: boolean;
  cards: IndexCardData[];
}
```

```tsx
function IndexCard({ card }: { card: IndexCardData }) {
  const gradientId = `indices-gradient-${card.code.replace(/\W/g, "").toLowerCase()}`;

  return (
    <article className="panel indices-card">
      <div className="indices-card__header">
        <div>
          <h2>{card.name}</h2>
          <p className="indices-card__meta">
            <span>{card.code}</span>
            <span>•</span>
            <span>{card.market}</span>
          </p>
          <p className="indices-card__description">{card.description}</p>
        </div>
        <div className="indices-card__value-block">
          <strong>{card.value}</strong>
          <span className={`indices-card__change indices-card__change--${card.tone}`}>
            {formatIndexMove(card.changeValue, card.changePercent)}
          </span>
        </div>
      </div>
      <div className="indices-card__chart" data-testid="indices-card-chart">
        <ResponsiveContainer height={250} width="100%">
          <AreaChart data={card.trendSeries}>
            <defs>
              <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={toneColor(card.tone)} stopOpacity={0.28} />
                <stop offset="100%" stopColor={toneColor(card.tone)} stopOpacity={0.04} />
              </linearGradient>
            </defs>
            <CartesianGrid opacity={0.45} stroke="var(--fh-border)" strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={formatShortTrendDate} tickLine={false} />
            <YAxis domain={buildWideCardDomain(card.trendSeries)} tickLine={false} />
            <Area dataKey="value" fill={`url(#${gradientId})`} stroke={toneColor(card.tone)} type="monotone" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </article>
  );
}
```

```css
.chinese-indices__grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.indices-card {
  display: grid;
  gap: 1.25rem;
  padding: 1.75rem 2rem;
}

.indices-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
}
```

- [ ] **Step 4: Run the indices page test again and verify it passes**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && npm test -- src/features/chinese-indices/ChineseIndicesPage.test.tsx --run`

Expected: PASS with four cards, new styling, and no old comparison panel.

- [ ] **Step 5: Commit the front-end page redesign**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add src/services/chinaMarketApi.ts \
  src/features/chinese-indices/ChineseIndicesPage.tsx \
  src/features/chinese-indices/ChineseIndicesPage.test.tsx \
  src/styles/app-shell.css
git commit -m "feat(indices): redesign china indices page"
```

### Task 3: Update route-level shell tests and run focused verification

**Files:**
- Modify: `src/app/App.test.tsx`
- Verify: `backend/tests/test_market_service.py`
- Verify: `backend/tests/test_api.py`
- Verify: `src/features/chinese-indices/ChineseIndicesPage.test.tsx`
- Verify: `src/app/App.test.tsx`

- [ ] **Step 1: Write the failing route-level test expectations for the new indices payload**

Update the `/api/indices` mock in `App.test.tsx` to return `cards[]` and assert the route still mounts with the indices nav tab active while showing the new card headings.

```tsx
if (url.endsWith("/api/indices")) {
  return jsonResponse({
    asOfDate: "2026-04-01",
    stale: false,
    cards: [
      {
        name: "上证指数",
        code: "000001.SH",
        market: "中国市场",
        description: "沪市核心宽基指数",
        value: "3,245.50",
        valueNumber: 3245.5,
        changeValue: 7.3,
        changePercent: 0.2254,
        tone: "positive",
        trendSeries: [
          { date: "2026-03-28", value: 3226.4 },
          { date: "2026-03-31", value: 3238.2 },
          { date: "2026-04-01", value: 3245.5 },
        ],
      },
    ],
  });
}
```

```tsx
it("navigates to the indices page with the indices tab active", async () => {
  render(<App />);
  const user = userEvent.setup();

  await user.click(screen.getByRole("link", { name: "指数" }));

  expect(await screen.findByRole("heading", { name: "中国指数" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "上证指数" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "指数" })).toHaveClass("is-active");
});
```

- [ ] **Step 2: Run the route-level test and verify it fails**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && npm test -- src/app/App.test.tsx --run`

Expected: FAIL until the mock payload and mounted page expectations are updated to the new `cards[]` contract.

- [ ] **Step 3: Implement the minimal route-test and fixture updates**

Align the `/api/indices` mock shape and the route assertions with the new page contract, without changing unrelated routes.

```tsx
expect(await screen.findByRole("heading", { name: "上证指数" })).toBeInTheDocument();
expect(screen.getByRole("heading", { name: "科创50" })).toBeInTheDocument();
expect(screen.queryByRole("heading", { name: "指数对比" })).not.toBeInTheDocument();
```

- [ ] **Step 4: Run focused verification for backend and frontend**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend && \
pytest -q tests/test_market_service.py tests/test_api.py

cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && \
npm test -- src/features/chinese-indices/ChineseIndicesPage.test.tsx src/app/App.test.tsx --run
```

Expected:

- backend tests PASS
- front-end indices and route tests PASS

- [ ] **Step 5: Commit the route-level test alignment**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add src/app/App.test.tsx
git commit -m "test(indices): align route shell coverage"
```

### Task 4: Final verification sweep for the changed surface

**Files:**
- Verify only; no planned file edits

- [ ] **Step 1: Run the full narrow verification suite for the touched surface**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend && \
pytest -q tests/test_market_service.py tests/test_api.py tests/test_index_data_client.py

cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && \
npm test -- src/features/chinese-indices/ChineseIndicesPage.test.tsx src/app/App.test.tsx --run
```

Expected:

- backend index-related tests PASS
- front-end indices-related tests PASS

- [ ] **Step 2: Run a production build to catch integration regressions**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && npm run build`

Expected: PASS, allowing existing chunk-size warnings if they are pre-existing and non-fatal.

- [ ] **Step 3: Summarize verification results before handing off**

Capture:

- exact commands run
- pass/fail outcomes
- any non-blocking warnings
- any known residual risks, such as card-chart appearance on very narrow screens

