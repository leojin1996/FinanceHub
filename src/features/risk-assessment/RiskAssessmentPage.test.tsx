import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, vi } from "vitest";

import App from "../../app/App";

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

describe("RiskAssessmentPage", () => {
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
      vi.fn(() => new Promise<Response>(() => undefined)),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it(
    "completes the twenty-question flow and shows profile, diagnostics, and narrative",
    async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("link", { name: "风险测评" }));

    for (let index = 0; index < 20; index += 1) {
      await user.click(screen.getAllByRole("radio")[2]);
      await user.click(screen.getByRole("button", { name: /下一题|提交/ }));
    }

    expect(screen.getByText("你的风险类型")).toBeInTheDocument();
    expect(screen.getByText("风险承受度")).toBeInTheDocument();
    expect(screen.getByText("资金稳定性")).toBeInTheDocument();
    expect(screen.getByText(/你的风险承受能力与收益目标/)).toBeInTheDocument();
    },
    15_000,
  );

  it("renders locale-aware questionnaire copy in en-US", async () => {
    window.history.pushState({}, "", "/risk-assessment");
    const user = userEvent.setup();

    render(<App />);

    await user.selectOptions(screen.getByRole("combobox"), "en-US");

    expect(screen.getByRole("heading", { name: "Risk Assessment" })).toBeInTheDocument();
    expect(screen.getByText("Question 1 of 20")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
  });

  it("advances only one step when the next button is double-clicked", async () => {
    window.history.pushState({}, "", "/risk-assessment");
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getAllByRole("radio")[2]);
    await user.dblClick(screen.getByRole("button", { name: "下一题" }));

    expect(screen.getByText("第 2 / 20 题")).toBeInTheDocument();
    expect(screen.queryByText("第 3 / 20 题")).not.toBeInTheDocument();
  });
});
