import { AppShell } from "../../app/layout/AppShell";
import { useAppState } from "../../app/state/app-state";
import { InsightCard } from "../../components/InsightCard";
import { getMessages } from "../../i18n/messages";
import { RecommendationDeck } from "./RecommendationDeck";

function getGuidanceCopy(locale: "zh-CN" | "en-US") {
  if (locale === "en-US") {
    return {
      body: "Finish the questionnaire first and this page will then build a first-pass allocation and product recommendation plan.",
      title: "Complete the risk assessment first",
    };
  }

  return {
    body: "完成问卷后，这里会先给出资产配置结论，再展示基金、银行理财和股票的推荐建议。",
    title: "先完成风险评估",
  };
}

export function RecommendationsPage() {
  const { locale, riskAssessmentResult } = useAppState();
  const routeCopy = getMessages(locale).nav.recommendations;
  const guidanceCopy = getGuidanceCopy(locale);

  return (
    <AppShell pageSubtitle={routeCopy.subtitle} pageTitle={routeCopy.title}>
      {riskAssessmentResult ? (
        <RecommendationDeck locale={locale} riskAssessmentResult={riskAssessmentResult} />
      ) : (
        <InsightCard title={guidanceCopy.title}>
          <p>{guidanceCopy.body}</p>
        </InsightCard>
      )}
    </AppShell>
  );
}
