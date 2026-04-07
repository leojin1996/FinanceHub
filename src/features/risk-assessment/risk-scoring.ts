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

function lowerProfile(profile: RiskProfile): RiskProfile {
  if (profile === "aggressive") {
    return "growth";
  }

  if (profile === "growth") {
    return "balanced";
  }

  if (profile === "balanced") {
    return "stable";
  }

  if (profile === "stable") {
    return "conservative";
  }

  return "conservative";
}

function higherProfile(profile: RiskProfile): RiskProfile {
  if (profile === "conservative") {
    return "stable";
  }

  if (profile === "stable") {
    return "balanced";
  }

  if (profile === "balanced") {
    return "growth";
  }

  if (profile === "growth") {
    return "aggressive";
  }

  return "aggressive";
}

export function dimensionLevelFromScore(score: number): DimensionLevel {
  if (score <= 7) {
    return "low";
  }

  if (score <= 10) {
    return "mediumLow";
  }

  if (score <= 13) {
    return "medium";
  }

  if (score <= 16) {
    return "mediumHigh";
  }

  return "high";
}

function baseProfileFromScore(totalScore: number): RiskProfile {
  if (totalScore <= 35) {
    return "conservative";
  }

  if (totalScore <= 50) {
    return "stable";
  }

  if (totalScore <= 65) {
    return "balanced";
  }

  if (totalScore <= 80) {
    return "growth";
  }

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

  if (
    cappedByStability &&
    (baseProfile === "growth" || baseProfile === "aggressive")
  ) {
    return "balanced";
  }

  if (
    ["low", "mediumLow"].includes(dimensionLevels.riskTolerance) &&
    ["low", "mediumLow"].includes(dimensionLevels.capitalStability) &&
    (baseProfile === "growth" || baseProfile === "aggressive")
  ) {
    return lowerProfile(baseProfile);
  }

  const nearTopOfBand =
    (baseProfile === "stable" && totalScore >= 48) ||
    (baseProfile === "balanced" && totalScore >= 63) ||
    (baseProfile === "growth" && totalScore >= 78);

  const growthSignals = [
    dimensionLevels.investmentHorizon,
    dimensionLevels.investmentExperience,
    dimensionLevels.returnObjective,
  ].filter((level) => level === "mediumHigh" || level === "high").length;

  if (
    nearTopOfBand &&
    growthSignals >= 2 &&
    !cappedByStability &&
    !["low", "mediumLow"].includes(dimensionLevels.capitalStability)
  ) {
    return higherProfile(baseProfile);
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
