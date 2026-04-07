# FinanceHub Persisted Market Data Cache Design

## Goal

Make the three China market pages feel immediate on open by showing the last successful market snapshot as soon as the application loads, including after the browser is closed and reopened.

This design must:

- keep the existing `/`, `/stocks`, and `/indices` routes
- keep the existing `/api/market-overview`, `/api/stocks`, and `/api/indices` contracts stable
- show cached market data immediately when valid local browser data exists
- refresh market data in the background without blocking page rendering
- preserve the current server-side `stale` semantics for fallback snapshots
- add Redis as the shared back-end snapshot cache

## Scope

This design changes only the market data path for the overview, stocks, and indices pages, plus the tests needed to support that behavior.

In scope:

- a shared front-end market-data store for the three market pages
- persisted browser-side snapshots using `localStorage`
- background refresh after initial cache hydration
- Redis-backed snapshot caching in the back end
- clear UI behavior for cached, refreshing, stale, and error states
- front-end and back-end tests for the new cache behavior

Out of scope:

- new market routes
- real-time streaming, polling, or websockets
- service worker or Cache API based offline behavior
- server-side rendering or HTML data injection
- changing the recommendation or risk-assessment flows
- introducing MySQL or MongoDB persistence for this feature

## Current Product Context

The current front end fetches market data independently inside each page component:

- `src/features/market-overview/MarketOverviewPage.tsx`
- `src/features/chinese-stocks/ChineseStocksPage.tsx`
- `src/features/chinese-indices/ChineseIndicesPage.tsx`

Today each page:

- mounts with local component state set to `null`
- performs its own `useEffect` request after render
- shows a loading notice until the request resolves
- loses data when the route unmounts or when the browser is restarted

The current back end already has snapshot caching through:

- `backend/financehub_market_api/cache.py`
- `backend/financehub_market_api/service.py`

Today that cache is:

- process-local in-memory storage
- fresh for a short TTL window
- still readable as a stale fallback after expiry through `peek()`

This means the back end can often answer quickly once warmed, but the browser still waits on a network round trip every time it needs to rebuild the page state from scratch.

## Chosen Product Direction

Chosen approach: keep the current routes and response models, add a lightweight shared front-end market-data store with `localStorage` persistence, and replace the back-end in-memory snapshot cache with a Redis-backed cache that preserves the current fresh-versus-stale fallback behavior.

This approach is preferred because it:

- directly solves the user-facing delay on browser open and route entry
- keeps the existing API surface stable
- limits review scope to market data plumbing rather than visual page redesign
- reuses the current stale-snapshot behavior instead of inventing a new recovery model
- makes the back-end cache shared across restarts and worker processes

## System Architecture

The market data flow should become:

1. application boots
2. front-end market-data store reads persisted market snapshots from `localStorage`
3. valid cached snapshots are placed into in-memory shared state immediately
4. market pages render from the shared state instead of waiting for page-local fetches
5. the shared store starts a background refresh for overview, stocks, and indices
6. the back end checks Redis for a fresh snapshot before contacting upstream providers
7. fresh network responses update Redis, update front-end shared state, and overwrite the browser cache
8. refresh failures keep the last valid data on screen whenever a cached snapshot exists

This design makes the browser cache the source of immediate first paint and Redis the source of fast shared back-end refreshes.

## Front-End Cache Design

### Shared Store Ownership

The front end should introduce one market-data store near the existing app-state layer so the market pages can consume shared resource state without each page re-implementing fetch logic.

The store should manage three resources:

- `overview`
- `stocks`
- `indices`

Each resource should keep:

- `data`
- `loadStatus`
- `refreshStatus`
- `error`
- `source`
- `lastHydratedAt`

State values:

- `loadStatus`: `idle | loading | ready | error`
- `refreshStatus`: `idle | refreshing | failed`
- `source`: `storage | network`

### Browser Persistence Format

Each persisted resource should be stored in a versioned envelope instead of writing the raw API payload directly.

Envelope fields:

- `version`
- `savedAt`
- `resource`
- `data`

Persistence rules:

- parse and validate the envelope before using it
- discard the entry if parsing fails
- discard the entry if the version is unsupported
- discard the entry if the resource name does not match the expected slot
- discard the entry if the payload shape is invalid

### Browser Retention Rules

The browser cache should prioritize immediacy over strict freshness, but not keep snapshots forever.

Retention rule:

- valid browser snapshots may be shown immediately for up to `14 days`
- snapshots older than `14 days` should be discarded before rendering

The front end should still refresh in the background even when a valid local snapshot is shown.

### Store Behavior

On application startup:

- hydrate the three resources from `localStorage`
- immediately expose any valid cached data to the UI
- start one background refresh per resource

On refresh success:

- replace the resource state with the new network payload
- set `source` to `network`
- clear any refresh failure state
- overwrite the corresponding `localStorage` entry

On refresh failure:

- if cached data already exists, keep rendering it and mark the resource refresh as failed
- if no cached data exists, surface the normal blocking error state for that resource

## Redis Cache Design

### Purpose

Redis should replace the current process-local snapshot cache as the shared back-end cache for:

- stock snapshot data
- index snapshot data

Redis is used here as a cache, not as a system-of-record database.

### Cache Envelope

Each Redis entry should store both the normalized snapshot and the metadata needed to decide whether it is fresh, stale, or unusable.

Redis envelope fields:

- `version`
- `savedAt`
- `freshUntil`
- `retainUntil`
- `asOfDate`
- `payload`

### Freshness And Fallback Rules

The Redis rules should preserve the current semantics of `SnapshotCache.get()` and `SnapshotCache.peek()`.

Policy:

- `fresh TTL`: `300 seconds`
- `retain TTL`: `14 days`

Decision rules:

- if no Redis entry exists, refresh from upstream
- if the entry exists but cannot be parsed or validated, delete it and refresh from upstream
- if `now <= freshUntil`, return the Redis payload without hitting upstream
- if `freshUntil < now <= retainUntil`, try to refresh from upstream
- if refresh succeeds, replace the Redis entry and return the new payload
- if refresh fails and the retained payload is still valid, return it as stale fallback
- if `now > retainUntil`, treat the entry as expired and refresh from upstream

`asOfDate` should be used as a guard against accidentally replacing a newer snapshot with an older upstream result.

## Request And Refresh Flow

### Overview, Stocks, And Indices Pages

The pages should stop owning their own first-load fetch lifecycle.

Instead:

- `MarketOverviewPage` reads the shared `overview` resource
- `ChineseStocksPage` reads the shared `stocks` resource
- `ChineseIndicesPage` reads the shared `indices` resource

Page-level fetch logic should become a store concern so route transitions do not trigger full empty-state resets when valid data is already in memory.

### Route Changes

After the shared store has been hydrated once:

- moving between `/`, `/stocks`, and `/indices` should reuse existing in-memory data
- the pages should not drop back to blocking loading states unless their resource has never been loaded and no persisted data exists

### Browser Restart

After the browser is closed and reopened:

- valid persisted snapshots should render immediately on first app load
- the shared store should start a background refresh for all three market resources

## UI State Rules

The UI should keep using the shared notice pattern through `DataStatusNotice`, but add client-cache-aware status messages.

Visible behavior:

- `has data + refresh in progress`: show data immediately and do not show a blocking loading notice
- `has data + refresh failed`: keep showing data and show a warning such as `正在显示上次缓存数据`
- `has data + server response marked stale`: keep the current stale close-data notice with `asOfDate`
- `no data + first request in progress`: show the existing loading notice
- `no data + request failed`: show the existing blocking error notice

Important semantic rule:

- server-side `stale` means the API returned an older but valid back-end snapshot
- client-side cached rendering means the page was hydrated from `localStorage`

These two states should remain separate in both code and copy.

## Error Handling

The design should fail closed on malformed cache data and fail open on previously valid snapshots.

Front-end rules:

- never trust raw `localStorage` blindly
- silently discard malformed persisted entries
- never block rendering when valid cached data exists

Back-end rules:

- never trust raw Redis entries blindly
- delete malformed Redis envelopes rather than repeatedly reusing them
- return stale retained snapshots only when they still validate against the expected normalized shape

## Testing Strategy

### Front-End Tests

Add or update tests to cover:

- hydrating valid `localStorage` snapshots into the shared store
- discarding malformed or version-mismatched browser cache entries
- rendering market pages immediately from cached data
- background refresh success replacing cached data
- background refresh failure preserving cached data
- showing blocking loading only when neither memory, browser cache, nor network data is available

### Back-End Tests

Add or update tests to cover:

- Redis fresh-hit behavior returning cached data without upstream refresh
- refresh-on-expired-fresh-window behavior
- stale fallback behavior when refresh fails but retained Redis data exists
- malformed Redis envelope eviction
- older upstream `asOfDate` not overwriting newer cached data

### Manual Verification

Manual verification should confirm:

1. warm the app once so valid market data is persisted locally
2. close the browser
3. reopen the app and confirm the three market pages render immediately from persisted data
4. confirm background refresh updates the rendered data without a full-page loading reset
5. simulate back-end refresh failure and confirm cached data remains visible with warning semantics

## Risks And Mitigations

Risk: browser cache and server stale semantics could be conflated.

Mitigation:

- keep separate state fields for client cache source and server stale response

Risk: malformed persisted cache could break rendering.

Mitigation:

- use versioned envelopes and strict parse-and-discard rules

Risk: Redis integration adds an infrastructure dependency to a project that currently has none.

Mitigation:

- keep Redis usage narrow and isolated behind the existing snapshot-cache boundary
- use the same cache interface so tests can keep using a fake or in-memory implementation without changing service behavior

Risk: background refreshes could trigger duplicate requests if multiple components refresh independently.

Mitigation:

- centralize refresh ownership in the shared market-data store rather than in page components

## Acceptance Criteria

This feature is complete when all of the following are true:

- opening `/`, `/stocks`, or `/indices` with a valid browser cache shows data immediately without blocking loading UI
- reopening the browser still shows the last successful market snapshot immediately
- the front end refreshes the three market resources in the background after hydration
- Redis serves as the shared back-end snapshot cache for market data
- the back end preserves the current stale-fallback behavior when upstream refresh fails
- malformed browser or Redis cache entries are discarded safely
- targeted front-end and back-end tests cover the new behavior
