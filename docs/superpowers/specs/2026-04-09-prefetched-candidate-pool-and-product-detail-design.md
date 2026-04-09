# 2026-04-09 Recommendation Candidate Pool And Product Detail Design

## Status

- Drafted in terminal brainstorming on 2026-04-09
- Scope: recommendation backend and recommendation frontend detail experience
- Design status: drafted for review
- Chosen approach: offline or near-real-time prefetched candidate pools plus in-app product detail pages

## Context

The recommendation system has already moved onto the LangGraph funnel runtime, but the product source model is still uneven:

- `fund` candidates are partially dynamic
- `wealth_management` candidates are still effectively proxy products rather than real public bank wealth-management products
- `stock` candidates still rely on a very small static pool
- recommendation cards do not provide a detail entry point for users who want to inspect performance, chart data, or product facts

The next phase should make recommendation results feel both more credible and more explorable:

1. product candidates should come from prefetched dynamic pools rather than request-time upstream fetches
2. the system should use Redis-backed cached snapshots to reduce request latency and shield users from upstream instability
3. every recommended product should expose an in-app detail route
4. detail pages should show a richer, standard-level information set and support stale-first rendering plus background refresh

## Goals

1. Replace request-time candidate sourcing with prefetched candidate pools for `fund`, `wealth_management`, and `stock`.
2. Make `wealth_management` candidates prioritize real public bank or wealth-subsidiary products, with proxy products only as fallback.
3. Replace the tiny static stock set with a dynamic premium stock universe and dynamic candidate selection.
4. Add in-app product detail pages for all recommendation cards.
5. Keep recommendation request latency stable by serving recommendation responses from cached snapshots rather than live upstream fetches.
6. Preserve graceful degradation: stale snapshots are usable, and static catalogs remain the final fallback.

## Non-Goals

1. Full-market unconstrained stock picking across the entire A-share universe.
2. Full production scheduler infrastructure in this phase. A scriptable refresh entry point is sufficient.
3. Tick-level or second-level refresh behavior.
4. Full regulatory document center or complete issuer disclosure pages.
5. Refactoring unrelated market overview, indices, or login flows.

## Approved Product Decisions

- Candidate source strategy: offline or near-real-time prefetched candidate pools
- Cache strategy: Redis-backed snapshots with in-memory fallback
- Detail entry strategy: in-app route, not external links
- Detail data strategy: stale-first read plus background refresh
- Wealth-management source posture: public bank or wealth-subsidiary products first, proxy fallback allowed
- Stock universe posture: index or theme derived premium stock universe, not a hand-maintained tiny whitelist
- Stock style posture: balanced core with meaningful growth participation, not growth as a mere add-on

## Design Principles

### Recommendation requests should not fetch upstream product facts directly

The recommendation path should consume only prepared candidate pool snapshots. This keeps recommendation latency and failure behavior predictable.

### Product detail is a separate concern from recommendation selection

Recommendation selection only needs concise candidate fields. Detail pages need richer fields such as yields, charts, fees, volatility or drawdown, and fit explanations. These should be modeled separately.

### Stale-but-usable is better than hard failure

If a snapshot is expired but structurally valid, the system should prefer returning stale data with warnings over returning no recommendation at all.

### Static product catalogs remain the last fallback

Static catalog data should no longer be the default source, but it should remain the final safety net when candidate pools are missing or corrupted.

## Recommended Architecture

The system will use two snapshot families:

1. `CandidatePoolSnapshot`
   - optimized for recommendation-time filtering and ranking
   - small, stable, decision-oriented
2. `ProductDetailSnapshot`
   - optimized for detail-page rendering
   - richer, heavier, presentation-oriented

These snapshots are produced by refresh jobs and stored in Redis-backed cache keys. Recommendation requests read candidate pool snapshots only. Detail pages read product detail snapshots first and may trigger background refresh when data is stale.

## Data Model

### Candidate Pool Snapshot

Each category has one current snapshot:

- `fund`
- `wealth_management`
- `stock`

Each snapshot should include:

- `category`
- `generated_at`
- `fresh_until`
- `source`
- `fallback_used`
- `warnings`
- `stale`
- `items`

Each candidate item should include:

- `id`
- `category`
- `code`
- `name_zh`
- `name_en`
- `risk_level`
- `liquidity`
- `tags_zh`
- `tags_en`
- `rationale_zh`
- `rationale_en`
- `as_of_date`
- `detail_route`

### Product Detail Snapshot

Each product detail snapshot should include:

- `id`
- `category`
- `code`
- `name_zh`
- `name_en`
- `provider_name`
- `as_of_date`
- `generated_at`
- `fresh_until`
- `source`
- `stale`
- `risk_level`
- `liquidity`
- `tags_zh`
- `tags_en`
- `summary_zh`
- `summary_en`
- `recommendation_rationale_zh`
- `recommendation_rationale_en`
- `yield_metrics`
- `chart`
- `fees`
- `drawdown_or_volatility`
- `fit_for_profile_zh`
- `fit_for_profile_en`

The chart payload should be a simple time-series structure already compatible with the frontend chart components:

- `label`
- `points: [{date, value}]`

## Cache Layout

The existing `SnapshotCache` and `RedisSnapshotCache` behavior should be reused rather than replaced.

Recommended Redis keys:

- `financehub:recommendation:candidate-pool:fund`
- `financehub:recommendation:candidate-pool:wealth_management`
- `financehub:recommendation:candidate-pool:stock`
- `financehub:recommendation:product-detail:<product_id>`

Cache behavior:

- `get()` means only fresh data
- `peek()` means stale or fresh data is still readable
- malformed cached payloads must be deleted
- Redis failures must fall back to in-memory cache behavior without breaking request flow

## Refresh Pipeline

### Refresh Execution Model

The first phase should use an executable refresh script rather than a full scheduler platform:

- `backend/scripts/refresh_recommendation_candidate_pool.py`

This script should:

1. refresh `fund` candidate pool
2. refresh `wealth_management` candidate pool
3. refresh `stock` candidate pool
4. optionally refresh detail snapshots for the selected candidates

Each category refresh should be independent. Failure in one category must not erase already-valid snapshots for the others.

### Refresh Frequency

Recommended starting intervals:

- `fund` candidate pool: every 30-60 minutes
- `wealth_management` candidate pool: every 60 minutes
- `stock` candidate pool: every 5-15 minutes
- product detail snapshots:
  - `fund`: every 30-60 minutes
  - `wealth_management`: every 60-120 minutes
  - `stock`: every 5-15 minutes

## Candidate Source Strategy

### Fund

The current dynamic public bond-fund path can remain in place as the initial dynamic source, but it should now write prefetched candidate pool snapshots rather than being called from the request path.

### Wealth Management

`wealth_management` should move to the following priority order:

1. public bank wealth-management or wealth-subsidiary product data
2. public proxy products for cash-management or stable wealth use cases
3. static fallback catalog

Candidate filtering rules:

- prefer `R1-R2`
- prefer shorter tenor or better liquidity
- require recognizable provider and date fields
- keep candidate count intentionally small and high-quality

### Stock

Stocks should no longer come from the tiny static catalog by default. Instead, the system should build a premium stock universe from index or theme constituents, then derive a dynamic stock candidate pool from that universe.

#### Premium Stock Universe Strategy

The universe should be auto-generated from curated index or theme sources, not maintained as a tiny manual list.

Recommended starting universe sources:

- CSI 300 or HS300 quality blue chips
- dividend or low-volatility dividend constituents
- financial, utility, and consumer leaders
- central SOE or other quality large-cap leaders
- growth sector leaders in technology, healthcare, advanced manufacturing, or new energy

This matches the approved stance:

- balanced core
- meaningful growth participation
- not growth-only
- not dividend-only

#### Stock Filtering And Ranking

The first phase should still avoid fully unconstrained whole-market stock selection.

Recommended process:

1. generate the premium stock universe
2. fetch dynamic price, change, trend, and liquidity facts
3. filter out illiquid, structurally noisy, or data-poor names
4. score candidates against:
   - user suitability
   - market stance
   - style relevance
   - liquidity and stability
5. write top stock candidates into the stock candidate pool snapshot

This means growth names can compete normally, but they still need to pass suitability and market-fit scoring.

## Recommendation Serving Path

`RecommendationGraphRuntime.with_default_services()` should stop using request-time real-data repositories as the default serving model. Instead it should use a prefetched-candidate repository that reads candidate pool snapshots.

Serving path:

1. request enters FastAPI
2. graph runtime loads candidate pool snapshots from cache
3. if fresh pool exists, use it
4. if only stale pool exists, use it and attach warnings
5. if no valid pool exists, fall back to static repository and attach warnings
6. the rest of the graph stays unchanged:
   - user profile analyst
   - market intelligence
   - product match expert
   - compliance risk officer
   - manager coordinator

## Product Detail Experience

### Routing

The frontend should add an in-app detail route:

- `/recommendations/products/:productId`

Recommendation cards should link to this route through a `detailRoute` field or deterministic route construction from `product.id`.

### Recommendation Card Contract

Each `RecommendationProduct` should add:

- `detailRoute`
- `asOfDate`

The recommendation card UI should add a CTA such as:

- `查看详情`
- `View details`

### Product Detail API

Add:

- `GET /api/recommendations/products/{product_id}`

Response contract should include the `ProductDetailSnapshot` fields in a frontend-friendly shape.

### Detail Page Content

The chosen detail-page scope is the standard level:

- basic product information
- recent yield or performance metrics
- chart
- risk level
- liquidity
- fees
- drawdown or volatility when available
- strategy or style tags
- recommendation rationale
- fit-for-user explanation

### Stale-First Detail Behavior

Detail read behavior should be:

1. read detail snapshot from cache
2. if fresh, return immediately
3. if stale, return stale payload plus stale marker
4. trigger background refresh without blocking the response
5. if no detail exists, return fallback summary if possible and attempt refresh

The API should never block detail-page rendering on a slow upstream fetch in the normal path.

## Proposed Module Layout

Recommended new modules:

- `backend/financehub_market_api/recommendation/candidate_pool/schemas.py`
- `backend/financehub_market_api/recommendation/candidate_pool/cache.py`
- `backend/financehub_market_api/recommendation/candidate_pool/refresh.py`
- `backend/financehub_market_api/recommendation/candidate_pool/details.py`
- `backend/financehub_market_api/recommendation/repositories/prefetched_candidate_repository.py`
- `backend/scripts/refresh_recommendation_candidate_pool.py`

Likely modified modules:

- `backend/financehub_market_api/recommendation/graph/runtime.py`
- `backend/financehub_market_api/main.py`
- `backend/financehub_market_api/models.py`
- `backend/financehub_market_api/recommendation/services/assembler.py`
- `backend/financehub_market_api/recommendation/repositories/real_data_repository.py`
- `backend/financehub_market_api/recommendation/repositories/real_data_adapters.py`
- `src/services/chinaMarketApi.ts`
- `src/app/router.tsx`
- `src/features/recommendations/RecommendationDeck.tsx`
- new recommendation detail page component files

## Failure And Degradation Behavior

### Refresh Failures

- do not clear an existing valid snapshot because a new refresh failed
- retain the last known snapshot
- attach warnings to metadata
- let the next refresh try again

### Serving Failures

- candidate pool missing -> fallback to static repository with warning
- detail snapshot missing -> return best-effort fallback response or clear error state
- Redis unavailable -> fall back to in-memory cache behavior where possible
- malformed cache payload -> delete and fall back

## Testing Strategy

### Backend

Add focused tests for:

- candidate pool cache serialization and stale behavior
- refresh script per-category success and failure paths
- prefetched repository reading fresh snapshots
- prefetched repository falling back from stale or missing snapshots
- detail snapshot reading and background refresh triggering
- recommendation response includes `detailRoute` and `asOfDate`
- product detail API returns standard detail payload and stale markers

### Frontend

Add focused tests for:

- recommendation cards render detail CTA
- detail CTA routes into the in-app product detail page
- detail page renders standard sections and chart
- detail page shows stale notices when appropriate
- detail page handles refresh or fallback states cleanly

## Rollout Notes

Recommended rollout order:

1. introduce snapshot models and cache helpers
2. implement prefetched repository and switch default recommendation serving to it
3. add refresh script and initial candidate sources
4. add detail snapshot API
5. add frontend detail route and card links
6. replace default wealth-management and stock sources with prefetched dynamic pools

This order keeps the recommendation API usable throughout the migration and allows static fallback to remain in place until the new pools are proven stable.

## Open Constraints Resolved In This Design

- wealth-management data should prefer real public bank or wealth-subsidiary products
- proxy products are allowed only as fallback
- stock selection should use a larger premium stock universe derived from index or theme constituents
- growth names can compete normally instead of being permanently suppressed
- recommendation pages should expose in-app product detail pages
- detail pages should use stale-first cached data plus background refresh

## Summary

The chosen design moves recommendation serving away from request-time product fetching and toward a dual-snapshot model:

- candidate pools for recommendation decisions
- detail snapshots for in-app product exploration

This gives the system lower request latency, stronger operational resilience, richer detail pages, and a more credible wealth-management and stock sourcing model without rewriting the LangGraph recommendation funnel itself.
