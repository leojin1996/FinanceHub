import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { LoginPage } from "../features/auth/LoginPage";
import { ChineseIndicesPage } from "../features/chinese-indices/ChineseIndicesPage";
import { ChineseStocksPage } from "../features/chinese-stocks/ChineseStocksPage";
import { MarketOverviewPage } from "../features/market-overview/MarketOverviewPage";
import { RecommendationsPage } from "../features/recommendations/RecommendationsPage";
import { RiskAssessmentPage } from "../features/risk-assessment/RiskAssessmentPage";
import { useAppState } from "./state/app-state";

function ProtectedRoutes() {
  const { session } = useAppState();
  const location = useLocation();

  if (!session) {
    return (
      <Navigate
        replace
        state={{ from: `${location.pathname}${location.search}${location.hash}`, protected: true }}
        to="/login"
      />
    );
  }

  return <Outlet />;
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<LoginPage />} path="/login" />
        <Route element={<ProtectedRoutes />}>
          <Route element={<MarketOverviewPage />} path="/" />
          <Route element={<ChineseStocksPage />} path="/stocks" />
          <Route element={<ChineseIndicesPage />} path="/indices" />
          <Route element={<RiskAssessmentPage />} path="/risk-assessment" />
          <Route element={<RecommendationsPage />} path="/recommendations" />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
