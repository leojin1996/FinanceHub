# Risk Assessment 20-Question Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the current 6-question risk flow into a 20-question, 5-dimension assessment that produces a final profile, dimension diagnostics, a personalized narrative, and dimension-aware recommendations.

**Architecture:** Replace the flat questionnaire dataset with a structured 20-question model, add a dedicated scoring helper that computes base profile, final profile, and dimension levels, then update the risk assessment and recommendation pages to consume a richer shared result object instead of only a single `riskProfile`. Keep routing and shell behavior unchanged, and preserve existing locale patterns by localizing question copy, result copy, and recommendation reasoning in feature-local helpers backed by typed mock data.

**Tech Stack:** React, TypeScript, React Router, Vitest, Testing Library, plain CSS, existing FinanceHub app-state and mock data modules

---

## File Structure

- Modify: `src/app/state/app-state.ts` - replace single-profile-only shared result with a richer risk assessment result type
- Modify: `src/app/state/AppStateProvider.tsx` - store and expose the richer assessment result while keeping a convenient final profile accessor if needed
- Modify: `src/mock/questionnaire.ts` - replace the 6-question flat list with a 20-question, 5-dimension structured questionnaire
- Create: `src/features/risk-assessment/risk-scoring.ts` - pure helper for dimension scores, level mapping, base profile, final profile adjustment, and personalized narrative inputs
- Create: `src/features/risk-assessment/risk-scoring.test.ts` - focused scoring and adjustment rule tests
- Modify: `src/features/risk-assessment/RiskQuestionnaireWizard.tsx` - support 20 questions, 5-option answers, and submit a rich result object
- Modify: `src/features/risk-assessment/RiskAssessmentPage.tsx` - render final profile, 5 dimension cards, and narrative
- Modify: `src/mock/recommendations.ts` - keep base pools but add enough metadata/templates for dimension-aware explanation and ordering
- Modify: `src/features/recommendations/RecommendationDeck.tsx` - consume rich result object and adjust order/reasoning by dimensions
- Modify: `src/features/recommendations/RecommendationsPage.tsx` - read richer assessment result while preserving empty state behavior
- Modify: `src/features/risk-assessment/RiskAssessmentPage.test.tsx` - expand the flow test from 6 questions to 20 and assert diagnostics plus narrative
- Modify: `src/features/recommendations/RecommendationsPage.test.tsx` - verify dimension-aware recommendation behavior and English recommendation copy after completion
- Modify: `src/app/locale.test.tsx` - update progress assertions from 6 to 20 and preserve locale-switch stability checks
- Modify: `src/styles/app-shell.css` - add layout styles for 5 dimension cards and longer assessment/report content

## Task 1: Introduce the structured 20-question dataset and scoring helper

**Files:**
- Modify: `src/mock/questionnaire.ts`
- Create: `src/features/risk-assessment/risk-scoring.ts`
- Create: `src/features/risk-assessment/risk-scoring.test.ts`

- [ ] **Step 1: Write the failing scoring tests**

Create `src/features/risk-assessment/risk-scoring.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import {
  buildAssessmentResult,
  dimensionLevelFromScore,
  finalProfileFromAssessment,
} from "./risk-scoring";

describe("risk scoring", () => {
  it("maps dimension scores into five fixed levels", () => {
    expect(dimensionLevelFromScore(4)).toBe("low");
    expect(dimensionLevelFromScore(9)).toBe("mediumLow");
    expect(dimensionLevelFromScore(12)).toBe("medium");
    expect(dimensionLevelFromScore(15)).toBe("mediumHigh");
    expect(dimensionLevelFromScore(19)).toBe("high");
  });

  it("keeps a high total score capped when capital stability is low", () => {
    const result = finalProfileFromAssessment({
      baseProfile: "aggressive",
      dimensionLevels: {
        capitalStability: "low",
        investmentExperience: "high",
        investmentHorizon: "high",
        returnObjective: "high",
        riskTolerance: "high",
      },
      totalScore: 92,
    });

    expect(result).toBe("balanced");
  });

  it("allows a one-level upward adjustment near the top of the score band", () => {
    const result = finalProfileFromAssessment({
      baseProfile: "balanced",
      dimensionLevels: {
        capitalStability: "medium",
        investmentExperience: "high",
        investmentHorizon: "mediumHigh",
        returnObjective: "high",
        riskTolerance: "mediumHigh",
      },
      totalScore: 64,
    });

    expect(result).toBe("growth");
  });

  it("builds a balanced result from 20 medium answers", () => {
    const result = buildAssessmentResult(
      Array.from({ length: 20 }, () => ({ dimension: "riskTolerance", score: 3 })),
    );

    expect(result.totalScore).toBe(60);
    expect(result.baseProfile).toBe("balanced");
  });
});
```

- [ ] **Step 2: Run the scoring test to verify it fails**

Run:

```bash
npx vitest run src/features/risk-assessment/risk-scoring.test.ts
```

Expected: FAIL because `risk-scoring.ts` does not exist yet and the current questionnaire shape cannot support the new assessment flow.

- [ ] **Step 3: Implement the minimal structured questionnaire model and scoring helper**

Create `src/features/risk-assessment/risk-scoring.ts` with:

```ts
import type { RiskProfile } from "../../app/state/app-state";

export type RiskDimension =
  | "riskTolerance"
  | "investmentHorizon"
  | "capitalStability"
  | "investmentExperience"
  | "returnObjective";

export type DimensionLevel = "low" | "mediumLow" | "medium" | "mediumHigh" | "high";

export interface AnswerScore {
  dimension: RiskDimension;
  score: number;
}

export interface RiskAssessmentResult {
  baseProfile: RiskProfile;
  dimensionLevels: Record<RiskDimension, DimensionLevel>;
  dimensionScores: Record<RiskDimension, number>;
  finalProfile: RiskProfile;
  totalScore: number;
}

export function dimensionLevelFromScore(score: number): DimensionLevel {
  if (score <= 7) return "low";
  if (score <= 10) return "mediumLow";
  if (score <= 13) return "medium";
  if (score <= 16) return "mediumHigh";
  return "high";
}

function baseProfileFromScore(totalScore: number): RiskProfile {
  if (totalScore <= 35) return "conservative";
  if (totalScore <= 50) return "stable";
  if (totalScore <= 65) return "balanced";
  if (totalScore <= 80) return "growth";
  return "aggressive";
}

export function finalProfileFromAssessment(input: {
  baseProfile: RiskProfile;
  dimensionLevels: Record<RiskDimension, DimensionLevel>;
  totalScore: number;
}): RiskProfile {
  const { baseProfile, dimensionLevels, totalScore } = input;
  const cappedByStability =
    dimensionLevels.riskTolerance === "low" || dimensionLevels.capitalStability === "low";

  if (cappedByStability && (baseProfile === "growth" || baseProfile === "aggressive")) {
    return "balanced";
  }

  const bothWeak =
    ["low", "mediumLow"].includes(dimensionLevels.riskTolerance) &&
    ["low", "mediumLow"].includes(dimensionLevels.capitalStability);

  if (bothWeak && (baseProfile === "growth" || baseProfile === "aggressive")) {
    return baseProfile === "aggressive" ? "growth" : "balanced";
  }

  const upperEdge =
    (baseProfile === "stable" && totalScore >= 48) ||
    (baseProfile === "balanced" && totalScore >= 63) ||
    (baseProfile === "growth" && totalScore >= 78);

  const growthSignals = [
    dimensionLevels.investmentHorizon,
    dimensionLevels.investmentExperience,
    dimensionLevels.returnObjective,
  ].filter((level) => level === "mediumHigh" || level === "high").length;

  if (upperEdge && growthSignals >= 2 && !["low", "mediumLow"].includes(dimensionLevels.capitalStability)) {
    if (baseProfile === "stable") return "balanced";
    if (baseProfile === "balanced") return "growth";
    if (baseProfile === "growth") return "aggressive";
  }

  return baseProfile;
}

export function buildAssessmentResult(answerScores: AnswerScore[]): RiskAssessmentResult {
  const dimensionScores: Record<RiskDimension, number> = {
    capitalStability: 0,
    investmentExperience: 0,
    investmentHorizon: 0,
    returnObjective: 0,
    riskTolerance: 0,
  };

  for (const answer of answerScores) {
    dimensionScores[answer.dimension] += answer.score;
  }

  const totalScore = answerScores.reduce((sum, answer) => sum + answer.score, 0);
  const dimensionLevels: Record<RiskDimension, DimensionLevel> = {
    capitalStability: dimensionLevelFromScore(dimensionScores.capitalStability),
    investmentExperience: dimensionLevelFromScore(dimensionScores.investmentExperience),
    investmentHorizon: dimensionLevelFromScore(dimensionScores.investmentHorizon),
    returnObjective: dimensionLevelFromScore(dimensionScores.returnObjective),
    riskTolerance: dimensionLevelFromScore(dimensionScores.riskTolerance),
  };
  const baseProfile = baseProfileFromScore(totalScore);

  return {
    baseProfile,
    dimensionLevels,
    dimensionScores,
    finalProfile: finalProfileFromAssessment({ baseProfile, dimensionLevels, totalScore }),
    totalScore,
  };
}
```

Replace `src/mock/questionnaire.ts` with a typed 20-question dataset that includes `dimension`, `promptZh`, `promptEn`, and five scored answers per question across the five dimensions from the spec.

- [ ] **Step 4: Run the scoring tests to verify they pass**

Run:

```bash
npx vitest run src/features/risk-assessment/risk-scoring.test.ts
```

Expected: PASS with the new helper and threshold rules implemented.

- [ ] **Step 5: Commit the dataset and scoring helper**

```bash
git add src/mock/questionnaire.ts src/features/risk-assessment/risk-scoring.ts src/features/risk-assessment/risk-scoring.test.ts
git commit -m "feat: add structured risk scoring model"
```

## Task 2: Upgrade shared state and the questionnaire flow to submit a rich result

**Files:**
- Modify: `src/app/state/app-state.ts`
- Modify: `src/app/state/AppStateProvider.tsx`
- Modify: `src/features/risk-assessment/RiskQuestionnaireWizard.tsx`
- Modify: `src/features/risk-assessment/RiskAssessmentPage.test.tsx`
- Modify: `src/app/locale.test.tsx`

- [ ] **Step 1: Write the failing flow tests for 20 questions and updated progress**

Update `src/features/risk-assessment/RiskAssessmentPage.test.tsx`:

```tsx
it("completes the twenty-question flow and shows profile, diagnostics, and narrative", async () => {
  window.history.pushState({}, "", "/");
  const user = userEvent.setup();

  render(<App />);

  await user.click(screen.getByRole("link", { name: "风险评估" }));

  for (let index = 0; index < 20; index += 1) {
    await user.click(screen.getAllByRole("radio")[2]);
    await user.click(screen.getByRole("button", { name: /下一题|提交/ }));
  }

  expect(screen.getByText("你的风险类型")).toBeInTheDocument();
  expect(screen.getByText("风险承受度")).toBeInTheDocument();
  expect(screen.getByText(/你的投资期限与收益目标/)).toBeInTheDocument();
});
```

Update `src/app/locale.test.tsx`:

```tsx
it("shows the expanded questionnaire progress in English", async () => {
  window.history.pushState({}, "", "/risk-assessment");
  const user = userEvent.setup();

  render(<App />);

  await user.selectOptions(screen.getByRole("combobox"), "en-US");

  expect(screen.getByText("Question 1 of 20")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the flow tests to verify they fail**

Run:

```bash
npx vitest run src/features/risk-assessment/RiskAssessmentPage.test.tsx src/app/locale.test.tsx
```

Expected: FAIL because the current wizard still assumes 6 questions and only returns a final profile without diagnostics or narrative.

- [ ] **Step 3: Implement the richer shared state and the 20-question wizard**

Update `src/app/state/app-state.ts` so shared state includes a `riskAssessmentResult` object typed from `risk-scoring.ts`, plus a setter such as:

```ts
import type { RiskAssessmentResult } from "../../features/risk-assessment/risk-scoring";

export interface AppStateValue {
  locale: Locale;
  riskAssessmentResult: RiskAssessmentResult | null;
  riskProfile: RiskProfile | null;
  setLocale: (locale: Locale) => void;
  setRiskAssessmentResult: (result: RiskAssessmentResult | null) => void;
}
```

Update `src/app/state/AppStateProvider.tsx` to store `riskAssessmentResult` and derive `riskProfile` from `riskAssessmentResult?.finalProfile ?? null`.

Update `src/features/risk-assessment/RiskQuestionnaireWizard.tsx` to:

- iterate through 20 questions
- collect `{ dimension, score }` answers
- use `buildAssessmentResult(...)` on submit
- call `onComplete(result)` with the full result object

Update `src/features/risk-assessment/RiskAssessmentPage.tsx` to:

- pass `setRiskAssessmentResult` into the wizard
- render five diagnostic cards from `riskAssessmentResult.dimensionLevels`
- render a localized narrative paragraph based on strongest and weakest dimensions

- [ ] **Step 4: Run the updated flow tests to verify they pass**

Run:

```bash
npx vitest run src/features/risk-assessment/RiskAssessmentPage.test.tsx src/app/locale.test.tsx
```

Expected: PASS with `Question 1 of 20` in English and a complete 20-question Chinese flow ending in diagnostics plus narrative.

- [ ] **Step 5: Commit the questionnaire flow upgrade**

```bash
git add src/app/state/app-state.ts src/app/state/AppStateProvider.tsx src/features/risk-assessment/RiskQuestionnaireWizard.tsx src/features/risk-assessment/RiskAssessmentPage.tsx src/features/risk-assessment/RiskAssessmentPage.test.tsx src/app/locale.test.tsx
git commit -m "feat: expand risk questionnaire to twenty questions"
```

## Task 3: Make recommendations dimension-aware

**Files:**
- Modify: `src/mock/recommendations.ts`
- Modify: `src/features/recommendations/RecommendationDeck.tsx`
- Modify: `src/features/recommendations/RecommendationsPage.tsx`
- Modify: `src/features/recommendations/RecommendationsPage.test.tsx`

- [ ] **Step 1: Write the failing recommendation refinement tests**

Update `src/features/recommendations/RecommendationsPage.test.tsx`:

```tsx
it("uses the final profile for the base pool and adjusts the rationale by dimensions", async () => {
  window.history.pushState({}, "", "/");
  const user = userEvent.setup();

  render(<App />);

  await user.click(screen.getByRole("link", { name: "风险评估" }));

  for (let index = 0; index < 20; index += 1) {
    const optionIndex = index < 4 ? 1 : 2;
    await user.click(screen.getAllByRole("radio")[optionIndex]);
    await user.click(screen.getByRole("button", { name: /下一题|提交/ }));
  }

  await user.click(screen.getByRole("link", { name: "个性化推荐" }));

  expect(screen.getByText(/控制高波动仓位|强调配置纪律/)).toBeInTheDocument();
});

it("keeps English recommendation copy after completing the twenty-question assessment", async () => {
  window.history.pushState({}, "", "/");
  const user = userEvent.setup();

  render(<App />);

  await user.selectOptions(screen.getByRole("combobox"), "en-US");
  await user.click(screen.getByRole("link", { name: "Risk Assessment" }));

  for (let index = 0; index < 20; index += 1) {
    await user.click(screen.getAllByRole("radio")[4]);
    await user.click(screen.getByRole("button", { name: /Next|Submit/ }));
  }

  await user.click(screen.getByRole("link", { name: "Personalized Recommendations" }));

  expect(screen.getByText(/Higher volatility|long-term growth runway|allocation discipline/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the recommendation tests to verify they fail**

Run:

```bash
npx vitest run src/features/recommendations/RecommendationsPage.test.tsx
```

Expected: FAIL because the current recommendation deck only reads `riskProfile` and does not adjust ordering or rationale by dimension scores.

- [ ] **Step 3: Implement dimension-aware recommendation refinement**

Update `src/mock/recommendations.ts` to add lightweight metadata per stock, for example:

```ts
export const recommendationGroups = {
  balanced: [
    {
      code: "600519",
      experienceBias: "low",
      horizonBias: "high",
      name: "贵州茅台",
      reasonEn: "Category leader with durable fundamentals.",
      reasonZh: "龙头地位稳固，基本面扎实。",
      stabilityBias: "medium",
    },
  ],
} as const;
```

Update `src/features/recommendations/RecommendationDeck.tsx` to:

- read `riskAssessmentResult`
- sort or prioritize items by matching dimension biases
- append localized explanation snippets based on weak or strong dimensions

Update `src/features/recommendations/RecommendationsPage.tsx` to consume `riskAssessmentResult` instead of only `riskProfile`.

- [ ] **Step 4: Run the recommendation tests to verify they pass**

Run:

```bash
npx vitest run src/features/recommendations/RecommendationsPage.test.tsx
```

Expected: PASS with dimension-aware Chinese rationale and English recommendation copy still working after the full 20-question flow.

- [ ] **Step 5: Commit the recommendation refinement**

```bash
git add src/mock/recommendations.ts src/features/recommendations/RecommendationDeck.tsx src/features/recommendations/RecommendationsPage.tsx src/features/recommendations/RecommendationsPage.test.tsx
git commit -m "feat: refine recommendations with risk dimensions"
```

## Task 4: Polish the assessment report layout and run the final verification suite

**Files:**
- Modify: `src/styles/app-shell.css`
- Modify: `src/features/risk-assessment/RiskAssessmentPage.tsx` if layout hooks are still needed
- Modify: `src/features/recommendations/RecommendationDeck.tsx` if responsive hooks are still needed

- [ ] **Step 1: Write the failing integration expectation by locking the final suite**

Run:

```bash
npx vitest run src/app/App.test.tsx src/app/locale.test.tsx src/components/MetricCard.test.tsx src/features/market-overview/MarketOverviewPage.test.tsx src/features/chinese-stocks/ChineseStocksPage.test.tsx src/features/chinese-indices/ChineseIndicesPage.test.tsx src/features/risk-assessment/RiskAssessmentPage.test.tsx src/features/recommendations/RecommendationsPage.test.tsx
```

Expected: If any layout or text contract is still broken after Tasks 1-3, this suite will fail and identify the remaining integration gap.

- [ ] **Step 2: Apply minimal layout polish for longer assessment content**

Update `src/styles/app-shell.css` to add:

```css
.risk-diagnostics {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.risk-diagnostics__card {
  min-width: 0;
}

.risk-report__narrative {
  margin: 0;
}

@media (max-width: 1280px) {
  .risk-diagnostics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .risk-diagnostics {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 3: Run the full targeted suite and production build**

Run:

```bash
npx vitest run src/app/App.test.tsx src/app/locale.test.tsx src/components/MetricCard.test.tsx src/features/market-overview/MarketOverviewPage.test.tsx src/features/chinese-stocks/ChineseStocksPage.test.tsx src/features/chinese-indices/ChineseIndicesPage.test.tsx src/features/risk-assessment/RiskAssessmentPage.test.tsx src/features/recommendations/RecommendationsPage.test.tsx
npm run build
```

Expected:

- all targeted tests PASS
- Vite build PASS
- chunk-size warning may remain, but no build failure

- [ ] **Step 4: Commit the final integration pass**

```bash
git add src/styles/app-shell.css src/features/risk-assessment/RiskAssessmentPage.tsx src/features/recommendations/RecommendationDeck.tsx
git commit -m "test: finalize twenty-question risk assessment flow"
```
