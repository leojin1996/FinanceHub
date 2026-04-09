import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { type Locale } from "../../app/state/app-state";
import { InsightCard } from "../../components/InsightCard";
import {
  buildRecommendationGenerationPayload,
  fetchRecommendations,
  type RecommendationAgentTraceEvent,
  type RecommendationAgentTraceToolCall,
  type RecommendationProduct,
  type RecommendationResponse,
} from "../../services/chinaMarketApi";
import type { RiskAssessmentResult } from "../risk-assessment/risk-scoring";

interface RecommendationDeckProps {
  locale: Locale;
  riskAssessmentResult: RiskAssessmentResult;
}

function getCopy(locale: Locale) {
  if (locale === "en-US") {
    return {
      allocation: "Allocation",
      aggressive: "More aggressive option",
      degradedBody:
        "The enhanced recommendation runtime is unavailable right now, so this plan is based on the fallback rules engine.",
      degradedTitle: "Recommendation currently uses the rules fallback path",
      partialDegradedBody:
        "Part of the AI analysis was unavailable, so the system automatically fell back to default ranking or summary logic for the affected steps.",
      partialDegradedTitle: "Part of the AI analysis used fallback handling",
      traceSummary: (stageCount: number, toolCount: number) =>
        `${stageCount} stages logged, ${toolCount} tool calls recorded.`,
      traceTitle: "AI analysis trace",
      loading: "Building your recommendation plan...",
      loadingBody:
        "We are combining your assessment profile with the current market stance to assemble a first-pass recommendation set.",
      riskNotices: "Risk notices",
      source: "Built from your questionnaire result",
      viewDetails: "View details",
      whyThisPlan: "Why this plan fits",
    };
  }

  return {
    allocation: "配置比例",
    aggressive: "进取型备选",
    degradedBody: "由于智能增强暂不可用，当前结果基于规则引擎生成，建议结合自身情况谨慎参考。",
    degradedTitle: "当前推荐已回退到规则引擎结果",
    partialDegradedBody: "部分 AI 分析阶段暂时不可用，系统已对受影响步骤自动回退到默认逻辑，当前推荐仍可正常参考。",
    partialDegradedTitle: "部分 AI 分析已自动降级处理",
    traceSummary: (stageCount: number, toolCount: number) =>
      `已记录 ${stageCount} 个阶段，${toolCount} 次工具调用。`,
    traceTitle: "AI 分析足迹",
    loading: "正在生成你的推荐方案...",
    loadingBody: "系统正在结合你的风险测评结果与当前市场判断，生成第一版资产配置与选品建议。",
    riskNotices: "风险提示",
    source: "基于你的风险测评结果生成",
    viewDetails: "查看详情",
    whyThisPlan: "为什么这样配",
  };
}

function getLocalizedText(locale: Locale, zh: string, en: string) {
  return locale === "en-US" ? en : zh;
}

function getToolCalls(event: RecommendationAgentTraceEvent) {
  return Array.isArray(event.toolCalls) ? event.toolCalls : [];
}

function getTraceStageLabel(
  locale: Locale,
  requestName: string | undefined,
  nodeName: string,
) {
  const zhLabels: Record<string, string> = {
    manager_coordinator: "方案统筹",
    market_intelligence: "市场研判",
    product_match_expert: "产品匹配",
    user_profile_analyst: "画像分析",
  };
  const enLabels: Record<string, string> = {
    manager_coordinator: "Plan coordination",
    market_intelligence: "Market intelligence",
    product_match_expert: "Product matching",
    user_profile_analyst: "Profile analysis",
  };
  const stageName = requestName ?? nodeName;

  if (locale === "en-US") {
    return enLabels[stageName] ?? stageName;
  }

  return zhLabels[stageName] ?? stageName;
}

function getTraceData(agentTrace: RecommendationResponse["agentTrace"]) {
  const traceEvents =
    agentTrace?.filter((event) => event.status === "finish" && getToolCalls(event).length > 0) ?? [];
  const toolCount = traceEvents.reduce((total, event) => total + getToolCalls(event).length, 0);

  return {
    toolCount,
    traceEvents,
  };
}

function AllocationBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="recommendation-allocation__row">
      <div className="recommendation-allocation__meta">
        <strong>{label}</strong>
        <span>{value}%</span>
      </div>
      <div aria-hidden="true" className="recommendation-allocation__track">
        <div className="recommendation-allocation__fill" style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function ProductCard({ locale, product }: { locale: Locale; product: RecommendationProduct }) {
  const detailRoute = product.detailRoute ?? `/recommendations/products/${product.id}`;

  return (
    <article className="panel recommendation-product-card">
      <header className="recommendation-product-card__header">
        <div>
          <h3>{getLocalizedText(locale, product.nameZh, product.nameEn)}</h3>
          <p>
            {product.code ? `${product.code} · ` : ""}
            {product.riskLevel}
            {product.liquidity ? ` · ${product.liquidity}` : ""}
            {product.asOfDate ? ` · ${product.asOfDate}` : ""}
          </p>
        </div>
      </header>
      <div className="recommendation-product-card__tags">
        {(locale === "en-US" ? product.tagsEn : product.tagsZh).map((tag, index) => (
          <span className="tag-badge" key={`${product.id}-${tag}-${index}`}>
            {tag}
          </span>
        ))}
      </div>
      <p className="recommendation-product-card__body">
        {getLocalizedText(locale, product.rationaleZh, product.rationaleEn)}
      </p>
      <div className="recommendation-product-card__actions">
        <Link className="recommendation-product-card__link" to={detailRoute}>
          {locale === "en-US" ? "View details" : "查看详情"}
        </Link>
      </div>
    </article>
  );
}

export function RecommendationDeck({
  locale,
  riskAssessmentResult,
}: RecommendationDeckProps) {
  const copy = getCopy(locale);
  const recommendationRequestKey = JSON.stringify(
    buildRecommendationGenerationPayload(locale, riskAssessmentResult),
  );
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    fetchRecommendations(locale, riskAssessmentResult)
      .then((response) => {
        if (cancelled) {
          return;
        }
        setData(response);
      })
      .catch((requestError: unknown) => {
        if (cancelled) {
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "request failed");
      })
      .finally(() => {
        if (cancelled) {
          return;
        }
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [recommendationRequestKey]);

  const sectionList = useMemo(() => {
    if (!data) {
      return [];
    }

    return [data.sections.funds, data.sections.wealthManagement, data.sections.stocks];
  }, [data]);
  const traceData = useMemo(() => getTraceData(data?.agentTrace), [data?.agentTrace]);

  if (loading) {
    return (
      <InsightCard title={copy.loading}>
        <p>{copy.loadingBody}</p>
      </InsightCard>
    );
  }

  if (error || !data) {
    return (
      <InsightCard title={locale === "en-US" ? "Unable to load recommendations" : "暂时无法生成推荐"}>
        <p>{error ?? (locale === "en-US" ? "Request failed." : "请求失败。")}</p>
      </InsightCard>
    );
  }

  const showDegradedBanner =
    data.executionMode === "rules_fallback" || data.warnings.length > 0;
  const degradedTitle =
    data.executionMode === "rules_fallback"
      ? copy.degradedTitle
      : copy.partialDegradedTitle;
  const degradedBody =
    data.executionMode === "rules_fallback"
      ? copy.degradedBody
      : copy.partialDegradedBody;

  return (
    <section className="recommendation-page-layout">
      <article className="panel recommendation-hero">
        <p className="recommendation-hero__eyebrow">{copy.source}</p>
        <h2>{getLocalizedText(locale, data.summary.titleZh, data.summary.titleEn)}</h2>
        <p>{getLocalizedText(locale, data.summary.subtitleZh, data.summary.subtitleEn)}</p>
        <div className="recommendation-hero__summary-grid">
          <div>
            <strong>{getLocalizedText(locale, "用户画像", "Profile summary")}</strong>
            <p>{getLocalizedText(locale, data.profileSummary.zh, data.profileSummary.en)}</p>
          </div>
          <div>
            <strong>{getLocalizedText(locale, "市场判断", "Market stance")}</strong>
            <p>{getLocalizedText(locale, data.marketSummary.zh, data.marketSummary.en)}</p>
          </div>
        </div>
      </article>

      {showDegradedBanner ? (
        <article className="panel recommendation-degraded">
          <header className="panel__header">
            <h2>{degradedTitle}</h2>
          </header>
          <p>{degradedBody}</p>
          {data.warnings.length > 0 ? (
            <ul>
              {data.warnings.map((warning) => (
                <li key={`${warning.stage}-${warning.code}`}>{warning.message}</li>
              ))}
            </ul>
          ) : null}
        </article>
      ) : null}

      {traceData.toolCount > 0 ? (
        <article className="panel recommendation-trace">
          <header className="panel__header">
            <h2>{copy.traceTitle}</h2>
          </header>
          <p>{copy.traceSummary(traceData.traceEvents.length, traceData.toolCount)}</p>
          <div className="recommendation-grid recommendation-grid--stacked">
            {traceData.traceEvents.map((event, eventIndex) => (
              <article
                className="recommendation-product-card"
                key={`${event.requestName}-${event.nodeName}-${eventIndex}`}
              >
                <strong>{getTraceStageLabel(locale, event.requestName, event.nodeName)}</strong>
                <div className="recommendation-product-card__tags">
                  {getToolCalls(event).map((toolCall: RecommendationAgentTraceToolCall, toolIndex: number) => (
                    <span
                      className="tag-badge"
                      key={`${event.nodeName}-${toolCall.toolName}-${toolIndex}`}
                    >
                      {toolCall.toolName}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </article>
      ) : null}

      <section className="recommendation-two-column">
        <article className="panel recommendation-allocation">
          <header className="panel__header">
            <h2>{copy.allocation}</h2>
          </header>
          <div className="recommendation-allocation__list">
            <AllocationBar
              label={getLocalizedText(locale, "基金", "Funds")}
              value={data.allocationDisplay.fund}
            />
            <AllocationBar
              label={getLocalizedText(locale, "银行理财", "Wealth management")}
              value={data.allocationDisplay.wealthManagement}
            />
            <AllocationBar
              label={getLocalizedText(locale, "股票", "Stocks")}
              value={data.allocationDisplay.stock}
            />
          </div>
        </article>

        <article className="panel recommendation-why">
          <header className="panel__header">
            <h2>{copy.whyThisPlan}</h2>
          </header>
          <ul>
            {(locale === "en-US" ? data.whyThisPlan.en : data.whyThisPlan.zh).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </section>

      <section className="recommendation-sections">
        {sectionList.map((section, index) => (
          <article
            className="recommendation-section"
            key={`${section.titleZh}-${section.titleEn}-${index}`}
          >
            <header className="panel__header recommendation-section__header">
              <h2>{getLocalizedText(locale, section.titleZh, section.titleEn)}</h2>
            </header>
            <div className="recommendation-grid recommendation-grid--stacked">
              {section.items.map((product) => (
                <ProductCard key={product.id} locale={locale} product={product} />
              ))}
            </div>
          </article>
        ))}
      </section>

      <section className="recommendation-two-column">
        {data.aggressiveOption ? (
          <article className="panel recommendation-aggressive">
            <header className="panel__header">
              <h2>{getLocalizedText(locale, data.aggressiveOption.titleZh, data.aggressiveOption.titleEn)}</h2>
            </header>
            <p>{getLocalizedText(locale, data.aggressiveOption.subtitleZh, data.aggressiveOption.subtitleEn)}</p>
            <div className="recommendation-allocation__list">
              <AllocationBar
                label={getLocalizedText(locale, "基金", "Funds")}
                value={data.aggressiveOption.allocation.fund}
              />
              <AllocationBar
                label={getLocalizedText(locale, "银行理财", "Wealth management")}
                value={data.aggressiveOption.allocation.wealthManagement}
              />
              <AllocationBar
                label={getLocalizedText(locale, "股票", "Stocks")}
                value={data.aggressiveOption.allocation.stock}
              />
            </div>
          </article>
        ) : null}

        <article className="panel recommendation-notices">
          <header className="panel__header">
            <h2>{copy.riskNotices}</h2>
          </header>
          <ul>
            {(locale === "en-US" ? data.riskNotice.en : data.riskNotice.zh).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </section>
    </section>
  );
}
