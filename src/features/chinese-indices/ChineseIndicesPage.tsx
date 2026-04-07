import { Area, AreaChart, CartesianGrid, ResponsiveContainer, XAxis, YAxis } from "recharts";

import { AppShell } from "../../app/layout/AppShell";
import { useAppState } from "../../app/state/app-state";
import { useMarketData } from "../../app/state/market-data";
import { DataStatusNotice } from "../../components/DataStatusNotice";
import { getMessages } from "../../i18n/messages";
import { type TrendPoint } from "../../services/chinaMarketApi";

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

function formatChangeLabel(changeValue: number, changePercent: number): string {
  const arrow = changeValue > 0 ? "▲" : changeValue < 0 ? "▼" : "■";
  return `${arrow} ${formatSignedNumber(changeValue)} (${formatSignedNumber(changePercent)}%)`;
}

function buildTightCardDomain(series: TrendPoint[]): [number, number] {
  if (series.length === 0) {
    return [0, 1];
  }

  let minValue = series[0].value;
  let maxValue = series[0].value;

  for (const point of series) {
    minValue = Math.min(minValue, point.value);
    maxValue = Math.max(maxValue, point.value);
  }

  const spread = maxValue - minValue;
  const padding = Math.max(spread * 0.15, Math.abs(maxValue) * 0.002, 1);
  return [minValue - padding, maxValue + padding];
}

function buildCardTicks(series: TrendPoint[]): [number, number, number] {
  const [domainMin, domainMax] = buildTightCardDomain(series);
  const midpoint = (domainMin + domainMax) / 2;
  return [domainMin, midpoint, domainMax];
}

function formatAxisValue(value: number): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
}

function normalizeMarketLabel(market: string): string {
  const normalized = market.trim();
  if (normalized === "中国市场") {
    return normalized;
  }
  return "中国市场";
}

export function ChineseIndicesPage() {
  const { locale } = useAppState();
  const messages = getMessages(locale);
  const routeCopy = messages.nav.indices;
  const dataStateCopy = messages.dataState;
  const { indices } = useMarketData();
  const data = indices.data;

  return (
    <AppShell pageSubtitle={routeCopy.subtitle} pageTitle={routeCopy.title}>
      {!data && indices.loadStatus === "error" ? (
        <DataStatusNotice
          body={dataStateCopy.errorBody}
          title={dataStateCopy.errorTitle}
          tone="danger"
        />
      ) : null}
      {!data && indices.loadStatus !== "error" ? (
        <DataStatusNotice title={dataStateCopy.loading} tone="info" />
      ) : null}
      {data && indices.refreshStatus === "failed" ? (
        <DataStatusNotice title={dataStateCopy.cachedLabel} tone="warning" />
      ) : null}
      {data?.stale ? (
        <DataStatusNotice
          title={`${dataStateCopy.staleLabel}: ${data.asOfDate}`}
          tone="warning"
        />
      ) : null}
      {data ? (
        <section className="chinese-indices__layout">
          {data.cards.map((card) => {
            const axisTicks = buildCardTicks(card.trendSeries);

            return (
              <article className="panel indices-card" key={card.code}>
              <header className="indices-card__header">
                <h3>{card.name}</h3>
                <p className="indices-card__meta">
                  {card.code} • {normalizeMarketLabel(card.market)}
                </p>
                <p className="indices-card__description">{card.description}</p>
              </header>

              <p className={`indices-card__value indices-card__value--${card.tone}`}>{card.value}</p>
              <p className={`indices-card__change indices-card__change--${card.tone}`}>
                {formatChangeLabel(card.changeValue, card.changePercent)}
              </p>

              <div
                className={`indices-card__chart indices-card__chart--${card.tone}`}
                data-testid="indices-card-chart"
              >
                <ResponsiveContainer height={120} width="100%">
                  <AreaChart data={card.trendSeries}>
                    <defs>
                      <linearGradient id={`indicesCardTrend-${card.code}`} x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor="currentColor" stopOpacity={0.32} />
                        <stop offset="100%" stopColor="currentColor" stopOpacity={0.03} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid opacity={0.3} stroke="var(--fh-border)" strokeDasharray="3 3" />
                    <XAxis
                      axisLine={false}
                      dataKey="date"
                      minTickGap={16}
                      stroke="var(--fh-text-muted)"
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                    />
                    <YAxis
                      axisLine={false}
                      domain={buildTightCardDomain(card.trendSeries)}
                      interval={0}
                      tick={{ fontSize: 10 }}
                      tickCount={3}
                      tickFormatter={formatAxisValue}
                      tickLine={false}
                      scale="linear"
                      ticks={axisTicks}
                      type="number"
                      width={44}
                    />
                    <Area
                      dataKey="value"
                      fill={`url(#indicesCardTrend-${card.code})`}
                      fillOpacity={1}
                      stroke="currentColor"
                      strokeWidth={2}
                      type="monotone"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              </article>
            );
          })}
        </section>
      ) : null}
    </AppShell>
  );
}
