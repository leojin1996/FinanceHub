import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, it, vi } from "vitest";

import App from "./App";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
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

function buildCachedOverviewPayload() {
  return {
    asOfDate: "2026-04-01",
    chartLabel: "上证指数近10个交易日",
    metrics: [
      {
        label: "上证指数",
        value: "3,880.10",
        delta: "+0.38%",
        changeValue: 12.24,
        changePercent: 0.38,
        tone: "positive" as const,
      },
    ],
    stale: false,
    topGainers: [],
    topLosers: [],
    trendSeries: [{ date: "2026-04-01", value: 3880.1 }],
  };
}

describe("App routing shell", () => {
  beforeEach(() => {
    const localStorageMock = createStorageMock();
    vi.stubGlobal("localStorage", localStorageMock);
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: localStorageMock,
    });
    window.localStorage.clear();

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);

        if (url.endsWith("/api/market-overview")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: false,
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
            ],
          });
        }

        if (url.endsWith("/api/indices")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: false,
            cards: [
              {
                name: "上证指数",
                code: "000001.SH",
                market: "中国市场",
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

        if (url.endsWith("/api/stocks")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: false,
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
            ],
          });
        }

        if (url.endsWith("/api/recommendations/generate")) {
          return jsonResponse({
            aggressiveOption: {
              allocation: { fund: 40, stock: 35, wealthManagement: 25 },
              subtitleEn:
                "If you are willing to accept higher volatility, this enhanced allocation can be considered, but it is not the default recommendation.",
              subtitleZh: "如果你愿意承受更高波动，可参考这一增强版配置，但不作为默认推荐。",
              titleEn: "More aggressive option",
              titleZh: "进取型备选",
            },
            allocationDisplay: { fund: 45, stock: 20, wealthManagement: 35 },
            executionMode: "agent_assisted",
            marketSummary: {
              en:
                "Current conditions support a mix of steady assets and selective equity exposure while controlling overall volatility.",
              zh: "当前市场更适合稳健资产与权益增强搭配，控制整体波动。",
            },
            profileSummary: {
              en:
                "Your assessment aligns with a Balanced profile, which calls for drawdown control before chasing extra upside.",
              zh: "您的测评结果更接近平衡型，适合先控制回撤，再追求稳步增值。",
            },
            reviewStatus: "pass",
            riskNotice: {
              en: [
                "Wealth-management products are not deposits, and fund or product NAVs may fluctuate with markets.",
                "The stock sleeve is intended only as an enhancing allocation and should not replace the stable core.",
              ],
              zh: [
                "理财非存款，基金和理财产品净值会随市场波动。",
                "股票部分仅适合作为增强配置，不宜替代稳健底仓。",
              ],
            },
            sections: {
              funds: {
                items: [
                  {
                    category: "fund",
                    id: "fund-001",
                    liquidity: "T+1",
                    nameEn: "Zhongou Steady Bond A",
                    nameZh: "中欧稳利债券A",
                    rationaleEn: "Works well as the portfolio core thanks to lower volatility and steadier return expectations.",
                    rationaleZh: "作为组合底仓，波动较低，更适合用来承接稳健增值目标。",
                    riskLevel: "R2",
                    tagsEn: ["Low drawdown", "Bond core"],
                    tagsZh: ["低回撤", "债券底仓"],
                  },
                ],
                titleEn: "Fund ideas",
                titleZh: "基金推荐",
              },
              stocks: {
                items: [
                  {
                    category: "stock",
                    code: "600036",
                    id: "stock-001",
                    nameEn: "China Merchants Bank",
                    nameZh: "招商银行",
                    rationaleEn: "As a satellite equity holding, it leans on earnings stability and dividend quality to keep volatility more contained.",
                    rationaleZh: "作为增强配置，更偏向盈利稳定和股息特征，适合控制波动。",
                    riskLevel: "R3",
                    tagsEn: ["Dividend quality", "Large cap"],
                    tagsZh: ["高股息", "大盘蓝筹"],
                  },
                ],
                titleEn: "Equity boost",
                titleZh: "股票增强",
              },
              wealthManagement: {
                items: [
                  {
                    category: "wealth_management",
                    id: "wm-001",
                    liquidity: "90天",
                    nameEn: "CMB Wealth Stable 90D",
                    nameZh: "招银理财稳享90天",
                    rationaleEn: "Fits the role of a stable base allocation while preserving reasonable liquidity.",
                    rationaleZh: "适合承担组合的稳定底仓角色，同时兼顾一定流动性。",
                    riskLevel: "R2",
                    tagsEn: ["Short tenor", "Liquidity-friendly"],
                    tagsZh: ["短期限", "流动性友好"],
                  },
                ],
                titleEn: "Wealth management ideas",
                titleZh: "银行理财推荐",
              },
            },
            summary: {
              subtitleEn: "Build the base with steadier assets, then add selective funds and equities for measured upside.",
              subtitleZh: "以稳健资产打底，再配置适量基金与股票增强收益弹性。",
              titleEn: "A Balanced plan that fits you",
              titleZh: "适合您的平衡型配置建议",
            },
            warnings: [],
            whyThisPlan: {
              en: [
                "Your profile screens as Balanced, so the base plan prioritizes overall volatility control.",
                "Current conditions favor steadier assets as the base, with a smaller equity sleeve for upside.",
              ],
              zh: [
                "您的风险画像为平衡型，主方案优先控制整体波动。",
                "当前市场更适合稳健资产打底，再用权益类做小比例增强。",
              ],
            },
          });
        }

        throw new Error(`Unhandled fetch for ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it(
    "enforces the five-route Chinese shell contract and navigation paths",
    async () => {
      window.history.pushState({}, "", "/");
      window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
      const user = userEvent.setup();

      render(<App />);

      const expectedNav = [
        { href: "/", navLabel: "市场", heading: "市场概览" },
        { href: "/stocks", navLabel: "股票", heading: "中国股票" },
        { href: "/indices", navLabel: "指数", heading: "中国指数" },
        { href: "/risk-assessment", navLabel: "风险测评", heading: "风险评估" },
        { href: "/recommendations", navLabel: "推荐", heading: "个性化推荐" },
      ];

      const primaryNav = screen.getByRole("navigation", { name: "主导航" });
      expect(primaryNav).toBeInTheDocument();

      for (const item of expectedNav) {
        const link = within(primaryNav).getByRole("link", { name: item.navLabel });
        expect(link).toHaveAttribute("href", item.href);
      }
      expect(within(primaryNav).getByRole("link", { name: "市场" })).toHaveClass("is-active");

      expect(screen.getByRole("heading", { name: "市场概览" })).toBeInTheDocument();
      expect(await screen.findByRole("heading", { name: "涨幅榜" })).toBeInTheDocument();

      for (const item of expectedNav.slice(1)) {
        const currentNav = screen.getByRole("navigation", { name: "主导航" });
        await user.click(within(currentNav).getByRole("link", { name: item.navLabel }));

        if (item.href === "/indices") {
          expect(screen.getByRole("heading", { name: "中国指数" })).toBeInTheDocument();
          await waitFor(() => {
            expect(screen.getByText("上证指数")).toBeInTheDocument();
          });
          expect(await screen.findByText("科创50")).toBeInTheDocument();
          expect(screen.queryByRole("heading", { name: "指数对比" })).not.toBeInTheDocument();
          const navAfterNavigation = screen.getByRole("navigation", { name: "主导航" });
          expect(within(navAfterNavigation).getByRole("link", { name: "指数" })).toHaveClass("is-active");
        } else {
          expect(screen.getByRole("heading", { name: item.heading })).toBeInTheDocument();
        }
      }
    },
    15_000,
  );

  it("renders the top navigation in Chinese by default and switches nav chrome to English", async () => {
    window.history.pushState({}, "", "/");
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
    const user = userEvent.setup();

    render(<App />);

    const primaryNav = screen.getByRole("navigation", { name: "主导航" });
    expect(within(primaryNav).getByRole("link", { name: "市场" })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: "股票" })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: "指数" })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: "风险测评" })).toBeInTheDocument();
    expect(within(primaryNav).getByRole("link", { name: "推荐" })).toBeInTheDocument();
    expect(screen.getByText("demo@financehub.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "退出登录" })).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox"), "en-US");

    const englishNav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(englishNav).getByRole("link", { name: "Market" })).toBeInTheDocument();
    expect(within(englishNav).getByRole("link", { name: "Stocks" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Logout" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Market Overview" })).toBeInTheDocument();
  });

  it("updates shell copy when switching locale with i18n catalogs", async () => {
    window.history.pushState({}, "", "/risk-assessment");
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
    const user = userEvent.setup();

    render(<App />);

    expect(screen.getByRole("heading", { name: "风险评估" })).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox"), "en-US");

    const primaryNav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(primaryNav).getByRole("link", { name: "Risk Survey" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Risk Assessment" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Logout" })).toBeInTheDocument();
  });

  it("redirects unauthenticated users to login and returns them to the requested route after demo sign-in", async () => {
    window.history.pushState({}, "", "/stocks");
    const user = userEvent.setup();

    render(<App />);

    expect(screen.getByRole("heading", { name: "欢迎来到 FinanceHub" })).toBeInTheDocument();
    expect(screen.getByLabelText("邮箱地址")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "体验 Demo 账户" }));

    expect(await screen.findByRole("heading", { name: "中国股票" })).toBeInTheDocument();
    expect(screen.getByText("demo@financehub.com")).toBeInTheDocument();
  });

  it("preserves full deep-link URL including search and hash through login redirect", async () => {
    window.history.pushState({}, "", "/stocks?query=bank#table");
    const user = userEvent.setup();

    render(<App />);

    expect(screen.getByRole("heading", { name: "欢迎来到 FinanceHub" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "体验 Demo 账户" }));

    expect(await screen.findByRole("heading", { name: "中国股票" })).toBeInTheDocument();
    expect(`${window.location.pathname}${window.location.search}${window.location.hash}`).toBe(
      "/stocks?query=bank#table",
    );
  });

  it("redirects signed-in users visiting /login to market overview instead of prior from route", async () => {
    window.history.pushState({}, "", "/stocks");
    const user = userEvent.setup();
    const firstRender = render(<App />);

    await user.click(screen.getByRole("button", { name: "体验 Demo 账户" }));
    expect(await screen.findByRole("heading", { name: "中国股票" })).toBeInTheDocument();

    firstRender.unmount();
    window.history.pushState({ from: "/stocks" }, "", "/login");
    render(<App />);

    expect(await screen.findByRole("heading", { name: "市场概览" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "中国股票" })).not.toBeInTheDocument();
  });

  it("loads protected routes directly on cold start when a valid session is already persisted", () => {
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
    window.history.pushState({}, "", "/stocks");

    render(<App />);

    expect(screen.queryByRole("heading", { name: "欢迎来到 FinanceHub" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "中国股票" })).toBeInTheDocument();
  });

  it("clears persisted session and redirects to login when logging out from the top navigation", async () => {
    window.history.pushState({}, "", "/");
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("button", { name: "退出登录" }));

    expect(window.localStorage.getItem("financehub.session")).toBeNull();
    expect(window.location.pathname).toBe("/login");
    expect(await screen.findByRole("heading", { name: "欢迎来到 FinanceHub" })).toBeInTheDocument();
  });

  it("shows localized login actions after logout and supports switching login copy to English", async () => {
    window.history.pushState({}, "", "/recommendations");
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
    const user = userEvent.setup();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "个性化推荐" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "退出登录" }));

    expect(await screen.findByRole("heading", { name: "欢迎来到 FinanceHub" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "体验 Demo 账户" })).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox"), "en-US");

    expect(await screen.findByRole("heading", { name: "Welcome to FinanceHub" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign In" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try Demo Account" })).toBeInTheDocument();
  });

  it("does not expose a hardcoded English label for login highlights", () => {
    window.history.pushState({}, "", "/login");

    render(<App />);

    expect(screen.queryByRole("region", { name: "Login highlights" })).not.toBeInTheDocument();
  });

  it("does not preload market data while signed out on the login route", () => {
    window.history.pushState({}, "", "/login");

    render(<App />);

    expect(screen.getByRole("heading", { name: "欢迎来到 FinanceHub" })).toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("shows cached market content immediately after app restart before network resolves", () => {
    window.history.pushState({}, "", "/");
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
    window.localStorage.setItem(
      "financehub.market.overview",
      JSON.stringify({
        data: buildCachedOverviewPayload(),
        resource: "overview",
        savedAt: new Date(Date.now() - 60_000).toISOString(),
        version: 1,
      }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/market-overview")) {
          return new Promise<Response>(() => undefined);
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

    render(<App />);

    expect(screen.getByRole("heading", { name: "市场概览" })).toBeInTheDocument();
    expect(screen.getByText("3,880.10")).toBeInTheDocument();
    expect(screen.queryByText("正在加载市场数据")).not.toBeInTheDocument();
  });
});
