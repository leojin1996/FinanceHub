# FinanceHub China Indices Page Redesign

## Goal

Redesign the China indices page to visually match the provided FinanceHub reference as closely as possible while preserving the product's China-market semantics, existing route structure, and current shell behavior.

This redesign must:

- keep the current `/indices` route
- keep the existing top navigation shell and active-tab behavior
- replace the current comparison-chart-plus-insight layout with a four-card indices grid
- keep the page grounded in Chinese market indices rather than switching to US/global entities
- use real recent closing data for each card sparkline
- extend `GET /api/indices` instead of introducing a new API route

## Scope

This design changes only the China indices page, the `/api/indices` response contract, the upstream index set needed for that page, and the tests that support those changes.

In scope:

- index page layout and visual structure
- four-card index grid rendering
- card-level trend sparkline rendering
- expanded `/api/indices` payload
- inclusion of `科创50` in the indices dataset for this page
- front-end and back-end tests needed for the redesign

Out of scope:

- new routes
- index detail drill-down pages
- interactive chart switching
- intraday or real-time data
- changes to the market overview, stocks, recommendations, or risk-assessment pages
- changes to the top navigation information architecture

## Current Product Context

The current indices page is implemented in:

- `src/features/chinese-indices/ChineseIndicesPage.tsx`
- `src/features/chinese-indices/IndexComparisonPanel.tsx`

Today the page:

- fetches `GET /api/indices`
- shows a loading, error, or stale state using the shared notice pattern
- renders a bar-chart comparison panel
- renders a separate insight card
- only consumes a minimal `series: [{ name, value }]` payload

The current backend path is implemented through:

- `backend/financehub_market_api/main.py`
- `backend/financehub_market_api/service.py`
- `backend/financehub_market_api/models.py`
- `backend/financehub_market_api/upstreams/index_data.py`

Today the backend only returns latest values for three indices:

- 上证指数
- 深证成指
- 创业板指

## Chosen Product Direction

Chosen approach: keep the existing `/indices` route, expand the backend response into an index-card-focused contract, and rebuild the page as a dedicated four-card grid that mirrors the reference layout.

This approach is preferred because it:

- gets much closer to the provided design than stretching the current comparison panel
- keeps route and shell behavior stable
- places index metadata and trend computation in the backend rather than splitting those responsibilities across front end and back end
- keeps the change reviewable by limiting scope to one page and one existing API

## Layout And Visual Structure

The page should continue to render inside `AppShell` and keep the current header area from `PageHeader`, including the existing route title and subtitle.

The page body should be replaced with a dedicated indices grid:

1. shared page header from `AppShell`
2. shared loading, error, and stale notices
3. a 2x2 grid of four index cards

The current `IndexComparisonPanel` and the current insight card should be removed from this page.

Card order is fixed:

1. 上证指数
2. 深证成指
3. 创业板指
4. 科创50

Desktop layout should use a two-column grid matching the reference rhythm. Smaller screens may collapse to a single column, but the card internals should remain visually consistent.

## Card Structure

Each index card should follow the reference composition as closely as possible while using Chinese-market content.

Each card contains:

- top-left: index name
- secondary metadata row: index code and market label
- short descriptive sentence
- top-right value block: latest close and signed daily move
- bottom chart area: recent-closes area sparkline

The metadata row should display:

- index code
- separator dot
- market label `中国市场`

Descriptions should be short and fixed per index. Recommended descriptions:

- 上证指数: `沪市核心宽基指数`
- 深证成指: `深市代表性综合指数`
- 创业板指: `成长风格代表指数`
- 科创50: `科创板核心龙头指数`

## Visual Rules

The page should prioritize reference fidelity over exposing exaggerated movement.

Value and move presentation rules:

- positive values use green text and an upward arrow
- negative values use red text and a downward arrow
- neutral values use a muted neutral tone

Chart rules:

- each card renders a recent-closes area chart using real data
- chart line and fill color follow the card tone
- y-axis range uses a reference-first wider domain strategy so the line appears flatter, closer to the supplied design
- x-axis uses real recent trading dates
- charts are display-only and do not support interaction-driven card state changes

## Data Contract

This redesign keeps the existing endpoint:

- `GET /api/indices`

The current response shape should be expanded from a simple summary into a card-specific payload:

- `asOfDate: str`
- `stale: bool`
- `cards: list[IndexCard]`

Each `IndexCard` should contain:

- `name: str`
- `code: str`
- `market: str`
- `description: str`
- `value: str`
- `valueNumber: float`
- `changeValue: float`
- `changePercent: float`
- `tone: "positive" | "negative" | "neutral"`
- `trendSeries: list[{ date: str, value: float }]`

Contract notes:

- `value` remains display-safe so the page can render immediately without duplicating formatting logic
- `valueNumber`, `changeValue`, and `changePercent` provide raw numeric values for chart and state decisions
- `tone` prevents the front end from re-deriving sign semantics in multiple places
- `trendSeries` provides the card-specific chart sequence

## Data Mapping Strategy

The backend should become the source of truth for index metadata as well as recent-close calculations.

Per-index metadata should be defined centrally in the backend:

- 上证指数 -> code `000001.SH`
- 深证成指 -> code `399001.SZ`
- 创业板指 -> code `399006.SZ`
- 科创50 -> code `000688.SH`

The upstream AkShare symbols remain aligned with the current implementation style:

- 上证指数 -> `sh000001`
- 深证成指 -> `sz399001`
- 创业板指 -> `sz399006`
- 科创50 -> `sh000688`

Field mapping responsibilities:

- `name`, `code`, `market`, and `description` come from the backend metadata table
- `valueNumber` comes from the latest close
- `value` is a formatted version of `valueNumber`
- `changeValue` comes from latest close minus previous close
- `changePercent` comes from the latest-versus-previous percentage move
- `tone` comes from the sign of `changeValue`
- `trendSeries` comes from the recent closing sequence for that same index

## Backend Behavior

The index upstream client should fetch recent close sequences for all four configured indices and continue to normalize dates into `YYYY-MM-DD`.

The service layer should:

- validate that all four configured indices are present
- require at least two closes per index for change calculation
- build the new card payload in fixed order
- preserve the existing stale-snapshot behavior

Fallback rules remain simple:

- if refresh succeeds, return fresh data
- if refresh fails but a valid stale cache exists, return stale data
- if neither fresh nor valid stale data exists, raise `indices data is unavailable`
- do not return partially built card sets

## Front-End Behavior

The front end should replace the current comparison panel with an indices-page-specific card grid.

The page should:

- keep the existing `AppShell` and route copy
- keep the existing loading, error, and stale notice behavior
- render exactly four cards from `data.cards`
- not render the previous comparison chart or insight block

The page should not introduce:

- filters
- tabs
- pagination
- chart selection
- card clicks

## Localization

The surrounding shell should continue to respect the existing locale system.

For this page, the index entities themselves remain Chinese-market content. The intended default experience is Chinese, and the card identity content should not be replaced with US-style naming or wording from the reference image.

To avoid fake or unstable translations, the backend-provided index names and descriptions should remain Chinese strings. Shared shell chrome, notices, and navigation continue to use the existing locale path.

## Testing

Back-end tests should cover:

- `GET /api/indices` returning the new `cards` structure
- inclusion of `科创50`
- correct `changeValue`, `changePercent`, `tone`, and `trendSeries`
- fixed card order
- stale and unavailable behavior remaining intact

Front-end page tests should cover:

- loading state
- error state
- stale notice rendering
- four cards rendering from API data
- positive and negative move styling
- presence of a chart region in each card
- absence of the old comparison-panel and insight layout

Route-level tests should cover:

- `/indices` still mounting correctly
- indices nav active state remaining intact after the redesign

## Implementation Notes

The redesign should stay focused and avoid shared-component refactors unless they are required for correctness.

Preferred implementation shape:

- keep changes localized to the indices feature, API types, backend models/service/upstream, and adjacent tests
- reuse existing charting dependencies already in the repo
- add a new indices-page-specific card renderer rather than forcing the design into the current `IndexComparisonPanel`

## Risks And Mitigations

Risk: widening the `/api/indices` contract may break existing tests and consumers.

Mitigation:

- update the typed front-end client and the API tests in the same change
- keep the endpoint path unchanged

Risk: adding `科创50` increases backend dependency on upstream availability.

Mitigation:

- keep the current cache-and-stale behavior
- validate the entire configured set consistently so failures are explicit and testable

Risk: chart visuals may drift from the reference if axes are auto-scaled too tightly.

Mitigation:

- use a dedicated wider-domain calculation for this page rather than reusing the market overview chart behavior

