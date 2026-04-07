# Persisted Market Data Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the market overview, stocks, and indices pages render immediately from persisted browser data while refreshing in the background, and back the server snapshot cache with Redis.

**Architecture:** Replace the current page-local fetch-on-mount flow with a shared front-end market-data provider that hydrates `localStorage` on app startup and refreshes all three market resources in the background. Replace the current process-local Python snapshot cache with a Redis-backed cache that preserves the existing fresh-versus-stale fallback semantics through the same `get/peek/put/delete` interface.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, FastAPI, pytest, redis-py, localStorage

---

### Task 1: Add a Redis-backed market snapshot cache behind the existing back-end cache boundary

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/financehub_market_api/cache.py`
- Modify: `backend/financehub_market_api/main.py`
- Test: `backend/tests/test_cache.py`

- [ ] **Step 1: Write the failing back-end tests for Redis envelope freshness and fallback semantics**

Add Redis-specific cache tests next to the existing `SnapshotCache` tests so the desired behavior is locked in before production code changes.

```python
def test_redis_snapshot_cache_returns_fresh_value_before_fresh_until() -> None:
    clock = MutableClock(datetime(2026, 4, 6, 9, 0, tzinfo=UTC))
    redis_client = FakeRedisClient()
    cache = RedisSnapshotCache(
        redis_client,
        ttl_seconds=300,
        retain_seconds=1_209_600,
        now=clock.now,
    )

    cache.put("market:overview", {"asOfDate": "2026-04-03"})

    assert cache.get("market:overview") == {"asOfDate": "2026-04-03"}
    assert cache.peek("market:overview") == {"asOfDate": "2026-04-03"}
```

```python
def test_redis_snapshot_cache_returns_none_after_fresh_expiry_but_peek_keeps_value() -> None:
    clock = MutableClock(datetime(2026, 4, 6, 9, 0, tzinfo=UTC))
    redis_client = FakeRedisClient()
    cache = RedisSnapshotCache(
        redis_client,
        ttl_seconds=300,
        retain_seconds=1_209_600,
        now=clock.now,
    )

    cache.put("market:overview", {"asOfDate": "2026-04-03"})
    clock.advance(seconds=301)

    assert cache.get("market:overview") is None
    assert cache.peek("market:overview") == {"asOfDate": "2026-04-03"}
```

```python
def test_build_snapshot_cache_uses_redis_when_url_is_configured() -> None:
    cache = build_snapshot_cache(
        environ={"FINANCEHUB_MARKET_CACHE_REDIS_URL": "redis://localhost:6379/0"},
        redis_factory=lambda url: FakeRedisClient(url=url),
    )

    assert isinstance(cache, RedisSnapshotCache)
```

- [ ] **Step 2: Run the narrow back-end tests and verify they fail for the right reason**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend && pytest -q tests/test_cache.py`

Expected: FAIL because `RedisSnapshotCache` and `build_snapshot_cache()` do not exist yet.

- [ ] **Step 3: Implement the minimal Redis cache support**

Add `redis` to the Python dependencies, keep the existing in-memory `SnapshotCache` intact for tests and narrow fallbacks, and introduce a Redis-backed implementation with the same `get/peek/put/delete` surface.

```python
class RedisSnapshotCache:
    def __init__(
        self,
        redis_client: RedisLike,
        ttl_seconds: int = 300,
        retain_seconds: int = 1_209_600,
        now: Callable[[], datetime] | None = None,
        key_prefix: str = "financehub:market:",
    ) -> None:
        ...

    def get(self, key: str) -> object | None:
        envelope = self._read_envelope(key)
        if envelope is None or self._now() > envelope.retain_at:
            self.delete(key)
            return None
        if self._now() > envelope.fresh_until:
            return None
        return envelope.value

    def peek(self, key: str) -> object | None:
        envelope = self._read_envelope(key)
        if envelope is None or self._now() > envelope.retain_at:
            self.delete(key)
            return None
        return envelope.value
```

```python
def build_snapshot_cache(
    *,
    environ: Mapping[str, str] | None = None,
    redis_factory: Callable[[str], RedisLike] | None = None,
) -> SnapshotCache | RedisSnapshotCache:
    env = dict(os.environ if environ is None else environ)
    redis_url = env.get("FINANCEHUB_MARKET_CACHE_REDIS_URL", "").strip()
    if not redis_url:
        return SnapshotCache()
    factory = redis_factory or (lambda url: Redis.from_url(url, decode_responses=True))
    return RedisSnapshotCache(factory(redis_url))
```

Then switch `main.py` to call `build_snapshot_cache()` when constructing `MarketDataService`.

- [ ] **Step 4: Run the same back-end tests and verify they pass**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell/backend && pytest -q tests/test_cache.py tests/test_market_service.py tests/test_api.py`

Expected: PASS with the new Redis cache coverage plus the existing market service and API suite.

- [ ] **Step 5: Commit the back-end cache change**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add backend/pyproject.toml \
  backend/financehub_market_api/cache.py \
  backend/financehub_market_api/main.py \
  backend/tests/test_cache.py
git commit -m "feat(cache): add redis-backed market snapshot cache"
```

### Task 2: Build a shared front-end market data provider with persisted localStorage hydration

**Files:**
- Create: `src/app/state/market-data.ts`
- Create: `src/app/state/MarketDataProvider.tsx`
- Test: `src/app/state/MarketDataProvider.test.tsx`
- Modify: `src/app/App.tsx`

- [ ] **Step 1: Write the failing provider tests for cache hydration and background refresh**

Create a focused provider test file that exercises the provider directly instead of relying on page-specific UI.

```tsx
it("hydrates overview data from localStorage before network refresh resolves", async () => {
  window.localStorage.setItem(
    "financehub.market.overview",
    JSON.stringify({
      version: 1,
      resource: "overview",
      savedAt: "2026-04-06T00:00:00.000Z",
      data: {
        asOfDate: "2026-04-03",
        stale: false,
        metrics: [{ label: "上证指数", value: "3,880.10", delta: "-1.00%", changeValue: -39.18, changePercent: -1.0, tone: "negative" }],
        chartLabel: "上证指数",
        trendSeries: [{ date: "2026-04-03", value: 3880.1 }],
        topGainers: [],
        topLosers: [],
      },
    }),
  );

  const fetchDeferred = createDeferred<Response>();
  vi.stubGlobal("fetch", vi.fn(() => fetchDeferred.promise));

  render(
    <AppStateProvider>
      <MarketDataProvider>
        <MarketDataProbe resource="overview" />
      </MarketDataProvider>
    </AppStateProvider>,
  );

  expect(screen.getByTestId("resource-source")).toHaveTextContent("storage");
  expect(screen.getByTestId("resource-value")).toHaveTextContent("3,880.10");
});
```

```tsx
it("drops expired local snapshots and waits for network data", async () => {
  window.localStorage.setItem(
    "financehub.market.overview",
    JSON.stringify({
      version: 1,
      resource: "overview",
      savedAt: "2026-03-01T00:00:00.000Z",
      data: { asOfDate: "2026-03-01", stale: false, metrics: [], chartLabel: "上证指数", trendSeries: [], topGainers: [], topLosers: [] },
    }),
  );

  vi.stubGlobal("fetch", vi.fn(() => jsonResponse(buildOverviewPayload())));

  render(
    <AppStateProvider>
      <MarketDataProvider>
        <MarketDataProbe resource="overview" />
      </MarketDataProvider>
    </AppStateProvider>,
  );

  expect(screen.getByTestId("resource-status")).toHaveTextContent("loading");
  expect(await screen.findByTestId("resource-source")).toHaveTextContent("network");
});
```

- [ ] **Step 2: Run the new provider test file and verify it fails**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && npm test -- src/app/state/MarketDataProvider.test.tsx --run`

Expected: FAIL because `MarketDataProvider`, `useMarketData`, and the persistence helpers do not exist yet.

- [ ] **Step 3: Implement the minimal shared provider and storage envelope helpers**

Create a market-data context with one resource entry per endpoint, hydrate initial state from `localStorage`, then kick off exactly one background refresh per resource on provider mount.

```ts
export type MarketResourceKey = "overview" | "indices" | "stocks";

export interface MarketResourceState<T> {
  data: T | null;
  error: string | null;
  loadStatus: "idle" | "loading" | "ready" | "error";
  refreshStatus: "idle" | "refreshing" | "failed";
  source: "storage" | "network" | null;
  lastHydratedAt: string | null;
}
```

```tsx
const initialMarketState = {
  overview: hydrateResource("overview"),
  indices: hydrateResource("indices"),
  stocks: hydrateResource("stocks"),
};

useEffect(() => {
  void refreshResource("overview", fetchMarketOverview);
  void refreshResource("indices", fetchIndices);
  void refreshResource("stocks", fetchStocks);
}, [refreshResource]);
```

Wrap `AppRouter` with `MarketDataProvider` in `App.tsx` so the store survives route changes.

- [ ] **Step 4: Run the provider test file and route shell test to verify the provider passes**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && npm test -- src/app/state/MarketDataProvider.test.tsx src/app/App.test.tsx --run`

Expected: PASS for the new provider behavior, with no route regressions from adding the provider wrapper.

- [ ] **Step 5: Commit the provider and hydration layer**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add src/app/state/market-data.ts \
  src/app/state/MarketDataProvider.tsx \
  src/app/state/MarketDataProvider.test.tsx \
  src/app/App.tsx
git commit -m "feat(market-data): add persisted front-end market data provider"
```

### Task 3: Move the market pages onto the shared provider and add cache-aware UI coverage

**Files:**
- Modify: `src/features/market-overview/MarketOverviewPage.tsx`
- Modify: `src/features/market-overview/MarketOverviewPage.test.tsx`
- Modify: `src/features/chinese-stocks/ChineseStocksPage.tsx`
- Modify: `src/features/chinese-stocks/ChineseStocksPage.test.tsx`
- Modify: `src/features/chinese-indices/ChineseIndicesPage.tsx`
- Modify: `src/features/chinese-indices/ChineseIndicesPage.test.tsx`
- Modify: `src/app/App.test.tsx`
- Modify: `src/i18n/messages.ts`
- Modify: `src/i18n/locales/zh-CN.ts`
- Modify: `src/i18n/locales/en-US.ts`

- [ ] **Step 1: Write the failing page and route tests for cached rendering and refresh-failure fallback**

Update the three market page tests so they consume provider state instead of page-local fetch state, then add one route-shell test proving cached market content renders before a slow network response resolves.

```tsx
it("renders overview data from persisted cache without blocking loading", () => {
  seedMarketStorage("overview", buildOverviewPayload());
  vi.stubGlobal("fetch", vi.fn(() => createDeferred<Response>().promise));

  render(
    <AppStateProvider>
      <MarketDataProvider>
        <MemoryRouter initialEntries={["/"]}>
          <MarketOverviewPage />
        </MemoryRouter>
      </MarketDataProvider>
    </AppStateProvider>,
  );

  expect(screen.getByText("上证指数")).toBeInTheDocument();
  expect(screen.queryByRole("status", { name: /正在加载市场数据/i })).not.toBeInTheDocument();
});
```

```tsx
it("keeps stale cached stocks visible when refresh fails", async () => {
  seedMarketStorage("stocks", STOCKS_PAYLOAD);
  vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ detail: "stocks data is unavailable" }, 503)));

  renderPageWithProviders("/stocks");

  expect(screen.getByText("宁德时代")).toBeInTheDocument();
  expect(await screen.findByRole("status")).toHaveTextContent("正在显示上次缓存数据");
});
```

```tsx
it("shows cached market content immediately after app restart", async () => {
  seedMarketStorage("overview", buildOverviewPayload());
  const deferredResponse = createDeferred<Response>();
  vi.stubGlobal("fetch", vi.fn(() => deferredResponse.promise));

  render(<App />);

  await userEvent.click(screen.getByRole("button", { name: "体验 Demo 账户" }));
  expect(screen.getByText("上证指数")).toBeInTheDocument();
  expect(screen.queryByText("正在加载市场数据")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused front-end tests and verify they fail**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && npm test -- src/features/market-overview/MarketOverviewPage.test.tsx src/features/chinese-stocks/ChineseStocksPage.test.tsx src/features/chinese-indices/ChineseIndicesPage.test.tsx src/app/App.test.tsx --run`

Expected: FAIL because the pages still own their own `useEffect` fetch flow and the locale files do not yet define cache-aware copy.

- [ ] **Step 3: Implement the minimal page migration and UI copy changes**

Remove the market fetch `useEffect` blocks from the three pages, read resource state from `useMarketData()`, and only show blocking loading when a resource has no cached or network data. Add new copy entries for the cache-warning state.

```tsx
const { overview } = useMarketData();

if (overview.loadStatus === "loading" && !overview.data) {
  return <DataStatusNotice title={messages.dataState.loading} tone="info" />;
}

if (overview.loadStatus === "error" && !overview.data) {
  return (
    <DataStatusNotice
      body={messages.dataState.errorBody}
      title={messages.dataState.errorTitle}
      tone="danger"
    />
  );
}
```

```tsx
{overview.data && overview.refreshStatus === "failed" ? (
  <DataStatusNotice title={messages.dataState.cachedLabel} tone="warning" />
) : null}
```

```ts
dataState: {
  loading: string;
  errorTitle: string;
  errorBody: string;
  staleLabel: string;
  cachedLabel: string;
}
```

- [ ] **Step 4: Run the same focused front-end tests and then the full app-facing suite**

Run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && npm test -- src/features/market-overview/MarketOverviewPage.test.tsx src/features/chinese-stocks/ChineseStocksPage.test.tsx src/features/chinese-indices/ChineseIndicesPage.test.tsx src/app/App.test.tsx --run`

Expected: PASS with market pages rendering from cache-aware shared state and the app route shell showing cached content immediately.

Then run: `cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell && npm test --run`

Expected: PASS for the full front-end suite.

- [ ] **Step 5: Commit the page migration**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add src/features/market-overview/MarketOverviewPage.tsx \
  src/features/market-overview/MarketOverviewPage.test.tsx \
  src/features/chinese-stocks/ChineseStocksPage.tsx \
  src/features/chinese-stocks/ChineseStocksPage.test.tsx \
  src/features/chinese-indices/ChineseIndicesPage.tsx \
  src/features/chinese-indices/ChineseIndicesPage.test.tsx \
  src/app/App.test.tsx \
  src/i18n/messages.ts \
  src/i18n/locales/zh-CN.ts \
  src/i18n/locales/en-US.ts
git commit -m "feat(market-data): render market pages from persisted shared cache"
```
