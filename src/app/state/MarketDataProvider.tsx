import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import {
  fetchIndices,
  fetchMarketOverview,
  fetchStocks,
  type IndicesResponse,
  type MarketOverviewResponse,
  type StocksResponse,
} from "../../services/chinaMarketApi";
import {
  createInitialMarketDataState,
  MarketDataContext,
  type MarketDataState,
  type MarketResourceKey,
  persistResourceSnapshot,
  validateResourcePayload,
} from "./market-data";
import { useAppState } from "./app-state";

interface MarketDataProviderProps {
  children: ReactNode;
}

function readErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "request failed";
}

export function MarketDataProvider({ children }: MarketDataProviderProps) {
  const { session } = useAppState();
  const [state, setState] = useState<MarketDataState>(() => createInitialMarketDataState());
  const isMountedRef = useRef(true);
  const refreshedSessionEmailRef = useRef<string | null>(null);
  const requestVersionRef = useRef<Record<MarketResourceKey, number>>({
    indices: 0,
    overview: 0,
    stocks: 0,
  });

  const refreshResource = useCallback(
    async <T,>(resource: MarketResourceKey, loader: () => Promise<T>) => {
      const requestVersion = requestVersionRef.current[resource] + 1;
      requestVersionRef.current[resource] = requestVersion;

      setState((previousState) => {
        const previousResource = previousState[resource];
        const hasData = previousResource.data !== null;

        return {
          ...previousState,
          [resource]: {
            ...previousResource,
            error: null,
            loadStatus: hasData ? "ready" : "loading",
            refreshStatus: "refreshing",
          },
        };
      });

      try {
        const payload = await loader();

        if (
          !isMountedRef.current ||
          requestVersionRef.current[resource] !== requestVersion
        ) {
          return;
        }

        if (!validateResourcePayload(resource, payload)) {
          throw new Error(`invalid ${resource} payload`);
        }

        const data = payload;

        persistResourceSnapshot(resource, data);

        setState((previousState) => ({
          ...previousState,
          [resource]: {
            data,
            error: null,
            lastHydratedAt: new Date().toISOString(),
            loadStatus: "ready",
            refreshStatus: "idle",
            source: "network",
          },
        }));
      } catch (error) {
        if (
          !isMountedRef.current ||
          requestVersionRef.current[resource] !== requestVersion
        ) {
          return;
        }

        const message = readErrorMessage(error);
        setState((previousState) => {
          const previousResource = previousState[resource];
          const hasData = previousResource.data !== null;

          return {
            ...previousState,
            [resource]: {
              ...previousResource,
              error: message,
              loadStatus: hasData ? "ready" : "error",
              refreshStatus: "failed",
            },
          };
        });
      }
    },
    [],
  );

  useEffect(() => {
    isMountedRef.current = true;

    if (!session?.email) {
      refreshedSessionEmailRef.current = null;
      return () => {
        isMountedRef.current = false;
      };
    }

    if (refreshedSessionEmailRef.current === session.email) {
      return () => {
        isMountedRef.current = false;
      };
    }

    refreshedSessionEmailRef.current = session.email;

    void refreshResource<MarketOverviewResponse>("overview", () => fetchMarketOverview());
    void refreshResource<IndicesResponse>("indices", () => fetchIndices());
    void refreshResource<StocksResponse>("stocks", () => fetchStocks());

    return () => {
      isMountedRef.current = false;
    };
  }, [refreshResource, session?.email]);

  return <MarketDataContext.Provider value={state}>{children}</MarketDataContext.Provider>;
}
