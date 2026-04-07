# FinanceHub 20-Question Risk Assessment Upgrade Design

## Goal

Upgrade the existing 6-question risk questionnaire into a more precise 20-question model while keeping the FinanceHub experience fast, explainable, and consistent with the current shell.

The upgraded flow must:

- expand the questionnaire to 20 questions
- organize questions into 5 dimensions with 4 questions each
- keep Simplified Chinese as the default locale and support English copy
- produce both a final risk profile and dimension-level diagnostics
- show a personalized explanation of the result
- let recommendations continue to be driven by the main profile, with dimension scores used to refine stock ordering and recommendation reasons

## Scope

This upgrade changes only the risk assessment and recommendation logic plus the related UI and tests.

In scope:

- questionnaire data model
- questionnaire copy
- scoring and profile classification
- result presentation on the risk assessment page
- recommendation explanation and ordering logic
- tests for scoring, result rendering, and recommendation behavior

Out of scope:

- real brokerage compliance wording
- legal disclosures
- backend persistence
- user accounts or saved history
- replacing the current recommendation content source with live market data

## Product Direction

Use a structured, explainable assessment model instead of a single flat score.

The questionnaire will use:

- 20 total questions
- 5 dimensions
- 4 questions per dimension
- 5 answer options per question
- 1 to 5 points per answer

This keeps the experience formal enough to feel credible without turning the flow into a heavy compliance form.

## Assessment Dimensions

The 5 dimensions are:

1. `riskTolerance`
How comfortable the user is with short-term drawdowns, volatility, and adverse price moves.

2. `investmentHorizon`
How long the user can keep capital invested and whether time can be used to absorb volatility.

3. `capitalStability`
How stable the user’s income, emergency reserves, and investable capital are.

4. `investmentExperience`
How familiar the user is with equity products, market cycles, and portfolio behavior.

5. `returnObjective`
How strongly the user prioritizes capital preservation, steady growth, or higher upside.

## Question Structure

Each dimension receives 4 questions. Each question has 5 ordered answers from lowest-risk to highest-risk preference.

Question writing rules:

- all questions must have both `promptZh` and `promptEn`
- all answers must have both `labelZh` and `labelEn`
- all answers must map to integer scores `1` through `5`
- questions must be written so higher scores consistently represent higher tolerance for risk or uncertainty
- avoid regulatory claims or suitability promises
- keep each answer short enough to remain readable in card-based layouts

### Dimension Coverage

`riskTolerance`

- reaction to short-term volatility
- reaction to a 10% drawdown
- reaction to several consecutive losing weeks
- acceptable temporary decline before changing strategy

`investmentHorizon`

- expected holding period
- willingness to wait through multi-quarter volatility
- time sensitivity of invested funds
- long-term financial planning horizon

`capitalStability`

- income stability
- adequacy of emergency cash reserves
- likelihood of needing invested money within 12 months
- whether investable funds are truly discretionary

`investmentExperience`

- experience with stocks, funds, and index products
- understanding of drawdown and compounding
- experience living through market declines
- comfort interpreting portfolio volatility

`returnObjective`

- preference between preservation and upside
- target growth expectations
- willingness to trade stability for higher returns
- desired role of higher-volatility assets in the portfolio

## Scoring Model

### Raw Scores

- each question score range: `1-5`
- each dimension score range: `4-20`
- total score range: `20-100`

### Dimension Levels

Each dimension score maps to a five-level interpretation:

- `4-7`: low
- `8-10`: mediumLow
- `11-13`: medium
- `14-16`: mediumHigh
- `17-20`: high

These labels are internal values. The UI should show localized human labels.

Chinese display labels:

- `low`: `低`
- `mediumLow`: `中低`
- `medium`: `中`
- `mediumHigh`: `中高`
- `high`: `高`

English display labels:

- `low`: `Low`
- `mediumLow`: `Medium-Low`
- `medium`: `Medium`
- `mediumHigh`: `Medium-High`
- `high`: `High`

### Base Risk Profile by Total Score

The base profile comes from total score:

- `20-35`: `conservative`
- `36-50`: `stable`
- `51-65`: `balanced`
- `66-80`: `growth`
- `81-100`: `aggressive`

### Profile Adjustment Rules

The final profile is not a pure total-score result. It must be corrected by key dimensions.

#### Downward adjustment

- if `riskTolerance` or `capitalStability` is `low`, the final profile must not exceed `balanced`
- if both `riskTolerance` and `capitalStability` are `mediumLow` or below, and the base profile is above `balanced`, lower the final profile by one level

#### Upward adjustment

- if the base profile sits at the upper edge of its score band, and at least 2 of `investmentHorizon`, `investmentExperience`, and `returnObjective` are `mediumHigh` or `high`, and `capitalStability` is at least `medium`, raise the final profile by one level

#### Stability-first rule

When upward and downward signals conflict, the downward signal wins. The model should prefer underestimating aggressiveness over overstating it.

### Upper-edge rule

To keep the adjustment deterministic, the upper-edge threshold is defined as the top 20% of a score band.

That means:

- `stable`: `48-50`
- `balanced`: `63-65`
- `growth`: `78-80`
- `aggressive`: no upward adjustment above this band
- `conservative`: no upward adjustment from this band

## Result Page Design

The risk assessment result must present 3 layers of output:

### 1. Final profile summary

Show:

- final profile label
- a short localized profile summary sentence

Examples:

- `保守型`: prioritizes capital preservation and lower volatility exposure
- `平衡型`: accepts moderate volatility for a blend of stability and growth
- `进取型`: seeks higher upside and can tolerate larger swings

### 2. Five-dimension diagnostics

Show 5 dimension cards, one per dimension.

Each card must contain:

- localized dimension title
- localized level label
- one short interpretation sentence tied to that dimension

These cards explain why the user landed in the final profile.

### 3. Personalized narrative

Show a short localized paragraph that synthesizes the result.

This narrative must reference the user’s strongest and weakest dimensions rather than repeating score labels mechanically. Example structure:

- highlight the user’s more aggressive signals
- identify the constraining dimension
- explain why the final profile settled where it did

## Recommendation Strategy

Recommendations remain primarily profile-driven, but dimension scores refine the presentation.

### Main selection rule

The final profile chooses the primary recommendation pool:

- `conservative`: defensive and stable names
- `stable`: dividend, utility, and large-cap defensive names
- `balanced`: quality blue chips with moderate growth
- `growth`: stronger sector growth names
- `aggressive`: higher-beta innovation or tech-oriented names

### Dimension-based refinement

Dimension scores do not replace the main profile. They refine:

- card ordering
- emphasis in rationale text
- tone of the recommendation explanation

#### `capitalStability`

- lower values should reduce emphasis on high-volatility exposure
- explanation should stress allocation discipline and drawdown control

#### `investmentHorizon`

- lower values should favor shorter-cycle, higher-clarity names
- higher values can justify long-term growth framing

#### `investmentExperience`

- lower values should favor simpler, more recognizable names and clearer rationale
- higher values can tolerate more nuanced growth cases

#### `returnObjective`

- higher values should surface more aggressive upside-oriented names earlier within a pool
- lower values should surface steadier names first

### Recommendation explanation format

Recommendation cards should continue showing stock code, name, and localized rationale. The rationale generator may remain template-based, but it should read as profile-plus-dimension aware rather than profile-only.

## Data Model Changes

### Questionnaire data

Replace the current flat 6-question dataset with a 20-question structured dataset.

Each question entry should include:

- `id`
- `dimension`
- `promptZh`
- `promptEn`
- `answers`

Each answer should include:

- `labelZh`
- `labelEn`
- `score`

### Derived result model

Introduce a structured derived result in the questionnaire flow:

- `totalScore`
- `baseProfile`
- `finalProfile`
- `dimensionScores`
- `dimensionLevels`
- `summary`
- `narrative`

This can stay page-local or feature-local for now, but the shared app state should at least retain the final profile and the dimension-level data needed by the recommendation page.

## State Changes

The current shared state stores only `riskProfile`.

Upgrade it to store a richer object, for example:

- `riskAssessmentResult: null | { finalProfile, baseProfile, totalScore, dimensionScores, dimensionLevels }`

To minimize breakage:

- existing consumers can continue reading `finalProfile`
- recommendation pages should switch to the richer result object when available

## Localization

All new content must support:

- `zh-CN` as default
- `en-US` as alternate locale

Localization covers:

- 20 question prompts
- 100 answer labels
- dimension names
- level labels
- profile summaries
- personalized narratives
- refined recommendation rationales where needed

## Testing Strategy

### Scoring tests

Add unit coverage for:

- all-low answer sheet -> `conservative`
- all middle-leaning answer sheet -> `stable` or `balanced` depending on exact scores
- all medium answer sheet -> `balanced`
- all high-but-not-max answer sheet -> `growth`
- all-high answer sheet -> `aggressive`

### Adjustment rule tests

Add focused cases for:

- high total score but low `capitalStability` -> capped result
- medium-high total score plus strong horizon, experience, and return objective -> upward adjustment allowed
- conflicting aggressive and conservative signals -> conservative correction wins

### Flow tests

Update page tests to:

- complete 20 questions instead of 6
- verify the result page shows final profile plus dimension diagnostics plus narrative
- verify the recommendation page changes explanation or ordering based on dimension-aware result state

### Locale tests

Verify:

- progress label updates from `Question 1 of 20`
- English result labels and recommendation copy render correctly
- locale switching still leaves shell navigation usable

## Risks

The main implementation risks are:

- overfitting thresholds so the model feels erratic
- making the recommendation logic too opaque
- bloating the questionnaire UI with too much text

Mitigations:

- keep rules explicit and testable
- prefer deterministic thresholds over fuzzy scoring
- keep card copy concise
- use profile-driven recommendations with dimension refinement instead of fully dynamic generation

## Success Criteria

This upgrade is successful when:

- the questionnaire contains 20 localized questions across 5 dimensions
- users receive a final risk profile and dimension-level explanation
- the result page reads like a concise assessment report instead of a raw score dump
- recommendations still feel stable, but their rationale and ordering better reflect the user’s actual profile
- all targeted tests and build verification pass
