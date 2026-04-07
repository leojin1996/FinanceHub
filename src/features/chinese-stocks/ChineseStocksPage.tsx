import { useState } from "react";

import { AppShell } from "../../app/layout/AppShell";
import { type Locale, useAppState } from "../../app/state/app-state";
import { useMarketData } from "../../app/state/market-data";
import { DataStatusNotice } from "../../components/DataStatusNotice";
import { getMessages } from "../../i18n/messages";
import { type StockRowData } from "../../services/chinaMarketApi";
import { StockFilters } from "./StockFilters";

function getPageCopy(locale: Locale) {
  if (locale === "en-US") {
    return {
      filterLabel: "Search Stocks",
      filterPlaceholder: "Enter code or name",
      sectorLabel: "Industries",
      allSectorLabel: "All",
      boardLabel: "A-share stocks board",
      columns: {
        favorite: "Favorite",
        code: "Code",
        name: "Name",
        price: "Price",
        change: "Change",
        volume: "Volume",
        amount: "Amount",
        sector: "Sector",
        trend: "7-Day Trend",
      },
    };
  }

  return {
    filterLabel: "搜索股票",
    filterPlaceholder: "输入代码或名称",
    sectorLabel: "行业筛选",
    allSectorLabel: "全部",
    boardLabel: "A股股票看板",
    columns: {
      favorite: "自选",
      code: "代码",
      name: "名称",
      price: "价格",
      change: "涨跌幅",
      volume: "成交量",
      amount: "成交额",
      sector: "板块",
      trend: "7日趋势",
    },
  };
}

function formatCompactNumber(value: number, locale: Locale) {
  const absoluteValue = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  const units =
    locale === "zh-CN"
      ? [
          { promotionThreshold: Number.POSITIVE_INFINITY, suffix: "亿", value: 100_000_000 },
          { promotionThreshold: 10_000, suffix: "万", value: 10_000 },
        ]
      : [
          { promotionThreshold: Number.POSITIVE_INFINITY, suffix: "B", value: 1_000_000_000 },
          { promotionThreshold: 1_000, suffix: "M", value: 1_000_000 },
          { promotionThreshold: 1_000, suffix: "K", value: 1_000 },
        ];

  const unitIndex = units.findIndex((unit) => absoluteValue >= unit.value);

  if (unitIndex !== -1) {
    const unit = units[unitIndex];
    const roundedScaledValue = roundToTwoDecimals(absoluteValue / unit.value);

    if (roundedScaledValue >= unit.promotionThreshold && unitIndex > 0) {
      const promotedUnit = units[unitIndex - 1];
      return `${sign}${formatScaledNumber(absoluteValue / promotedUnit.value, locale)}${promotedUnit.suffix}`;
    }

    return `${sign}${formatScaledNumber(absoluteValue / unit.value, locale)}${unit.suffix}`;
  }

  return `${sign}${new Intl.NumberFormat(locale, {
    maximumFractionDigits: absoluteValue >= 100 ? 0 : 2,
  }).format(absoluteValue)}`;
}

function formatPrice(value: number, locale: Locale) {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatScaledNumber(value: number, locale: Locale) {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(value);
}

function roundToTwoDecimals(value: number) {
  return Math.round(value * 100) / 100;
}

function formatChangePercent(value: number, locale: Locale) {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";

  return `${sign}${new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
    minimumFractionDigits: 1,
  }).format(Math.abs(value))}%`;
}

function buildSparklinePoints(points: StockRowData["trend7d"]) {
  if (points.length === 0) {
    return "";
  }

  const values = points.map((point) => point.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const width = 100;
  const height = 28;
  const horizontalPadding = 3;
  const verticalPadding = 3;
  const drawableWidth = width - horizontalPadding * 2;
  const drawableHeight = height - verticalPadding * 2;

  return values
    .map((value, index) => {
      const x =
        points.length === 1
          ? width / 2
          : horizontalPadding + (index / (points.length - 1)) * drawableWidth;
      const y =
        maximum === minimum
          ? height / 2
          : verticalPadding + drawableHeight - ((value - minimum) / (maximum - minimum)) * drawableHeight;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function StockTrendSparkline({
  trend,
  tone,
}: {
  trend: StockRowData["trend7d"];
  tone: "positive" | "negative" | "neutral";
}) {
  if (trend.length === 0) {
    return <span className="stocks-sparkline stocks-sparkline--empty" aria-hidden="true" />;
  }

  return (
    <svg
      aria-hidden="true"
      className={`stocks-sparkline stocks-sparkline--${tone}`}
      preserveAspectRatio="none"
      viewBox="0 0 100 28"
    >
      <polyline fill="none" points={buildSparklinePoints(trend)} strokeLinecap="round" strokeWidth="3" />
    </svg>
  );
}

export function ChineseStocksPage() {
  const { locale } = useAppState();
  const messages = getMessages(locale);
  const routeCopy = messages.nav.stocks;
  const pageCopy = getPageCopy(locale);
  const dataStateCopy = messages.dataState;
  const [query, setQuery] = useState("");
  const [selectedSector, setSelectedSector] = useState<string>("");
  const { stocks } = useMarketData();
  const data = stocks.data;

  const normalizedQuery = query.trim().toLowerCase();
  const sectors = [
    pageCopy.allSectorLabel,
    ...Array.from(new Set((data?.rows ?? []).map((row) => row.sector).filter(Boolean))),
  ];
  const visibleRows = (data?.rows ?? []).filter((row) => {
    const matchesQuery =
      !normalizedQuery ||
      row.code.toLowerCase().includes(normalizedQuery) ||
      row.name.toLowerCase().includes(normalizedQuery);
    const matchesSector = !selectedSector || row.sector === selectedSector;

    return matchesQuery && matchesSector;
  });

  return (
    <AppShell pageSubtitle={routeCopy.subtitle} pageTitle={routeCopy.title}>
      <StockFilters
        label={pageCopy.filterLabel}
        onQueryChange={setQuery}
        onSectorChange={(sector) => setSelectedSector(sector === pageCopy.allSectorLabel ? "" : sector)}
        placeholder={pageCopy.filterPlaceholder}
        query={query}
        sectorLabel={pageCopy.sectorLabel}
        sectors={sectors}
        selectedSector={selectedSector || pageCopy.allSectorLabel}
      />
      {!data && stocks.loadStatus === "error" ? (
        <DataStatusNotice
          body={dataStateCopy.errorBody}
          title={dataStateCopy.errorTitle}
          tone="danger"
        />
      ) : null}
      {!data && stocks.loadStatus !== "error" ? (
        <DataStatusNotice title={dataStateCopy.loading} tone="info" />
      ) : null}
      {data && stocks.refreshStatus === "failed" ? (
        <DataStatusNotice title={dataStateCopy.cachedLabel} tone="warning" />
      ) : null}
      {data?.stale ? (
        <DataStatusNotice
          title={`${dataStateCopy.staleLabel}: ${data.asOfDate}`}
          tone="warning"
        />
      ) : null}
      {data ? (
        <section className="chinese-stocks__layout">
          <div className="chinese-stocks__table">
            <section aria-label={pageCopy.boardLabel} className="panel chinese-stocks-board">
              <div className="chinese-stocks-board__scroll">
                <table>
                  <thead>
                    <tr>
                      <th aria-label={pageCopy.columns.favorite} scope="col">
                        <span aria-hidden="true">☆</span>
                      </th>
                      <th scope="col">{pageCopy.columns.code}</th>
                      <th scope="col">{pageCopy.columns.name}</th>
                      <th className="stocks-board__numeric" scope="col">
                        {pageCopy.columns.price}
                      </th>
                      <th className="stocks-board__numeric" scope="col">
                        {pageCopy.columns.change}
                      </th>
                      <th className="stocks-board__numeric" scope="col">
                        {pageCopy.columns.volume}
                      </th>
                      <th className="stocks-board__numeric" scope="col">
                        {pageCopy.columns.amount}
                      </th>
                      <th scope="col">{pageCopy.columns.sector}</th>
                      <th scope="col">{pageCopy.columns.trend}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRows.map((row) => {
                      const tone =
                        row.changePercent > 0 ? "positive" : row.changePercent < 0 ? "negative" : "neutral";
                      const arrow = tone === "positive" ? "▲" : tone === "negative" ? "▼" : "•";

                      return (
                        <tr key={row.code}>
                          <td className="stocks-board__favorite">
                            <span aria-hidden="true">☆</span>
                          </td>
                          <td className="stocks-board__code">{row.code}</td>
                          <td className="stocks-board__name">{row.name}</td>
                          <td className="stocks-board__numeric">{formatPrice(row.priceValue, locale)}</td>
                          <td className="stocks-board__numeric">
                            <span className={`stocks-change stocks-change--${tone}`}>
                              <span aria-hidden="true" className="stocks-change__arrow">
                                {arrow}
                              </span>
                              <span>{formatChangePercent(row.changePercent, locale)}</span>
                            </span>
                          </td>
                          <td className="stocks-board__numeric">
                            {formatCompactNumber(row.volumeValue, locale)}
                          </td>
                          <td className="stocks-board__numeric">
                            {formatCompactNumber(row.amountValue, locale)}
                          </td>
                          <td>
                            <span className="stocks-sector-badge">{row.sector}</span>
                          </td>
                          <td>
                            <StockTrendSparkline tone={tone} trend={row.trend7d} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </section>
      ) : null}
    </AppShell>
  );
}
