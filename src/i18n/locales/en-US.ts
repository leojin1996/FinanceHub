import type { Messages } from "../messages";

export const enUSMessages: Messages = {
  auth: {
    title: "Welcome to FinanceHub",
    subtitle: "Sign in to access your investment dashboard.",
    emailLabel: "Email Address",
    highlightMarkets: "Market focus",
    highlightData: "Live data",
    highlightInsights: "Risk insights",
    passwordLabel: "Password",
    signInAction: "Sign In",
    demoAction: "Try Demo Account",
  },
  dataState: {
    cachedLabel: "Showing last cached market snapshot",
    loading: "Loading market data",
    errorTitle: "Market data is temporarily unavailable",
    errorBody: "Please try again later or wait for the last successful snapshot to recover.",
    staleLabel: "Latest available close data",
  },
  languageLabel: "Language",
  marketOverview: {
    chartTitle: "Recent Close Trend",
    insightTitle: "Market Insights",
    gainersTitle: "Top Gainers",
    losersTitle: "Top Losers",
    insightBody: "Track representative stocks and benchmark closes from the latest trading day.",
  },
  session: {
    logoutAction: "Logout",
    userAriaLabel: "Signed-in user",
  },
  topStatus: {
    workspaceLabel: "China Market Workspace",
    dataBadgeLabel: "A-Share EOD",
  },
  nav: {
    overview: {
      navLabel: "Market",
      title: "Market Overview",
      subtitle: "Track key market indicators and daily moves.",
      description: "Monitor China market momentum and core benchmark trends.",
    },
    stocks: {
      navLabel: "Stocks",
      title: "China Stocks",
      subtitle: "Focus on key equities and turnover activity.",
      description: "Review representative A-share sectors and stock snapshots.",
    },
    indices: {
      navLabel: "Indices",
      title: "China Indices",
      subtitle: "Compare benchmark index trends and relative strength.",
      description: "Follow intraday and medium-term movement across major indices.",
    },
    riskAssessment: {
      navLabel: "Risk Survey",
      title: "Risk Assessment",
      subtitle: "Assess risk appetite and portfolio tolerance.",
      description: "Outline risk dimensions and prepare for questionnaire intake.",
    },
    recommendations: {
      navLabel: "Recommendations",
      title: "Personalized Recommendations",
      subtitle: "Show candidate strategies by risk preference.",
      description: "Display placeholder strategy content by profile and market state.",
    },
  },
};
