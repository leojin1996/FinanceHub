import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";

import { AppStateProvider } from "../../app/state/AppStateProvider";
import { MarketDataProvider } from "../../app/state/MarketDataProvider";
import { ChineseIndicesPage } from "./ChineseIndicesPage";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("ChineseIndicesPage", () => {
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
      "ResizeObserver",
      class {
        disconnect() {}
        observe() {}
        unobserve() {}
      },
    );
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(() => {
      return {
        bottom: 120,
        height: 120,
        left: 0,
        right: 360,
        toJSON: () => ({}),
        top: 0,
        width: 360,
        x: 0,
        y: 0,
      };
    });
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(360);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(120);
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(360);
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(120);
    Object.defineProperty(SVGElement.prototype, "getBBox", {
      configurable: true,
      value: () => ({
        height: 10,
        width: 24,
        x: 0,
        y: 0,
      }),
    });
    Object.defineProperty(SVGElement.prototype, "getComputedTextLength", {
      configurable: true,
      value: () => 24,
    });

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/indices")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: false,
            cards: [
              {
                name: "上证指数",
                code: "000001.SH",
                market: "沪深市场",
                description: "沪市核心宽基指数",
                value: "3,245.50",
                valueNumber: 3245.5,
                changeValue: 7.3,
                changePercent: 0.23,
                tone: "positive",
                trendSeries: [
                  { date: "2026-03-28", value: 3210.2 },
                  { date: "2026-03-29", value: 3228.5 },
                  { date: "2026-03-30", value: 3236.1 },
                  { date: "2026-03-31", value: 3245.5 },
                ],
              },
              {
                name: "深证成指",
                code: "399001.SZ",
                market: "中国市场",
                description: "深市代表性综合指数",
                value: "10,422.90",
                valueNumber: 10422.9,
                changeValue: -3.6,
                changePercent: -0.17,
                tone: "negative",
                trendSeries: [
                  { date: "2026-03-28", value: 10480.1 },
                  { date: "2026-03-29", value: 10455.4 },
                  { date: "2026-03-30", value: 10440.3 },
                  { date: "2026-03-31", value: 10422.9 },
                ],
              },
              {
                name: "创业板指",
                code: "399006.SZ",
                market: "中国市场",
                description: "成长风格代表指数",
                value: "2,094.40",
                valueNumber: 2094.4,
                changeValue: 2.1,
                changePercent: 0.1,
                tone: "positive",
                trendSeries: [
                  { date: "2026-03-28", value: 2078.8 },
                  { date: "2026-03-29", value: 2084.3 },
                  { date: "2026-03-30", value: 2089.5 },
                  { date: "2026-03-31", value: 2094.4 },
                ],
              },
              {
                name: "科创50",
                code: "000688.SH",
                market: "中国市场",
                description: "科创板核心龙头指数",
                value: "988.60",
                valueNumber: 988.6,
                changeValue: 0,
                changePercent: 0,
                tone: "neutral",
                trendSeries: [
                  { date: "2026-03-28", value: 986.1 },
                  { date: "2026-03-29", value: 987.4 },
                  { date: "2026-03-30", value: 988.2 },
                  { date: "2026-03-31", value: 988.6 },
                ],
              },
            ],
          });
        }
        if (url.endsWith("/api/market-overview")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            chartLabel: "上证指数近10个交易日",
            metrics: [],
            stale: false,
            topGainers: [],
            topLosers: [],
            trendSeries: [],
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
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it(
    "renders four index cards with date axes and arrowed move styles",
    async () => {
      const { container } = render(
        <AppStateProvider>
          <MarketDataProvider>
            <MemoryRouter initialEntries={["/indices"]}>
              <ChineseIndicesPage />
            </MemoryRouter>
          </MarketDataProvider>
        </AppStateProvider>,
      );

      expect(screen.getByRole("status")).toHaveTextContent("正在加载市场数据");
      expect(await screen.findByRole("heading", { name: "上证指数" })).toBeInTheDocument();

      const indexHeadings = screen.getAllByRole("heading", { level: 3 });
      expect(indexHeadings.map((heading) => heading.textContent)).toEqual([
        "上证指数",
        "深证成指",
        "创业板指",
        "科创50",
      ]);

      expect(screen.queryByRole("heading", { name: "指数对比" })).not.toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "指数洞察" })).not.toBeInTheDocument();
      expect(screen.getAllByTestId("indices-card-chart")).toHaveLength(4);
      expect(container.querySelectorAll(".recharts-responsive-container")).toHaveLength(4);
      await waitFor(() => {
        expect(container.querySelectorAll(".recharts-xAxis")).toHaveLength(4);
      });
      await waitFor(() => {
        expect(container.querySelectorAll(".recharts-yAxis")).toHaveLength(4);
      });
      expect(container.querySelectorAll(".indices-card__axis-labels")).toHaveLength(0);
      expect(container.querySelectorAll(".indices-card__axis-tick")).toHaveLength(0);
      expect(container.querySelectorAll(".recharts-yAxis .recharts-cartesian-axis-tick")).toHaveLength(
        12,
      );

      expect(screen.getByText("▲ +7.30 (+0.23%)")).toHaveClass("indices-card__change--positive");
      expect(screen.getByText("▼ -3.60 (-0.17%)")).toHaveClass("indices-card__change--negative");
      expect(screen.getByText("000001.SH • 中国市场")).toBeInTheDocument();
      expect(screen.getByText("399001.SZ • 中国市场")).toBeInTheDocument();
      expect(screen.getByText("3,245.50")).toHaveClass("indices-card__value--positive");
      expect(screen.getByText("10,422.90")).toHaveClass("indices-card__value--negative");
      expect(screen.getByText("988.60")).toHaveClass("indices-card__value--neutral");
    },
    15_000,
  );

  it("renders indices from persisted cache without blocking loading", () => {
    window.localStorage.setItem(
      "financehub.market.indices",
      JSON.stringify({
        data: {
          asOfDate: "2026-04-01",
          cards: [
            {
              code: "000001.SH",
              changePercent: 0.23,
              changeValue: 7.3,
              description: "沪市核心宽基指数",
              market: "中国市场",
              name: "上证指数",
              stale: false,
              tone: "positive",
              trendSeries: [
                { date: "2026-03-28", value: 3210.2 },
                { date: "2026-03-29", value: 3228.5 },
              ],
              value: "3,245.50",
              valueNumber: 3245.5,
            },
          ],
          stale: false,
        },
        resource: "indices",
        savedAt: new Date(Date.now() - 60_000).toISOString(),
        version: 1,
      }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => undefined)),
    );

    render(
      <AppStateProvider>
        <MarketDataProvider>
          <MemoryRouter initialEntries={["/indices"]}>
            <ChineseIndicesPage />
          </MemoryRouter>
        </MarketDataProvider>
      </AppStateProvider>,
    );

    expect(screen.getByRole("heading", { name: "上证指数" })).toBeInTheDocument();
    expect(screen.queryByText("正在加载市场数据")).not.toBeInTheDocument();
  });

  it("shows only blocking error when indices request fails without cached data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/indices")) {
          return jsonResponse({ detail: "indices data is unavailable" }, 503);
        }
        if (url.endsWith("/api/market-overview")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            chartLabel: "上证指数近10个交易日",
            metrics: [],
            stale: false,
            topGainers: [],
            topLosers: [],
            trendSeries: [],
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

    render(
      <AppStateProvider>
        <MarketDataProvider>
          <MemoryRouter initialEntries={["/indices"]}>
            <ChineseIndicesPage />
          </MemoryRouter>
        </MarketDataProvider>
      </AppStateProvider>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("市场数据暂不可用");
    expect(screen.queryByText("正在加载市场数据")).not.toBeInTheDocument();
  });
});

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
