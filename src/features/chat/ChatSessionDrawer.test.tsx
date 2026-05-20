import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatStateContext, type ChatStateValue } from "./chat-state";
import { ChatSessionDrawer } from "./ChatSessionDrawer";

function renderDrawerWithSessions(sessions: ChatStateValue["sessions"]) {
  const value: ChatStateValue = {
    activeSessionId: sessions[0]?.id ?? null,
    clearError: vi.fn(),
    closePanel: vi.fn(),
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    error: null,
    isLoadingMessages: false,
    isLoadingSessions: false,
    isOpen: true,
    isStreaming: false,
    messages: [],
    openPanel: vi.fn(),
    sendMessage: vi.fn(),
    sessions,
    streamingContent: "",
    switchSession: vi.fn(),
  };

  return render(
    <ChatStateContext.Provider value={value}>
      <ChatSessionDrawer onClose={vi.fn()} open />
    </ChatStateContext.Provider>,
  );
}

describe("ChatSessionDrawer", () => {
  it("uses generated summaries to distinguish chat history rows", () => {
    renderDrawerWithSessions([
      {
        created_at: "2026-05-18T09:00:00+00:00",
        id: "session-1",
        summary: "分析宁德时代是否值得继续关注",
        title: "New Chat",
        updated_at: "2026-05-18T09:05:00+00:00",
      },
      {
        created_at: "2026-05-18T08:00:00+00:00",
        id: "session-2",
        summary: "比较稳健理财与债券基金配置",
        title: "资产配置讨论",
        updated_at: "2026-05-18T08:15:00+00:00",
      },
      {
        created_at: "2026-05-18T07:00:00+00:00",
        id: "session-3",
        summary: null,
        title: "New Chat",
        updated_at: "2026-05-18T07:00:00+00:00",
      },
    ]);

    const historyRows = screen.getAllByRole("button").filter((button) =>
      button.classList.contains("chat-session-drawer__item"),
    );

    expect(within(historyRows[0]).getByText("分析宁德时代是否值得继续关注")).toBeInTheDocument();
    expect(within(historyRows[1]).getByText("资产配置讨论")).toBeInTheDocument();
    expect(within(historyRows[1]).getByText("比较稳健理财与债券基金配置")).toBeInTheDocument();
    expect(within(historyRows[2]).getByText("New Chat")).toBeInTheDocument();
    expect(within(historyRows[2]).getByText("暂无消息，发送问题后会生成摘要")).toBeInTheDocument();
  });
});
