import { enUSMessages } from "./locales/en-US";
import { zhCNMessages } from "./locales/zh-CN";

export type RouteKey =
  | "overview"
  | "stocks"
  | "indices"
  | "riskAssessment"
  | "recommendations";

export interface RouteDefinition {
  key: RouteKey;
  path: string;
}

export interface RouteMessages {
  description: string;
  navLabel: string;
  subtitle: string;
  title: string;
}

export interface Messages {
  auth: {
    demoAction: string;
    emailLabel: string;
    errorEmailRegistered: string;
    errorInvalidCredentials: string;
    errorGeneric: string;
    errorNetwork: string;
    highlightData: string;
    highlightInsights: string;
    highlightMarkets: string;
    passwordLabel: string;
    registerAction: string;
    registerSubtitle: string;
    registerTitle: string;
    signInAction: string;
    subtitle: string;
    switchToLogin: string;
    switchToRegister: string;
    title: string;
  };
  dataState: {
    cachedLabel: string;
    errorBody: string;
    errorTitle: string;
    loading: string;
    staleLabel: string;
  };
  languageLabel: string;
  nav: Record<RouteKey, RouteMessages>;
  marketOverview: {
    chartTitle: string;
    insightBody: string;
    insightTitle: string;
    losersTitle: string;
    gainersTitle: string;
  };
  session: {
    logoutAction: string;
    userAriaLabel: string;
  };
  topStatus: {
    dataBadgeLabel: string;
    workspaceLabel: string;
  };
}

export const routeDefinitions: RouteDefinition[] = [
  { key: "overview", path: "/" },
  { key: "stocks", path: "/stocks" },
  { key: "indices", path: "/indices" },
  { key: "riskAssessment", path: "/risk-assessment" },
  { key: "recommendations", path: "/recommendations" },
];

const defaultLocale = "zh-CN";

const messagesByLocale: Record<string, Messages> = {
  "zh-CN": zhCNMessages,
  "en-US": enUSMessages,
};

export function getMessages(locale: string): Messages {
  return messagesByLocale[locale] ?? messagesByLocale[defaultLocale];
}
