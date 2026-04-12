import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link, useParams } from "react-router-dom";

import { AppShell } from "../../app/layout/AppShell";
import { useAppState } from "../../app/state/app-state";
import { InsightCard } from "../../components/InsightCard";
import {
  fetchRecommendationProductDetail,
  type RecommendationProductDetailResponse,
} from "../../services/chinaMarketApi";

function getCopy(locale: "zh-CN" | "en-US") {
  if (locale === "en-US") {
    return {
      backToRecommendations: "Back to recommendations",
      detailUnavailable: "Product detail is temporarily unavailable",
      fallbackChart: "Trend chart is unavailable for this product right now.",
      fitForProfile: "Who it fits",
      loading: "Loading product detail...",
      metrics: "Key metrics",
      references: "References",
      rationale: "Why it was selected",
      summary: "Product summary",
      subtitle: "Review the latest profile, metrics, and trend snapshot before making a decision.",
      title: "Recommendation product detail",
    };
  }

  return {
    backToRecommendations: "返回推荐页",
    detailUnavailable: "暂时无法加载产品详情",
    fallbackChart: "当前产品暂时没有可展示的走势图。",
    fitForProfile: "适合谁",
    loading: "正在加载产品详情...",
    metrics: "关键指标",
    references: "参考资料",
    rationale: "为什么推荐它",
    summary: "产品概览",
    subtitle: "在做决定前，先看清产品画像、关键指标和近期走势。",
    title: "推荐产品详情",
  };
}

function getLocalizedText(locale: "zh-CN" | "en-US", zh: string, en: string) {
  return locale === "en-US" ? en : zh;
}

function getMetricLabel(locale: "zh-CN" | "en-US", key: string) {
  const labels: Record<string, { en: string; zh: string }> = {
    annualizedReturn: { en: "Annualized return", zh: "年化回报" },
    changePercent: { en: "Price change", zh: "价格涨跌" },
    expectedYield: { en: "Expected yield", zh: "预期收益" },
    latestPrice: { en: "Latest price", zh: "最新价格" },
    managementFee: { en: "Management fee", zh: "管理费" },
    maxDrawdown: { en: "Max drawdown", zh: "最大回撤" },
    weeklyRangePercent: { en: "Weekly range", zh: "周内波动" },
  };
  const label = labels[key];
  if (label) {
    return getLocalizedText(locale, label.zh, label.en);
  }
  return key;
}

function buildMetricEntries(
  locale: "zh-CN" | "en-US",
  detail: RecommendationProductDetailResponse,
) {
  return [
    ...Object.entries(detail.yieldMetrics),
    ...Object.entries(detail.fees),
    ...Object.entries(detail.drawdownOrVolatility),
  ].map(([key, value]) => ({
    key,
    label: getMetricLabel(locale, key),
    value,
  }));
}

function getEvidence(detail: RecommendationProductDetailResponse) {
  return Array.isArray(detail.evidence) ? detail.evidence : [];
}

function getSafeExternalLink(sourceUri: string | null): string | null {
  if (!sourceUri) {
    return null;
  }

  try {
    const parsed = new URL(sourceUri);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.toString();
    }
  } catch (_error) {
    return null;
  }

  return null;
}

export function RecommendationProductDetailPage() {
  const { locale } = useAppState();
  const { productId } = useParams<{ productId: string }>();
  const [detail, setDetail] = useState<RecommendationProductDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [requestVersion, setRequestVersion] = useState(0);
  const staleRevalidationIdsRef = useRef<Set<string>>(new Set());
  const copy = getCopy(locale);

  useEffect(() => {
    if (!productId) {
      setError(locale === "en-US" ? "Missing product id." : "缺少产品编号。");
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchRecommendationProductDetail(productId)
      .then((response) => {
        if (cancelled) {
          return;
        }
        setDetail(response);
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
  }, [locale, productId, requestVersion]);

  useEffect(() => {
    if (!detail?.stale) {
      return;
    }
    if (staleRevalidationIdsRef.current.has(detail.id)) {
      return;
    }

    staleRevalidationIdsRef.current.add(detail.id);
    const timer = window.setTimeout(() => {
      startTransition(() => {
        setRequestVersion((version) => version + 1);
      });
    }, 200);

    return () => {
      window.clearTimeout(timer);
    };
  }, [detail]);

  const metrics = useMemo(() => {
    if (!detail) {
      return [];
    }
    return buildMetricEntries(locale, detail);
  }, [detail, locale]);
  const evidence = useMemo(() => (detail ? getEvidence(detail) : []), [detail]);

  const pageTitle = detail ? getLocalizedText(locale, detail.nameZh, detail.nameEn) : copy.title;

  return (
    <AppShell pageSubtitle={copy.subtitle} pageTitle={pageTitle}>
      {loading ? (
        <InsightCard title={copy.loading}>
          <p>{copy.subtitle}</p>
        </InsightCard>
      ) : null}

      {!loading && error ? (
        <InsightCard title={copy.detailUnavailable}>
          <p>{error}</p>
          <p>
            <Link to="/recommendations">{copy.backToRecommendations}</Link>
          </p>
        </InsightCard>
      ) : null}

      {!loading && !error && detail ? (
        <section className="recommendation-detail-layout">
          <article className="panel recommendation-detail-hero">
            <div className="recommendation-detail-hero__topline">
              <Link className="recommendation-detail__back-link" to="/recommendations">
                {copy.backToRecommendations}
              </Link>
              {detail.stale ? (
                <span className="tag-badge recommendation-detail__stale-badge">
                  {locale === "en-US" ? "Cached snapshot" : "缓存快照"}
                </span>
              ) : null}
            </div>
            <div className="recommendation-detail-hero__summary">
              <div>
                <p className="recommendation-detail-hero__eyebrow">
                  {detail.providerName ?? detail.source}
                </p>
                <h2>{getLocalizedText(locale, detail.nameZh, detail.nameEn)}</h2>
                <p>
                  {[detail.code, detail.riskLevel, detail.liquidity, detail.asOfDate]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <div className="recommendation-product-card__tags">
                {(locale === "en-US" ? detail.tagsEn : detail.tagsZh).map((tag) => (
                  <span className="tag-badge" key={tag}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </article>

          <section className="recommendation-two-column">
            <article className="panel recommendation-detail-summary">
              <header className="panel__header">
                <h2>{copy.summary}</h2>
              </header>
              <p>{getLocalizedText(locale, detail.summary.zh, detail.summary.en)}</p>
            </article>

            <article className="panel recommendation-detail-fit">
              <header className="panel__header">
                <h2>{copy.fitForProfile}</h2>
              </header>
              <p>{getLocalizedText(locale, detail.fitForProfile.zh, detail.fitForProfile.en)}</p>
            </article>
          </section>

          <section className="recommendation-two-column">
            <article className="panel recommendation-detail-chart">
              <header className="panel__header">
                <h2>{getLocalizedText(locale, detail.chartLabel.zh, detail.chartLabel.en)}</h2>
              </header>
              {detail.chart.length > 0 ? (
                <div className="recommendation-detail-chart__canvas">
                  <ResponsiveContainer height={280} width="100%">
                    <AreaChart data={detail.chart}>
                      <defs>
                        <linearGradient id="recommendation-detail-chart-fill" x1="0" x2="0" y1="0" y2="1">
                          <stop offset="5%" stopColor="#1b6fd8" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="#1b6fd8" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#d9e4f5" strokeDasharray="3 3" />
                      <XAxis dataKey="date" tickLine={false} />
                      <YAxis tickLine={false} width={72} />
                      <Tooltip />
                      <Area
                        dataKey="value"
                        fill="url(#recommendation-detail-chart-fill)"
                        stroke="#1b6fd8"
                        strokeWidth={2}
                        type="monotone"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p>{copy.fallbackChart}</p>
              )}
            </article>

            <article className="panel recommendation-detail-metrics">
              <header className="panel__header">
                <h2>{copy.metrics}</h2>
              </header>
              {metrics.length > 0 ? (
                <div className="recommendation-detail-metrics__grid">
                  {metrics.map((metric) => (
                    <article className="recommendation-detail-metric" key={metric.key}>
                      <strong>{metric.label}</strong>
                      <span>{metric.value}</span>
                    </article>
                  ))}
                </div>
              ) : (
                <p>{locale === "en-US" ? "No extra metrics are available yet." : "暂时没有更多可展示指标。"}</p>
              )}
            </article>
          </section>

          <article className="panel recommendation-detail-rationale">
            <header className="panel__header">
              <h2>{copy.rationale}</h2>
            </header>
            <p>{getLocalizedText(locale, detail.recommendationRationale.zh, detail.recommendationRationale.en)}</p>
          </article>

          {evidence.length > 0 ? (
            <article className="panel recommendation-detail-references">
              <header className="panel__header">
                <h2>{copy.references}</h2>
              </header>
              <div className="recommendation-evidence-list recommendation-evidence-list--detail">
                {evidence.map((reference) => {
                  const safeSourceUri = getSafeExternalLink(reference.sourceUri);

                  return (
                    <article className="recommendation-evidence-item" key={reference.evidenceId}>
                      <p className="recommendation-evidence-item__excerpt" lang={reference.excerptLanguage}>
                        {reference.excerpt}
                      </p>
                      <p className="recommendation-evidence-item__meta">
                        {safeSourceUri ? (
                          <a
                            className="recommendation-evidence-item__source-link"
                            href={safeSourceUri}
                            rel="noopener noreferrer"
                            target="_blank"
                          >
                            {reference.sourceTitle}
                          </a>
                        ) : (
                          <span className="recommendation-evidence-item__source-title">
                            {reference.sourceTitle}
                          </span>
                        )}
                        {reference.asOfDate ? (
                          <span className="recommendation-evidence-item__as-of-date">
                            {reference.asOfDate}
                          </span>
                        ) : null}
                      </p>
                    </article>
                  );
                })}
              </div>
            </article>
          ) : null}
        </section>
      ) : null}
    </AppShell>
  );
}
