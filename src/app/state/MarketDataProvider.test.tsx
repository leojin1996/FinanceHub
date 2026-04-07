import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  IndicesResponse,
  MarketOverviewResponse,
  StocksResponse,
} from "../../services/chinaMarketApi";
import {
  fetchIndices,
  fetchMarketOverview,
  fetchStocks,
} from "../../services/chinaMarketApi";
import { AppStateProvider } from "./AppStateProvider";

import { MarketDataProvider } from "./MarketDataProvider";
import { useMarketData } from "./market-data";

vi.mock("../../services/chinaMarketApi", () => ({
  fetchIndices: vi.fn(),
  fetchMarketOverview: vi.fn(),
  fetchStocks: vi.fn(),
}));

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
}

function createDeferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => undefined;
  let reject: (reason?: unknown) => void = () => undefined;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });

  return { promise, resolve, reject };
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

function buildOverview(metricValue: string): MarketOverviewResponse {
  return {
    asOfDate: "2026-04-03",
    chartLabel: "上证指数近10个交易日",
    stale: false,
    metrics: [
      {
        label: "上证指数",
        value: metricValue,
        delta: "+0.38%",
        changeValue: 12.24,
        changePercent: 0.38,
        tone: "positive",
      },
    ],
    trendSeries: [{ date: "2026-04-03", value: 3245.55 }],
    topGainers: [],
    topLosers: [],
  };
}

function buildIndices(): IndicesResponse {
  return {
    asOfDate: "2026-04-03",
    stale: false,
    cards: [],
  };
}

function buildStocks(): StocksResponse {
  return {
    asOfDate: "2026-04-03",
    stale: false,
    rows: [],
  };
}

function OverviewProbe() {
  const marketData = useMarketData();
  const entry = marketData.overview;

  return (
    <div>
      <span data-testid="resource-source">{entry.source ?? "none"}</span>
      <span data-testid="resource-load-status">{entry.loadStatus}</span>
      <span data-testid="resource-refresh-status">{entry.refreshStatus}</span>
      <span data-testid="resource-value">{entry.data?.metrics?.[0]?.value ?? "none"}</span>
    </div>
  );
}

function IndicesProbe() {
  const marketData = useMarketData();
  const entry = marketData.indices;

  return (
    <div>
      <span data-testid="indices-source">{entry.source ?? "none"}</span>
      <span data-testid="indices-load-status">{entry.loadStatus}</span>
      <span data-testid="indices-refresh-status">{entry.refreshStatus}</span>
    </div>
  );
}

function renderWithProviders(children: ReactNode) {
  return render(
    <AppStateProvider>
      <MarketDataProvider>{children}</MarketDataProvider>
    </AppStateProvider>,
  );
}

describe("MarketDataProvider", () => {
  beforeEach(() => {
    const localStorageMock = createStorageMock();
    vi.stubGlobal("localStorage", localStorageMock);
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: localStorageMock,
    });
    window.localStorage.clear();
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));

    vi.mocked(fetchIndices).mockResolvedValue(buildIndices());
    vi.mocked(fetchStocks).mockResolvedValue(buildStocks());
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("hydrates overview data from localStorage before network refresh resolves", async () => {
    const savedAt = new Date(Date.now() - 60_000).toISOString();
    window.localStorage.setItem(
      "financehub.market.overview",
      JSON.stringify({
        data: buildOverview("3,880.10"),
        resource: "overview",
        savedAt,
        version: 1,
      }),
    );

    const overviewDeferred = createDeferred<MarketOverviewResponse>();
    vi.mocked(fetchMarketOverview).mockReturnValue(overviewDeferred.promise);

    renderWithProviders(<OverviewProbe />);

    expect(screen.getByTestId("resource-source")).toHaveTextContent("storage");
    expect(screen.getByTestId("resource-load-status")).toHaveTextContent("ready");
    expect(screen.getByTestId("resource-refresh-status")).toHaveTextContent("refreshing");
    expect(screen.getByTestId("resource-value")).toHaveTextContent("3,880.10");

    await waitFor(() => {
      expect(fetchMarketOverview).toHaveBeenCalledTimes(1);
      expect(fetchIndices).toHaveBeenCalledTimes(1);
      expect(fetchStocks).toHaveBeenCalledTimes(1);
    });

    overviewDeferred.resolve(buildOverview("3,920.00"));

    await waitFor(() => {
      expect(screen.getByTestId("resource-source")).toHaveTextContent("network");
      expect(screen.getByTestId("resource-refresh-status")).toHaveTextContent("idle");
      expect(screen.getByTestId("resource-value")).toHaveTextContent("3,920.00");
    });
  });

  it("drops expired local snapshots and waits for network data", async () => {
    const savedAt = new Date(Date.now() - 15 * 24 * 60 * 60 * 1000).toISOString();
    window.localStorage.setItem(
      "financehub.market.overview",
      JSON.stringify({
        data: buildOverview("3,100.00"),
        resource: "overview",
        savedAt,
        version: 1,
      }),
    );

    vi.mocked(fetchMarketOverview).mockResolvedValue(buildOverview("3,245.55"));

    renderWithProviders(<OverviewProbe />);

    expect(screen.getByTestId("resource-source")).toHaveTextContent("none");
    expect(screen.getByTestId("resource-load-status")).toHaveTextContent("loading");
    expect(screen.getByTestId("resource-value")).toHaveTextContent("none");

    await waitFor(() => {
      expect(screen.getByTestId("resource-source")).toHaveTextContent("network");
      expect(screen.getByTestId("resource-load-status")).toHaveTextContent("ready");
      expect(screen.getByTestId("resource-value")).toHaveTextContent("3,245.55");
    });
  });

  it("ignores stale refresh responses from a discarded provider lifecycle", async () => {
    const firstOverviewRequest = createDeferred<MarketOverviewResponse>();
    const secondOverviewRequest = createDeferred<MarketOverviewResponse>();
    vi.mocked(fetchMarketOverview)
      .mockReturnValueOnce(firstOverviewRequest.promise)
      .mockReturnValueOnce(secondOverviewRequest.promise);

    const firstRender = renderWithProviders(<OverviewProbe />);
    firstRender.unmount();

    renderWithProviders(<OverviewProbe />);

    secondOverviewRequest.resolve(buildOverview("3,920.00"));
    await waitFor(() => {
      expect(screen.getByTestId("resource-source")).toHaveTextContent("network");
      expect(screen.getByTestId("resource-value")).toHaveTextContent("3,920.00");
    });

    firstOverviewRequest.resolve(buildOverview("3,100.00"));
    await waitFor(() => {
      const rawOverview = window.localStorage.getItem("financehub.market.overview");
      expect(rawOverview).not.toBeNull();
      const parsedOverview = JSON.parse(rawOverview as string) as {
        data: { metrics: Array<{ value: string }> };
      };
      expect(parsedOverview.data.metrics[0]?.value).toBe("3,920.00");
    });
  });

  it("rejects malformed nested overview cache payloads", async () => {
    const savedAt = new Date(Date.now() - 60_000).toISOString();
    window.localStorage.setItem(
      "financehub.market.overview",
      JSON.stringify({
        data: {
          ...buildOverview("3,500.00"),
          metrics: [
            {
              label: "上证指数",
              value: 3500,
            },
          ],
        },
        resource: "overview",
        savedAt,
        version: 1,
      }),
    );

    const overviewDeferred = createDeferred<MarketOverviewResponse>();
    vi.mocked(fetchMarketOverview).mockReturnValue(overviewDeferred.promise);

    renderWithProviders(<OverviewProbe />);

    expect(screen.getByTestId("resource-source")).toHaveTextContent("none");
    expect(screen.getByTestId("resource-load-status")).toHaveTextContent("loading");
    expect(screen.getByTestId("resource-value")).toHaveTextContent("none");

    overviewDeferred.resolve(buildOverview("3,245.55"));
    await waitFor(() => {
      expect(screen.getByTestId("resource-source")).toHaveTextContent("network");
      expect(screen.getByTestId("resource-value")).toHaveTextContent("3,245.55");
    });
  });

  it("rejects malformed network overview payloads and does not persist them", async () => {
    vi.mocked(fetchMarketOverview).mockResolvedValue({
      ...buildOverview("3,245.55"),
      metrics: [{ label: "上证指数", value: 3245.55 }] as unknown as MarketOverviewResponse["metrics"],
    });

    renderWithProviders(<OverviewProbe />);

    await waitFor(() => {
      expect(screen.getByTestId("resource-load-status")).toHaveTextContent("error");
      expect(screen.getByTestId("resource-refresh-status")).toHaveTextContent("failed");
      expect(screen.getByTestId("resource-source")).toHaveTextContent("none");
      expect(screen.getByTestId("resource-value")).toHaveTextContent("none");
    });

    expect(window.localStorage.getItem("financehub.market.overview")).toBeNull();
  });

  it("rejects malformed network indices payloads", async () => {
    vi.mocked(fetchIndices).mockResolvedValue({
      ...buildIndices(),
      cards: [{ name: "上证指数" }],
    } as unknown as IndicesResponse);
    vi.mocked(fetchMarketOverview).mockResolvedValue(buildOverview("3,245.55"));

    renderWithProviders(
      <>
        <OverviewProbe />
        <IndicesProbe />
      </>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("indices-load-status")).toHaveTextContent("error");
      expect(screen.getByTestId("indices-refresh-status")).toHaveTextContent("failed");
      expect(screen.getByTestId("indices-source")).toHaveTextContent("none");
    });

    expect(window.localStorage.getItem("financehub.market.indices")).toBeNull();
  });
});
