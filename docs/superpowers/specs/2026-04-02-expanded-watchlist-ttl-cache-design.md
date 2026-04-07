# FinanceHub Expanded Watchlist And TTL Cache Design

## Goal

Expand the current representative A-share stock universe from a very small curated list to a broader but still reviewable set of roughly 20 to 30 core names, while reducing repeated upstream requests through a 5-minute backend cache.

This change should preserve the current lightweight product shape:

- the China stocks page still shows a curated stock table rather than full-market search
- the market overview page still derives movers from the curated stock set
- the front end should not gain new caching logic
- the backend remains a lightweight in-memory service without a database

## Scope

This design changes only the backend stock-universe definition and the backend caching behavior for runtime market-data fetches.

In scope:

- expanding the curated `WATCHLIST`
- introducing 5-minute TTL behavior in the backend cache
- caching raw upstream stock and index snapshots instead of only endpoint responses
- reducing duplicate upstream fetches across `/api/market-overview`, `/api/indices`, and `/api/stocks`
- backend tests for TTL, stale fallback, and expanded watchlist behavior

Out of scope:

- full-market stock coverage
- browser-side caching
- persistent cache storage across process restarts
- background refresh workers
- changes to the front-end page structure
- pagination or stock-pool management UI
- replacing the current recommendation or questionnaire data

## Current Product Context

The current runtime data flow already works end to end:

- FastAPI serves `/api/market-overview`, `/api/indices`, and `/api/stocks`
- the front end requests those endpoints at runtime
- upstream stock data comes from DoltHub-backed `investment_data`
- upstream index data comes from the current AkShare-backed adapter

The current stock universe is defined in:

- `backend/financehub_market_api/watchlist.py`

The current cache is intentionally simple:

- `backend/financehub_market_api/cache.py` stores untyped values by key
- `backend/financehub_market_api/service.py` caches endpoint-shaped payloads after successful refresh

This means:

- the curated stock set is still narrower than desired
- repeated endpoint requests can trigger repeated upstream fetches
- the cache does not enforce time-based expiry

## Chosen Product Direction

Chosen approach: keep the curated-universe model, expand it to a broader representative stock pool, and move the backend cache to 5-minute TTL caching of raw upstream snapshots.

This approach is preferred because it:

- matches the existing product contract
- keeps the front-end diff minimal
- reduces repeated DoltHub and index upstream calls
- preserves current stale-data semantics
- avoids the complexity of a full-market query system

## Stock Universe Strategy

The product continues to use a curated watchlist rather than a dynamic full-market screener.

Target size:

- approximately 24 representative stocks

Selection principle:

- industry coverage first
- within each industry, prefer the most recognizable or widely followed leaders

Expected coverage areas:

- new energy and EV supply chain
- semiconductors and electronics
- consumer staples and food and beverage
- banks, insurers, brokers, and financial platforms
- home appliances and advanced manufacturing
- pharmaceuticals and medical devices
- telecom, energy, utilities, metals, and other heavyweight state-owned or large-cap names

Representative candidates include, but are not limited to:

- 宁德时代
- 比亚迪
- 贵州茅台
- 五粮液
- 伊利股份
- 海天味业
- 招商银行
- 中国平安
- 中信证券
- 东方财富
- 美的集团
- 格力电器
- 中芯国际
- 海光信息
- 立讯精密
- 恒瑞医药
- 迈瑞医疗
- 药明康德
- 工业富联
- 中国移动
- 中国石油
- 长江电力
- 中国神华
- 紫金矿业

The exact final list should stay within the approved size range and prioritize data stability and recognizability over exhaustive sector completeness.

## Cache Direction

The cache remains backend-local and in-memory.

Chosen caching model:

- no browser cache
- no persistent disk cache
- no external cache service

The backend cache should be upgraded from plain key-value storage to TTL-aware entries:

- value
- stored-at timestamp
- expires-at timestamp

TTL:

- 300 seconds

This TTL applies to all runtime upstream-derived data in this phase.

## Cache Granularity

The cache should no longer optimize only endpoint-shaped payloads.

Instead, it should cache raw normalized upstream snapshots at the service boundary:

- `stock-snapshot`
- `index-snapshots`

These two cached inputs then become the shared source for:

- `get_market_overview()`
- `get_indices()`
- `get_stocks()`

This is important because:

- `get_market_overview()` and `get_stocks()` both depend on the same stock upstream data
- `get_market_overview()` and `get_indices()` both depend on the same index upstream data
- caching shared raw inputs avoids duplicate refreshes across endpoints during the same TTL window

## Service Behavior

The service should continue to expose the same response contracts, but its refresh logic should be reorganized around TTL-aware raw-snapshot reads.

Preferred read flow for stocks:

1. check whether `stock-snapshot` exists and is still fresh
2. if fresh, use it directly
3. if missing or expired, fetch from the stock upstream
4. on success, update cache and use fresh snapshot
5. on failure, if an older cached snapshot exists, use it as stale input
6. on failure with no cached snapshot, raise `DataUnavailableError`

Preferred read flow for indices:

1. check whether `index-snapshots` exists and is still fresh
2. if fresh, use it directly
3. if missing or expired, fetch from the index upstream
4. on success, update cache and use fresh snapshot
5. on failure, if an older cached snapshot exists, use it as stale input
6. on failure with no cached snapshot, raise `DataUnavailableError`

The existing page-facing methods should keep their current responsibilities:

- `get_market_overview()` builds cards, chart series, and mover rankings
- `get_indices()` builds the three-index comparison response
- `get_stocks()` builds table rows and applies query filtering

## Freshness And Stale Semantics

The cache TTL determines when the backend should attempt an upstream refresh. It does not change the existing API contract.

### Fresh cache hit

If the needed raw snapshot is present and unexpired:

- do not call the upstream
- derive the endpoint response from cached raw data
- return `stale=false`

### Expired or missing cache, refresh succeeds

If the snapshot is missing or expired and the refresh succeeds:

- replace cached raw snapshot
- derive the endpoint response from fresh data
- return `stale=false`

### Expired or missing cache, refresh fails, old snapshot still exists

If refresh fails but an older cached raw snapshot still exists:

- derive the endpoint response from that old cached snapshot
- return `stale=true`

### Cold start, refresh fails, no snapshot exists

If refresh fails and no cached raw snapshot exists:

- raise `DataUnavailableError`
- preserve existing HTTP 503 behavior in the API layer

## API And Front-End Impact

No front-end API contract changes are required for this phase.

The current API shapes remain valid:

- `MarketOverviewResponse`
- `IndicesResponse`
- `StocksResponse`

Expected visible product effects:

- the China stocks page shows more representative names
- the market overview mover lists are computed from a broader representative stock set
- repeated page visits within 5 minutes should avoid unnecessary upstream fetches
- stale banners continue to work as they do today

Because the response shapes are stable, the front end should not need structural changes for this work.

## Implementation Boundaries

The likely implementation surface is intentionally narrow:

- `backend/financehub_market_api/watchlist.py`
- `backend/financehub_market_api/cache.py`
- `backend/financehub_market_api/service.py`
- backend tests covering service and cache behavior

Possible test files to update or add:

- `backend/tests/test_market_service.py`
- `backend/tests/test_package_smoke.py`
- an additional cache-focused test file if that keeps TTL behavior easier to reason about

This work should not require changes to:

- front-end page components
- FastAPI route contracts
- upstream adapter interfaces

unless a narrow compatibility adjustment is necessary for correctness.

## Testing Strategy

Testing should focus on observable behavior and be deterministic.

### Cache tests

Add or update tests to verify:

- fresh cache hit does not refresh upstream
- expired cache triggers upstream refresh
- expired cache plus refresh failure falls back to old cached snapshot
- missing cache plus refresh failure raises `DataUnavailableError`

The cleanest approach is to make cache time injectable or otherwise controllable in tests so TTL behavior can be tested without sleeps.

### Stock-universe tests

Add or update tests to verify:

- expanded watchlist remains valid and non-empty
- stock service returns more rows than before
- stock filtering still works correctly by code and name
- ranking helpers still behave correctly with the broader stock pool

### Regression tests

Run the existing backend API and service tests to confirm:

- response shapes remain unchanged
- stale fallback still works
- API translation to HTTP 503 is unaffected

## Risks And Guardrails

### Risk: cache logic becomes harder to reason about

Guardrail:

- keep cache API very small and explicit
- test TTL behavior directly

### Risk: broader watchlist increases upstream sensitivity

Guardrail:

- stay within a curated 20 to 30 stock range
- keep the current stale fallback path

### Risk: stale semantics become inconsistent across endpoints

Guardrail:

- derive stale state from whether the endpoint ultimately used expired fallback raw snapshots
- keep response contracts unchanged

### Risk: broad refactoring of service code

Guardrail:

- keep the diff focused on snapshot retrieval and watchlist expansion
- do not redesign the API layer or front-end data contracts

## Success Criteria

This design is successful when:

- the curated stock universe is expanded to roughly 24 representative A-share names
- repeated requests within 5 minutes do not repeatedly hit the same upstream source
- the market overview, indices, and stocks APIs continue to return the same contract shapes
- stale fallback still works after cache expiry
- cold-start failures still return the current service-level error behavior
- backend tests clearly verify TTL behavior and expanded stock coverage
