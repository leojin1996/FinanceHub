# FinanceHub Product RAG Design

## Goal

Add product-document RAG to the existing recommendation graph so recommendation
generation can cite product evidence, product detail pages can show public
references, and internal product knowledge can improve backend judgment without
being exposed to end users.

## Requirement Understanding

The first phase focuses on product information RAG, not a general chat assistant.
The primary user-facing outcome is better recommendation generation with explicit
evidence. The same retrieval layer must also support product detail reference
display. Knowledge sources include both public product documents and internal
curated product materials.

## Confirmed Decisions

- Prioritize product information RAG first.
- Use the recommendation-generation flow as the primary integration point.
- Reuse the same retrieval layer later for product detail explanations.
- Use self-hosted `Qdrant + embeddings`, not hosted file search.
- Support immediate indexing after document upload plus later incremental sync.
- Allow internal materials in backend retrieval, but never return them to the
  frontend.
- Add smoke coverage and end-to-end coverage.
- First-phase live E2E must run against a real Qdrant instance.

## Current Project Context

The repository already has the right extension points:

- Candidate retrieval and ranking live in
  `backend/financehub_market_api/recommendation/product_index/service.py`.
- Memory recall lives in
  `backend/financehub_market_api/recommendation/memory/service.py`.
- Graph state already has `retrieval_context` in
  `backend/financehub_market_api/recommendation/graph/state.py`.
- The recommendation flow already routes through
  `user_profile_analyst -> market_intelligence -> product_match_expert ->
  compliance_risk_officer -> manager_coordinator`.
- The backend already depends on `qdrant-client`.

This means the design should extend the existing graph rather than introduce a
separate RAG-specific runtime.

## Scope

### In Scope

- Product-document evidence retrieval for shortlisted recommendation candidates
- Public and internal document coexistence in the same retrieval layer
- Public-only evidence projection into API responses
- Product evidence preview on recommendation cards
- Full public evidence list on product detail responses
- Graph degradation when document retrieval is unavailable
- Deterministic smoke and E2E test coverage
- Live smoke and live E2E coverage against real provider configuration and real
  Qdrant

### Out of Scope

- OCR for scanned-only PDFs
- Full document ingestion UI
- General-purpose conversational RAG
- Authorization-aware frontend display of internal evidence
- Automatic multilingual translation of source excerpts
- Replacing the existing candidate-pool refresh pipeline

## Architecture

The design keeps the current recommendation pipeline and inserts product evidence
retrieval inside `product_match_expert`.

### Retrieval Sequence

1. Build user profile and market stance as today.
2. Use the existing `ProductRetrievalService` to shortlist candidate products.
3. Query Qdrant for product-document evidence constrained to the shortlisted
   product ids.
4. Pass product facts plus evidence bundles into `product_match_expert`.
5. Store evidence in graph state so downstream compliance and manager nodes can
   reuse it without re-querying.
6. Project only public evidence into API responses for frontend display.

### Why This Shape

- Candidate retrieval remains responsible for product ranking.
- Product knowledge retrieval becomes a separate concern for evidence.
- The graph keeps a single source of truth for downstream nodes.
- The frontend receives explicit citations without learning anything about
  internal-only materials.

## Data Model

### Backend Retrieval Objects

Add retrieval-specific models for document evidence:

- `RetrievedProductEvidence`
- `ProductEvidenceBundle`

Recommended fields:

- `evidence_id`
- `product_id`
- `score`
- `snippet`
- `source_title`
- `source_uri`
- `doc_type`
- `source_type`
- `visibility`
- `user_displayable`
- `as_of_date`
- `page_number`
- `section_title`
- `language`

`RetrievalContext` should gain:

- `product_evidences: list[ProductEvidenceBundle]`

The internal graph state keeps the full evidence list, including internal
materials.

### Frontend Response Objects

Add a new public-facing response model:

- `RecommendationEvidenceReference`

Recommended fields:

- `evidenceId`
- `excerpt`
- `excerptLanguage`
- `sourceTitle`
- `docType`
- `asOfDate`
- `pageNumber`
- `sectionTitle`
- `sourceUri`

Use it in two places:

- `RecommendationProduct.evidencePreview`
- `RecommendationProductDetailResponse.evidence`

Do not expose retrieval score, raw visibility, or internal source markers in the
frontend response model.

## Qdrant Collection Shape

Each indexed chunk should be stored as one point with the original chunk text and
payload metadata.

Recommended payload fields:

- `product_id`
- `product_category`
- `product_code`
- `document_id`
- `chunk_id`
- `doc_type`
- `source_type`
- `visibility`
- `user_displayable`
- `source_title`
- `source_uri`
- `as_of_date`
- `page_number`
- `section_title`
- `language`
- `text`

Recommended source values:

- Public documents: `source_type=public_official`, `visibility=public`,
  `user_displayable=true`
- Internal materials: `source_type=internal_curated`, `visibility=internal`,
  `user_displayable=false`

Recommended online filters:

- `product_id in shortlisted_ids`
- `visibility in {public, internal}` for backend graph retrieval
- `user_displayable=true` for frontend projection
- Optional `doc_type` and recency constraints

## Graph Integration

### `product_match_expert`

Modify `product_match_expert` so it:

1. Builds the shortlist with the existing `ProductRetrievalService`
2. Retrieves product-document evidence for the shortlisted products
3. Adds evidence bundles to the prompt context
4. Persists evidence bundles into `retrieval_context`

The prompt must explicitly instruct the model:

- prefer retrieved evidence over generic candidate summaries when they conflict
- do not invent product terms or restrictions when no evidence is present
- ground ranking rationale in evidence when possible

### `compliance_risk_officer`

Reuse `retrieval_context.product_evidences` to check whether recommendation claims
are supported by product documents. This node should not re-run retrieval.

### `manager_coordinator`

Reuse `retrieval_context.product_evidences` to produce evidence-backed user-facing
justification and explanation text. This node should also avoid re-querying.

## Product Detail Reuse

The same retrieval layer must support the product detail endpoint.

The detail flow should:

1. Query public evidence for the requested product id
2. Return all public evidence references in the detail response
3. Keep internal evidence out of the response entirely

## Visibility and Compliance Rules

Internal materials may influence backend judgment, but they must never be exposed
to the frontend.

### Allowed Backend Uses

- ranking support
- compliance review support
- manager summary support
- warning generation
- operator debugging

### Disallowed Frontend Uses

- raw internal excerpts
- internal source titles
- internal-only links
- internal score or visibility markers

If a product has only internal evidence and no public evidence:

- backend nodes may still use internal evidence
- frontend evidence arrays must be empty
- the system must not fabricate a public citation

## API Response Behavior

### Recommendation Generation Response

Each returned product may include `evidencePreview`, containing at most a small
number of public references, recommended as `1-2` per product.

### Product Detail Response

Each detail payload should include `evidence`, containing the full list of public
references for that product, subject to reasonable truncation if needed.

### Empty-Evidence Cases

If public evidence is unavailable:

- return an empty evidence array
- do not fail the recommendation request
- optionally emit a degradation warning when retrieval infrastructure failed

## Error Handling and Degradation

### Qdrant Unavailable

- keep recommendation generation alive
- fall back to existing candidate ranking behavior
- return empty public evidence arrays
- append a warning describing retrieval degradation

### No Evidence Hits

- keep recommendation generation alive
- tell the model that specific document support is unavailable
- do not invent product restrictions, fees, or liquidity terms

### Public/Internal Conflict

When public and internal materials disagree, backend logic should prefer the more
recent and more authoritative evidence while preserving a warning or trace marker
for inspection. Frontend responses should continue to display only public
citations.

## File Responsibilities

### New Backend Modules

- `backend/financehub_market_api/recommendation/product_knowledge/schemas.py`
  - retrieval-specific evidence models
- `backend/financehub_market_api/recommendation/product_knowledge/service.py`
  - graph-facing retrieval service API
- `backend/financehub_market_api/recommendation/product_knowledge/qdrant_store.py`
  - Qdrant query and mapping logic

### Existing Backend Files To Modify

- `backend/financehub_market_api/recommendation/graph/state.py`
  - add evidence bundles to retrieval context
- `backend/financehub_market_api/recommendation/graph/nodes.py`
  - retrieve and pass evidence inside `product_match_expert`
- `backend/financehub_market_api/recommendation/graph/runtime.py`
  - inject knowledge retrieval service and deterministic stubs
- `backend/financehub_market_api/models.py`
  - add public evidence response models
- `backend/financehub_market_api/recommendation/services/assembler.py`
  - project graph evidence into frontend-safe response fields
- `backend/financehub_market_api/recommendation/services/product_detail_service.py`
  - add public evidence to detail responses

### Frontend Files To Modify

- `src/services/chinaMarketApi.ts`
  - TypeScript types for evidence references
- `src/features/recommendations/RecommendationDeck.tsx`
  - show evidence previews on recommendation cards
- `src/features/recommendations/RecommendationProductDetailPage.tsx`
  - show full public evidence block on the detail page

## Testing Strategy

### Unit Tests

Add focused tests for:

- Qdrant hit mapping into evidence bundles
- public/internal filtering
- per-product truncation and deduplication
- projection from internal graph evidence to public API fields

### Integration Tests

Extend graph runtime coverage to prove:

- `product_match_expert` stores evidence bundles in graph state
- downstream nodes reuse graph evidence
- recommendation output exposes only public evidence previews

### API Tests

Extend API coverage to prove:

- recommendation responses include `evidencePreview`
- product detail responses include `evidence`
- internal-only evidence never appears in JSON responses

### Deterministic Smoke Tests

Add deterministic smoke tests that:

- load a small seeded product-document corpus
- run recommendation generation
- verify preview evidence exists in the response
- fetch a recommended product detail
- verify detail evidence exists and remains public-only

These should be suitable for CI and local repeated runs without live provider
dependencies.

### Deterministic E2E Tests

Add end-to-end tests that execute:

1. `POST /api/recommendations/generate`
2. parse one returned product
3. `GET /api/recommendations/products/{product_id}`
4. verify preview evidence and detail evidence align
5. verify no internal evidence leaks

### Live Smoke Tests

Add live smoke tests gated by environment variables, following the same pattern as
the existing live OpenAI smoke coverage. The live smoke path should validate that
real provider configuration plus real Qdrant connectivity can produce usable
evidence-backed outputs.

### Live E2E Tests

Add live E2E tests gated by environment variables that run against:

- a real configured provider
- a real Qdrant instance

The live E2E path must verify:

- recommendation generation succeeds with evidence-backed products
- product detail retrieval succeeds
- public evidence is returned
- internal evidence is not returned

## Acceptance Criteria

The first phase is complete when all of the following are true:

- recommendation generation can attach public evidence previews to products
- backend nodes can consume internal and public evidence together
- product detail responses return public evidence references
- internal evidence never appears in frontend responses
- Qdrant failure degrades cleanly without breaking recommendation generation
- deterministic smoke and deterministic E2E coverage exist
- live smoke and live E2E coverage exist
- live E2E is capable of running against a real Qdrant instance

## Risks and Edge Cases

- Some products may have only internal evidence and no public citation path.
- Public PDFs may contain poor extractable text and need later OCR support.
- Over-retrieval can crowd prompts with repetitive chunks from the same document.
- Evidence recency conflicts may require stronger tie-breaking rules.
- Live E2E can become flaky if Qdrant contents drift without controlled fixtures.

## Technical References

- OpenAI retrieval guide:
  `https://platform.openai.com/docs/guides/retrieval`
- OpenAI embeddings docs:
  `https://developers.openai.com/api/docs/models/text-embedding-3-small`
  and
  `https://developers.openai.com/api/docs/models/text-embedding-3-large`
