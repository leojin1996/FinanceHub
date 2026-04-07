import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AppShell } from "../../app/layout/AppShell";
import { type Locale, useAppState } from "../../app/state/app-state";
import { useMarketData } from "../../app/state/market-data";
import { DataStatusNotice } from "../../components/DataStatusNotice";
import { getMessages } from "../../i18n/messages";
import {
  type RankingItem,
  type TrendPoint,
} from "../../services/chinaMarketApi";

function classifyChange(value: number): "positive" | "negative" | "neutral" {
  if (value > 0) {
    return "positive";
  }

  if (value < 0) {
    return "negative";
  }

  return "neutral";
}

function formatSignedNumber(value: number, fractionDigits = 2): string {
  const absolute = Math.abs(value).toFixed(fractionDigits);

  if (value > 0) {
    return `+${absolute}`;
  }

  if (value < 0) {
    return `-${absolute}`;
  }

  return absolute;
}

function formatPercent(value: number): string {
  return `${formatSignedNumber(value)}%`;
}

function formatMetricChange(changeValue: number, changePercent: number): string {
  return `${formatSignedNumber(changeValue)} (${formatPercent(changePercent)})`;
}

function buildChangeDisplay(change: string, changePercent: number): string {
  const arrow = changePercent > 0 ? "▲" : changePercent < 0 ? "▼" : "■";
  return `${arrow} ${change} / ${formatPercent(changePercent)}`;
}

export function formatTrendDateLabel(value: string): string {
  return value;
}

export function formatTrendValueLabel(value: number, locale: Locale): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value);
}

function formatTrendTooltipValue(value: number, locale: Locale): string {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(value);
}

export function buildTightYAxisDomain(series: TrendPoint[]): [number, number] {
  if (series.length === 0) {
    return [0, 1];
  }

  let min = series[0].value;
  let max = series[0].value;

  for (const point of series) {
    min = Math.min(min, point.value);
    max = Math.max(max, point.value);
  }

  const range = max - min;
  const padding = range === 0 ? Math.max(Math.abs(max) * 0.004, 1) : range * 0.08;
  return [min - padding, max + padding];
}

function MarketRankCard({
  changeLabel,
  identityLabel,
  items,
  priceLabel,
  title,
}: {
  changeLabel: string;
  identityLabel: string;
  items: RankingItem[];
  priceLabel: string;
  title: string;
}) {
  return (
    <section className="panel market-overview__rank-card">
      <header className="panel__header">
        <h2>{title}</h2>
      </header>
      <div className="market-overview__rank-head">
        <span>{identityLabel}</span>
        <span>{priceLabel}</span>
        <span>{changeLabel}</span>
      </div>
      <ul className="market-overview__rank-list">
        {items.map((item) => {
          const tone = classifyChange(item.changePercent);
          return (
            <li className="market-overview__rank-row" key={`${item.code}-${item.name}`}>
              <div className="market-overview__rank-name">
                <span className="market-overview__rank-code">{item.code}</span>
                <strong>{item.name}</strong>
              </div>
              <span className="market-overview__rank-price">{item.price}</span>
              <span className={`market-overview__rank-change market-overview__rank-change--${tone}`}>
                {buildChangeDisplay(item.change, item.changePercent)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function MarketOverviewContent() {
  const { locale } = useAppState();
  const messages = getMessages(locale);
  const bodyCopy = messages.marketOverview;
  const changeLabel = locale === "zh-CN" ? "涨跌幅" : "Change";
  const identityLabel = locale === "zh-CN" ? "代码 / 名称" : "Code / Name";
  const priceLabel = locale === "zh-CN" ? "价格" : "Price";
  const { overview } = useMarketData();
  const data = overview.data;

  if (!data && overview.loadStatus === "error") {
    return (
      <DataStatusNotice
        body={messages.dataState.errorBody}
        title={messages.dataState.errorTitle}
        tone="danger"
      />
    );
  }

  if (!data) {
    return <DataStatusNotice title={messages.dataState.loading} tone="info" />;
  }

  const yAxisDomain = buildTightYAxisDomain(data.trendSeries);

  return (
    <>
      {overview.refreshStatus === "failed" ? (
        <DataStatusNotice
          title={messages.dataState.cachedLabel}
          tone="warning"
        />
      ) : null}
      {data.stale ? (
        <DataStatusNotice
          title={`${messages.dataState.staleLabel}: ${data.asOfDate}`}
          tone="warning"
        />
      ) : null}
      <section className="market-overview__metrics">
        {data.metrics.slice(0, 3).map((metric) => (
          <article className="panel market-overview__metric-card" key={metric.label}>
            <p className="market-overview__metric-label">{metric.label}</p>
            <strong className="market-overview__metric-value">{metric.value}</strong>
            <span className={`market-overview__metric-change market-overview__metric-change--${metric.tone}`}>
              {formatMetricChange(metric.changeValue, metric.changePercent)}
            </span>
          </article>
        ))}
      </section>

      <section className="panel market-overview__chart-card">
        <header className="panel__header">
          <h2>{data.chartLabel}</h2>
        </header>
        <div className="market-overview__chart">
          <ResponsiveContainer height={300} width="100%">
            <AreaChart data={data.trendSeries}>
              <defs>
                <linearGradient id="overviewTrendGradient" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="5%" stopColor="#4d8fff" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#4d8fff" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid opacity={0.4} stroke="var(--fh-border)" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                stroke="var(--fh-text-muted)"
                tickFormatter={formatTrendDateLabel}
                tickLine={false}
              />
              <YAxis
                domain={yAxisDomain}
                stroke="var(--fh-text-muted)"
                tickFormatter={(value: number) => formatTrendValueLabel(value, locale)}
                tickLine={false}
              />
              <Tooltip
                formatter={(value: unknown) =>
                  typeof value === "number"
                    ? formatTrendTooltipValue(value, locale)
                    : typeof value === "string"
                      ? value
                      : ""
                }
                labelFormatter={(label: unknown) =>
                  typeof label === "string" ? formatTrendDateLabel(label) : ""
                }
              />
              <Area
                dataKey="value"
                fill="url(#overviewTrendGradient)"
                fillOpacity={1}
                stroke="#4d8fff"
                strokeWidth={2}
                type="monotone"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="market-overview__lists">
        <MarketRankCard
          changeLabel={changeLabel}
          identityLabel={identityLabel}
          items={data.topGainers}
          priceLabel={priceLabel}
          title={bodyCopy.gainersTitle}
        />
        <MarketRankCard
          changeLabel={changeLabel}
          identityLabel={identityLabel}
          items={data.topLosers}
          priceLabel={priceLabel}
          title={bodyCopy.losersTitle}
        />
      </section>
    </>
  );
}

export function MarketOverviewPage() {
  const { locale } = useAppState();
  const routeCopy = getMessages(locale).nav.overview;

  return (
    <AppShell pageSubtitle={routeCopy.subtitle} pageTitle={routeCopy.title}>
      <MarketOverviewContent />
    </AppShell>
  );
}
