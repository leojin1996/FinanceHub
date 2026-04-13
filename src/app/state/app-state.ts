import { createContext, useContext } from "react";
import type { RecommendationResponse } from "../../services/chinaMarketApi";
import type { RiskAssessmentResult } from "../../features/risk-assessment/risk-scoring";

export type Locale = "zh-CN" | "en-US";
export type RiskProfile =
  | "conservative"
  | "stable"
  | "balanced"
  | "growth"
  | "aggressive";

export interface AuthSession {
  email: string;
}

export interface AppStateValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  recommendationCache: Record<string, RecommendationResponse>;
  setRecommendationCacheEntry: (key: string, value: RecommendationResponse) => void;
  clearRecommendationCache: () => void;
  riskAssessmentResult: RiskAssessmentResult | null;
  setRiskAssessmentResult: (result: RiskAssessmentResult | null) => void;
  riskProfile: RiskProfile | null;
  session: AuthSession | null;
  signIn: (session: AuthSession) => void;
  signOut: () => void;
}

export const AppStateContext = createContext<AppStateValue | null>(null);

export function useAppState(): AppStateValue {
  const context = useContext(AppStateContext);
  if (!context) {
    throw new Error("useAppState must be used within AppStateProvider");
  }
  return context;
}
