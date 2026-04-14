import { type ReactNode, useEffect, useState } from "react";
import type { RecommendationResponse } from "../../services/chinaMarketApi";
import type { RiskAssessmentResult } from "../../features/risk-assessment/risk-scoring";
import { clearStoredToken } from "../../services/authApi";

import {
  AppStateContext,
  type AuthSession,
  type Locale,
} from "./app-state";

interface AppStateProviderProps {
  children: ReactNode;
}

const SESSION_STORAGE_KEY = "financehub.session";

function getSafeStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function parseSession(rawSession: string | null): AuthSession | null {
  if (!rawSession) {
    return null;
  }

  try {
    const parsedSession: unknown = JSON.parse(rawSession);
    if (
      parsedSession &&
      typeof parsedSession === "object" &&
      "email" in parsedSession &&
      typeof parsedSession.email === "string" &&
      parsedSession.email.trim() &&
      "userId" in parsedSession &&
      typeof parsedSession.userId === "string" &&
      parsedSession.userId.trim()
    ) {
      return { userId: parsedSession.userId, email: parsedSession.email };
    }
  } catch {
    return null;
  }

  return null;
}

interface InitialSessionState {
  cleanupInvalidStoredSession: boolean;
  session: AuthSession | null;
}

function readInitialSessionState(): InitialSessionState {
  const storage = getSafeStorage();
  if (!storage) {
    return { cleanupInvalidStoredSession: false, session: null };
  }

  let rawSession: string | null = null;
  try {
    rawSession = storage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return { cleanupInvalidStoredSession: false, session: null };
  }

  const parsedSession = parseSession(rawSession);
  if (parsedSession) {
    return { cleanupInvalidStoredSession: false, session: parsedSession };
  }

  return {
    cleanupInvalidStoredSession: rawSession !== null,
    session: null,
  };
}

export function AppStateProvider({ children }: AppStateProviderProps) {
  const [{ cleanupInvalidStoredSession, session: initialSession }] = useState<InitialSessionState>(
    () => readInitialSessionState(),
  );
  const [locale, setLocale] = useState<Locale>("zh-CN");
  const [recommendationCache, setRecommendationCache] =
    useState<Record<string, RecommendationResponse>>({});
  const [riskAssessmentResult, setRiskAssessmentResult] =
    useState<RiskAssessmentResult | null>(null);
  const [session, setSession] = useState<AuthSession | null>(initialSession);
  const riskProfile = riskAssessmentResult?.finalProfile ?? null;

  useEffect(() => {
    if (!cleanupInvalidStoredSession) {
      return;
    }

    const storage = getSafeStorage();
    if (!storage) {
      return;
    }

    try {
      storage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // Ignore storage removal failures and fall back to signed-out state.
    }
  }, [cleanupInvalidStoredSession]);

  const setRecommendationCacheEntry = (key: string, value: RecommendationResponse) => {
    setRecommendationCache((currentCache) => ({
      ...currentCache,
      [key]: value,
    }));
  };

  const clearRecommendationCache = () => {
    setRecommendationCache({});
  };

  const signIn = (nextSession: AuthSession) => {
    setSession(nextSession);
    const storage = getSafeStorage();
    if (!storage) {
      return;
    }

    try {
      storage.setItem(SESSION_STORAGE_KEY, JSON.stringify(nextSession));
    } catch {
      // Ignore storage write failures and keep in-memory signed-in state.
    }
  };

  const signOut = () => {
    setSession(null);
    clearRecommendationCache();
    clearStoredToken();
    const storage = getSafeStorage();
    if (!storage) {
      return;
    }

    try {
      storage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // Ignore storage removal failures and keep in-memory signed-out state.
    }
  };

  return (
    <AppStateContext.Provider
      value={{
        locale,
        setLocale,
        recommendationCache,
        setRecommendationCacheEntry,
        clearRecommendationCache,
        riskAssessmentResult,
        setRiskAssessmentResult,
        riskProfile,
        session,
        signIn,
        signOut,
      }}
    >
      {children}
    </AppStateContext.Provider>
  );
}
