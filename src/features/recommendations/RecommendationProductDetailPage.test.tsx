import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../../app/App";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      headers: { "Content-Type": "application/json" },
      status,
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

describe("RecommendationProductDetailPage", () => {
  beforeEach(() => {
    const localStorageMock = createStorageMock();
    vi.stubGlobal("localStorage", localStorageMock);
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: localStorageMock,
    });
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/recommendations/products/fund-001")) {
          return jsonResponse({
            asOfDate: "2026-04-09",
            category: "fund",
            chart: [],
            chartLabel: {
              en: "Recent NAV",
              zh: "近期净值",
            },
            code: "A00001",
            drawdownOrVolatility: {
              maxDrawdown: "-0.80%",
            },
            evidence: [
              {
                excerptEn: "The quarterly report shows duration stayed short and credit exposure remained high grade.",
                excerptZh: "季度报告显示组合久期维持偏短，信用持仓继续以高评级资产为主。",
                publishedAt: "2026-04-08",
                sourceTitle: "基金季报（2026Q1）",
                sourceUri: "https://example.com/reports/fund-001-2026q1",
              },
              {
                excerptEn: "Fund manager commentary highlights stable coupon carry strategy.",
                excerptZh: "基金经理月报强调以票息策略为主，目标维持净值平稳。",
                publishedAt: "2026-04-05",
                sourceTitle: "基金经理月报",
                sourceUri: null,
              },
            ],
            fees: {
              managementFee: "0.30%",
            },
            fitForProfile: {
              en: "Fits users who want a steadier bond-fund core.",
              zh: "适合希望先用债券基金打底的稳健型用户。",
            },
            id: "fund-001",
            liquidity: "T+1",
            nameEn: "Zhongou Steady Bond A",
            nameZh: "中欧稳利债券A",
            providerName: "Public bond fund universe",
            recommendationRationale: {
              en: "Selected as a steady bond core with controlled drawdown.",
              zh: "作为稳健债券底仓候选，重点控制回撤。",
            },
            riskLevel: "R2",
            source: "public_bond_fund_refresh",
            stale: false,
            summary: {
              en: "A public bond fund candidate focused on stability and liquidity.",
              zh: "公开债券基金底仓候选，强调稳健与流动性。",
            },
            tagsEn: ["Low drawdown", "Bond core"],
            tagsZh: ["低回撤", "债券底仓"],
            yieldMetrics: {
              annualizedReturn: "3.42%",
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

  it("renders references with linked source titles when sourceUri exists", async () => {
    window.history.pushState({}, "", "/recommendations/products/fund-001");

    render(<App />);

    expect(await screen.findByRole("heading", { level: 2, name: "参考资料" })).toBeInTheDocument();
    expect(screen.getByText("季度报告显示组合久期维持偏短，信用持仓继续以高评级资产为主。")).toBeInTheDocument();
    expect(screen.getByText("基金经理月报强调以票息策略为主，目标维持净值平稳。")).toBeInTheDocument();

    const linkedSource = screen.getByRole("link", { name: "基金季报（2026Q1）" });
    expect(linkedSource).toHaveAttribute("href", "https://example.com/reports/fund-001-2026q1");

    expect(screen.getByText("基金经理月报")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "基金经理月报" })).not.toBeInTheDocument();
  });
});
