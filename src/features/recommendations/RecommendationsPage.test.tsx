import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../../app/App";
import { questionnaire } from "../../mock/questionnaire";

const dimensionAwareAnswerPattern = [
  2, 2, 2, 2,
  3, 3, 3, 3,
  1, 1, 1, 1,
  3, 3, 3, 3,
  2, 2, 2, 2,
];
const conservativeAnswerPattern = new Array(questionnaire.length).fill(0);
const RECOMMENDATIONS_FLOW_TIMEOUT_MS = 30_000;

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

async function completeQuestionnaireWithPattern(
  user: ReturnType<typeof userEvent.setup>,
  answerPattern: number[],
) {
  for (const optionIndex of answerPattern) {
    await user.click(screen.getAllByRole("radio")[optionIndex]);
    await user.click(screen.getByRole("button", { name: /下一题|提交|Next|Submit/ }));
  }
}

async function completeQuestionnaire(user: ReturnType<typeof userEvent.setup>) {
  await completeQuestionnaireWithPattern(user, dimensionAwareAnswerPattern);
}

describe("RecommendationsPage", () => {
  let recommendationRequests: unknown[];

  beforeEach(() => {
    recommendationRequests = [];
    const localStorageMock = createStorageMock();
    vi.stubGlobal("localStorage", localStorageMock);
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: localStorageMock,
    });
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);

        if (url.endsWith("/api/recommendations/generate")) {
          recommendationRequests.push(JSON.parse(String(init?.body ?? "{}")));
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
                    evidencePreview: [
                      {
                        asOfDate: "2026-04-08",
                        docType: "fund_quarterly_report",
                        evidenceId: "ev-fund-001",
                        excerpt: "持仓继续以高等级债券为主，回撤区间控制在较低水平。",
                        excerptLanguage: "zh-CN",
                        pageNumber: 3,
                        sectionTitle: "资产组合分析",
                        sourceTitle: "基金季报（2026Q1）",
                        sourceUri: "https://example.com/reports/fund-001-2026q1",
                      },
                    ],
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
                    evidencePreview: [
                      {
                        asOfDate: "2026-04-07",
                        docType: "company_announcement",
                        evidenceId: "ev-stock-001",
                        excerpt: "季度利润保持韧性，同时拨备策略延续审慎。",
                        excerptLanguage: "zh-CN",
                        pageNumber: null,
                        sectionTitle: "经营情况摘要",
                        sourceTitle: "公司公告摘要",
                        sourceUri: "javascript:alert('xss')",
                      },
                    ],
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
                    evidencePreview: [],
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

      const fundEvidencePreview = screen.getByTestId("recommendation-evidence-preview-fund-001");
      expect(within(fundEvidencePreview).getByText("持仓继续以高等级债券为主，回撤区间控制在较低水平。")).toBeInTheDocument();
      expect(within(fundEvidencePreview).getByRole("link", { name: "基金季报（2026Q1）" })).toHaveAttribute(
        "href",
        "https://example.com/reports/fund-001-2026q1",
      );

      const stockEvidencePreview = screen.getByTestId("recommendation-evidence-preview-stock-001");
      expect(within(stockEvidencePreview).getByText("季度利润保持韧性，同时拨备策略延续审慎。")).toBeInTheDocument();
      expect(within(stockEvidencePreview).getByText("公司公告摘要")).toBeInTheDocument();
      expect(within(stockEvidencePreview).queryByRole("link", { name: "公司公告摘要" })).not.toBeInTheDocument();
    },
    RECOMMENDATIONS_FLOW_TIMEOUT_MS,
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
  }, RECOMMENDATIONS_FLOW_TIMEOUT_MS);

  it("sends questionnaire answers and web locale context to recommendation generation", async () => {
    window.history.pushState({}, "", "/risk-assessment");
    const user = userEvent.setup();

    render(<App />);

    await user.selectOptions(screen.getAllByRole("combobox")[0], "en-US");
    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "Recommendations" }));
    await screen.findByRole("heading", { name: "A Balanced plan that fits you", level: 2 });

    expect(recommendationRequests).toHaveLength(1);
    expect(recommendationRequests[0]).toMatchObject({
      clientContext: {
        channel: "web",
        locale: "en-US",
      },
      historicalHoldings: [],
      historicalTransactions: [],
      questionnaireAnswers: questionnaire.map((question, index) => ({
        answerId: String(dimensionAwareAnswerPattern[index] + 1),
        dimension: question.dimension,
        questionId: String(question.id),
        score: dimensionAwareAnswerPattern[index] + 1,
      })),
    });
  }, RECOMMENDATIONS_FLOW_TIMEOUT_MS);

  it("shows a partial degradation banner when only some AI stages fall back", async () => {
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
            funds: { items: [], titleEn: "Fund ideas", titleZh: "基金推荐" },
            stocks: { items: [], titleEn: "Equity boost", titleZh: "股票增强" },
            wealthManagement: {
              items: [],
              titleEn: "Wealth management ideas",
              titleZh: "银行理财推荐",
            },
          },
          summary: {
            subtitleEn: "Subtitle",
            subtitleZh: "副标题",
            titleEn: "Title",
            titleZh: "标题",
          },
          warnings: [
            {
              code: "agent_fund_selection_failed",
              message: "基金智能排序暂时不可用，已自动回退到默认候选顺序。",
              stage: "product_match_expert",
            },
          ],
          whyThisPlan: { en: [], zh: [] },
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

    expect(await screen.findByRole("heading", { name: "标题", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("部分 AI 分析已自动降级处理")).toBeInTheDocument();
    expect(
      screen.getByText("部分 AI 分析阶段暂时不可用，系统已对受影响步骤自动回退到默认逻辑，当前推荐仍可正常参考。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("基金智能排序暂时不可用，已自动回退到默认候选顺序。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("当前推荐已回退到规则引擎结果")).not.toBeInTheDocument();
  }, RECOMMENDATIONS_FLOW_TIMEOUT_MS);

  it("renders a compact AI trace when tool calls are returned", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/recommendations/generate")) {
        return jsonResponse({
          aggressiveOption: null,
          agentTrace: [
            {
              nodeName: "profile_analysis",
              providerName: "openai",
              requestName: "user_profile_analyst",
              status: "finish",
              toolCalls: [
                {
                  arguments: { profile: "balanced" },
                  result: { score: 0.71 },
                  toolName: "profile_intelligence_score",
                },
              ],
            },
            {
              nodeName: "market_analysis",
              providerName: "openai",
              requestName: "market_intelligence",
              status: "finish",
              toolCalls: [
                {
                  arguments: { market: "cn" },
                  result: { summary: "steady" },
                  toolName: "market_snapshot",
                },
                {
                  arguments: { limit: 3 },
                  result: { count: 3 },
                  toolName: "candidate_ranker",
                },
              ],
            },
          ],
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
            funds: { items: [], titleEn: "Fund ideas", titleZh: "基金推荐" },
            stocks: { items: [], titleEn: "Equity boost", titleZh: "股票增强" },
            wealthManagement: {
              items: [],
              titleEn: "Wealth management ideas",
              titleZh: "银行理财推荐",
            },
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

      throw new Error(`Unhandled fetch for ${url}`);
    });

    window.history.pushState({}, "", "/recommendations");
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("link", { name: "风险测评" }));
    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "推荐" }));

    expect(await screen.findByRole("heading", { name: "标题", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("AI 分析足迹")).toBeInTheDocument();
    expect(screen.getByText("已记录 2 个阶段，3 次工具调用。")).toBeInTheDocument();
    expect(screen.getByText("画像分析")).toBeInTheDocument();
    expect(screen.getByText("市场研判")).toBeInTheDocument();
    expect(screen.getByText("profile_intelligence_score")).toBeInTheDocument();
    expect(screen.getByText("market_snapshot")).toBeInTheDocument();
    expect(screen.getByText("candidate_ranker")).toBeInTheDocument();
  }, RECOMMENDATIONS_FLOW_TIMEOUT_MS);

  it("ignores incomplete agent trace events without crashing the page", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/recommendations/generate")) {
        return jsonResponse({
          aggressiveOption: null,
          agentTrace: [
            {
              nodeName: "profile_analysis",
              requestName: "user_profile_analyst",
              status: "finish",
            },
            {
              nodeName: "market_analysis",
              requestName: "market_intelligence",
              status: "finish",
              toolCalls: null,
            },
          ],
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
            funds: { items: [], titleEn: "Fund ideas", titleZh: "基金推荐" },
            stocks: { items: [], titleEn: "Equity boost", titleZh: "股票增强" },
            wealthManagement: {
              items: [],
              titleEn: "Wealth management ideas",
              titleZh: "银行理财推荐",
            },
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

      throw new Error(`Unhandled fetch for ${url}`);
    });

    window.history.pushState({}, "", "/recommendations");
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("link", { name: "风险测评" }));
    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "推荐" }));

    expect(await screen.findByRole("heading", { name: "标题", level: 2 })).toBeInTheDocument();
    expect(screen.queryByText("AI 分析足迹")).not.toBeInTheDocument();
  }, RECOMMENDATIONS_FLOW_TIMEOUT_MS);

  it("hides empty recommendation sections when a category has no products", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/recommendations/generate")) {
        return jsonResponse({
          aggressiveOption: null,
          allocationDisplay: { fund: 100, stock: 0, wealthManagement: 0 },
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
            wealthManagement: {
              items: [],
              titleEn: "Wealth management ideas",
              titleZh: "银行理财推荐",
            },
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

      throw new Error(`Unhandled fetch for ${url}`);
    });

    window.history.pushState({}, "", "/recommendations");
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("link", { name: "风险测评" }));
    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "推荐" }));

    expect(await screen.findByRole("heading", { name: "标题", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "基金推荐", level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "银行理财推荐", level: 2 })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "股票增强", level: 2 })).not.toBeInTheDocument();
  }, RECOMMENDATIONS_FLOW_TIMEOUT_MS);

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
  }, RECOMMENDATIONS_FLOW_TIMEOUT_MS);

  it("reuses the cached recommendation after returning from product detail", async () => {
    window.history.pushState({}, "", "/recommendations");
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("link", { name: "风险测评" }));
    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "推荐" }));
    await screen.findByRole("heading", { name: "适合您的平衡型配置建议", level: 2 });

    const fetchMock = vi.mocked(fetch);
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/api/recommendations/generate"),
      ),
    ).toHaveLength(1);

    await user.click(screen.getAllByRole("link", { name: "查看详情" })[0]);
    expect(await screen.findByRole("heading", { level: 1, name: "中欧稳利债券A" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "返回推荐页" }));
    expect(await screen.findByRole("heading", { name: "适合您的平衡型配置建议", level: 2 })).toBeInTheDocument();

    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/api/recommendations/generate"),
      ),
    ).toHaveLength(1);
  }, RECOMMENDATIONS_FLOW_TIMEOUT_MS);

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
  }, RECOMMENDATIONS_FLOW_TIMEOUT_MS);

  it("invalidates the recommendation cache when locale changes", async () => {
    window.history.pushState({}, "", "/risk-assessment");
    const user = userEvent.setup();

    render(<App />);

    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "推荐" }));
    await screen.findByRole("heading", { name: "适合您的平衡型配置建议", level: 2 });

    const fetchMock = vi.mocked(fetch);
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/api/recommendations/generate"),
      ),
    ).toHaveLength(1);

    await user.selectOptions(screen.getAllByRole("combobox")[0], "en-US");
    await screen.findByRole("heading", { name: "A Balanced plan that fits you", level: 2 });

    expect(
      fetchMock.mock.calls.filter(([input, init]) =>
        String(input).endsWith("/api/recommendations/generate") &&
        JSON.parse(String(init?.body ?? "{}")).clientContext?.locale === "en-US",
      ),
    ).toHaveLength(1);
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/api/recommendations/generate"),
      ),
    ).toHaveLength(2);
  });

  it("invalidates the recommendation cache when the assessment result changes", async () => {
    window.history.pushState({}, "", "/risk-assessment");
    const user = userEvent.setup();

    render(<App />);

    await completeQuestionnaire(user);
    await user.click(screen.getByRole("link", { name: "推荐" }));
    await screen.findByRole("heading", { name: "适合您的平衡型配置建议", level: 2 });

    const fetchMock = vi.mocked(fetch);
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/api/recommendations/generate"),
      ),
    ).toHaveLength(1);

    await user.click(screen.getByRole("link", { name: "风险测评" }));
    await completeQuestionnaireWithPattern(user, conservativeAnswerPattern);
    await user.click(screen.getByRole("link", { name: "推荐" }));
    await screen.findByRole("heading", { name: "适合您的平衡型配置建议", level: 2 });

    expect(
      fetchMock.mock.calls.filter(([input, init]) => {
        if (!String(input).endsWith("/api/recommendations/generate")) {
          return false;
        }
        const payload = JSON.parse(String(init?.body ?? "{}")) as {
          riskAssessmentResult?: { finalProfile?: string };
        };
        return payload.riskAssessmentResult?.finalProfile === "conservative";
      }),
    ).toHaveLength(1);
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).endsWith("/api/recommendations/generate"),
      ),
    ).toHaveLength(2);
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
      clientContext: {
        channel: string;
        locale: string;
      };
      historicalHoldings: unknown[];
      historicalTransactions: unknown[];
      includeAggressiveOption: boolean;
      questionnaireAnswers: Array<{
        answerId: string;
        dimension: string;
        questionId: string;
        score: number;
      }>;
      riskAssessmentResult: {
        baseProfile: string;
        dimensionLevels: Record<string, string>;
        dimensionScores: Record<string, number>;
        finalProfile: string;
        totalScore: number;
      };
    };
    expect(body.clientContext).toEqual({
      channel: "web",
      locale: "zh-CN",
    });
    expect(body.includeAggressiveOption).toBe(true);
    expect(body.questionnaireAnswers).toEqual(
      questionnaire.map((question, index) => ({
        answerId: String(dimensionAwareAnswerPattern[index] + 1),
        dimension: question.dimension,
        questionId: String(question.id),
        score: dimensionAwareAnswerPattern[index] + 1,
      })),
    );
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
