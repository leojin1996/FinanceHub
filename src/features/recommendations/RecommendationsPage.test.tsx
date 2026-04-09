import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../../app/App";

const dimensionAwareAnswerPattern = [
  2, 2, 2, 2,
  3, 3, 3, 3,
  1, 1, 1, 1,
  3, 3, 3, 3,
  2, 2, 2, 2,
];

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

async function completeQuestionnaire(user: ReturnType<typeof userEvent.setup>) {
  for (const optionIndex of dimensionAwareAnswerPattern) {
    await user.click(screen.getAllByRole("radio")[optionIndex]);
    await user.click(screen.getByRole("button", { name: /下一题|提交|Next|Submit/ }));
  }
}

describe("RecommendationsPage", () => {
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
            executionMode: "rules_fallback",
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
                    asOfDate: "2026-04-09",
                    category: "fund",
                    detailRoute: "/recommendations/products/fund-001",
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
                    asOfDate: "2026-04-09",
                    category: "stock",
                    code: "600036",
                    detailRoute: "/recommendations/products/stock-001",
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
                    asOfDate: "2026-04-09",
                    category: "wealth_management",
                    detailRoute: "/recommendations/products/wm-001",
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
            warnings: [
              {
                code: "llm_config_missing",
                message: "LLM provider is disabled because one or more required env vars are missing.",
                stage: "runtime",
              },
            ],
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

        if (url.endsWith("/api/recommendations/products/fund-001")) {
          return jsonResponse({
            asOfDate: "2026-04-09",
            category: "fund",
            chart: [
              { date: "2026-04-03", value: 1.014 },
              { date: "2026-04-04", value: 1.016 },
              { date: "2026-04-07", value: 1.017 },
              { date: "2026-04-08", value: 1.019 },
              { date: "2026-04-09", value: 1.02 },
            ],
            chartLabel: {
              en: "Recent NAV",
              zh: "近期净值",
            },
            code: "A00001",
            drawdownOrVolatility: {
              maxDrawdown: "-0.80%",
            },
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

  it(
    "shows empty guidance before questionnaire completion and then renders grouped recommendation sections in Chinese",
    async () => {
      window.history.pushState({}, "", "/recommendations");
      const user = userEvent.setup();

      render(<App />);

      expect(screen.getByText("先完成风险评估")).toBeInTheDocument();

      await user.click(screen.getByRole("link", { name: "风险测评" }));
      await completeQuestionnaire(user);
      await user.click(screen.getByRole("link", { name: "推荐" }));

      expect(await screen.findByRole("heading", { name: "适合您的平衡型配置建议", level: 2 })).toBeInTheDocument();
      expect(screen.getByText("当前推荐已回退到规则引擎结果")).toBeInTheDocument();
      expect(
        screen.getByText("由于智能增强暂不可用，当前结果基于规则引擎生成，建议结合自身情况谨慎参考。"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("LLM provider is disabled because one or more required env vars are missing."),
      ).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "基金推荐", level: 2 })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "银行理财推荐", level: 2 })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "股票增强", level: 2 })).toBeInTheDocument();
      expect(screen.getByText("中欧稳利债券A")).toBeInTheDocument();
      expect(screen.getByText("招银理财稳享90天")).toBeInTheDocument();
      expect(screen.getByText("招商银行")).toBeInTheDocument();
      expect(screen.getByText("45%")).toBeInTheDocument();
    },
    15_000,
  );

  it("renders locale-aware empty guidance in en-US", async () => {
    window.history.pushState({}, "", "/recommendations");
    const user = userEvent.setup();

    render(<App />);

    await user.selectOptions(screen.getAllByRole("combobox")[0], "en-US");

    expect(screen.getByRole("heading", { name: "Personalized Recommendations" })).toBeInTheDocument();
    expect(screen.getByText("Complete the risk assessment first")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Finish the questionnaire first and this page will then build a first-pass allocation and product recommendation plan.",
      ),
    ).toBeInTheDocument();
  });

  it("renders English grouped recommendation content after questionnaire completion", async () => {
    window.history.pushState({}, "", "/risk-assessment");
    const user = userEvent.setup();

    render(<App />);

    await user.selectOptions(screen.getAllByRole("combobox")[0], "en-US");
    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "Recommendations" }));

    expect(await screen.findByRole("heading", { name: "A Balanced plan that fits you", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Fund ideas", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Wealth management ideas", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Equity boost", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("Zhongou Steady Bond A")).toBeInTheDocument();
    expect(screen.getByText("CMB Wealth Stable 90D")).toBeInTheDocument();
    expect(screen.getByText("China Merchants Bank")).toBeInTheDocument();
    expect(screen.getByText("Why this plan fits")).toBeInTheDocument();
    expect(screen.getByText("Recommendation currently uses the rules fallback path")).toBeInTheDocument();
    expect(
      screen.getByText(
        "The enhanced recommendation runtime is unavailable right now, so this plan is based on the fallback rules engine.",
      ),
    ).toBeInTheDocument();
  });

  it("opens an in-app product detail page from the recommendation card", async () => {
    window.history.pushState({}, "", "/recommendations");
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("link", { name: "风险测评" }));
    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "推荐" }));
    await screen.findByRole("heading", { name: "适合您的平衡型配置建议", level: 2 });

    await user.click(screen.getAllByRole("link", { name: "查看详情" })[0]);

    expect(await screen.findByRole("heading", { level: 1, name: "中欧稳利债券A" })).toBeInTheDocument();
    expect(screen.getByText("公开债券基金底仓候选，强调稳健与流动性。")).toBeInTheDocument();
    expect(screen.getByText("年化回报")).toBeInTheDocument();
  });

  it("revalidates stale product detail once after the initial cached response", async () => {
    let detailCallCount = 0;
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/recommendations/generate")) {
        return jsonResponse({
          aggressiveOption: null,
          allocationDisplay: { fund: 45, stock: 20, wealthManagement: 35 },
          executionMode: "agent_assisted",
          marketSummary: {
            en: "Market summary",
            zh: "市场摘要",
          },
          profileSummary: {
            en: "Profile summary",
            zh: "画像摘要",
          },
          reviewStatus: "pass",
          riskNotice: { en: [], zh: [] },
          sections: {
            funds: {
              items: [
                {
                  asOfDate: "2026-04-09",
                  category: "fund",
                  detailRoute: "/recommendations/products/fund-001",
                  id: "fund-001",
                  liquidity: "T+1",
                  nameEn: "Zhongou Steady Bond A",
                  nameZh: "中欧稳利债券A",
                  rationaleEn: "Reason",
                  rationaleZh: "理由",
                  riskLevel: "R2",
                  tagsEn: ["Low drawdown"],
                  tagsZh: ["低回撤"],
                },
              ],
              titleEn: "Fund ideas",
              titleZh: "基金推荐",
            },
            stocks: { items: [], titleEn: "Equity boost", titleZh: "股票增强" },
            wealthManagement: { items: [], titleEn: "Wealth management ideas", titleZh: "银行理财推荐" },
          },
          summary: {
            subtitleEn: "Subtitle",
            subtitleZh: "副标题",
            titleEn: "Title",
            titleZh: "标题",
          },
          warnings: [],
          whyThisPlan: { en: [], zh: [] },
        });
      }

      if (url.endsWith("/api/recommendations/products/fund-001")) {
        detailCallCount += 1;
        return jsonResponse({
          asOfDate: "2026-04-09",
          category: "fund",
          chart: [{ date: "2026-04-09", value: 1.02 }],
          chartLabel: { en: "Recent NAV", zh: "近期净值" },
          code: "000001",
          drawdownOrVolatility: {},
          fees: {},
          fitForProfile: {
            en: "Fits stable users.",
            zh: "适合稳健型用户。",
          },
          id: "fund-001",
          liquidity: "T+1",
          nameEn: "Zhongou Steady Bond A",
          nameZh: "中欧稳利债券A",
          providerName: "Test provider",
          recommendationRationale: {
            en: "Reason",
            zh: "理由",
          },
          riskLevel: "R2",
          source: "test_detail_source",
          stale: detailCallCount === 1,
          summary:
            detailCallCount === 1
              ? {
                  en: "Cached detail summary.",
                  zh: "缓存详情摘要。",
                }
              : {
                  en: "Fresh detail summary.",
                  zh: "刷新后的详情摘要。",
                },
          tagsEn: ["Low drawdown"],
          tagsZh: ["低回撤"],
          yieldMetrics: {},
        });
      }

      throw new Error(`Unhandled fetch for ${url}`);
    });

    window.history.pushState({}, "", "/recommendations");
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("link", { name: "风险测评" }));
    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "推荐" }));
    await screen.findByRole("heading", { name: "标题", level: 2 });

    await user.click(screen.getAllByRole("link", { name: "查看详情" })[0]);

    expect(await screen.findByText("刷新后的详情摘要。")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([input]) =>
          String(input).endsWith("/api/recommendations/products/fund-001"),
        ),
      ).toHaveLength(2);
    });
  });

  it("posts the full risk assessment payload to the generate endpoint", async () => {
    window.history.pushState({}, "", "/risk-assessment");
    const user = userEvent.setup();

    render(<App />);

    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "推荐" }));
    await screen.findByRole("heading", { name: "适合您的平衡型配置建议", level: 2 });

    const fetchMock = vi.mocked(fetch);
    const recommendationCall = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/recommendations/generate"),
    );

    expect(recommendationCall).toBeDefined();
    const requestInit = recommendationCall?.[1];
    const body = JSON.parse(String(requestInit?.body)) as {
      historicalHoldings: unknown[];
      historicalTransactions: unknown[];
      includeAggressiveOption: boolean;
      questionnaireAnswers: unknown[];
      riskAssessmentResult: {
        baseProfile: string;
        dimensionLevels: Record<string, string>;
        dimensionScores: Record<string, number>;
        finalProfile: string;
        totalScore: number;
      };
    };
    expect(body.includeAggressiveOption).toBe(true);
    expect(body.questionnaireAnswers).toEqual([]);
    expect(body.historicalHoldings).toEqual([]);
    expect(body.historicalTransactions).toEqual([]);
    expect(body.riskAssessmentResult).toEqual({
      baseProfile: "balanced",
      dimensionLevels: {
        capitalStability: "mediumLow",
        investmentExperience: "mediumHigh",
        investmentHorizon: "mediumHigh",
        returnObjective: "medium",
        riskTolerance: "medium",
      },
      dimensionScores: {
        capitalStability: 8,
        investmentExperience: 16,
        investmentHorizon: 16,
        returnObjective: 12,
        riskTolerance: 12,
      },
      finalProfile: "balanced",
      totalScore: 64,
    });
  });
});
