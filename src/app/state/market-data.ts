import { createContext, useContext } from "react";
import type {
  IndicesResponse,
  MarketOverviewResponse,
  StocksResponse,
} from "../../services/chinaMarketApi";

export type MarketResourceKey = "overview" | "indices" | "stocks";

export type LoadStatus = "idle" | "loading" | "ready" | "error";
export type RefreshStatus = "idle" | "refreshing" | "failed";
export type MarketDataSource = "storage" | "network" | null;

export interface MarketResourceState<T> {
  data: T | null;
  error: string | null;
  loadStatus: LoadStatus;
  refreshStatus: RefreshStatus;
  source: MarketDataSource;
  lastHydratedAt: string | null;
}

export interface MarketDataState {
  overview: MarketResourceState<MarketOverviewResponse>;
  indices: MarketResourceState<IndicesResponse>;
  stocks: MarketResourceState<StocksResponse>;
}

interface PersistedResourceEnvelope<T> {
  version: number;
  resource: MarketResourceKey;
  savedAt: string;
  data: T;
}

const CACHE_VERSION = 1;
const CACHE_RETENTION_MS = 14 * 24 * 60 * 60 * 1000;
const STORAGE_KEY_PREFIX = "financehub.market";

export function getMarketStorageKey(resource: MarketResourceKey): string {
  return `${STORAGE_KEY_PREFIX}.${resource}`;
}

function getSafeStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function isTone(value: unknown): value is "positive" | "negative" | "neutral" {
  return value === "positive" || value === "negative" || value === "neutral";
}

function isTrendPoint(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.date === "string" &&
    typeof value.value === "number"
  );
}

function isMetricCard(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.label === "string" &&
    typeof value.value === "string" &&
    typeof value.delta === "string" &&
    typeof value.changeValue === "number" &&
    typeof value.changePercent === "number" &&
    isTone(value.tone)
  );
}

function isRankingItem(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.code === "string" &&
    typeof value.name === "string" &&
    typeof value.price === "string" &&
    typeof value.priceValue === "number" &&
    typeof value.change === "string" &&
    typeof value.changePercent === "number"
  );
}

function isOverviewResponse(value: unknown): value is MarketOverviewResponse {
  return (
    isObject(value) &&
    typeof value.asOfDate === "string" &&
    typeof value.stale === "boolean" &&
    Array.isArray(value.metrics) &&
    value.metrics.every(isMetricCard) &&
    typeof value.chartLabel === "string" &&
    Array.isArray(value.trendSeries) &&
    value.trendSeries.every(isTrendPoint) &&
    Array.isArray(value.topGainers) &&
    value.topGainers.every(isRankingItem) &&
    Array.isArray(value.topLosers) &&
    value.topLosers.every(isRankingItem)
  );
}

function isIndexCard(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.name === "string" &&
    typeof value.code === "string" &&
    typeof value.market === "string" &&
    typeof value.description === "string" &&
    typeof value.value === "string" &&
    typeof value.valueNumber === "number" &&
    typeof value.changeValue === "number" &&
    typeof value.changePercent === "number" &&
    isTone(value.tone) &&
    Array.isArray(value.trendSeries) &&
    value.trendSeries.every(isTrendPoint)
  );
}

function isIndicesResponse(value: unknown): value is IndicesResponse {
  return (
    isObject(value) &&
    typeof value.asOfDate === "string" &&
    typeof value.stale === "boolean" &&
    Array.isArray(value.cards) &&
    value.cards.every(isIndexCard)
  );
}

function isStockRow(value: unknown): boolean {
  return (
    isObject(value) &&
    typeof value.code === "string" &&
    typeof value.name === "string" &&
    typeof value.sector === "string" &&
    typeof value.price === "string" &&
    typeof value.change === "string" &&
    typeof value.priceValue === "number" &&
    typeof value.changePercent === "number" &&
    typeof value.volumeValue === "number" &&
    typeof value.amountValue === "number" &&
    Array.isArray(value.trend7d) &&
    value.trend7d.every(isTrendPoint)
  );
}

function isStocksResponse(value: unknown): value is StocksResponse {
  return (
    isObject(value) &&
    typeof value.asOfDate === "string" &&
    typeof value.stale === "boolean" &&
    Array.isArray(value.rows) &&
    value.rows.every(isStockRow)
  );
}

function isResourceData(
  resource: MarketResourceKey,
  data: unknown,
): data is MarketOverviewResponse | IndicesResponse | StocksResponse {
  if (resource === "overview") {
    return isOverviewResponse(data);
  }

  if (resource === "indices") {
    return isIndicesResponse(data);
  }

  return isStocksResponse(data);
}

export function validateResourcePayload(
  resource: "overview",
  data: unknown,
): data is MarketOverviewResponse;
export function validateResourcePayload(
  resource: "indices",
  data: unknown,
): data is IndicesResponse;
export function validateResourcePayload(
  resource: "stocks",
  data: unknown,
): data is StocksResponse;
export function validateResourcePayload(
  resource: MarketResourceKey,
  data: unknown,
): data is MarketOverviewResponse | IndicesResponse | StocksResponse;
export function validateResourcePayload(
  resource: MarketResourceKey,
  data: unknown,
): data is MarketOverviewResponse | IndicesResponse | StocksResponse {
  return isResourceData(resource, data);
}

function parseEnvelope(resource: MarketResourceKey, rawValue: string | null): {
  data: MarketOverviewResponse | IndicesResponse | StocksResponse;
  savedAt: string;
} | null {
  if (!rawValue) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(rawValue);
    if (!isObject(parsed)) {
      return null;
    }

    const envelope = parsed as Partial<PersistedResourceEnvelope<unknown>>;
    if (
      envelope.version !== CACHE_VERSION ||
      envelope.resource !== resource ||
      typeof envelope.savedAt !== "string" ||
      !validateResourcePayload(resource, envelope.data)
    ) {
      return null;
    }

    const savedAtTime = Date.parse(envelope.savedAt);
    if (!Number.isFinite(savedAtTime) || Date.now() - savedAtTime > CACHE_RETENTION_MS) {
      return null;
    }

    return { data: envelope.data, savedAt: envelope.savedAt };
  } catch {
    return null;
  }
}

function createEmptyResourceState<T>(): MarketResourceState<T> {
  return {
    data: null,
    error: null,
    lastHydratedAt: null,
    loadStatus: "idle",
    refreshStatus: "idle",
    source: null,
  };
}

export function hydrateResourceState<T>(resource: MarketResourceKey): MarketResourceState<T> {
  const storage = getSafeStorage();
  if (!storage) {
    return createEmptyResourceState<T>();
  }

  const key = getMarketStorageKey(resource);
  let rawValue: string | null = null;

  try {
    rawValue = storage.getItem(key);
  } catch {
    return createEmptyResourceState<T>();
  }

  const parsed = parseEnvelope(resource, rawValue);
  if (!parsed) {
    if (rawValue !== null) {
      try {
        storage.removeItem(key);
      } catch {
        // Ignore cleanup failures and continue with empty state.
      }
    }

    return createEmptyResourceState<T>();
  }

  return {
    data: parsed.data as T,
    error: null,
    lastHydratedAt: parsed.savedAt,
    loadStatus: "ready",
    refreshStatus: "idle",
    source: "storage",
  };
}

export function createInitialMarketDataState(): MarketDataState {
  return {
    overview: hydrateResourceState<MarketOverviewResponse>("overview"),
    indices: hydrateResourceState<IndicesResponse>("indices"),
    stocks: hydrateResourceState<StocksResponse>("stocks"),
  };
}

export function persistResourceSnapshot<T>(resource: MarketResourceKey, data: T): void {
  const storage = getSafeStorage();
  if (!storage) {
    return;
  }

  const envelope: PersistedResourceEnvelope<T> = {
    data,
    resource,
    savedAt: new Date().toISOString(),
    version: CACHE_VERSION,
  };

  try {
    storage.setItem(getMarketStorageKey(resource), JSON.stringify(envelope));
  } catch {
    // Ignore storage write failures and keep in-memory state.
  }
}

export const MarketDataContext = createContext<MarketDataState | null>(null);

export function useMarketData(): MarketDataState {
  const context = useContext(MarketDataContext);
  if (!context) {
    throw new Error("useMarketData must be used within MarketDataProvider");
  }

  return context;
}
