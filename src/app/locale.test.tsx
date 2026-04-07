import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, vi } from "vitest";

import App from "./App";
import { getMessages } from "../i18n/messages";
import { useAppState } from "./state/app-state";
import { AppStateProvider } from "./state/AppStateProvider";

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

describe("App localization", () => {
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

  it("defaults to Simplified Chinese on first load", () => {
    window.history.pushState({}, "", "/");

    render(<App />);

    const primaryNav = screen.getByRole("navigation", { name: "主导航" });
    expect(within(primaryNav).getByRole("link", { name: "市场" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "市场概览" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "退出登录" })).toBeInTheDocument();
  });

  it("switches shell labels to English", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();

    render(<App />);

    await user.selectOptions(screen.getByRole("combobox"), "en-US");

    const primaryNav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(primaryNav).getByRole("link", { name: "Market" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Market Overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Logout" })).toBeInTheDocument();
  });

  it("falls back to zh-CN when an unknown locale is requested", () => {
    const messages = getMessages("fr-FR");

    expect(messages.topStatus.workspaceLabel).toBe("中国市场工作区");
    expect(messages.nav.overview.title).toBe("市场概览");
  });

  it("keeps the shell usable after changing locales multiple times", async () => {
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();

    render(<App />);

    await user.selectOptions(screen.getByRole("combobox"), "en-US");
    await user.selectOptions(screen.getByRole("combobox"), "zh-CN");

    const primaryNav = screen.getByRole("navigation", { name: "主导航" });
    expect(within(primaryNav).getByRole("link", { name: "市场" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "市场概览" })).toBeInTheDocument();
  });

  it("shows the expanded questionnaire progress in English", async () => {
    window.history.pushState({}, "", "/risk-assessment");
    const user = userEvent.setup();

    render(<App />);

    await user.selectOptions(screen.getByRole("combobox"), "en-US");

    expect(screen.getByText("Question 1 of 20")).toBeInTheDocument();
  });

  it("degrades to signed-out when storage is unavailable", () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("storage unavailable");
      },
    });

    window.history.pushState({}, "", "/");

    expect(() => render(<App />)).not.toThrow();
    expect(screen.getByRole("heading", { name: "欢迎来到 FinanceHub" })).toBeInTheDocument();
  });

  it("hydrates persisted session synchronously for first render", () => {
    let firstRenderEmail: string | null | undefined;

    function SessionProbe() {
      const { session } = useAppState();
      if (firstRenderEmail === undefined) {
        firstRenderEmail = session?.email ?? null;
      }
      return null;
    }

    render(
      <AppStateProvider>
        <SessionProbe />
      </AppStateProvider>,
    );

    expect(firstRenderEmail).toBe("demo@financehub.com");
  });
});
