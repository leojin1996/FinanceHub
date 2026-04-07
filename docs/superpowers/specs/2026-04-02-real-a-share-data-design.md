# FinanceHub Real A-Share Data Integration Design

## Goal

Replace the current mock-driven China market pages with real A-share end-of-day data while keeping the existing FinanceHub front-end structure stable and reviewable.

The first phase must:

- replace mock data on the China market overview page
- replace mock data on the China indices page
- replace mock data on the China stocks page
- use a lightweight API layer instead of direct browser access to upstream data
- return the latest valid trading-day data rather than intraday real-time data
- degrade safely when the upstream data source is unavailable

## Scope

This design changes only the data path for the three China market pages and the tests needed to support that change.

In scope:

- a lightweight backend API for China market data
- normalization from upstream market data into page-specific response shapes
- runtime data fetching from the front end
- loading, error, and stale-data states for the three affected pages
- backend and front-end tests for the new data flow

Out of scope:

- real-time intraday data
- websockets or streaming updates
- user watchlists or portfolios
- replacing recommendation or questionnaire mock data
- a persistent production database
- background scheduling infrastructure
- direct browser access to `investment_data`, DoltHub, Tushare, or other upstream providers

## Current Product Context

The current `financehub-app-shell` application is a `React + Vite + TypeScript` front end that reads static arrays from local files such as:

- `src/mock/marketOverview.ts`
- `src/mock/indices.ts`
- `src/mock/stocks.ts`

These arrays are consumed directly by:

- the market overview page
- the China indices page
- the China stocks page

There is no existing backend or front-end data access layer in this project, so the safest migration path is to preserve page structure and component contracts as much as possible while replacing the data source behind them.

## Chosen Product Direction

Chosen approach: keep the existing front-end page and component structure, add a small FastAPI service, and use that service as the only runtime bridge to real market data.

This approach is preferred because it:

- keeps the front-end diff small
- isolates upstream schema and availability risk on the server side
- avoids exposing provider details or tokens to the browser
- creates a clean boundary for future data-source changes
- supports safe stale-data fallback without forcing the UI to understand upstream failure modes

## Upstream Data Strategy

The preferred upstream source for this phase is `chenditc/investment_data`.

This repository is treated as an upstream market-data source and reference schema, not as a browser-facing API. The backend is responsible for extracting the specific fields needed for FinanceHub and translating them into stable response contracts.

The product assumption for phase one is:

- data freshness target: latest valid trading day
- data type: A-share end-of-day and close-based market data
- no requirement for intraday live updates

If the upstream source is temporarily unavailable, the API should serve the last successfully normalized snapshot when one exists.

## Technical Direction

The implementation should use:

- existing front end: `React + Vite + TypeScript`
- new lightweight backend: `FastAPI`

The choice of `FastAPI` is intentional:

- the repository guidance is oriented toward Python production work
- data normalization and fallback behavior are more natural on the server side
- it keeps the API implementation small and explicit
- it provides a simple path for future caching, health checks, and typed response models

## System Architecture

The new flow should be:

1. Front-end pages request FinanceHub API endpoints under `/api/*`
2. The FastAPI service fetches raw upstream market data for the latest valid trading day
3. The FastAPI service normalizes upstream fields into FinanceHub-specific response models
4. The FastAPI service caches the last successful normalized snapshot
5. The front end renders the normalized API response and shows loading, error, or stale-state UI when needed

This design keeps the front end intentionally unaware of upstream table names, provider conventions, token requirements, and fallback logic.

## Backend Responsibilities

The backend should have four focused responsibilities:

### 1. Upstream access

Read the required latest-trading-day data from the chosen upstream source.

### 2. Normalization

Transform upstream fields into the exact shapes needed by the FinanceHub pages.

### 3. Snapshot fallback

Retain the last successful normalized result so temporary upstream failures do not immediately break the product.

### 4. HTTP delivery

Expose simple JSON endpoints that the front end can consume without additional transformation logic.

The backend should not try to become a general-purpose market data platform in this phase.

## API Surface

The first phase should expose three endpoints.

### `GET /api/market-overview`

Purpose:
Provide the market overview page with summary cards, a recent-trading-day trend series, top gainers, top losers, and metadata about freshness.

Response shape:

- `asOfDate`: latest trading date represented by the payload
- `stale`: boolean indicating whether the response came from fallback snapshot data
- `metrics`: three metric cards for `上证指数`, `深证成指`, and `创业板指`
- `trendSeries`: recent end-of-day trend data for the main chart
- `topGainers`: ranked list for the gainers panel
- `topLosers`: ranked list for the losers panel

Each metric item should contain:

- `label`
- `value`
- `delta`
- `tone`

Each `trendSeries` item should contain:

- `date`
- `value`

### `GET /api/indices`

Purpose:
Provide the China indices page with the index-comparison chart data.

Response shape:

- `asOfDate`
- `stale`
- `series`

Each `series` item should contain:

- `name`
- `value`

Phase one keeps the current three-index scope:

- `上证指数`
- `深证成指`
- `创业板指`

### `GET /api/stocks`

Purpose:
Provide the China stocks page with table rows.

Response shape:

- `asOfDate`
- `stale`
- `rows`

Each row should contain:

- `code`
- `name`
- `sector`
- `price`
- `change`

This endpoint should support a simple optional query parameter for code-or-name filtering:

- `query`

The filtering should remain case-insensitive and match the current front-end behavior as closely as practical.

## Data Mapping Rules

The API must return front-end-friendly values rather than leaking raw upstream field naming or formatting into the UI layer.

Mapping expectations:

- numeric values should be converted into display-safe strings only when current components require them
- chart values should remain numeric where the chart library benefits from numeric input
- `tone` should be derived from the sign of the change value and limited to `positive`, `negative`, or `neutral`
- `asOfDate` should use one consistent date format across all endpoints

The backend is the correct place to centralize:

- field mapping
- percentage formatting
- sign handling
- label normalization
- fallback defaults for incomplete upstream rows

## Caching And Failure Strategy

Phase one should favor small, deterministic infrastructure over ambitious platform design.

### Cache behavior

The backend should keep the last successful normalized snapshot for each endpoint or for the shared market snapshot it derives them from.

Preferred order:

1. in-memory cache for normal runtime use
2. optional local JSON snapshot persistence for restart resilience

This keeps the service simple while still protecting the UI from transient upstream failures.

### Failure behavior

If upstream fetch succeeds:

- return fresh normalized data
- set `stale` to `false`

If upstream fetch fails and a previous snapshot exists:

- return the cached snapshot
- set `stale` to `true`

If upstream fetch fails and no snapshot exists:

- return an API error response
- do not silently fall back to the old mock files

This is important: after the migration, mock data should no longer masquerade as real data during runtime failures.

## Front-End Integration

The front end should introduce a small data access layer instead of embedding fetch logic directly in each page.

Recommended boundary:

- a shared `src/services` or equivalent module for China market API requests

The three affected pages should stop importing mock arrays and instead request data at runtime:

- market overview page -> `/api/market-overview`
- China indices page -> `/api/indices`
- China stocks page -> `/api/stocks`

The existing presentation components should remain reusable with minimal prop changes.

The current market overview chart should stop using the locally hardcoded intraday array. In phase one it should become a recent trading-day trend chart based on end-of-day values from the API. This keeps the page fully real-data-backed without introducing a real-time market-data requirement.

## Front-End State Handling

The three affected pages should explicitly support these runtime states:

### Loading

- show a clear loading state while the initial request is in flight

### Error

- show a clear data-unavailable message when the API cannot return fresh or cached data

### Stale

- show the returned data
- also show a small stale-data indicator tied to `asOfDate`

The stale state should inform the user that the data reflects the last successful trading-day snapshot rather than the latest attempted refresh.

## Development Environment

The Vite development server should proxy `/api/*` requests to the local FastAPI service.

That allows:

- same-origin front-end development
- no hardcoded backend host in browser code
- simpler local setup for contributors

This should be configured in the existing Vite development setup rather than by adding unnecessary environment complexity in phase one.

## Testing Strategy

Testing should verify observable behavior in increasing layers, with deterministic inputs.

### Backend tests

Required:

- normalization unit tests
- endpoint success tests using mocked upstream responses
- fallback snapshot tests when upstream fetch fails after a prior success
- startup failure tests when upstream fetch fails and no snapshot exists

These tests should mock only the upstream boundary and test FinanceHub behavior directly.

### Front-end tests

Required:

- market overview page loads API-backed content successfully
- China indices page loads chart data successfully
- China stocks page loads table data successfully
- pages show error state when the API returns an unrecoverable failure
- pages show a stale-data indicator when `stale` is `true`

Front-end tests should avoid depending on live network calls.

## Migration Strategy

The migration should be incremental:

1. add the FastAPI backend and response models
2. add upstream client and normalization logic
3. add cache and fallback behavior
4. add front-end request layer
5. switch the three pages from mock imports to API consumption
6. update tests for backend and front-end behavior
7. remove or isolate no-longer-used mock market files only when the pages no longer depend on them

This order keeps the diff reviewable and reduces the chance of breaking all three pages at once without backend support in place.

## Risks And Constraints

The main risks for this phase are:

- upstream schema or availability changes
- uncertainty in sector/category mapping for the stock list
- accidental drift between backend response shapes and front-end expectations
- weak handling of first-start failures when no cached snapshot exists

The design responds to those risks by:

- isolating upstream logic in the backend
- defining explicit endpoint contracts
- keeping the page scope narrow
- requiring tests around failure and stale-data behavior

## Non-Goals Reaffirmed

To keep this phase small and safe, it explicitly does not include:

- live intraday charts
- auto-refresh during market hours
- generalized multi-market support
- historical range selectors
- database-backed market storage
- user-personalized market data

## Success Criteria

This phase is successful when:

- the three China market pages no longer depend on local mock market arrays at runtime
- the pages render real A-share end-of-day data through the new API layer
- upstream failures return cached data when available
- the UI exposes clear loading, error, and stale states
- automated tests cover success and key failure paths for both backend and front-end behavior
