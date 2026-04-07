# Light Shell, Login, And Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone login experience, protect the existing app routes with a lightweight front-end session, and restyle the FinanceHub shell into a light top-navigation layout with consistent brand and navigation icons.

**Architecture:** Keep the backend and feature-page data contracts unchanged. Extend the existing front-end app state with a persisted demo session, route unauthenticated users through `/login`, and reuse the current page components inside a redesigned `AppShell` that swaps the left sidebar for a single top navigation bar. Centralize new copy in the existing i18n catalogs, implement icons as local inline SVG React components, and retheme the shared CSS variables and shell styles so all pages inherit the same lighter visual system.

**Tech Stack:** React 19, TypeScript, react-router-dom 7, Vitest, Testing Library, existing CSS token + shell styles under `src/styles`

---

## File Structure

- Create: `src/features/auth/LoginPage.tsx` - public login screen with email/password fields, demo-account shortcut, and redirect-on-success behavior
- Create: `src/components/AppIcons.tsx` - local inline SVG icon set for the FinanceHub brand mark, top-nav items, form fields, language/user/logout actions
- Modify: `src/app/state/app-state.ts` - add persisted auth session types and auth mutators to the shared app state contract
- Modify: `src/app/state/AppStateProvider.tsx` - hydrate and persist the auth session in `localStorage` while keeping locale and risk state intact
- Modify: `src/app/router.tsx` - add `/login`, gate the existing five product routes behind a protected wrapper, and preserve return-to-path redirects
- Modify: `src/app/layout/AppShell.tsx` - remove the sidebar slot and render the new top navigation shell above the current page content
- Modify: `src/app/layout/TopStatusBar.tsx` - turn the current status bar into the full brand + nav + user-actions top bar
- Modify: `src/i18n/messages.ts` - add separate short nav labels plus login and session copy
- Modify: `src/i18n/locales/zh-CN.ts` - add Chinese login, logout, demo-account, and nav-label strings
- Modify: `src/i18n/locales/en-US.ts` - add matching English strings so language switching stays complete
- Modify: `src/styles/tokens.css` - replace dark theme variables with light tokens and updated accent/text/surface colors
- Modify: `src/styles/app-shell.css` - restyle the body, top nav, login page, cards, panels, tables, filters, and responsive layout for the new light shell
- Modify: `src/app/App.test.tsx` - cover auth redirects, demo login, localized nav labels, and logout flow under the new shell
- Keep unchanged: `src/features/*` market-data fetch logic and backend `/api/*` contracts

## Task 1: Add lightweight auth state and protected routing

**Files:**
- Create: `src/features/auth/LoginPage.tsx`
- Modify: `src/app/state/app-state.ts`
- Modify: `src/app/state/AppStateProvider.tsx`
- Modify: `src/app/router.tsx`
- Modify: `src/i18n/messages.ts`
- Modify: `src/i18n/locales/zh-CN.ts`
- Modify: `src/i18n/locales/en-US.ts`
- Test: `src/app/App.test.tsx`

- [ ] **Step 1: Write the failing app-routing tests for login redirect and demo sign-in**

Update `src/app/App.test.tsx` with auth-flow coverage before touching the router:

```tsx
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/market-overview")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: false,
            metrics: [
              { label: "上证指数", value: "3,245.55", delta: "+0.8%", tone: "positive" },
              { label: "深证成指", value: "10,422.88", delta: "+1.1%", tone: "positive" },
              { label: "创业板指", value: "2,094.41", delta: "-0.2%", tone: "negative" },
            ],
            trendSeries: [
              { date: "2026-03-31", value: 3238.2 },
              { date: "2026-04-01", value: 3245.5 },
            ],
            topGainers: [{ name: "宁德时代", value: "+6.2%" }],
            topLosers: [{ name: "招商银行", value: "-3.5%" }],
          });
        }
        if (url.endsWith("/api/indices")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: false,
            series: [
              { name: "上证指数", value: 3245.5 },
              { name: "深证成指", value: 10422.9 },
              { name: "创业板指", value: 2094.4 },
            ],
          });
        }
        if (url.endsWith("/api/stocks")) {
          return jsonResponse({
            asOfDate: "2026-04-01",
            stale: false,
            rows: [
              { code: "300750", name: "宁德时代", sector: "新能源", price: "188.55", change: "+6.2%" },
            ],
          });
        }
        throw new Error(`Unhandled fetch for ${url}`);
      }),
    );
  });

  it("redirects unauthenticated users to login and returns them to the requested route after demo sign-in", async () => {
    window.history.pushState({}, "", "/stocks");
    const user = userEvent.setup();

    render(<App />);

    expect(screen.getByRole("heading", { name: "欢迎来到 FinanceHub" })).toBeInTheDocument();
    expect(screen.getByLabelText("邮箱地址")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "体验 Demo 账户" }));

    expect(await screen.findByRole("heading", { name: "中国股票" })).toBeInTheDocument();
    expect(screen.getByText("demo@financehub.com")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the routing test to confirm the current shell fails it**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/app/App.test.tsx -t "redirects unauthenticated users to login and returns them to the requested route after demo sign-in"
```

Expected: FAIL because there is no `/login` route, no auth session in app state, and `/stocks` currently renders directly.

- [ ] **Step 3: Implement persisted auth session, public login route, and protected app routes**

Update `src/app/state/app-state.ts` to extend the shared contract:

```ts
export interface AuthSession {
  email: string;
}

export interface AppStateValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  riskAssessmentResult: RiskAssessmentResult | null;
  setRiskAssessmentResult: (result: RiskAssessmentResult | null) => void;
  riskProfile: RiskProfile | null;
  session: AuthSession | null;
  signIn: (session: AuthSession) => void;
  signOut: () => void;
}
```

Update `src/app/state/AppStateProvider.tsx` to hydrate and persist the session:

```tsx
const SESSION_STORAGE_KEY = "financehub.session";

function readStoredSession(): AuthSession | null {
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

export function AppStateProvider({ children }: AppStateProviderProps) {
  const [locale, setLocale] = useState<Locale>("zh-CN");
  const [session, setSession] = useState<AuthSession | null>(() => readStoredSession());
  const [riskAssessmentResult, setRiskAssessmentResult] =
    useState<RiskAssessmentResult | null>(null);
  const riskProfile = riskAssessmentResult?.finalProfile ?? null;

  useEffect(() => {
    if (session) {
      window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
      return;
    }
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  }, [session]);

  return (
    <AppStateContext.Provider
      value={{
        locale,
        setLocale,
        riskAssessmentResult,
        setRiskAssessmentResult,
        riskProfile,
        session,
        signIn: setSession,
        signOut: () => setSession(null),
      }}
    >
      {children}
    </AppStateContext.Provider>
  );
}
```

Add the initial login copy contract to `src/i18n/messages.ts` and the two locale files before wiring the page. In `src/i18n/messages.ts`, insert this `auth` property into the existing `Messages` interface:

```ts
auth: {
  demoAction: string;
  emailLabel: string;
  passwordLabel: string;
  signInAction: string;
  subtitle: string;
  title: string;
};
```

In `src/i18n/locales/zh-CN.ts`, add this `auth` block near the top of the object:

```ts
auth: {
  title: "欢迎来到 FinanceHub",
  subtitle: "登录后即可访问你的投资仪表盘。",
  emailLabel: "邮箱地址",
  passwordLabel: "密码",
  signInAction: "登录",
  demoAction: "体验 Demo 账户",
},
```

In `src/i18n/locales/en-US.ts`, add the matching `auth` block:

```ts
auth: {
  title: "Welcome to FinanceHub",
  subtitle: "Sign in to access your investment dashboard.",
  emailLabel: "Email Address",
  passwordLabel: "Password",
  signInAction: "Sign In",
  demoAction: "Try Demo Account",
},
```

Create `src/features/auth/LoginPage.tsx` with redirect-aware demo auth:

```tsx
import { FormEvent, useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAppState } from "../../app/state/app-state";
import { getMessages } from "../../i18n/messages";

export function LoginPage() {
  const { locale, session, signIn } = useAppState();
  const messages = getMessages(locale);
  const location = useLocation();
  const navigate = useNavigate();
  const redirectTo = useMemo(
    () => (location.state as { from?: string } | null)?.from ?? "/",
    [location.state],
  );
  const [email, setEmail] = useState("demo@financehub.com");
  const [password, setPassword] = useState("demo1234");

  if (session) {
    return <Navigate replace to={redirectTo} />;
  }

  function finishLogin(nextEmail: string) {
    signIn({ email: nextEmail });
    navigate(redirectTo, { replace: true });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password.trim()) {
      return;
    }
    finishLogin(email.trim());
  }

  return (
    <main className="login-page">
      <section className="login-page__hero">
        <div className="login-page__brand">
          <h1>{messages.auth.title}</h1>
          <p>{messages.auth.subtitle}</p>
        </div>
        <form className="login-card" onSubmit={handleSubmit}>
          <label>
            <span>{messages.auth.emailLabel}</span>
            <input
              aria-label={messages.auth.emailLabel}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              value={email}
            />
          </label>
          <label>
            <span>{messages.auth.passwordLabel}</span>
            <input
              aria-label={messages.auth.passwordLabel}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </label>
          <button type="submit">{messages.auth.signInAction}</button>
          <button onClick={() => finishLogin("demo@financehub.com")} type="button">
            {messages.auth.demoAction}
          </button>
        </form>
      </section>
    </main>
  );
}
```

Update `src/app/router.tsx` so `/login` is public and the existing routes are protected:

```tsx
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { LoginPage } from "../features/auth/LoginPage";
import { useAppState } from "./state/app-state";

function ProtectedRoutes() {
  const { session } = useAppState();
  const location = useLocation();

  if (!session) {
    return <Navigate replace state={{ from: location.pathname }} to="/login" />;
  }

  return <Outlet />;
}

function PublicOnlyRoutes() {
  const { session } = useAppState();

  if (session) {
    return <Navigate replace to="/" />;
  }

  return <Outlet />;
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<PublicOnlyRoutes />}>
          <Route element={<LoginPage />} path="/login" />
        </Route>
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
```

- [ ] **Step 4: Run the auth routing test again**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/app/App.test.tsx -t "redirects unauthenticated users to login and returns them to the requested route after demo sign-in"
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit the auth-routing foundation**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add src/app/state/app-state.ts src/app/state/AppStateProvider.tsx src/app/router.tsx src/i18n/messages.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/features/auth/LoginPage.tsx src/app/App.test.tsx
git commit -m "feat: add demo auth and protected routes"
```

## Task 2: Add localized nav labels, brand icons, and the new top navigation shell

**Files:**
- Create: `src/components/AppIcons.tsx`
- Modify: `src/i18n/messages.ts`
- Modify: `src/i18n/locales/zh-CN.ts`
- Modify: `src/i18n/locales/en-US.ts`
- Modify: `src/app/layout/AppShell.tsx`
- Modify: `src/app/layout/TopStatusBar.tsx`
- Test: `src/app/App.test.tsx`

- [ ] **Step 1: Write the failing shell test for short nav labels, user actions, and locale switching**

Extend `src/app/App.test.tsx` with a shell-level regression test:

```tsx
  it("renders the top navigation in Chinese by default and switches nav chrome to English", async () => {
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
    window.history.pushState({}, "", "/");
    const user = userEvent.setup();

    render(<App />);

    const primaryNav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(primaryNav).getByRole("link", { name: "市场" })).toHaveAttribute("href", "/");
    expect(within(primaryNav).getByRole("link", { name: "股票" })).toHaveAttribute("href", "/stocks");
    expect(within(primaryNav).getByRole("link", { name: "指数" })).toHaveAttribute("href", "/indices");
    expect(within(primaryNav).getByRole("link", { name: "风险测评" })).toHaveAttribute("href", "/risk-assessment");
    expect(within(primaryNav).getByRole("link", { name: "推荐" })).toHaveAttribute("href", "/recommendations");
    expect(screen.getByText("demo@financehub.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "退出登录" })).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "语言" }), "en-US");

    const englishNav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(englishNav).getByRole("link", { name: "Market" })).toBeInTheDocument();
    expect(within(englishNav).getByRole("link", { name: "Stocks" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Logout" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Market Overview" })).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the shell-copy test to capture the current mismatch**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/app/App.test.tsx -t "renders the top navigation in Chinese by default and switches nav chrome to English"
```

Expected: FAIL because the current messages only expose long route titles, there are no login/session strings, and the top bar does not yet render route links or logout actions.

- [ ] **Step 3: Add new i18n fields, inline SVG icons, and upgrade the top bar into the app navigation**

Update `src/i18n/messages.ts` so nav labels and auth/session copy are first-class. Insert these fields into the existing interfaces:

```ts
export interface RouteMessages {
  description: string;
  navLabel: string;
  subtitle: string;
  title: string;
}

auth: {
  demoAction: string;
  emailLabel: string;
  highlightData: string;
  highlightInsights: string;
  highlightMarkets: string;
  passwordLabel: string;
  signInAction: string;
  subtitle: string;
  title: string;
};

session: {
  logoutAction: string;
  userAriaLabel: string;
};
```

Add the icon primitives in `src/components/AppIcons.tsx`:

```tsx
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function BaseIcon(props: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="20"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.9"
      viewBox="0 0 24 24"
      width="20"
      {...props}
    />
  );
}

function BrandMark(props: IconProps) {
  return (
    <BaseIcon viewBox="0 0 28 28" {...props}>
      <path d="M4 18.5L10 12.5L15 17.5L24 8.5" />
      <path d="M18.5 8.5H24V14" />
    </BaseIcon>
  );
}

export const AppIcons = {
  BrandMark,
  Market: (props: IconProps) => (
    <BaseIcon {...props}>
      <path d="M4 18L10 12L14 16L20 9" />
      <path d="M16 9H20V13" />
    </BaseIcon>
  ),
  Stocks: (props: IconProps) => (
    <BaseIcon {...props}>
      <path d="M5 19V9" />
      <path d="M11 19V5" />
      <path d="M17 19V12" />
      <path d="M3 19H21" />
    </BaseIcon>
  ),
  Indices: (props: IconProps) => (
    <BaseIcon {...props}>
      <path d="M4 17L9 12L13 15L20 8" />
      <path d="M4 5V19H20" />
    </BaseIcon>
  ),
  Risk: (props: IconProps) => (
    <BaseIcon {...props}>
      <rect height="15" rx="2.5" width="12" x="6" y="5" />
      <path d="M9.5 10H14.5" />
      <path d="M9.5 14H14.5" />
    </BaseIcon>
  ),
  Recommendation: (props: IconProps) => (
    <BaseIcon {...props}>
      <circle cx="12" cy="12" r="7" />
      <circle cx="12" cy="12" r="2.5" />
    </BaseIcon>
  ),
  Mail: (props: IconProps) => (
    <BaseIcon {...props}>
      <rect height="14" rx="2.5" width="18" x="3" y="5" />
      <path d="M4 7L12 13L20 7" />
    </BaseIcon>
  ),
  Lock: (props: IconProps) => (
    <BaseIcon {...props}>
      <rect height="11" rx="2" width="14" x="5" y="10" />
      <path d="M8 10V7.5C8 5.57 9.57 4 11.5 4H12.5C14.43 4 16 5.57 16 7.5V10" />
    </BaseIcon>
  ),
  Globe: (props: IconProps) => (
    <BaseIcon {...props}>
      <circle cx="12" cy="12" r="8" />
      <path d="M4 12H20" />
      <path d="M12 4C14.4 6.2 15.8 9 15.8 12C15.8 15 14.4 17.8 12 20" />
      <path d="M12 4C9.6 6.2 8.2 9 8.2 12C8.2 15 9.6 17.8 12 20" />
    </BaseIcon>
  ),
  Logout: (props: IconProps) => (
    <BaseIcon {...props}>
      <path d="M10 6H6.5C5.67 6 5 6.67 5 7.5V16.5C5 17.33 5.67 18 6.5 18H10" />
      <path d="M14 8L19 12L14 16" />
      <path d="M19 12H10" />
    </BaseIcon>
  ),
};
```

Update the locale files so the short nav labels and login/session copy exist in both languages. In `src/i18n/locales/zh-CN.ts`, add these `auth`, `session`, and `nav` sections:

```ts
auth: {
  title: "欢迎来到 FinanceHub",
  subtitle: "登录后即可访问你的投资仪表盘。",
  emailLabel: "邮箱地址",
  passwordLabel: "密码",
  signInAction: "登录",
  demoAction: "体验 Demo 账户",
  highlightMarkets: "中国市场",
  highlightData: "真实数据",
  highlightInsights: "策略洞察",
},
session: {
  logoutAction: "退出登录",
  userAriaLabel: "当前登录用户",
},
nav: {
  overview: {
    navLabel: "市场",
    title: "市场概览",
    subtitle: "追踪市场关键指标与今日异动。",
    description: "追踪中国市场与核心指数动态。",
  },
  stocks: {
    navLabel: "股票",
    title: "中国股票",
    subtitle: "聚焦重点股票表现与成交情况。",
    description: "查看A股重点板块与代表个股行情。",
  },
  indices: {
    navLabel: "指数",
    title: "中国指数",
    subtitle: "对比核心指数走势与相对强弱。",
    description: "跟踪沪深主要指数的日内与阶段表现。",
  },
  riskAssessment: {
    navLabel: "风险测评",
    title: "风险评估",
    subtitle: "评估当前风险偏好与组合承受能力。",
    description: "梳理风险维度，为后续问卷评估预留入口。",
  },
  recommendations: {
    navLabel: "推荐",
    title: "个性化推荐",
    subtitle: "根据风险偏好展示候选策略方向。",
    description: "展示基于画像与市场状态的策略占位内容。",
  },
},
```

Refactor `src/app/layout/TopStatusBar.tsx` into the full top bar:

```tsx
import { NavLink } from "react-router-dom";

import { AppIcons } from "../../components/AppIcons";
import { getMessages, routeDefinitions } from "../../i18n/messages";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { useAppState } from "../state/app-state";

export function TopStatusBar() {
  const { locale, session, signOut } = useAppState();
  const messages = getMessages(locale);

  return (
    <header className="top-status-bar">
      <div className="top-status-bar__brand-group">
        <AppIcons.BrandMark className="top-status-bar__brand-icon" />
        <p className="top-status-bar__brand">FinanceHub</p>
      </div>
      <nav aria-label="Primary" className="top-status-bar__nav">
        {routeDefinitions.map((route) => {
          const Icon = {
            overview: AppIcons.Market,
            stocks: AppIcons.Stocks,
            indices: AppIcons.Indices,
            riskAssessment: AppIcons.Risk,
            recommendations: AppIcons.Recommendation,
          }[route.key];

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
      <div className="top-status-bar__actions">
        <div aria-label={messages.session.userAriaLabel} className="top-status-bar__user">
          <span>{session?.email}</span>
        </div>
        <LanguageSwitcher />
        <button className="top-status-bar__logout" onClick={signOut} type="button">
          <AppIcons.Logout className="top-status-bar__logout-icon" />
          <span>{messages.session.logoutAction}</span>
        </button>
      </div>
    </header>
  );
}
```

Update `src/app/layout/AppShell.tsx` so it is a simple top-bar shell:

```tsx
export function AppShell({ pageSubtitle, pageTitle, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <TopStatusBar />
      <main className="app-shell__main">
        <PageHeader subtitle={pageSubtitle} title={pageTitle} />
        <ContentGrid>{children}</ContentGrid>
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run the shell-copy test again**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/app/App.test.tsx -t "renders the top navigation in Chinese by default and switches nav chrome to English"
```

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit the localized top-navigation shell**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add src/components/AppIcons.tsx src/i18n/messages.ts src/i18n/locales/zh-CN.ts src/i18n/locales/en-US.ts src/app/layout/AppShell.tsx src/app/layout/TopStatusBar.tsx src/app/App.test.tsx
git commit -m "feat: add localized top navigation shell"
```

## Task 3: Apply the light theme, polish the login page, and verify logout behavior

**Files:**
- Modify: `src/features/auth/LoginPage.tsx`
- Modify: `src/styles/tokens.css`
- Modify: `src/styles/app-shell.css`
- Test: `src/app/App.test.tsx`

- [ ] **Step 1: Write the failing logout-and-login-page regression test**

Add a final flow test in `src/app/App.test.tsx`:

```tsx
  it("logs out from the light shell and exposes localized login actions", async () => {
    window.localStorage.setItem("financehub.session", JSON.stringify({ email: "demo@financehub.com" }));
    window.history.pushState({}, "", "/recommendations");
    const user = userEvent.setup();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "个性化推荐" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "退出登录" }));

    expect(await screen.findByRole("heading", { name: "欢迎来到 FinanceHub" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "体验 Demo 账户" })).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "语言" }), "en-US");

    expect(screen.getByRole("heading", { name: "Welcome to FinanceHub" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign In" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try Demo Account" })).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the logout/login regression test before the style pass**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/app/App.test.tsx -t "logs out from the light shell and exposes localized login actions"
```

Expected: FAIL until the login page copy, language control placement, and logout return path are all wired through the new shell.

- [ ] **Step 3: Re-theme the shared CSS and finish the login-page structure**

Update `src/features/auth/LoginPage.tsx` so the hero, inputs, language switch, and highlight tiles match the new shell structure:

```tsx
return (
  <main className="login-page">
    <section className="login-page__hero">
      <div className="login-page__hero-copy">
        <div className="login-page__brand-badge">
          <AppIcons.BrandMark className="login-page__brand-icon" />
        </div>
        <h1>{messages.auth.title}</h1>
        <p>{messages.auth.subtitle}</p>
      </div>
      <div className="login-card">
        <div className="login-card__toolbar">
          <LanguageSwitcher />
        </div>
        <form className="login-form" onSubmit={handleSubmit}>
          <label className="login-form__field">
            <span>{messages.auth.emailLabel}</span>
            <div className="login-form__input-shell">
              <AppIcons.Mail className="login-form__icon" />
              <input
                aria-label={messages.auth.emailLabel}
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                value={email}
              />
            </div>
          </label>
          <label className="login-form__field">
            <span>{messages.auth.passwordLabel}</span>
            <div className="login-form__input-shell">
              <AppIcons.Lock className="login-form__icon" />
              <input
                aria-label={messages.auth.passwordLabel}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                value={password}
              />
            </div>
          </label>
          <button className="login-form__primary" type="submit">
            {messages.auth.signInAction}
          </button>
          <button className="login-form__secondary" onClick={() => finishLogin("demo@financehub.com")} type="button">
            {messages.auth.demoAction}
          </button>
        </form>
      </div>
    </section>
    <section className="login-highlights">
      <article className="login-highlights__card">{messages.auth.highlightMarkets}</article>
      <article className="login-highlights__card">{messages.auth.highlightData}</article>
      <article className="login-highlights__card">{messages.auth.highlightInsights}</article>
    </section>
  </main>
);
```

Replace the dark tokens in `src/styles/tokens.css`:

```css
:root {
  color-scheme: light;
  font-family: "Avenir Next", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  --fh-bg: #f5f8fc;
  --fh-bg-elevated: #ffffff;
  --fh-bg-overlay: #edf3fb;
  --fh-border: #d8e3f2;
  --fh-text-primary: #13233f;
  --fh-text-muted: #5d7291;
  --fh-accent: #2563eb;
  --fh-accent-soft: #eaf1ff;
  --fh-success: #16a34a;
  --fh-positive: #16a34a;
  --fh-negative: #dc2626;
  --fh-tag-bg: #eaf1ff;
  --fh-tag-text: #295ec9;
  --fh-radius-lg: 24px;
  --fh-radius-md: 18px;
  --fh-radius-sm: 12px;
  --fh-shadow: 0 18px 40px rgba(24, 49, 97, 0.08);
}
```

Update `src/styles/app-shell.css` to style the light shell and login page:

```css
body {
  margin: 0;
  min-height: 100vh;
  background:
    radial-gradient(circle at top, rgba(71, 125, 255, 0.15) 0%, transparent 38%),
    linear-gradient(180deg, #f8fbff 0%, #f2f6fc 100%);
  color: var(--fh-text-primary);
}

.app-shell {
  min-height: 100vh;
}

.top-status-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 1.5rem;
  padding: 1rem 1.75rem;
  border-bottom: 1px solid var(--fh-border);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(16px);
}

.top-status-bar__nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  justify-content: center;
}

.top-status-bar__link {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: 999px;
  color: var(--fh-text-muted);
  text-decoration: none;
}

.top-status-bar__link.is-active,
.top-status-bar__link:hover,
.top-status-bar__link:focus-visible {
  background: var(--fh-accent-soft);
  color: var(--fh-accent);
}

.top-status-bar__actions {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
}

.top-status-bar__user,
.top-status-bar__logout,
.language-switcher__select {
  border: 1px solid var(--fh-border);
  border-radius: 999px;
  background: var(--fh-bg-elevated);
  color: var(--fh-text-primary);
}

.app-shell__main {
  display: grid;
  gap: 1.25rem;
  padding: 2rem;
}

.panel,
.metric-card,
.placeholder-card,
.data-status-notice {
  background: var(--fh-bg-elevated);
  border: 1px solid var(--fh-border);
  box-shadow: var(--fh-shadow);
}

.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem 1.5rem 3rem;
}

.login-page__hero {
  width: min(100%, 1160px);
  display: grid;
  gap: 1.75rem;
  justify-items: center;
}

.login-card {
  width: min(100%, 680px);
  border: 1px solid var(--fh-border);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: var(--fh-shadow);
  padding: 1.5rem;
}

.login-form {
  display: grid;
  gap: 1rem;
}

.login-form__input-shell {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  border: 1px solid var(--fh-border);
  border-radius: var(--fh-radius-md);
  background: var(--fh-bg-elevated);
  padding: 0.9rem 1rem;
}

.login-form__primary,
.login-form__secondary {
  min-height: 3.25rem;
  border-radius: 16px;
  font: inherit;
  font-weight: 700;
}

.login-form__primary {
  border: none;
  background: var(--fh-accent);
  color: #ffffff;
}

.login-form__secondary {
  border: 1px solid var(--fh-border);
  background: var(--fh-bg-elevated);
  color: var(--fh-text-primary);
}

.login-highlights {
  width: min(100%, 680px);
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}

.login-highlights__card {
  border: 1px solid var(--fh-border);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: var(--fh-shadow);
  padding: 1.25rem;
  text-align: center;
}

@media (max-width: 960px) {
  .top-status-bar {
    grid-template-columns: 1fr;
    justify-items: start;
  }

  .top-status-bar__nav,
  .top-status-bar__actions {
    justify-content: flex-start;
  }

  .market-overview__metrics,
  .market-overview__main,
  .market-overview__lists,
  .chinese-stocks__layout,
  .chinese-indices__layout,
  .login-highlights {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 4: Run focused tests, then full front-end verification**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npx vitest run src/app/App.test.tsx src/components/MetricCard.test.tsx
npm run build
```

Expected:

- `npx vitest run src/app/App.test.tsx src/components/MetricCard.test.tsx` passes all targeted tests
- `npm run build` completes without TypeScript or Vite errors

- [ ] **Step 5: Manually smoke-test the login flow and light shell**

Run:

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
npm run dev -- --host 127.0.0.1
```

Then verify in the browser:

- `/login` shows the centered FinanceHub login card and brand icon
- switching language on `/login` updates button and heading copy
- `体验 Demo 账户` enters the originally requested route
- the protected app shell shows the light top navigation with icons and `demo@financehub.com`
- logout returns to `/login`
- market overview, stocks, indices, risk assessment, and recommendations all still render inside the new light shell

- [ ] **Step 6: Commit the light-theme polish**

```bash
cd /Users/zefengjin/Desktop/Practice/FinanceHub/.worktrees/codex/financehub-app-shell
git add src/features/auth/LoginPage.tsx src/styles/tokens.css src/styles/app-shell.css src/app/App.test.tsx
git commit -m "feat: add light theme login experience"
```
