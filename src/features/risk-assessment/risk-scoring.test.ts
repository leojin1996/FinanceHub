import { describe, expect, it } from "vitest";

import { questionnaire } from "../../mock/questionnaire";
import {
  buildAssessmentResult,
  dimensionLevelFromScore,
  finalProfileFromAssessment,
  type AnswerScore,
} from "./risk-scoring";

describe("risk scoring", () => {
  it("defines a 20-question questionnaire with 5 dimensions and 4 questions each", () => {
    expect(questionnaire).toHaveLength(20);

    const expectedDimensions: AnswerScore["dimension"][] = [
      "riskTolerance",
      "investmentHorizon",
      "capitalStability",
      "investmentExperience",
      "returnObjective",
    ];

    const counts = questionnaire.reduce<Record<AnswerScore["dimension"], number>>(
      (accumulator, question) => {
        accumulator[question.dimension] += 1;
        expect(question.answers).toHaveLength(5);
        expect(question.answers.map((answer) => answer.score)).toEqual([1, 2, 3, 4, 5]);
        return accumulator;
      },
      {
        riskTolerance: 0,
        investmentHorizon: 0,
        capitalStability: 0,
        investmentExperience: 0,
        returnObjective: 0,
      },
    );

    expect(Object.keys(counts).sort()).toEqual(expectedDimensions.sort());
    for (const dimension of expectedDimensions) {
      expect(counts[dimension]).toBe(4);
    }
  });

  it("maps dimension scores into fixed levels", () => {
    expect(dimensionLevelFromScore(4)).toBe("low");
    expect(dimensionLevelFromScore(7)).toBe("low");
    expect(dimensionLevelFromScore(8)).toBe("mediumLow");
    expect(dimensionLevelFromScore(9)).toBe("mediumLow");
    expect(dimensionLevelFromScore(10)).toBe("mediumLow");
    expect(dimensionLevelFromScore(11)).toBe("medium");
    expect(dimensionLevelFromScore(12)).toBe("medium");
    expect(dimensionLevelFromScore(13)).toBe("medium");
    expect(dimensionLevelFromScore(14)).toBe("mediumHigh");
    expect(dimensionLevelFromScore(15)).toBe("mediumHigh");
    expect(dimensionLevelFromScore(16)).toBe("mediumHigh");
    expect(dimensionLevelFromScore(17)).toBe("high");
    expect(dimensionLevelFromScore(19)).toBe("high");
    expect(dimensionLevelFromScore(20)).toBe("high");
  });

  it("caps high totals when risk tolerance or capital stability is low", () => {
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

  it("allows a one-level upward adjustment near the top of a score band", () => {
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

  it("keeps downward correction ahead of upward correction", () => {
    const result = finalProfileFromAssessment({
      baseProfile: "growth",
      dimensionLevels: {
        capitalStability: "low",
        investmentExperience: "high",
        investmentHorizon: "high",
        returnObjective: "high",
        riskTolerance: "mediumHigh",
      },
      totalScore: 79,
    });

    expect(result).toBe("balanced");
  });

  it("never upgrades above balanced when risk tolerance is low", () => {
    const result = finalProfileFromAssessment({
      baseProfile: "balanced",
      dimensionLevels: {
        capitalStability: "mediumHigh",
        investmentExperience: "high",
        investmentHorizon: "high",
        returnObjective: "high",
        riskTolerance: "low",
      },
      totalScore: 65,
    });

    expect(result).toBe("balanced");
  });

  it("applies a one-level downward adjustment when both risk tolerance and capital stability are mediumLow or below", () => {
    const result = finalProfileFromAssessment({
      baseProfile: "aggressive",
      dimensionLevels: {
        capitalStability: "mediumLow",
        investmentExperience: "high",
        investmentHorizon: "high",
        returnObjective: "high",
        riskTolerance: "mediumLow",
      },
      totalScore: 90,
    });

    expect(result).toBe("growth");
  });

  it("only considers upper-edge upward adjustment on the top 20% of each band", () => {
    const nearEdge = finalProfileFromAssessment({
      baseProfile: "balanced",
      dimensionLevels: {
        capitalStability: "medium",
        investmentExperience: "high",
        investmentHorizon: "high",
        returnObjective: "mediumHigh",
        riskTolerance: "medium",
      },
      totalScore: 62,
    });

    expect(nearEdge).toBe("balanced");
  });

  it("builds a balanced result from medium answers across all dimensions", () => {
    const dimensions: AnswerScore["dimension"][] = [
      "riskTolerance",
      "riskTolerance",
      "riskTolerance",
      "riskTolerance",
      "investmentHorizon",
      "investmentHorizon",
      "investmentHorizon",
      "investmentHorizon",
      "capitalStability",
      "capitalStability",
      "capitalStability",
      "capitalStability",
      "investmentExperience",
      "investmentExperience",
      "investmentExperience",
      "investmentExperience",
      "returnObjective",
      "returnObjective",
      "returnObjective",
      "returnObjective",
    ];

    const result = buildAssessmentResult(
      dimensions.map((dimension) => ({ dimension, score: 3 })),
    );

    expect(result.totalScore).toBe(60);
    expect(result.baseProfile).toBe("balanced");
    expect(result.finalProfile).toBe("balanced");
    expect(result.dimensionLevels.riskTolerance).toBe("medium");
    expect(result.dimensionLevels.returnObjective).toBe("medium");
  });

  it("preserves raw questionnaire answers in the assessment result", () => {
    const answerScores: AnswerScore[] = [
      {
        answerId: "3",
        dimension: "riskTolerance",
        questionId: "1",
        score: 3,
      },
      {
        answerId: "4",
        dimension: "investmentHorizon",
        questionId: "5",
        score: 4,
      },
    ];

    const result = buildAssessmentResult(answerScores);

    expect(result.questionnaireAnswers).toEqual(answerScores);
  });
});
