import { describe, expect, it } from "vitest";

import { formatAssistantContent, stripAssistantMarkdownMarkers } from "./formatAssistantContent";

describe("stripAssistantMarkdownMarkers", () => {
  it("unwraps paired ** markers", () => {
    expect(stripAssistantMarkdownMarkers("**上证指数** +0.1%")).toBe("上证指数 +0.1%");
  });

  it("removes stray **", () => {
    expect(stripAssistantMarkdownMarkers("截至 2026-04-13: **")).toBe("截至 2026-04-13: ");
  });
});

describe("formatAssistantContent", () => {
  it("turns capability introductions into readable sections and lists", () => {
    const blocks = formatAssistantContent(`你好，我是FinanceHub智能理财助手，专注于中国A股市场。

我可以为你提供这些帮助：
查询大盘与板块行情，梳理市场强弱与热点方向
查询个股信息，包括代码、价格、涨跌情况等
分析上市公司基本面，如盈利能力、成长性、估值与同行对比
整理最新消息面、新闻面与市场情绪
根据你的风险偏好，提供投资建议参考

我会尽量用简洁、准确、专业的方式回答你的问题。

如果你愿意，现在就可以告诉我你想看：
今日A股市场情况
某只股票值不值得关注
某个行业最近有哪些消息
适合你的投资风格与配置建议`);

    expect(blocks).toEqual([
      {
        kind: "paragraph",
        text: "你好，我是FinanceHub智能理财助手，专注于中国A股市场。",
      },
      {
        heading: "我可以为你提供这些帮助",
        items: [
          "查询大盘与板块行情，梳理市场强弱与热点方向",
          "查询个股信息，包括代码、价格、涨跌情况等",
          "分析上市公司基本面，如盈利能力、成长性、估值与同行对比",
          "整理最新消息面、新闻面与市场情绪",
          "根据你的风险偏好，提供投资建议参考",
        ],
        kind: "list",
        tone: "primary",
      },
      {
        kind: "paragraph",
        text: "我会尽量用简洁、准确、专业的方式回答你的问题。",
      },
      {
        heading: "如果你愿意，现在就可以告诉我你想看",
        items: [
          "今日A股市场情况",
          "某只股票值不值得关注",
          "某个行业最近有哪些消息",
          "适合你的投资风格与配置建议",
        ],
        kind: "list",
        tone: "secondary",
      },
    ]);
  });

  it("keeps ordinary prose as a paragraph after removing markdown markers", () => {
    expect(formatAssistantContent("**上证指数** 今日小幅上涨。")).toEqual([
      { kind: "paragraph", text: "上证指数 今日小幅上涨。" },
    ]);
  });
});
