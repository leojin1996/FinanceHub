import { AppShell } from "../../app/layout/AppShell";
import { type Locale, type RiskProfile, useAppState } from "../../app/state/app-state";
import { InsightCard } from "../../components/InsightCard";
import { TagBadge } from "../../components/TagBadge";
import { getMessages } from "../../i18n/messages";
import { RiskQuestionnaireWizard } from "./RiskQuestionnaireWizard";
import type { DimensionLevel, RiskAssessmentResult, RiskDimension } from "./risk-scoring";

function getProfileLabel(locale: Locale, riskProfile: RiskProfile) {
  if (locale === "en-US") {
    return {
      aggressive: "Aggressive",
      balanced: "Balanced",
      conservative: "Conservative",
      growth: "Growth",
      stable: "Stable",
    }[riskProfile];
  }

  return {
    aggressive: "进取型",
    balanced: "平衡型",
    conservative: "保守型",
    growth: "成长型",
    stable: "稳健型",
  }[riskProfile];
}

function getResultCopy(locale: Locale) {
  if (locale === "en-US") {
    return {
      diagnosticsTitle: "Dimension Snapshot",
      dimensionDescriptions: {
        capitalStability:
          "Your capital stability determines how much volatility the portfolio can realistically absorb.",
        investmentExperience:
          "Your investment experience affects how much complexity and drawdown you can manage calmly.",
        investmentHorizon:
          "Your investment horizon tells us whether time can help absorb short-term volatility.",
        returnObjective:
          "Your return objective shows how much upside you want to pursue versus preserving stability.",
        riskTolerance:
          "Your risk tolerance reflects how you react when prices move sharply against you.",
      },
      dimensionLabels: {
        capitalStability: "Capital Stability",
        investmentExperience: "Investment Experience",
        investmentHorizon: "Investment Horizon",
        returnObjective: "Return Objective",
        riskTolerance: "Risk Tolerance",
      },
      levelLabels: {
        high: "High",
        low: "Low",
        medium: "Medium",
        mediumHigh: "Medium-High",
        mediumLow: "Medium-Low",
      },
      narrativeTemplates: {
        aggressive:
          "Your risk tolerance and return objective are strong, and your profile supports a more assertive allocation posture.",
        balanced:
          "Your risk tolerance and return objective are active, but the profile still favors a balanced mix over a fully aggressive stance.",
        conservative:
          "Your current answers point to capital preservation and stability as the clear priority over upside.",
        growth:
          "Your longer horizon and stronger upside preference support a growth-oriented allocation with controlled volatility.",
        stable:
          "Your answers support steady growth, but the portfolio should still keep a meaningful stability anchor.",
      },
      resultBody:
        "This profile will be used to tailor the recommendation deck so the stock ideas match your risk tolerance.",
      resultTitle: "Your Risk Profile",
    };
  }

  return {
    diagnosticsTitle: "维度画像",
    dimensionDescriptions: {
      capitalStability: "资金稳定性决定了组合能承受多大波动，不宜脱离现实现金流条件单独看收益。",
      investmentExperience: "投资经验反映你对回撤、波动和持仓节奏的理解与应对能力。",
      investmentHorizon: "投资期限决定你能否用时间来换取波动承受空间。",
      returnObjective: "收益目标体现你更偏向保值、稳健增值，还是更积极地争取更高回报。",
      riskTolerance: "风险承受度反映你面对亏损与波动时的真实心理承受能力。",
    },
    dimensionLabels: {
      capitalStability: "资金稳定性",
      investmentExperience: "投资经验",
      investmentHorizon: "投资期限",
      returnObjective: "收益目标",
      riskTolerance: "风险承受度",
    },
    levelLabels: {
      high: "高",
      low: "低",
      medium: "中",
      mediumHigh: "中高",
      mediumLow: "中低",
    },
    narrativeTemplates: {
      aggressive:
        "你的风险承受能力与收益目标都偏高，同时其他维度没有形成明显约束，因此结果更偏进取。",
      balanced:
        "你的风险承受能力与收益目标整体偏积极，但仍存在需要平衡的约束，因此更适合均衡配置。",
      conservative:
        "你的多个核心维度都更强调安全性和资金可用性，因此结果更偏保守。",
      growth:
        "你的投资期限、经验与收益目标支持更偏成长的组合表达，但仍需要关注波动管理。",
      stable:
        "你的回答支持稳健增值，但仍需保留较强的稳定性底仓与节奏控制。",
    },
    resultBody: "该结果会同步到个性化推荐页，用于展示更贴合你风险承受能力的候选股票。",
    resultTitle: "你的风险类型",
  };
}

function findExtremeDimensions(result: RiskAssessmentResult) {
  let strongestDimension: RiskDimension = "riskTolerance";
  let weakestDimension: RiskDimension = "riskTolerance";

  for (const dimension of Object.keys(result.dimensionScores) as RiskDimension[]) {
    if (result.dimensionScores[dimension] > result.dimensionScores[strongestDimension]) {
      strongestDimension = dimension;
    }

    if (result.dimensionScores[dimension] < result.dimensionScores[weakestDimension]) {
      weakestDimension = dimension;
    }
  }

  return { strongestDimension, weakestDimension };
}

function buildNarrative(
  locale: Locale,
  result: RiskAssessmentResult,
  resultCopy: ReturnType<typeof getResultCopy>,
) {
  const { strongestDimension, weakestDimension } = findExtremeDimensions(result);
  const profileSentence = resultCopy.narrativeTemplates[result.finalProfile];
  const strongestLabel = resultCopy.dimensionLabels[strongestDimension];
  const weakestLabel = resultCopy.dimensionLabels[weakestDimension];

  if (locale === "en-US") {
    return `${profileSentence} Your strongest dimension is ${strongestLabel}, while ${weakestLabel} remains the main constraint on how aggressive the portfolio should be.`;
  }

  return `${profileSentence} 其中，${strongestLabel}是你的相对优势维度，而${weakestLabel}仍是限制整体风险档位的关键因素。`;
}

export function RiskAssessmentPage() {
  const { locale, riskAssessmentResult, setRiskAssessmentResult } = useAppState();
  const routeCopy = getMessages(locale).nav.riskAssessment;
  const resultCopy = getResultCopy(locale);

  return (
    <AppShell pageSubtitle={routeCopy.subtitle} pageTitle={routeCopy.title}>
      <RiskQuestionnaireWizard onComplete={setRiskAssessmentResult} />
      {riskAssessmentResult ? (
        <InsightCard title={resultCopy.resultTitle}>
          <div className="risk-assessment__result">
            <TagBadge label={getProfileLabel(locale, riskAssessmentResult.finalProfile)} />
            <p>{resultCopy.resultBody}</p>
          </div>
        </InsightCard>
      ) : null}
      {riskAssessmentResult ? (
        <InsightCard title={resultCopy.diagnosticsTitle}>
          <div className="risk-diagnostics">
            {(Object.keys(riskAssessmentResult.dimensionLevels) as RiskDimension[]).map((dimension) => (
              <article className="risk-diagnostics__card" key={dimension}>
                <h3>{resultCopy.dimensionLabels[dimension]}</h3>
                <TagBadge
                  label={
                    resultCopy.levelLabels[
                      riskAssessmentResult.dimensionLevels[dimension] as DimensionLevel
                    ]
                  }
                />
                <p>{resultCopy.dimensionDescriptions[dimension]}</p>
              </article>
            ))}
          </div>
        </InsightCard>
      ) : null}
      {riskAssessmentResult ? (
        <InsightCard title={locale === "en-US" ? "Assessment Narrative" : "评估解读"}>
          <p className="risk-report__narrative">
            {buildNarrative(locale, riskAssessmentResult, resultCopy)}
          </p>
        </InsightCard>
      ) : null}
    </AppShell>
  );
}
