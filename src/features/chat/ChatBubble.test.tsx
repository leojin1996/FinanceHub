import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChatBubble } from "./ChatBubble";

describe("ChatBubble", () => {
  it("renders assistant capability replies as structured sections", () => {
    render(
      <ChatBubble
        role="assistant"
        content={`你好，我是FinanceHub智能理财助手。

我可以为你提供这些帮助：
查询大盘与板块行情
分析上市公司基本面
整理市场新闻与情绪`}
      />,
    );

    expect(screen.getByText("你好，我是FinanceHub智能理财助手。")).toBeInTheDocument();

    const section = screen.getByText("我可以为你提供这些帮助").closest("section");
    expect(section).not.toBeNull();
    expect(section).toHaveClass("chat-bubble__section--primary");

    const list = within(section as HTMLElement).getByRole("list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(within(list).getByText("分析上市公司基本面")).toBeInTheDocument();
  });
});
