# FinanceHub A-Share Stocks Page Redesign

## Goal

Redesign the China stocks page to visually match the provided FinanceHub reference layout as closely as possible while preserving the product's A-share data semantics and existing route structure.

This redesign must:

- keep the page language localized through the existing locale system
- keep the page positioned as an A-share stocks view rather than a US-stocks product
- replace the current simple table layout with a reference-style full-width stocks board
- add industry filtering
- add richer stock columns backed by real upstream data where available
- render change values with explicit color and arrow direction cues
- preserve the current `/api/stocks` endpoint rather than introducing a new route

## Scope

This design changes only the China stocks page, the `/api/stocks` response contract, and the tests needed to support that redesign.

In scope:

- stocks page layout and visual structure
- stocks-page-specific table rendering
- local search and industry filtering
- extended stock row data from the backend
- localized formatting for volume and amount
- seven-day trend sparkline rendering
- backend and front-end test updates

Out of scope:

- favorites or watchlist interactions
- table sorting
- pagination or infinite scroll
- new routes or new API resources
- replacing the curated A-share watchlist with a dynamic stock universe
- real-time intraday updates
- user-configurable columns

## Current Product Context

The current stocks page is implemented in:

- `src/features/chinese-stocks/ChineseStocksPage.tsx`
- `src/features/chinese-stocks/StockFilters.tsx`

The current page:

- fetches `GET /api/stocks`
- renders a search-only filter panel
- uses the generic `DataTable` component
- shows a right-side `InsightCard`
- displays only `code`, `name`, `sector`, `price`, and `change`

The current backend stocks path is implemented through:

- `backend/financehub_market_api/main.py`
- `backend/financehub_market_api/service.py`
- `backend/financehub_market_api/models.py`
- `backend/financehub_market_api/upstreams/dolthub.py`

Today the backend only reads enough upstream data to build latest price and day-over-day change for the curated A-share watchlist.

## Chosen Product Direction

Chosen approach: keep the existing stocks route and A-share watchlist concept, but redesign the page into a dedicated stocks-board view with a page-specific table implementation and an expanded `/api/stocks` payload.

This approach is preferred because it:

- matches the provided reference more closely than extending the current generic table
- keeps the route, page purpose, and data source stable
- allows richer cells such as arrows, pills, and sparklines without overloading shared table infrastructure
- limits backend changes to one existing endpoint
- keeps the implementation reviewable by avoiding unrelated refactors

## Layout And Visual Structure

The redesigned page should keep the existing page title and subtitle area within `AppShell`, but replace the current dual-column content area with a single full-width stocks board.

The page body should be organized as:

1. title and subtitle from the existing route copy
2. a reference-style filter bar card
3. a single large stocks table card
4. loading, error, and stale notices using the existing notice patterns

The current right-side `InsightCard` should be removed from this page.

## Filter Bar Design

The filter bar should visually follow the reference layout and contain two controls:

- a left-aligned search field
- a right-aligned, horizontally scrollable industry-chip list

Filter behavior:

- search matches stock code or stock name
- industry chips filter by `sector`
- the default chip is `全部`
- remaining chips are generated from the actual returned stock rows
- search and industry filtering both run locally in the front end
- changing either filter updates the visible rows immediately

The industry-chip list should support horizontal scrolling instead of wrapping so the desktop layout remains close to the reference.

## Table Structure

The stocks board should no longer use the generic `DataTable` component. The page should render a stocks-page-specific table view because the required cells are visually specialized and not a good fit for the current generic API.

The table columns should be:

- favorite marker
- code
- name
- price
- change
- volume
- amount
- sector
- seven-day trend

Behavior constraints:

- the favorite column is visual only and not interactive
- table headers are static and do not support sorting
- row order follows the backend response order
- mobile layouts should preserve the table structure through horizontal scrolling rather than collapsing into cards

## Localization And Formatting

The page should continue to respect the existing locale setting.

Chinese locale rules:

- labels remain in Chinese
- volume and amount use A-share-style Chinese units such as `万` and `亿`

English locale rules:

- labels use the existing English localization path
- volume and amount use compact international suffixes such as `K`, `M`, and `B`

The layout, columns, and interaction model remain the same across locales.

## Change And Trend Presentation

The change column should render from numeric change data rather than parsing existing display strings.

Change-state rules:

- positive change uses green text and an upward arrow icon
- negative change uses red text and a downward arrow icon
- zero change uses a neutral tone

The displayed change content should continue to show percentage movement, with formatting handled in the UI from backend-provided numeric values.

The seven-day trend column should render a compact sparkline for each stock.

Trend-state rules:

- if the latest trend value is above the first value, render the sparkline in green
- if the latest trend value is below the first value, render it in red
- if the values are equal, render a neutral tone

## API Surface

This redesign keeps the existing endpoint:

- `GET /api/stocks`

The endpoint continues to return:

- `asOfDate`
- `stale`
- `rows`

The route should continue to accept the current optional `query` parameter for compatibility, but the redesigned page does not need to rely on it because filtering stays local.

## Stock Row Contract

The current stock row contract should be expanded rather than replaced so the change remains compatible and reviewable.

Each row should contain:

- `code: str`
- `name: str`
- `sector: str`
- `price: str`
- `change: str`
- `priceValue: float`
- `changePercent: float`
- `volumeValue: float`
- `amountValue: float`
- `trend7d: list[{ date: str, value: float }]`

Contract guidance:

- `price` and `change` remain for compatibility with existing consumers and tests
- `priceValue` and `changePercent` provide raw numeric values for UI decisions
- `volumeValue` and `amountValue` are the locale-independent source for display formatting
- `trend7d` provides the chartable sequence for the sparkline

## Data Mapping Strategy

The backend should continue using the curated A-share watchlist in `watchlist.py` for stock identity and sector metadata.

Field mapping responsibilities:

- `code`, `name`, and `sector` come from the curated watchlist metadata
- `priceValue` comes from the latest available close
- `changePercent` comes from latest close versus previous close
- `price` remains a display-safe formatted version of `priceValue`
- `change` remains a display-safe formatted version of `changePercent`
- `volumeValue` comes from the latest row's `volume`
- `amountValue` comes from the latest row's `amount`
- `trend7d` comes from the latest seven valid trading-day closes for each symbol

The current DoltHub source does provide `volume` and `amount`, and it provides enough end-of-day history to derive `trend7d`. It does not expose a clear market-cap field in the currently used dataset, so this redesign uses `amount` instead of market capitalization.

## Upstream Query Strategy

The upstream access layer should be extended to fetch three categories of stock data for the curated symbols:

- latest trading-day values including `close`, `volume`, and `amount`
- previous trading-day close values for percentage change calculation
- the latest seven trading-day close series per symbol for sparklines

The service layer should normalize these upstream values into one stable `StocksResponse`.

The backend should not expose raw upstream field names or push formatting logic for locale-specific units into the API contract.

## Error Handling And Fallback Rules

The redesigned stocks page should preserve the current stale-data contract and backend fallback behavior.

Rules:

- if the upstream refresh succeeds, return a fresh snapshot
- if the upstream refresh fails but a previously valid cached snapshot exists, return it with `stale=true`
- if no valid snapshot exists, return the existing stocks-unavailable error path

For data completeness, this redesign should prefer whole-response validity over partial rows.

That means:

- if a required latest field such as `volume` or `amount` is missing for a tracked symbol, treat the refresh as invalid
- if a required seven-day trend series is incomplete for a tracked symbol, treat the refresh as invalid
- do not return mixed rows where some stocks have trend data and others do not

This keeps the UI contract simple and prevents hidden per-row quality drift.

## Front-End Responsibilities

The front end should own:

- local search state
- local industry-chip state
- deriving the visible row list from search plus selected industry
- locale-specific formatting of `volumeValue` and `amountValue`
- rendering change icons, tones, and formatted percentages
- rendering sector pills
- rendering seven-day sparklines

The front end should not own:

- upstream schema knowledge
- change calculation
- trend-series fetching
- stale-data decision logic

## Test Strategy

### Backend

Update backend tests to cover:

- expanded `StockRow` schema
- successful construction of `priceValue`, `changePercent`, `volumeValue`, `amountValue`, and `trend7d`
- correct seven-day trend ordering
- invalid refresh behavior when required upstream fields are missing
- stale-snapshot fallback when upstream refresh fails after a valid cache exists
- `/api/stocks` response-model coverage for the expanded payload

### Front End

Update front-end tests to cover:

- full-width stocks board rendering
- absence of the old right-side insight card
- search filtering
- industry-chip filtering
- positive and negative change styling
- trend-cell rendering presence
- stale notice behavior
- Chinese numeric formatting for volume and amount
- English compact numeric formatting for volume and amount

### Structural Assurance

The redesign should test for the key reference-driven structure rather than pixel-perfect snapshots.

Tests should assert the presence of:

- the search field
- the industry-chip rail
- the expanded table headers
- the trend column
- the full-width table container

## Risks And Constraints

The main implementation risks are:

- extending upstream queries without making the backend logic too brittle
- preserving stale-data semantics while validating more fields
- keeping the UI visually close to the reference without over-generalizing shared components

The design deliberately reduces risk by:

- keeping the route and page purpose unchanged
- using a page-specific table implementation instead of refactoring shared table primitives
- keeping filtering local
- avoiding favorites, sorting, and dynamic-stock-universe expansion

## Out-Of-Scope Follow-Ups

Possible future work that is intentionally excluded from this redesign:

- interactive favorites
- server-side industry filtering
- table sorting
- pagination
- additional market-cap or turnover-rate metrics if a future upstream source supports them cleanly
- richer per-sector analytics or insight cards
