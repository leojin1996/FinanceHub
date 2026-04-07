import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";

import { AppStateProvider } from "../../app/state/AppStateProvider";
import { MarketDataProvider } from "../../app/state/MarketDataProvider";
import type { StocksResponse } from "../../services/chinaMarketApi";
import { ChineseStocksPage } from "./ChineseStocksPage";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const STOCKS_PAYLOAD: StocksResponse = {
  asOfDate: "2026-04-01",
  stale: true,
  rows: [
    {
      code: "300750",
      name: "宁德时代",
      sector: "新能源",
      price: "188.55",
      change: "+6.2%",
      priceValue: 188.55,
      changePercent: 6.201419398445432,
      volumeValue: 123456789,
      amountValue: 2345678901,
      trend7d: [
        { date: "2026-03-24", value: 176.0 },
        { date: "2026-03-25", value: 177.1 },
        { date: "2026-03-26", value: 178.4 },
        { date: "2026-03-27", value: 179.0 },
        { date: "2026-03-28", value: 180.5 },
        { date: "2026-03-31", value: 182.0 },
        { date: "2026-04-01", value: 188.55 },
      ],
    },
    {
      code: "002594",
      name: "比亚迪",
      sector: "汽车",
      price: "221.88",
      change: "+4.8%",
      priceValue: 221.88,
      changePercent: 4.8,
      volumeValue: 87654321,
      amountValue: 1987654321,
      trend7d: [
        { date: "2026-03-24", value: 210.0 },
        { date: "2026-03-25", value: 211.6 },
        { date: "2026-03-26", value: 214.2 },
        { date: "2026-03-27", value: 216.0 },
        { date: "2026-03-28", value: 217.8 },
        { date: "2026-03-31", value: 219.1 },
        { date: "2026-04-01", value: 221.88 },
      ],
    },
    {
      code: "600519",
      name: "贵州茅台",
      sector: "消费",
      price: "1499.00",
      change: "-2.3%",
      priceValue: 1499.0,
      changePercent: -2.3,
      volumeValue: 99999999,
      amountValue: 999999,
      trend7d: [
        { date: "2026-03-24", value: 1542.0 },
        { date: "2026-03-25", value: 1538.2 },
        { date: "2026-03-26", value: 1531.6 },
        { date: "2026-03-27", value: 1524.0 },
        { date: "2026-03-28", value: 1518.3 },
        { date: "2026-03-31", value: 1508.6 },
        { date: "2026-04-01", value: 1499.0 },
      ],
    },
  ],
};

function renderPage() {
  render(
    <AppStateProvider>
      <MarketDataProvider>
        <MemoryRouter initialEntries={["/stocks"]}>
          <ChineseStocksPage />
        </MemoryRouter>
      </MarketDataProvider>
    </AppStateProvider>,
  );
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

function seedStocksStorage(payload: StocksResponse) {
  window.localStorage.setItem(
    "financehub.market.stocks",
    JSON.stringify({
      data: payload,
      resource: "stocks",
      savedAt: new Date(Date.now() - 60_000).toISOString(),
      version: 1,
    }),
  );
}

function countStocksFetchCalls(): number {
  return vi
    .mocked(fetch)
    .mock
    .calls.filter(([input]) => String(input).endsWith("/api/stocks")).length;
}

describe("ChineseStocksPage", () => {
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
        if (url.endsWith("/api/stocks")) {
          return jsonResponse(STOCKS_PAYLOAD);
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
        if (url.endsWith("/api/indices")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            cards: [],
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

  it("renders redesigned columns and industry chip rail while keeping stale-data notice", async () => {
    renderPage();

    expect(screen.getByRole("status")).toHaveTextContent("正在加载市场数据");
    expect(await screen.findByText("宁德时代")).toBeInTheDocument();
    expect(screen.getByText("+6.2%")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "成交量" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "成交额" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "7日趋势" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全部" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新能源" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "汽车" })).toBeInTheDocument();
    expect(screen.getByText("最近可用收盘数据: 2026-04-01")).toBeInTheDocument();
  });

  it("filters rows locally when an industry chip is selected", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("宁德时代")).toBeInTheDocument();
    expect(screen.getByText("比亚迪")).toBeInTheDocument();
    expect(screen.getByText("贵州茅台")).toBeInTheDocument();
    expect(countStocksFetchCalls()).toBe(1);

    await user.click(screen.getByRole("button", { name: "新能源" }));

    const table = screen.getByRole("table");
    expect(within(table).getByText("宁德时代")).toBeInTheDocument();
    expect(within(table).queryByText("比亚迪")).not.toBeInTheDocument();
    expect(within(table).queryByText("贵州茅台")).not.toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "搜索股票" }), "300");
    expect(within(table).getByText("宁德时代")).toBeInTheDocument();
    expect(countStocksFetchCalls()).toBe(1);
  });

  it("renders volume and amount with zh-CN compact units", async () => {
    renderPage();

    expect(await screen.findByText("宁德时代")).toBeInTheDocument();
    expect(screen.getByText("1.23亿")).toBeInTheDocument();
    expect(screen.getByText("23.46亿")).toBeInTheDocument();
    expect(screen.getByText("1亿")).toBeInTheDocument();
  });

  it("keeps negative change direction in rendered text", async () => {
    renderPage();

    expect(await screen.findByText("贵州茅台")).toBeInTheDocument();
    expect(screen.getByText("-2.3%")).toBeInTheDocument();
  });

  it("renders volume and amount with en-US compact suffixes after locale switch", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("宁德时代")).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "语言" }), "en-US");

    expect(screen.getByText("123.46M")).toBeInTheDocument();
    expect(screen.getByText("2.35B")).toBeInTheDocument();
    expect(screen.getByText("1M")).toBeInTheDocument();
  });

  it("keeps cached stocks visible when refresh fails and shows cache warning semantics", async () => {
    seedStocksStorage(STOCKS_PAYLOAD);
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/stocks")) {
          return jsonResponse({ detail: "stocks data is unavailable" }, 503);
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
        if (url.endsWith("/api/indices")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            cards: [],
            stale: false,
          });
        }
        throw new Error(`Unhandled fetch for ${url}`);
      }),
    );

    renderPage();

    expect(screen.getByText("宁德时代")).toBeInTheDocument();
    expect(await screen.findByText("正在显示上次缓存数据")).toBeInTheDocument();
  });

  it("shows only blocking error when stocks request fails without cached data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/stocks")) {
          return jsonResponse({ detail: "stocks data is unavailable" }, 503);
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
        if (url.endsWith("/api/indices")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            cards: [],
            stale: false,
          });
        }
        throw new Error(`Unhandled fetch for ${url}`);
      }),
    );

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("市场数据暂不可用");
    expect(screen.queryByText("正在加载市场数据")).not.toBeInTheDocument();
  });
});
