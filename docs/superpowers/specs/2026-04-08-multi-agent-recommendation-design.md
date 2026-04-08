# 2026-04-08 LangGraph Native Multi-Agent Recommendation Design

## Status

- Approved in terminal brainstorming on 2026-04-08
- Scope: recommendation backend only
- Delivery target: phase-one minimum viable full chain

## Context

The current backend exposes a stable recommendation API, but the internal recommendation flow is still centered on a rule-driven fallback engine with a thin agent-assisted overlay. The request model already accepts richer user inputs such as questionnaire answers, holdings, and transaction history, yet the orchestration layer only uses the final risk profile in its main decision path.

The new system must replace the current recommendation core with a graph-native, multi-agent pipeline that:

- models the recommendation process as a funnel rather than a linear rule chain
- uses LangGraph as the primary orchestration layer
- keeps FastAPI service boundaries intact
- remains compatible with the existing response model while allowing additive fields
- supports real external intelligence, semantic retrieval, and agent-led compliance review
- degrades in layers for upstream failures while treating compliance as a hard gate

## Goals

1. Replace the existing recommendation orchestration with a LangGraph-native pipeline built around 4+1 core agents.
2. Make real use of all first-phase user inputs: questionnaire answers, historical holdings, historical transactions, natural-language intent, and conversation history.
3. Add a production-shaped retrieval layer for product matching and user memory.
4. Add a production-shaped market intelligence layer for news, macro, and rate signals.
5. Keep `/api/recommendations/generate` and `RecommendationResponse` compatible for the existing frontend.
6. Add structured traceability so degraded paths, compliance outcomes, and evidence are visible in logs and API extensions.

## Non-Goals

1. Rebuild the frontend recommendation experience in this phase.
2. Introduce multi-provider LLM routing in this phase. Anthropic remains the only supported provider.
3. Support asynchronous human approval workflows or long-running resumable agent sessions in this phase.
4. Generalize the system into a reusable cross-domain agent platform.
5. Refactor unrelated market overview, indices, or stock APIs.

## Approved Product Decisions

- Architecture direction: full graph-native recommendation runtime, not a wrapper around the old rule orchestrator
- Orchestration framework: LangGraph
- External contract strategy: keep existing response contract compatible, allow additive fields
- Compliance posture: LLM-led compliance review with policy context
- Degradation posture: layered degradation for profile, market, and matching stages; hard gate at compliance
- Provider strategy: Anthropic only in phase one
- Infrastructure posture: production-shaped first phase is allowed, including additional services

## Recommended Architecture

The new recommendation flow will be implemented as a single compiled LangGraph graph that operates on one shared typed state object. Each core agent owns one explicit responsibility and writes only its portion of state. Retrieval, memory, intelligence, and policy access are implemented as tool services called from nodes rather than as hidden side effects.

The graph remains request-scoped and synchronous in phase one. Each API request constructs an initial graph state, executes the compiled graph, then maps the terminal state back into `RecommendationResponse` plus additive extension fields. This keeps the current FastAPI behavior intact while allowing the internals to become fully graph-native.

### Core Agent Roles

1. `user_profile_analyst`
   - Interprets questionnaire answers, holdings, transactions, natural-language intent, and recalled memory.
   - Produces a structured user profile with risk tier, liquidity preference, horizon, return objective, drawdown sensitivity, and inferred intent summary.
2. `market_intelligence`
   - Pulls current market evidence from news, macro, rates, and existing market data sources.
   - Produces a normalized market stance with sentiment, sector bias, macro summary, and evidence freshness.
3. `product_match_expert`
   - Queries the product vector index, applies category and suitability filters, and ranks candidates.
   - Produces top candidates per section plus ranking reasons and retrieval diagnostics.
4. `compliance_risk_officer`
   - Reviews candidate suitability and language against policy context and user tolerance.
   - Produces one of three outcomes: `approve`, `revise_conservative`, or `block`.
5. `manager_coordinator`
   - Merges all prior outputs into the final recommendation memo and response payload.
   - Does not override compliance verdicts or invent missing evidence.

## Graph Topology

The graph is intentionally funnel-shaped:

1. `normalize_request`
   - Converts request payload into internal state and default metadata.
2. `user_profile_analyst`
   - Runs after normalization.
   - Performs user memory recall internally before finalizing profile output.
3. `market_intelligence`
   - Runs in parallel with `user_profile_analyst` after normalization.
4. `product_match_expert`
   - Runs after both profile and market outputs are available.
   - Uses product retrieval tools and section-aware ranking.
5. `compliance_risk_officer`
   - Runs after product matching.
   - Routes to one of three branches:
   - `approve` -> `manager_coordinator`
   - `revise_conservative` -> `manager_coordinator`
   - `block` -> `manager_coordinator`
6. `manager_coordinator`
   - Generates the final response bundle, warnings, and compatibility mapping.

There is no rule-engine node in the main graph. The old rule flow may remain temporarily outside the graph as an emergency service-level fallback during rollout, but it is not part of the steady-state recommendation path.

## Shared Graph State

`RecommendationGraphState` will be the single source of truth for one request. It should use a LangGraph-friendly typed state definition with explicit nested models for structured outputs.

### Required Top-Level State Fields

- `request_context`
  - raw request payload
  - normalized language intent
  - questionnaire answers
  - historical holdings
  - historical transactions
  - conversation messages
  - request identifiers and timestamps
- `user_intelligence`
  - risk tier `R1` through `R5`
  - liquidity preference
  - investment horizon
  - return objective
  - drawdown sensitivity
  - capital stability
  - inferred intent summary
  - supporting evidence snippets
- `market_intelligence`
  - market sentiment
  - recommended stance: defensive, balanced, or offensive
  - sector or asset bias
  - macro summary
  - rate summary
  - evidence sources
  - freshness timestamp
- `retrieval_context`
  - recalled user memories
  - retrieved product candidates
  - vector scores
  - applied structured filters
  - filtered-out reasons
  - per-section ranked candidates
- `compliance_review`
  - verdict: `approve`, `revise_conservative`, or `block`
  - suitability findings
  - policy findings
  - required disclosures
  - allowed response scope
  - user-facing warning copy
- `final_response`
  - final recommendation memo
  - final section payloads
  - compatibility-mapped response fields
- `warnings`
  - stage-scoped degradation warnings
- `agent_trace`
  - node timings
  - request names
  - model names
  - fallback reasons
  - graph path summary

### State Ownership Rules

- Each node writes only its owned section plus generic warning and trace append-only lists.
- Downstream nodes may read upstream outputs but may not mutate them.
- The manager node may assemble response text from prior state, but may not rewrite compliance verdicts or evidence.
- Compliance output is terminal authority for whether a full recommendation can be shown.

## Data Model Changes

### Request Extensions

`RecommendationGenerationRequest` remains valid, but phase one adds optional fields:

- `userIntentText: str | None`
- `conversationMessages: list[ConversationMessage]`
- `clientContext: RecommendationClientContext | None`

`ConversationMessage` should include:

- `role`
- `content`
- `occurredAt`

`RecommendationClientContext` should include optional frontend metadata that helps trace requests without affecting recommendation logic, such as locale or channel.

Existing callers that do not send the new fields remain valid.

### Response Extensions

`RecommendationResponse` keeps all current fields. Phase one adds optional fields:

- `recommendationStatus`
  - `ready`
  - `limited`
  - `blocked`
- `complianceReview`
  - verdict
  - reason summary
  - required disclosures
  - suitability notes
- `marketEvidence`
  - source labels
  - as-of time
  - evidence summary
- `agentTrace`
  - node names
  - durations
  - degradation markers
  - graph version

`executionMode` remains backward compatible:

- `agent_assisted` for successful graph-native execution, including limited outputs
- `rules_fallback` only for emergency service-level fallback outside the graph

This avoids breaking the current frontend union types while still making graph-native behavior observable through additive fields.

## Service and Storage Layout

Phase one introduces production-shaped service boundaries inside the backend package.

### Proposed Package Structure

- `backend/financehub_market_api/recommendation/graph/`
  - `state.py`
  - `nodes.py`
  - `routing.py`
  - `runtime.py`
- `backend/financehub_market_api/recommendation/llm_runtime/`
  - Anthropic structured-output executor
  - shared retry and timeout handling
  - trace logging utilities
- `backend/financehub_market_api/recommendation/intelligence/`
  - market intelligence service
  - source adapters
  - normalization helpers
- `backend/financehub_market_api/recommendation/memory/`
  - conversation memory repository
  - embedding service
  - recall service
- `backend/financehub_market_api/recommendation/product_index/`
  - product document schema
  - vector repository
  - retrieval and filtering service
- `backend/financehub_market_api/recommendation/compliance/`
  - policy repository
  - review prompts
  - verdict normalizer

### Concrete Service Choices

- `LangGraph` is the orchestration runtime.
- `Anthropic` remains the only LLM provider in phase one.
- `Qdrant` is the vector database for:
  - product catalog embeddings
  - user memory embeddings
- `Redis` remains the cache layer for:
  - market intelligence cache
  - transient request-level intelligence cache
  - optional response snapshot cache

Phase one does not require durable LangGraph checkpoint persistence because each request runs synchronously to completion. Durable resumes can be added later without changing the node contracts.

## Node Contracts

### 1. User Profile Analyst

Inputs:

- normalized request context
- questionnaire answers
- holdings
- transactions
- user intent text
- conversation messages
- recalled memory documents

Outputs:

- structured risk tier `R1` through `R5`
- liquidity preference
- investment horizon
- return objective
- drawdown sensitivity
- user intent summary
- evidence list

Fallback behavior:

- If the node fails, use deterministic inference from questionnaire and historical behavior, then emit a warning.

### 2. Market Intelligence

Inputs:

- normalized request context
- existing market API data
- news feed documents
- macro indicators
- rate snapshots

Outputs:

- sentiment: positive, negative, or neutral
- stance: defensive, balanced, or offensive
- recommended sectors or asset classes
- Chinese and English market summaries
- evidence summary and freshness

Fallback behavior:

- If live intelligence fails, use cached intelligence or a static normalized summary derived from existing market services, then emit a warning.

### 3. Product Match Expert

Inputs:

- user profile output
- market intelligence output
- product vector index
- product metadata filters

Outputs:

- top candidates per section:
  - funds
  - wealth management
  - stocks
- ranking reasons
- retrieval diagnostics

Retrieval approach:

1. Build semantic query text from user and market outputs.
2. Retrieve top-k candidates from Qdrant per section.
3. Apply structured suitability filters such as risk level, horizon fit, liquidity fit, and category eligibility.
4. Ask the ranking model to order only the filtered candidate identifiers and produce short reasons.

Fallback behavior:

- If vector retrieval fails, use repository-backed deterministic candidate lists and category ordering, then emit a warning.

### 4. Compliance Risk Officer

Inputs:

- user profile output
- market output
- ranked product candidates
- policy library
- disclosure templates

Outputs:

- verdict:
  - `approve`
  - `revise_conservative`
  - `block`
- suitability notes
- risk disclosures
- permitted output scope

Hard-gate behavior:

- `approve`: full recommendation allowed
- `revise_conservative`: manager may only output the approved conservative subset and mandatory disclosures
- `block`: manager returns no actionable product recommendation, only explanation and safe next-step guidance

Failure behavior:

- If compliance output is missing, invalid, or provider-failed, the graph does not continue as a full recommendation.
- The graph returns either `limited` or `blocked` based on the last safe conservative subset available.

### 5. Manager / Coordinator

Inputs:

- all prior node outputs

Outputs:

- final recommendation memo
- compatibility response sections
- additive response extensions

Restrictions:

- Must not introduce products absent from retrieval output
- Must not contradict compliance verdict
- Must not hide warnings or required disclosures

## Product and Memory Indexing

### Product Index

The product vector store must be populated from repository-owned product documents rather than free-form raw text. Each stored document should include:

- stable product id
- category
- bilingual names
- risk level
- liquidity
- tags
- rationale text
- structured suitability metadata

Phase one bootstrap sources:

- existing static recommendation catalogs
- existing real-data candidate repository outputs

This allows the system to reuse current product assets while moving retrieval into a vector-first architecture.

### User Memory Store

The memory collection stores embeddings for:

- past conversation messages
- historical recommendations
- preference summaries derived from behavior

Memory recall is read-only in phase one during request execution. Memory writes happen after a successful response is assembled so request-time behavior stays deterministic.

## Market Intelligence Sources

The market intelligence layer will normalize several sources into one internal schema:

- existing market overview and indices data already available in the backend
- macro indicators
- rate snapshots
- curated news summaries

Each source adapter must produce:

- source name
- as-of timestamp
- normalized summary
- reliability flag

The node consumes only normalized outputs, which keeps model prompts stable even if raw sources change.

## Degradation and Error Handling

Layered degradation is explicit and traceable.

### Allowed Degradation

- `user_profile_analyst`
  - downgrade to deterministic profile inference
- `market_intelligence`
  - downgrade to cached or static market summary
- `product_match_expert`
  - downgrade to deterministic repository candidates

### Disallowed Bypass

- `compliance_risk_officer`
  - no full recommendation may be emitted if compliance fails

### Warning Format

Warnings remain stage-scoped and user-safe:

- `stage`
- `code`
- `message`

Trace logs remain operator-focused and can include richer internal context.

## Observability

Phase one keeps the existing trace-oriented mindset and extends it to the graph runtime.

### Required Telemetry

- request id
- graph version
- node start and finish logs
- node duration
- model name
- fallback cause
- final recommendation status
- compliance verdict

### Logging Rules

- Logs must remain structured and safe for uvicorn output.
- Raw provider payload capture remains opt-in through environment configuration.
- User-facing responses must never leak internal prompt text or provider exceptions verbatim.

## Testing Strategy

### Unit Tests

- graph state initialization
- node contract validation
- prompt payload assembly
- vector retrieval filters
- compliance verdict normalization

### Integration Tests

- successful full recommendation path
- degraded profile path
- degraded market path
- degraded retrieval path
- compliance revise-to-limited path
- compliance blocked path
- emergency service-level fallback path

### API Contract Tests

- existing frontend fields remain present and typed as before
- additive fields are omitted or null-safe when unavailable
- `executionMode` remains compatible
- `recommendationStatus` correctly distinguishes `ready`, `limited`, and `blocked`

### Regression Tests

- existing recommendation sections still populate funds, wealth management, and stocks in compatible structure
- warnings still surface in predictable order
- agent trace still records request names and stage timing

## Migration Plan

Migration should happen in small, reviewable steps without mixing old and new paths in one file more than necessary.

### Step 1

Introduce new graph-native state models, nested schemas, and additive API models.

### Step 2

Add service modules for market intelligence, memory recall, product retrieval, and compliance policy loading.

### Step 3

Implement LangGraph nodes and compile the graph runtime.

### Step 4

Add a new recommendation assembler that maps graph terminal state to `RecommendationResponse`.

### Step 5

Switch `RecommendationService` to the new graph runtime behind the existing FastAPI endpoints.

### Step 6

Retain the old rule-based orchestrator only as an emergency fallback during rollout and test parity.

### Step 7

After graph stability is verified, remove the old steady-state orchestrator path and obsolete runtime-only agent code that duplicated the graph node responsibilities.

## Implementation Constraints

- Python target remains 3.11+
- Changes should remain focused on the recommendation backend
- New and modified function signatures should be typed
- Tests should be added for every new branch with observable behavior
- Existing untracked workspace content, including `tmp/`, must remain untouched

## Acceptance Criteria

The design is complete when the implementation can satisfy all of the following:

1. A request to `/api/recommendations/generate` can execute a LangGraph-native 4+1 agent flow.
2. Questionnaire, holdings, transactions, user intent text, and conversation history all influence recommendation state.
3. Market intelligence uses normalized external evidence instead of only static profile summaries.
4. Product matching uses vector retrieval plus structured filters and ranking.
5. Compliance can return `approve`, `revise_conservative`, or `block`, and the response behavior changes accordingly.
6. Existing frontend consumers still receive a compatible `RecommendationResponse`.
7. The response can expose additive compliance, evidence, and trace fields without breaking older clients.
8. Upstream agent failures degrade in layers, while compliance remains a hard gate.
9. Tests cover full, degraded, limited, and blocked paths.
