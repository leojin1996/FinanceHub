import { NavLink } from "react-router-dom";

import {
  BrandMark,
  IndicesIcon,
  LogoutIcon,
  MarketIcon,
  RecommendationIcon,
  RiskIcon,
  StocksIcon,
} from "../../components/AppIcons";
import { getMessages } from "../../i18n/messages";
import type { RouteKey } from "../../i18n/messages";
import { routeDefinitions } from "../../i18n/messages";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { useAppState } from "../state/app-state";

const routeIcons: Record<RouteKey, typeof MarketIcon> = {
  overview: MarketIcon,
  stocks: StocksIcon,
  indices: IndicesIcon,
  riskAssessment: RiskIcon,
  recommendations: RecommendationIcon,
};

export function TopStatusBar() {
  const { locale, session, signOut } = useAppState();
  const messages = getMessages(locale);
  const primaryNavLabel = locale === "zh-CN" ? "主导航" : "Primary";

  return (
    <header className="top-status-bar">
      <div className="top-status-bar__brand">
        <BrandMark className="top-status-bar__brand-mark" />
        <span className="top-status-bar__brand-wordmark">FinanceHub</span>
      </div>
      <nav aria-label={primaryNavLabel} className="top-status-bar__nav">
        {routeDefinitions.map((route) => {
          const Icon = routeIcons[route.key];

          return (
            <NavLink
              className={({ isActive }) =>
                isActive ? "top-status-bar__link is-active" : "top-status-bar__link"
              }
              end={route.path === "/"}
              key={route.key}
              to={route.path}
            >
              <Icon className="top-status-bar__link-icon" />
              <span>{messages.nav[route.key].navLabel}</span>
            </NavLink>
          );
        })}
      </nav>
      <div className="top-status-bar__meta">
        {session ? (
          <span
            aria-label={messages.session.userAriaLabel}
            className="top-status-bar__session"
          >
            {session.email}
          </span>
        ) : null}
        <div className="top-status-bar__locale">
          <LanguageSwitcher />
        </div>
        {session ? (
          <button className="top-status-bar__logout" onClick={signOut} type="button">
            <LogoutIcon className="top-status-bar__logout-icon" />
            <span>{messages.session.logoutAction}</span>
          </button>
        ) : null}
      </div>
    </header>
  );
}
