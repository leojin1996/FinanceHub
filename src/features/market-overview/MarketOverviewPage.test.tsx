import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, it, vi } from "vitest";

import { AppStateProvider } from "../../app/state/AppStateProvider";
import { MarketDataProvider } from "../../app/state/MarketDataProvider";
import type { MarketOverviewResponse } from "../../services/chinaMarketApi";
import {
  buildTightYAxisDomain,
  formatTrendDateLabel,
  formatTrendValueLabel,
  MarketOverviewPage,
} from "./MarketOverviewPage";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function buildOverviewPayload(): MarketOverviewResponse {
  return {
    asOfDate: "2026-04-01",
    stale: true,
    metrics: [
      {
        label: "上证指数",
        value: "3,245.55",
        delta: "+0.38%",
        changeValue: 12.24,
        changePercent: 0.38,
        tone: "positive",
      },
      {
        label: "深证成指",
        value: "10,422.88",
        delta: "-0.16%",
        changeValue: -16.42,
        changePercent: -0.16,
        tone: "negative",
      },
      {
        label: "创业板指",
        value: "2,094.41",
        delta: "0.00%",
        changeValue: 0.0,
        changePercent: 0.0,
        tone: "neutral",
      },
    ],
    chartLabel: "上证指数近10个交易日",
    trendSeries: [
      { date: "2026-03-31", value: 3238.2 },
      { date: "2026-04-01", value: 3245.5 },
    ],
    topGainers: [
      {
        code: "300750",
        name: "宁德时代",
        price: "188.55",
        priceValue: 188.55,
        change: "+11.02",
        changePercent: 6.2,
      },
      {
        code: "002594",
        name: "比亚迪",
        price: "238.10",
        priceValue: 238.1,
        change: "+10.90",
        changePercent: 4.8,
      },
    ],
    topLosers: [
      {
        code: "600036",
        name: "招商银行",
        price: "42.88",
        priceValue: 42.88,
        change: "-1.56",
        changePercent: -3.5,
      },
      {
        code: "600519",
        name: "贵州茅台",
        price: "1688.00",
        priceValue: 1688,
        change: "-10.19",
        changePercent: -0.6,
      },
    ],
  };
}

function createStorageMock(): Storage {
  const store = new Map<string, string>();

  return {
    clear: () => {
      store.clear();
    },
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
  };
}

function seedOverviewStorage(payload: MarketOverviewResponse) {
  window.localStorage.setItem(
    "financehub.market.overview",
    JSON.stringify({
      data: payload,
      resource: "overview",
      savedAt: new Date(Date.now() - 60_000).toISOString(),
      version: 1,
    }),
  );
}

function renderPage() {
  return render(
    <AppStateProvider>
      <MarketDataProvider>
        <MemoryRouter initialEntries={["/"]}>
          <MarketOverviewPage />
        </MemoryRouter>
      </MarketDataProvider>
    </AppStateProvider>,
  );
}

describe("MarketOverviewPage", () => {
  beforeEach(() => {
    const localStorageMock = createStorageMock();
    vi.stubGlobal("localStorage", localStorageMock);
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: localStorageMock,
    });
    window.localStorage.clear();
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);

        if (url.endsWith("/api/market-overview")) {
          return jsonResponse(buildOverviewPayload());
        }

        if (url.endsWith("/api/indices")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            cards: [],
            stale: false,
          });
        }

        if (url.endsWith("/api/stocks")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            rows: [],
            stale: false,
          });
        }

        throw new Error(`Unhandled fetch for ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders API-backed overview data and a stale-data notice", async () => {
    const { container } = renderPage();

    expect(screen.getByRole("status")).toHaveTextContent("正在加载市场数据");
    expect(await screen.findByText("上证指数")).toBeInTheDocument();
    expect(screen.getByText("最近可用收盘数据: 2026-04-01")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "上证指数近10个交易日" })).toBeInTheDocument();
    expect(screen.getByText("招商银行")).toBeInTheDocument();
    expect(screen.getByText("300750")).toBeInTheDocument();
    expect(screen.getByText("188.55")).toBeInTheDocument();
    expect(screen.getByText("▲ +11.02 / +6.20%")).toBeInTheDocument();
    expect(screen.getByText("▼ -1.56 / -3.50%")).toBeInTheDocument();
    expect(container.querySelectorAll(".market-overview__metric-card")).toHaveLength(3);
  });

  it("renders an error message when the overview request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/market-overview")) {
          return jsonResponse({ detail: "market overview data is unavailable" }, 503);
        }
        if (url.endsWith("/api/indices")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            cards: [],
            stale: false,
          });
        }
        if (url.endsWith("/api/stocks")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            rows: [],
            stale: false,
          });
        }
        throw new Error(`Unhandled fetch for ${url}`);
      }),
    );

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("市场数据暂不可用");
  });

  it("renders overview data from persisted cache without blocking loading", () => {
    seedOverviewStorage(buildOverviewPayload());
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );

    renderPage();

    expect(screen.getByText("上证指数")).toBeInTheDocument();
    expect(screen.queryByText("正在加载市场数据")).not.toBeInTheDocument();
  });

  it("builds a tight y-axis domain around current trend data", () => {
    expect(
      buildTightYAxisDomain([
        { date: "2026-03-31", value: 3238.2 },
        { date: "2026-04-01", value: 3245.5 },
      ]),
    ).toEqual([3237.616, 3246.084]);
  });

  it("formats trend chart dates into compact labels", () => {
    expect(formatTrendDateLabel("2026-04-01")).toBe("2026-04-01");
    expect(formatTrendDateLabel("invalid-date")).toBe("invalid-date");
  });

  it("formats trend chart values for localized display", () => {
    expect(formatTrendValueLabel(3245.5, "zh-CN")).toBe("3,246");
    expect(formatTrendValueLabel(3245.5, "en-US")).toBe("3,246");
  });
});
