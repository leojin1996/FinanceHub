# FinanceHub App Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a desktop-first, Simplified-Chinese-default finance dashboard shell with five routed pages, locale switching, mock-data-backed market views, a six-question risk questionnaire, and recommendation rendering tied to the questionnaire result.

**Architecture:** Start from a Vite + React + TypeScript client, then add a shared `AppShell` with React Router, a thin app-state layer for locale and risk profile, and page-local state for tables and questionnaire progress. Keep display components presentational and feed them normalized mock data so future API work can replace only the page containers instead of rewriting the UI.

**Tech Stack:** React, TypeScript, Vite, React Router, Recharts, Vitest, Testing Library, CSS variables with plain CSS modules/files

---

## File Structure

Create these files and keep responsibilities narrow:

- `package.json` - package scripts and dependencies
- `vite.config.ts` - Vite build config
- `vitest.config.ts` - Vitest + jsdom config
- `tsconfig.json` - root TypeScript references
- `tsconfig.app.json` - browser TypeScript config
- `tsconfig.node.json` - Vite/Vitest TypeScript config
- `index.html` - Vite entry HTML
- `src/main.tsx` - React bootstrap
- `src/app/App.tsx` - root app component
- `src/app/router.tsx` - route definitions for the five pages
- `src/app/state/AppStateProvider.tsx` - locale + risk profile shared state
- `src/app/state/app-state.ts` - shared types and context helpers
- `src/app/layout/AppShell.tsx` - page frame wrapper
- `src/app/layout/SidebarNav.tsx` - left navigation
- `src/app/layout/TopStatusBar.tsx` - header with app metadata and locale switcher
- `src/app/layout/LanguageSwitcher.tsx` - locale selection UI
- `src/app/layout/PageHeader.tsx` - shared page title and subtitle block
- `src/app/layout/ContentGrid.tsx` - reusable page grid wrapper
- `src/components/MetricCard.tsx` - metric summary card
- `src/components/ChartPanel.tsx` - titled chart surface
- `src/components/RankingList.tsx` - sorted list block
- `src/components/DataTable.tsx` - stock table shell
- `src/components/InsightCard.tsx` - explanatory card surface
- `src/components/TagBadge.tsx` - reusable label badge
- `src/features/market-overview/MarketOverviewPage.tsx` - overview page container
- `src/features/chinese-stocks/ChineseStocksPage.tsx` - stocks page container
- `src/features/chinese-stocks/StockFilters.tsx` - local stock filter controls
- `src/features/chinese-indices/ChineseIndicesPage.tsx` - indices page container
- `src/features/chinese-indices/IndexComparisonPanel.tsx` - index comparison block
- `src/features/risk-assessment/RiskAssessmentPage.tsx` - questionnaire page container
- `src/features/risk-assessment/RiskQuestionnaireWizard.tsx` - six-question flow
- `src/features/recommendations/RecommendationsPage.tsx` - recommendation page container
- `src/features/recommendations/RecommendationDeck.tsx` - recommendation cards
- `src/i18n/locales/zh-CN.ts` - default Chinese copy
- `src/i18n/locales/en-US.ts` - first alternate locale
- `src/i18n/messages.ts` - message catalog and fallback helper
- `src/mock/marketOverview.ts` - overview mock data
- `src/mock/stocks.ts` - stock list + stock detail mocks
- `src/mock/indices.ts` - index comparison mocks
- `src/mock/questionnaire.ts` - six-question prompt and scoring data
- `src/mock/recommendations.ts` - recommendation groups by risk profile
- `src/styles/tokens.css` - design tokens
- `src/styles/global.css` - reset and base rules
- `src/styles/app-shell.css` - shell and page layout styles
- `src/test/setup.ts` - test setup
- `src/app/App.test.tsx` - smoke + routing test
- `src/app/locale.test.tsx` - locale switching + fallback test
- `src/components/MetricCard.test.tsx` - shared component contract test
- `src/features/market-overview/MarketOverviewPage.test.tsx` - overview page test
- `src/features/chinese-stocks/ChineseStocksPage.test.tsx` - stocks page test
- `src/features/chinese-indices/ChineseIndicesPage.test.tsx` - indices page test
- `src/features/risk-assessment/RiskAssessmentPage.test.tsx` - questionnaire behavior test
- `src/features/recommendations/RecommendationsPage.test.tsx` - recommendation rendering test

## Task 1: Bootstrap the React/Vite workspace

**Files:**
- Create: `package.json`
- Create: `vite.config.ts`
- Create: `vitest.config.ts`
- Create: `tsconfig.json`
- Create: `tsconfig.app.json`
- Create: `tsconfig.node.json`
- Create: `index.html`
- Create: `src/main.tsx`
- Create: `src/app/App.tsx`
- Create: `src/test/setup.ts`
- Test: `src/app/App.test.tsx`

- [ ] **Step 1: Initialize git, scaffold Vite, and install runtime/test dependencies**

Run:

```bash
git init -b main
npm create vite@latest . -- --template react-ts
npm install react-router-dom recharts
npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

Expected:

- `.git/` exists
- `src/`, `index.html`, and TypeScript config files exist
- `npm ls react react-router-dom recharts vitest` exits with code `0`

- [ ] **Step 2: Write the failing root smoke test**

Create `src/app/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import App from "./App";

describe("App bootstrap", () => {
  it("renders the shell title and default Chinese market overview heading", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("FinanceHub")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "市场概览" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the smoke test and verify it fails for the right reason**

Run:

```bash
npx vitest run src/app/App.test.tsx
```

Expected: FAIL because `App` still renders the Vite starter content instead of the FinanceHub shell.

- [ ] **Step 4: Replace the starter app with the minimal FinanceHub root and test setup**

Update `vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
  },
});
```

Create `src/test/setup.ts`:

```ts
import "@testing-library/jest-dom";
```

Replace `src/app/App.tsx`:

```tsx
export default function App() {
  return (
    <div>
      <header>
        <h1>FinanceHub</h1>
      </header>
      <main>
        <h2>市场概览</h2>
      </main>
    </div>
  );
}
```

Replace `src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./app/App";
import "./styles/global.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Create `src/styles/global.css`:

```css
:root {
  color-scheme: dark;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #08111f;
  color: #e2e8f0;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: radial-gradient(circle at top, #10213a 0%, #08111f 58%);
}

#root {
  min-height: 100vh;
}
```

- [ ] **Step 5: Run the smoke test and verify it passes**

Run:

```bash
npx vitest run src/app/App.test.tsx
```

Expected: PASS with `1 passed`.

- [ ] **Step 6: Commit the bootstrap**

Run:

```bash
git add package.json package-lock.json vite.config.ts vitest.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json index.html src
git commit -m "feat: bootstrap finance dashboard app"
```

## Task 2: Add routing, shared app state, and the desktop shell

**Files:**
- Create: `src/app/router.tsx`
- Create: `src/app/state/app-state.ts`
- Create: `src/app/state/AppStateProvider.tsx`
- Create: `src/app/layout/AppShell.tsx`
- Create: `src/app/layout/SidebarNav.tsx`
- Create: `src/app/layout/TopStatusBar.tsx`
- Create: `src/app/layout/LanguageSwitcher.tsx`
- Create: `src/app/layout/PageHeader.tsx`
- Create: `src/app/layout/ContentGrid.tsx`
- Create: `src/styles/tokens.css`
- Create: `src/styles/app-shell.css`
- Modify: `src/app/App.tsx`
- Modify: `src/main.tsx`
- Test: `src/app/App.test.tsx`

- [ ] **Step 1: Expand the routing test to cover all five destinations and default shell chrome**

Replace `src/app/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";

describe("App shell routing", () => {
  it("renders the default overview route in Simplified Chinese", () => {
    render(<App />);

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "市场概览" })).toBeInTheDocument();
    expect(screen.getByText("Mock Data")).toBeInTheDocument();
  });

  it("navigates to the recommendations route from the sidebar", async () => {
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("link", { name: "个性化推荐" }));

    expect(screen.getByRole("heading", { name: "个性化推荐" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the routing test and verify it fails because the shell and routes do not exist yet**

Run:

```bash
npx vitest run src/app/App.test.tsx
```

Expected: FAIL with missing navigation links and missing `Mock Data` label.

- [ ] **Step 3: Implement the app state, router, and shell**

Create `src/app/state/app-state.ts`:

```ts
import { createContext, useContext } from "react";

export type Locale = "zh-CN" | "en-US";
export type RiskProfile = "conservative" | "stable" | "balanced" | "growth" | "aggressive" | null;

export interface AppStateValue {
  locale: Locale;
  riskProfile: RiskProfile;
  setLocale: (locale: Locale) => void;
  setRiskProfile: (profile: Exclude<RiskProfile, null>) => void;
}

export const AppStateContext = createContext<AppStateValue | null>(null);

export function useAppState() {
  const value = useContext(AppStateContext);

  if (!value) {
    throw new Error("useAppState must be used inside AppStateProvider");
  }

  return value;
}
```

Create `src/app/state/AppStateProvider.tsx`:

```tsx
import { PropsWithChildren, useMemo, useState } from "react";

import { AppStateContext, Locale, RiskProfile } from "./app-state";

export function AppStateProvider({ children }: PropsWithChildren) {
  const [locale, setLocale] = useState<Locale>("zh-CN");
  const [riskProfile, setRiskProfile] = useState<RiskProfile>(null);

  const value = useMemo(
    () => ({ locale, riskProfile, setLocale, setRiskProfile }),
    [locale, riskProfile],
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}
```

Create `src/app/router.tsx`:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "./layout/AppShell";

type RouteKey = "overview" | "stocks" | "indices" | "risk" | "recommendations";

const routeTitles: Record<RouteKey, string> = {
  overview: "市场概览",
  stocks: "中国股票",
  indices: "中国指数",
  risk: "风险评估",
  recommendations: "个性化推荐",
};

function PlaceholderPage({ routeKey }: { routeKey: RouteKey }) {
  return (
    <AppShell title={routeTitles[routeKey]} subtitle="Shared shell preview for this route.">
      <section />
    </AppShell>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<PlaceholderPage routeKey="overview" />} />
        <Route path="/stocks" element={<PlaceholderPage routeKey="stocks" />} />
        <Route path="/indices" element={<PlaceholderPage routeKey="indices" />} />
        <Route path="/risk-assessment" element={<PlaceholderPage routeKey="risk" />} />
        <Route path="/recommendations" element={<PlaceholderPage routeKey="recommendations" />} />
      </Routes>
    </BrowserRouter>
  );
}
```

Create `src/app/layout/LanguageSwitcher.tsx`:

```tsx
import { ChangeEvent } from "react";

import { useAppState } from "../state/app-state";

export function LanguageSwitcher() {
  const { locale, setLocale } = useAppState();

  function handleChange(event: ChangeEvent<HTMLSelectElement>) {
    setLocale(event.target.value as "zh-CN" | "en-US");
  }

  return (
    <label>
      <span className="sr-only">Language</span>
      <select aria-label="Language" value={locale} onChange={handleChange}>
        <option value="zh-CN">简体中文</option>
        <option value="en-US">English</option>
      </select>
    </label>
  );
}
```

Create `src/app/layout/SidebarNav.tsx`:

```tsx
import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "市场概览" },
  { to: "/stocks", label: "中国股票" },
  { to: "/indices", label: "中国指数" },
  { to: "/risk-assessment", label: "风险评估" },
  { to: "/recommendations", label: "个性化推荐" },
];

export function SidebarNav() {
  return (
    <nav aria-label="Primary" className="sidebar-nav">
      <div className="sidebar-brand">FinanceHub</div>
      {links.map((link) => (
        <NavLink key={link.to} className="sidebar-link" to={link.to}>
          {link.label}
        </NavLink>
      ))}
    </nav>
  );
}
```

Create `src/app/layout/TopStatusBar.tsx`:

```tsx
import { LanguageSwitcher } from "./LanguageSwitcher";

export function TopStatusBar() {
  return (
    <header className="top-status-bar">
      <div>
        <strong>FinanceHub</strong>
        <span>China Market Workspace</span>
      </div>
      <div className="top-status-actions">
        <span className="mode-chip">Mock Data</span>
        <LanguageSwitcher />
      </div>
    </header>
  );
}
```

Create `src/app/layout/PageHeader.tsx`:

```tsx
export function PageHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="page-header">
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
  );
}
```

Create `src/app/layout/ContentGrid.tsx`:

```tsx
import { PropsWithChildren } from "react";

export function ContentGrid({ children }: PropsWithChildren) {
  return <section className="content-grid">{children}</section>;
}
```

Create `src/app/layout/AppShell.tsx`:

```tsx
import { PropsWithChildren } from "react";

import { ContentGrid } from "./ContentGrid";
import { PageHeader } from "./PageHeader";
import { SidebarNav } from "./SidebarNav";
import { TopStatusBar } from "./TopStatusBar";

export function AppShell({
  title,
  subtitle,
  children,
}: PropsWithChildren<{ title: string; subtitle: string }>) {
  return (
    <div className="app-shell">
      <SidebarNav />
      <div className="app-shell__main">
        <TopStatusBar />
        <main className="app-shell__content">
          <PageHeader title={title} subtitle={subtitle} />
          <ContentGrid>{children}</ContentGrid>
        </main>
      </div>
    </div>
  );
}
```

Create `src/styles/tokens.css`:

```css
:root {
  --bg-app: #08111f;
  --bg-sidebar: rgba(10, 18, 34, 0.96);
  --bg-panel: rgba(16, 24, 39, 0.78);
  --bg-panel-strong: rgba(20, 32, 52, 0.92);
  --border-subtle: rgba(148, 163, 184, 0.18);
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --accent-blue: #3b82f6;
  --accent-green: #10b981;
  --shadow-panel: 0 24px 60px rgba(2, 8, 23, 0.28);
  --radius-panel: 24px;
}
```

Create `src/styles/app-shell.css`:

```css
.app-shell {
  display: grid;
  grid-template-columns: 248px 1fr;
  min-height: 100vh;
}

.sidebar-nav {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 28px 20px;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-subtle);
}

.sidebar-brand {
  margin-bottom: 20px;
  font-size: 1.25rem;
  font-weight: 700;
}

.sidebar-link {
  padding: 14px 16px;
  border-radius: 16px;
  color: var(--text-secondary);
  text-decoration: none;
  background: transparent;
}

.sidebar-link.active {
  color: var(--text-primary);
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.32), rgba(16, 185, 129, 0.18));
}

.app-shell__main {
  display: grid;
  grid-template-rows: auto 1fr;
}

.top-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 22px 32px;
}

.top-status-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.mode-chip {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.18);
  color: #bfdbfe;
}

.app-shell__content {
  padding: 0 32px 32px;
}

.page-header p {
  color: var(--text-secondary);
}

.content-grid {
  display: grid;
  gap: 20px;
}
```

Update `src/styles/global.css`:

```css
@import "./tokens.css";
@import "./app-shell.css";

:root {
  color-scheme: dark;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg-app);
  color: var(--text-primary);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: radial-gradient(circle at top, #10213a 0%, var(--bg-app) 58%);
}

a,
button,
select,
input {
  font: inherit;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

Replace `src/app/App.tsx`:

```tsx
import { AppStateProvider } from "./state/AppStateProvider";
import { AppRouter } from "./router";

export default function App() {
  return (
    <AppStateProvider>
      <AppRouter />
    </AppStateProvider>
  );
}
```

- [ ] **Step 4: Run the app-shell test and verify it passes**

Run:

```bash
npx vitest run src/app/App.test.tsx
```

Expected: PASS with the overview route rendered by default and sidebar navigation working.

- [ ] **Step 5: Commit the app shell**

Run:

```bash
git add src/app src/styles src/app/App.test.tsx
git commit -m "feat: add finance dashboard shell and routing"
```

## Task 3: Add localization and fallback behavior

**Files:**
- Create: `src/i18n/locales/zh-CN.ts`
- Create: `src/i18n/locales/en-US.ts`
- Create: `src/i18n/messages.ts`
- Modify: `src/app/layout/SidebarNav.tsx`
- Modify: `src/app/layout/TopStatusBar.tsx`
- Modify: `src/app/router.tsx`
- Create: `src/app/locale.test.tsx`

- [ ] **Step 1: Write failing tests for default locale, locale switching, and fallback**

Create `src/app/locale.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";
import { getMessages } from "../i18n/messages";

describe("Localization", () => {
  it("uses Simplified Chinese on first load", () => {
    render(<App />);

    expect(screen.getByRole("link", { name: "市场概览" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "市场概览" })).toBeInTheDocument();
  });

  it("switches shell labels to English", async () => {
    const user = userEvent.setup();

    render(<App />);

    await user.selectOptions(screen.getByLabelText("Language"), "en-US");

    expect(screen.getByRole("link", { name: "Market Overview" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Market Overview" })).toBeInTheDocument();
  });

  it("falls back to zh-CN when an unknown locale is requested", () => {
    expect(getMessages("fr-FR").nav.overview).toBe("市场概览");
  });
});
```

- [ ] **Step 2: Run the locale test and verify it fails because the shell copy is hard-coded in Chinese**

Run:

```bash
npx vitest run src/app/locale.test.tsx
```

Expected: FAIL because changing the select does not update route labels or page headings.

- [ ] **Step 3: Implement locale catalogs and the lookup helper**

Create `src/i18n/locales/zh-CN.ts`:

```ts
export const zhCN = {
  nav: {
    overview: "市场概览",
    stocks: "中国股票",
    indices: "中国指数",
    risk: "风险评估",
    recommendations: "个性化推荐",
  },
  subtitles: {
    overview: "把握中国市场当日节奏与核心涨跌信号。",
    stocks: "按搜索、筛选和排序浏览个股池。",
    indices: "从指数视角观察市场结构与趋势。",
    risk: "完成 6 道题，识别你的风险承受能力。",
    recommendations: "基于风险偏好展示个性化股票建议。",
  },
  shell: {
    workspace: "中国市场工作台",
    mockData: "Mock Data",
  },
} as const;
```

Create `src/i18n/locales/en-US.ts`:

```ts
export const enUS = {
  nav: {
    overview: "Market Overview",
    stocks: "Chinese Stocks",
    indices: "Chinese Indices",
    risk: "Risk Assessment",
    recommendations: "Personalized Recommendations",
  },
  subtitles: {
    overview: "Track the daily tone of the China market at a glance.",
    stocks: "Browse stocks with search, filters, and sorting.",
    indices: "Use index views to understand structure and trend.",
    risk: "Answer 6 questions to identify your risk tolerance.",
    recommendations: "See stock ideas tailored to your risk profile.",
  },
  shell: {
    workspace: "China Market Workspace",
    mockData: "Mock Data",
  },
} as const;
```

Create `src/i18n/messages.ts`:

```ts
import { enUS } from "./locales/en-US";
import { zhCN } from "./locales/zh-CN";

export const messages = {
  "zh-CN": zhCN,
  "en-US": enUS,
} as const;

export type MessageCatalog = typeof zhCN;

export function getMessages(locale: string): MessageCatalog {
  return messages[locale as keyof typeof messages] ?? messages["zh-CN"];
}
```

Modify `src/app/layout/SidebarNav.tsx`:

```tsx
import { NavLink } from "react-router-dom";

import { getMessages } from "../../i18n/messages";
import { useAppState } from "../state/app-state";

export function SidebarNav() {
  const { locale } = useAppState();
  const message = getMessages(locale);

  const links = [
    { to: "/", label: message.nav.overview },
    { to: "/stocks", label: message.nav.stocks },
    { to: "/indices", label: message.nav.indices },
    { to: "/risk-assessment", label: message.nav.risk },
    { to: "/recommendations", label: message.nav.recommendations },
  ];

  return (
    <nav aria-label="Primary" className="sidebar-nav">
      <div className="sidebar-brand">FinanceHub</div>
      {links.map((link) => (
        <NavLink key={link.to} className="sidebar-link" to={link.to}>
          {link.label}
        </NavLink>
      ))}
    </nav>
  );
}
```

Modify `src/app/layout/TopStatusBar.tsx`:

```tsx
import { getMessages } from "../../i18n/messages";
import { useAppState } from "../state/app-state";
import { LanguageSwitcher } from "./LanguageSwitcher";

export function TopStatusBar() {
  const { locale } = useAppState();
  const message = getMessages(locale);

  return (
    <header className="top-status-bar">
      <div>
        <strong>FinanceHub</strong>
        <span>{message.shell.workspace}</span>
      </div>
      <div className="top-status-actions">
        <span className="mode-chip">{message.shell.mockData}</span>
        <LanguageSwitcher />
      </div>
    </header>
  );
}
```

Modify `src/app/router.tsx`:

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";

import { getMessages, MessageCatalog } from "../i18n/messages";
import { useAppState } from "./state/app-state";
import { AppShell } from "./layout/AppShell";

type RouteKey = keyof MessageCatalog["nav"];

function PlaceholderPage({ routeKey }: { routeKey: RouteKey }) {
  const { locale } = useAppState();
  const message = getMessages(locale);

  return (
    <AppShell title={message.nav[routeKey]} subtitle={message.subtitles[routeKey]}>
      <section />
    </AppShell>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<PlaceholderPage routeKey="overview" />} />
        <Route path="/stocks" element={<PlaceholderPage routeKey="stocks" />} />
        <Route path="/indices" element={<PlaceholderPage routeKey="indices" />} />
        <Route path="/risk-assessment" element={<PlaceholderPage routeKey="risk" />} />
        <Route path="/recommendations" element={<PlaceholderPage routeKey="recommendations" />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Run the locale tests and app-shell smoke test**

Run:

```bash
npx vitest run src/app/locale.test.tsx src/app/App.test.tsx
```

Expected: PASS with both locale assertions and prior routing assertions green.

- [ ] **Step 5: Commit localization support**

Run:

```bash
git add src/app src/i18n
git commit -m "feat: add zh-CN default locale switching"
```

## Task 4: Build reusable finance display components and mock data

**Files:**
- Create: `src/components/MetricCard.tsx`
- Create: `src/components/ChartPanel.tsx`
- Create: `src/components/RankingList.tsx`
- Create: `src/components/DataTable.tsx`
- Create: `src/components/InsightCard.tsx`
- Create: `src/components/TagBadge.tsx`
- Create: `src/mock/marketOverview.ts`
- Create: `src/mock/stocks.ts`
- Create: `src/mock/indices.ts`
- Create: `src/mock/recommendations.ts`
- Modify: `src/styles/app-shell.css`

- [ ] **Step 1: Add a small component contract test for the metric card and ranking list**

Create `src/components/MetricCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";

import { MetricCard } from "./MetricCard";
import { RankingList } from "./RankingList";

describe("Shared finance components", () => {
  it("renders key market metrics", () => {
    render(<MetricCard label="上证指数" value="3,245.55" delta="+0.82%" tone="positive" />);

    expect(screen.getByText("上证指数")).toBeInTheDocument();
    expect(screen.getByText("3,245.55")).toBeInTheDocument();
    expect(screen.getByText("+0.82%")).toHaveAttribute("data-tone", "positive");
  });

  it("renders a ranking list with item labels", () => {
    render(
      <RankingList
        title="涨幅榜"
        items={[
          { name: "宁德时代", value: "+6.2%" },
          { name: "比亚迪", value: "+4.8%" },
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: "涨幅榜" })).toBeInTheDocument();
    expect(screen.getByText("宁德时代")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the component test and verify it fails because those components do not exist yet**

Run:

```bash
npx vitest run src/components/MetricCard.test.tsx
```

Expected: FAIL with missing module errors.

- [ ] **Step 3: Implement the reusable components and mock data files**

Create `src/components/MetricCard.tsx`:

```tsx
export function MetricCard({
  label,
  value,
  delta,
  tone,
}: {
  label: string;
  value: string;
  delta: string;
  tone: "positive" | "negative" | "neutral";
}) {
  return (
    <article className="metric-card">
      <p>{label}</p>
      <strong>{value}</strong>
      <span data-tone={tone}>{delta}</span>
    </article>
  );
}
```

Create `src/components/ChartPanel.tsx`:

```tsx
import { PropsWithChildren } from "react";

export function ChartPanel({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <section className="panel chart-panel">
      <header className="panel__header">
        <h2>{title}</h2>
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
```

Create `src/components/RankingList.tsx`:

```tsx
export interface RankingItem {
  name: string;
  value: string;
}

export function RankingList({ title, items }: { title: string; items: RankingItem[] }) {
  return (
    <section className="panel ranking-list">
      <header className="panel__header">
        <h2>{title}</h2>
      </header>
      <ul>
        {items.map((item) => (
          <li key={item.name}>
            <span>{item.name}</span>
            <strong>{item.value}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}
```

Create `src/components/DataTable.tsx`:

```tsx
export interface DataTableColumn<Row> {
  key: keyof Row;
  label: string;
}

export function DataTable<Row extends { code: string }>({
  columns,
  rows,
}: {
  columns: DataTableColumn<Row>[];
  rows: Row[];
}) {
  return (
    <section className="panel data-table">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={String(column.key)}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.code}>
              {columns.map((column) => (
                <td key={String(column.key)}>{String(row[column.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
```

Create `src/components/InsightCard.tsx`:

```tsx
import { PropsWithChildren } from "react";

export function InsightCard({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <section className="panel insight-card">
      <header className="panel__header">
        <h2>{title}</h2>
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
```

Create `src/components/TagBadge.tsx`:

```tsx
export function TagBadge({ label }: { label: string }) {
  return <span className="tag-badge">{label}</span>;
}
```

Create `src/mock/marketOverview.ts`:

```ts
export const marketMetrics = [
  { label: "上证指数", value: "3,245.55", delta: "+0.82%", tone: "positive" as const },
  { label: "深证成指", value: "10,422.88", delta: "+1.10%", tone: "positive" as const },
  { label: "创业板指", value: "2,094.41", delta: "-0.23%", tone: "negative" as const },
];

export const topGainers = [
  { name: "宁德时代", value: "+6.2%" },
  { name: "比亚迪", value: "+4.8%" },
  { name: "东方财富", value: "+4.2%" },
];

export const topLosers = [
  { name: "海天味业", value: "-3.1%" },
  { name: "中国中免", value: "-2.8%" },
  { name: "五粮液", value: "-2.1%" },
];
```

Create `src/mock/stocks.ts`:

```ts
export const stockRows = [
  { code: "300750", name: "宁德时代", sector: "新能源", price: "188.55", change: "+6.2%" },
  { code: "002594", name: "比亚迪", sector: "汽车", price: "221.88", change: "+4.8%" },
  { code: "600519", name: "贵州茅台", sector: "白酒", price: "1,608.00", change: "+0.6%" },
];
```

Create `src/mock/indices.ts`:

```ts
export const indexSeries = [
  { name: "上证指数", value: 3245.55 },
  { name: "深证成指", value: 10422.88 },
  { name: "创业板指", value: 2094.41 },
];
```

Create `src/mock/recommendations.ts`:

```ts
export const recommendationGroups = {
  conservative: [{ code: "600036", name: "招商银行", reasonZh: "盈利稳定，分红记录较强。", reasonEn: "Stable earnings with strong dividend history." }],
  stable: [{ code: "600900", name: "长江电力", reasonZh: "防御属性较强，现金流稳健。", reasonEn: "Defensive profile with durable cash flows." }],
  balanced: [{ code: "600519", name: "贵州茅台", reasonZh: "龙头地位稳固，基本面扎实。", reasonEn: "Category leader with strong fundamentals." }],
  growth: [{ code: "300750", name: "宁德时代", reasonZh: "成长属性明显，行业景气度高。", reasonEn: "High-growth business in a strong sector." }],
  aggressive: [{ code: "688111", name: "金山办公", reasonZh: "估值波动更大，但成长弹性更强。", reasonEn: "Higher volatility with stronger growth optionality." }],
} as const;
```

Append to `src/styles/app-shell.css`:

```css
.panel,
.metric-card {
  padding: 20px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background: linear-gradient(180deg, var(--bg-panel-strong), var(--bg-panel));
  box-shadow: var(--shadow-panel);
}

.metric-card strong {
  display: block;
  margin: 8px 0;
  font-size: 1.8rem;
}

.metric-card [data-tone="positive"] {
  color: #34d399;
}

.metric-card [data-tone="negative"] {
  color: #f87171;
}

.panel__header {
  margin-bottom: 16px;
}

.ranking-list ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 10px;
}

.ranking-list li,
.data-table tbody tr {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.tag-badge {
  display: inline-flex;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.18);
  color: #bfdbfe;
}
```

- [ ] **Step 4: Run the shared component test**

Run:

```bash
npx vitest run src/components/MetricCard.test.tsx
```

Expected: PASS with both component assertions green.

- [ ] **Step 5: Commit the component foundation**

Run:

```bash
git add src/components src/mock src/styles/app-shell.css
git commit -m "feat: add shared finance components and mock data"
```

## Task 5: Build the Market Overview page

**Files:**
- Create: `src/features/market-overview/MarketOverviewPage.tsx`
- Modify: `src/app/router.tsx`
- Test: `src/features/market-overview/MarketOverviewPage.test.tsx`

- [ ] **Step 1: Write the failing Market Overview page test**

Create `src/features/market-overview/MarketOverviewPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";

import { MarketOverviewPage } from "./MarketOverviewPage";

describe("MarketOverviewPage", () => {
  it("renders key metrics plus gainers and losers panels", () => {
    render(<MarketOverviewPage />);

    expect(screen.getByText("上证指数")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "涨幅榜" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "跌幅榜" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the page test and verify it fails because the page has not been implemented**

Run:

```bash
npx vitest run src/features/market-overview/MarketOverviewPage.test.tsx
```

Expected: FAIL with a missing module error.

- [ ] **Step 3: Implement the Market Overview page and wire it into the router**

Create `src/features/market-overview/MarketOverviewPage.tsx`:

```tsx
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AppShell } from "../../app/layout/AppShell";
import { useAppState } from "../../app/state/app-state";
import { ChartPanel } from "../../components/ChartPanel";
import { InsightCard } from "../../components/InsightCard";
import { MetricCard } from "../../components/MetricCard";
import { RankingList } from "../../components/RankingList";
import { getMessages } from "../../i18n/messages";
import { marketMetrics, topGainers, topLosers } from "../../mock/marketOverview";

const overviewTrend = [
  { label: "09:30", value: 3210 },
  { label: "10:30", value: 3224 },
  { label: "11:30", value: 3232 },
  { label: "13:30", value: 3238 },
  { label: "14:30", value: 3245 },
  { label: "15:00", value: 3246 },
];

export function MarketOverviewPage() {
  const { locale } = useAppState();
  const message = getMessages(locale);
  const trendTitle = locale === "zh-CN" ? "日内走势" : "Intraday Trend";
  const snapshotTitle = locale === "zh-CN" ? "市场快照" : "Market Snapshot";
  const gainersTitle = locale === "zh-CN" ? "涨幅榜" : "Top Gainers";
  const losersTitle = locale === "zh-CN" ? "跌幅榜" : "Top Losers";
  const snapshotBody =
    locale === "zh-CN"
      ? "新能源与高股息板块共同支撑指数，北向资金保持净流入节奏。"
      : "New energy and high-dividend sectors are leading while northbound flows remain positive.";

  return (
    <AppShell title={message.nav.overview} subtitle={message.subtitles.overview}>
      <div className="metrics-row">
        {marketMetrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>
      <div className="overview-main-row">
        <ChartPanel title={trendTitle}>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={overviewTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
              <XAxis dataKey="label" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" />
              <Tooltip />
              <Area type="monotone" dataKey="value" stroke="#3b82f6" fill="rgba(59,130,246,0.25)" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartPanel>
        <InsightCard title={snapshotTitle}>
          <p>{snapshotBody}</p>
        </InsightCard>
      </div>
      <div className="overview-lists-row">
        <RankingList title={gainersTitle} items={topGainers} />
        <RankingList title={losersTitle} items={topLosers} />
      </div>
    </AppShell>
  );
}
```

Modify `src/app/router.tsx`:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { MarketOverviewPage } from "../features/market-overview/MarketOverviewPage";
import { getMessages, MessageCatalog } from "../i18n/messages";
import { useAppState } from "./state/app-state";
import { AppShell } from "./layout/AppShell";

type RouteKey = keyof MessageCatalog["nav"];

function PlaceholderPage({ routeKey }: { routeKey: RouteKey }) {
  const { locale } = useAppState();
  const message = getMessages(locale);

  return (
    <AppShell title={message.nav[routeKey]} subtitle={message.subtitles[routeKey]}>
      <section />
    </AppShell>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MarketOverviewPage />} />
        <Route path="/stocks" element={<PlaceholderPage routeKey="stocks" />} />
        <Route path="/indices" element={<PlaceholderPage routeKey="indices" />} />
        <Route path="/risk-assessment" element={<PlaceholderPage routeKey="risk" />} />
        <Route path="/recommendations" element={<PlaceholderPage routeKey="recommendations" />} />
      </Routes>
    </BrowserRouter>
  );
}
```

Append to `src/styles/app-shell.css`:

```css
.metrics-row,
.overview-lists-row {
  display: grid;
  gap: 20px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.overview-main-row {
  display: grid;
  gap: 20px;
  grid-template-columns: 1.7fr 1fr;
}
```

- [ ] **Step 4: Run the Market Overview tests and the original shell smoke test**

Run:

```bash
npx vitest run src/features/market-overview/MarketOverviewPage.test.tsx src/app/App.test.tsx
```

Expected: PASS with the overview route now rendering real dashboard content.

- [ ] **Step 5: Commit the Market Overview page**

Run:

```bash
git add src/features/market-overview src/app/router.tsx src/styles/app-shell.css
git commit -m "feat: add market overview dashboard page"
```

## Task 6: Build the Chinese Stocks and Chinese Indices pages

**Files:**
- Create: `src/features/chinese-stocks/ChineseStocksPage.tsx`
- Create: `src/features/chinese-stocks/StockFilters.tsx`
- Create: `src/features/chinese-indices/ChineseIndicesPage.tsx`
- Create: `src/features/chinese-indices/IndexComparisonPanel.tsx`
- Modify: `src/app/router.tsx`
- Test: `src/features/chinese-stocks/ChineseStocksPage.test.tsx`
- Test: `src/features/chinese-indices/ChineseIndicesPage.test.tsx`

- [ ] **Step 1: Write failing tests for the stocks and indices routes**

Create `src/features/chinese-stocks/ChineseStocksPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";

import { ChineseStocksPage } from "./ChineseStocksPage";

describe("ChineseStocksPage", () => {
  it("renders filters and the stock table", () => {
    render(<ChineseStocksPage />);

    expect(screen.getByLabelText("搜索股票")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
```

Create `src/features/chinese-indices/ChineseIndicesPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";

import { ChineseIndicesPage } from "./ChineseIndicesPage";

describe("ChineseIndicesPage", () => {
  it("renders the comparison panel and index insight", () => {
    render(<ChineseIndicesPage />);

    expect(screen.getByRole("heading", { name: "指数对比" })).toBeInTheDocument();
    expect(screen.getByText("上证指数")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the page tests and verify they fail because those modules do not exist yet**

Run:

```bash
npx vitest run src/features/chinese-stocks/ChineseStocksPage.test.tsx src/features/chinese-indices/ChineseIndicesPage.test.tsx
```

Expected: FAIL with missing module errors.

- [ ] **Step 3: Implement the stocks page, filters, and indices comparison page**

Create `src/features/chinese-stocks/StockFilters.tsx`:

```tsx
export function StockFilters({
  keyword,
  onKeywordChange,
  locale,
}: {
  keyword: string;
  onKeywordChange: (value: string) => void;
  locale: "zh-CN" | "en-US";
}) {
  const label = locale === "zh-CN" ? "搜索股票" : "Search Stocks";
  const placeholderText = locale === "zh-CN" ? "输入名称或代码" : "Search by company or ticker";

  return (
    <label className="stock-filter">
      <span>{label}</span>
      <input
        aria-label={label}
        value={keyword}
        onChange={(event) => onKeywordChange(event.target.value)}
        placeholder={placeholderText}
      />
    </label>
  );
}
```

Create `src/features/chinese-stocks/ChineseStocksPage.tsx`:

```tsx
import { useMemo, useState } from "react";

import { AppShell } from "../../app/layout/AppShell";
import { useAppState } from "../../app/state/app-state";
import { DataTable } from "../../components/DataTable";
import { InsightCard } from "../../components/InsightCard";
import { getMessages } from "../../i18n/messages";
import { stockRows } from "../../mock/stocks";
import { StockFilters } from "./StockFilters";

export function ChineseStocksPage() {
  const { locale } = useAppState();
  const [keyword, setKeyword] = useState("");
  const message = getMessages(locale);
  const stockInsightTitle = locale === "zh-CN" ? "观察提示" : "Watchlist Insight";
  const stockInsightBody =
    locale === "zh-CN"
      ? "优先关注成交活跃、趋势强化且与风险偏好匹配的标的。"
      : "Prioritize liquid names with strengthening trends that still fit the selected risk profile.";
  const columns =
    locale === "zh-CN"
      ? [
          { key: "code", label: "代码" },
          { key: "name", label: "名称" },
          { key: "sector", label: "行业" },
          { key: "price", label: "价格" },
          { key: "change", label: "涨跌幅" },
        ]
      : [
          { key: "code", label: "Ticker" },
          { key: "name", label: "Name" },
          { key: "sector", label: "Sector" },
          { key: "price", label: "Price" },
          { key: "change", label: "Change" },
        ];

  const rows = useMemo(
    () =>
      stockRows.filter((row) => row.name.includes(keyword) || row.code.includes(keyword)),
    [keyword],
  );

  return (
    <AppShell title={message.nav.stocks} subtitle={message.subtitles.stocks}>
      <StockFilters keyword={keyword} locale={locale} onKeywordChange={setKeyword} />
      <div className="overview-main-row">
        <DataTable columns={columns} rows={rows} />
        <InsightCard title={stockInsightTitle}>
          <p>{stockInsightBody}</p>
        </InsightCard>
      </div>
    </AppShell>
  );
}
```

Create `src/features/chinese-indices/IndexComparisonPanel.tsx`:

```tsx
import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis } from "recharts";

import { indexSeries } from "../../mock/indices";

export function IndexComparisonPanel() {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={indexSeries}>
        <XAxis dataKey="name" stroke="#94a3b8" />
        <YAxis stroke="#94a3b8" />
        <Bar dataKey="value" fill="#10b981" radius={[8, 8, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
```

Create `src/features/chinese-indices/ChineseIndicesPage.tsx`:

```tsx
import { AppShell } from "../../app/layout/AppShell";
import { useAppState } from "../../app/state/app-state";
import { ChartPanel } from "../../components/ChartPanel";
import { InsightCard } from "../../components/InsightCard";
import { getMessages } from "../../i18n/messages";
import { indexSeries } from "../../mock/indices";
import { IndexComparisonPanel } from "./IndexComparisonPanel";

export function ChineseIndicesPage() {
  const { locale } = useAppState();
  const message = getMessages(locale);
  const comparisonTitle = locale === "zh-CN" ? "指数对比" : "Index Comparison";
  const insightTitle = locale === "zh-CN" ? "指数解读" : "Index Insight";
  const insightBody =
    locale === "zh-CN"
      ? `${indexSeries.map((item) => item.name).join("、")} 共同构成市场观察主轴。`
      : `${indexSeries.map((item) => item.name).join(", ")} anchor the market structure view.`;

  return (
    <AppShell title={message.nav.indices} subtitle={message.subtitles.indices}>
      <div className="overview-main-row">
        <ChartPanel title={comparisonTitle}>
          <IndexComparisonPanel />
        </ChartPanel>
        <InsightCard title={insightTitle}>
          <p>{insightBody}</p>
        </InsightCard>
      </div>
    </AppShell>
  );
}
```

Modify `src/app/router.tsx`:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { ChineseIndicesPage } from "../features/chinese-indices/ChineseIndicesPage";
import { ChineseStocksPage } from "../features/chinese-stocks/ChineseStocksPage";
import { MarketOverviewPage } from "../features/market-overview/MarketOverviewPage";
import { getMessages, MessageCatalog } from "../i18n/messages";
import { useAppState } from "./state/app-state";
import { AppShell } from "./layout/AppShell";

type RouteKey = keyof MessageCatalog["nav"];

function PlaceholderPage({ routeKey }: { routeKey: RouteKey }) {
  const { locale } = useAppState();
  const message = getMessages(locale);

  return (
    <AppShell title={message.nav[routeKey]} subtitle={message.subtitles[routeKey]}>
      <section />
    </AppShell>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MarketOverviewPage />} />
        <Route path="/stocks" element={<ChineseStocksPage />} />
        <Route path="/indices" element={<ChineseIndicesPage />} />
        <Route path="/risk-assessment" element={<PlaceholderPage routeKey="risk" />} />
        <Route path="/recommendations" element={<PlaceholderPage routeKey="recommendations" />} />
      </Routes>
    </BrowserRouter>
  );
}
```

Append to `src/styles/app-shell.css`:

```css
.stock-filter {
  display: grid;
  gap: 8px;
  max-width: 360px;
}

.stock-filter input {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--border-subtle);
  background: rgba(15, 23, 42, 0.6);
  color: var(--text-primary);
}

.data-table table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 12px 10px;
  text-align: left;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}
```

- [ ] **Step 4: Run the stocks and indices page tests**

Run:

```bash
npx vitest run src/features/chinese-stocks/ChineseStocksPage.test.tsx src/features/chinese-indices/ChineseIndicesPage.test.tsx
```

Expected: PASS with filters, table, and comparison panel all rendering.

- [ ] **Step 5: Commit the stocks and indices pages**

Run:

```bash
git add src/features/chinese-stocks src/features/chinese-indices src/styles/app-shell.css
git commit -m "feat: add stock and index market pages"
```

## Task 7: Build the risk questionnaire and personalized recommendations

**Files:**
- Create: `src/features/risk-assessment/RiskQuestionnaireWizard.tsx`
- Create: `src/features/risk-assessment/RiskAssessmentPage.tsx`
- Create: `src/features/recommendations/RecommendationDeck.tsx`
- Create: `src/features/recommendations/RecommendationsPage.tsx`
- Create: `src/features/risk-assessment/RiskAssessmentPage.test.tsx`
- Create: `src/features/recommendations/RecommendationsPage.test.tsx`
- Modify: `src/mock/questionnaire.ts`
- Modify: `src/app/router.tsx`

- [ ] **Step 1: Write failing questionnaire and recommendation tests**

Create `src/features/risk-assessment/RiskAssessmentPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../../app/App";

describe("RiskAssessmentPage", () => {
  it("completes the six-question flow and shows the result summary", async () => {
    const user = userEvent.setup();

    render(<App />);

    await user.click(screen.getByRole("link", { name: "风险评估" }));

    for (let index = 0; index < 6; index += 1) {
      await user.click(screen.getAllByRole("radio")[1]);
      await user.click(screen.getByRole("button", { name: /下一题|提交/ }));
    }

    expect(screen.getByText("你的风险类型")).toBeInTheDocument();
  });
});
```

Create `src/features/recommendations/RecommendationsPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../../app/App";

describe("RecommendationsPage", () => {
  it("shows an empty guidance state before questionnaire completion", async () => {
    const user = userEvent.setup();

    render(<App />);
    await user.click(screen.getByRole("link", { name: "个性化推荐" }));

    expect(screen.getByText("先完成风险评估")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the questionnaire and recommendation tests and verify they fail**

Run:

```bash
npx vitest run src/features/risk-assessment/RiskAssessmentPage.test.tsx src/features/recommendations/RecommendationsPage.test.tsx
```

Expected: FAIL because the routes are still shell stubs without questionnaire behavior.

- [ ] **Step 3: Implement localized questionnaire content, the questionnaire flow, and recommendation rendering**

Replace `src/mock/questionnaire.ts`:

```ts
export const questionnaire = [
  {
    id: 1,
    promptZh: "面对短期波动，你更倾向于？",
    promptEn: "How do you usually react to short-term volatility?",
    answers: [
      { labelZh: "尽量避开亏损", labelEn: "Avoid losses whenever possible", score: 1 },
      { labelZh: "接受一定波动", labelEn: "Accept moderate fluctuations", score: 3 },
      { labelZh: "愿意追求更高收益", labelEn: "Pursue higher upside", score: 5 },
    ],
  },
  {
    id: 2,
    promptZh: "你的投资期限通常是？",
    promptEn: "What is your typical investment horizon?",
    answers: [
      { labelZh: "1 年以内", labelEn: "Less than 1 year", score: 1 },
      { labelZh: "1-3 年", labelEn: "1 to 3 years", score: 3 },
      { labelZh: "3 年以上", labelEn: "More than 3 years", score: 5 },
    ],
  },
  {
    id: 3,
    promptZh: "如果持仓下跌 10%，你会？",
    promptEn: "If a position drops 10%, what do you do?",
    answers: [
      { labelZh: "立即减仓", labelEn: "Reduce immediately", score: 1 },
      { labelZh: "观察一段时间", labelEn: "Wait and observe", score: 3 },
      { labelZh: "考虑加仓", labelEn: "Consider adding", score: 5 },
    ],
  },
  {
    id: 4,
    promptZh: "你更看重哪类目标？",
    promptEn: "Which goal matters most to you?",
    answers: [
      { labelZh: "本金安全", labelEn: "Capital preservation", score: 1 },
      { labelZh: "稳中求进", labelEn: "Steady growth", score: 3 },
      { labelZh: "收益最大化", labelEn: "Maximum returns", score: 5 },
    ],
  },
  {
    id: 5,
    promptZh: "你对权益类产品的熟悉程度？",
    promptEn: "How familiar are you with equity investing?",
    answers: [
      { labelZh: "较少接触", labelEn: "Limited experience", score: 1 },
      { labelZh: "有一定经验", labelEn: "Some experience", score: 3 },
      { labelZh: "比较熟悉", labelEn: "Very familiar", score: 5 },
    ],
  },
  {
    id: 6,
    promptZh: "在组合配置中，你愿意给高波动资产多大比例？",
    promptEn: "How much of your portfolio can you allocate to higher-volatility assets?",
    answers: [
      { labelZh: "10% 以下", labelEn: "Below 10%", score: 1 },
      { labelZh: "10%-30%", labelEn: "10% to 30%", score: 3 },
      { labelZh: "30% 以上", labelEn: "Above 30%", score: 5 },
    ],
  },
];
```

Create `src/features/risk-assessment/RiskQuestionnaireWizard.tsx`:

```tsx
import { useMemo, useState } from "react";

import { useAppState } from "../../app/state/app-state";
import { questionnaire } from "../../mock/questionnaire";

export function RiskQuestionnaireWizard({
  onComplete,
}: {
  onComplete: (profile: "conservative" | "stable" | "balanced" | "growth" | "aggressive") => void;
}) {
  const { locale } = useAppState();
  const [stepIndex, setStepIndex] = useState(0);
  const [scores, setScores] = useState<number[]>([]);

  const currentQuestion = questionnaire[stepIndex];
  const selectedScore = scores[stepIndex] ?? null;

  const buttonLabel = stepIndex === questionnaire.length - 1 ? "提交" : "下一题";
  const localizedButtonLabel =
    locale === "zh-CN"
      ? buttonLabel
      : stepIndex === questionnaire.length - 1
        ? "Submit"
        : "Next";
  const progressLabel =
    locale === "zh-CN"
      ? `第 ${stepIndex + 1} / ${questionnaire.length} 题`
      : `Question ${stepIndex + 1} of ${questionnaire.length}`;

  const profile = useMemo(() => {
    const total = scores.reduce((sum, score) => sum + score, 0);
    if (total <= 8) return "conservative";
    if (total <= 12) return "stable";
    if (total <= 18) return "balanced";
    if (total <= 24) return "growth";
    return "aggressive";
  }, [scores]);

  function handleSelect(score: number) {
    const next = [...scores];
    next[stepIndex] = score;
    setScores(next);
  }

  function handleNext() {
    if (stepIndex === questionnaire.length - 1) {
      onComplete(profile);
      return;
    }

    setStepIndex(stepIndex + 1);
  }

  return (
    <section className="panel questionnaire-panel">
      <p>{progressLabel}</p>
      <h2>{locale === "zh-CN" ? currentQuestion.promptZh : currentQuestion.promptEn}</h2>
      <div className="questionnaire-options">
        {currentQuestion.answers.map((answer) => (
          <label
            key={locale === "zh-CN" ? answer.labelZh : answer.labelEn}
            className="questionnaire-option"
          >
            <input
              type="radio"
              checked={selectedScore === answer.score}
              onChange={() => handleSelect(answer.score)}
            />
            <span>{locale === "zh-CN" ? answer.labelZh : answer.labelEn}</span>
          </label>
        ))}
      </div>
      <button disabled={selectedScore === null} onClick={handleNext} type="button">
        {localizedButtonLabel}
      </button>
    </section>
  );
}
```

Create `src/features/risk-assessment/RiskAssessmentPage.tsx`:

```tsx
import { AppShell } from "../../app/layout/AppShell";
import { useAppState } from "../../app/state/app-state";
import { getMessages } from "../../i18n/messages";
import { RiskQuestionnaireWizard } from "./RiskQuestionnaireWizard";

const profileLabels = {
  conservative: "保守型",
  stable: "稳健型",
  balanced: "平衡型",
  growth: "成长型",
  aggressive: "进取型",
} as const;

export function RiskAssessmentPage() {
  const { locale, riskProfile, setRiskProfile } = useAppState();
  const message = getMessages(locale);

  return (
    <AppShell title={message.nav.risk} subtitle={message.subtitles.risk}>
      <RiskQuestionnaireWizard onComplete={setRiskProfile} />
      {riskProfile ? (
        <p>{locale === "zh-CN" ? `你的风险类型：${profileLabels[riskProfile]}` : `Your risk profile: ${riskProfile}`}</p>
      ) : null}
    </AppShell>
  );
}
```

Create `src/features/recommendations/RecommendationDeck.tsx`:

```tsx
import { recommendationGroups } from "../../mock/recommendations";

export function RecommendationDeck({
  profile,
  locale,
}: {
  profile: keyof typeof recommendationGroups;
  locale: "zh-CN" | "en-US";
}) {
  return (
    <div className="recommendation-grid">
      {recommendationGroups[profile].map((item) => (
        <article key={item.code} className="panel">
          <h3>{item.name}</h3>
          <p>{item.code}</p>
          <p>{locale === "zh-CN" ? item.reasonZh : item.reasonEn}</p>
        </article>
      ))}
    </div>
  );
}
```

Create `src/features/recommendations/RecommendationsPage.tsx`:

```tsx
import { AppShell } from "../../app/layout/AppShell";
import { InsightCard } from "../../components/InsightCard";
import { getMessages } from "../../i18n/messages";
import { useAppState } from "../../app/state/app-state";
import { RecommendationDeck } from "./RecommendationDeck";

export function RecommendationsPage() {
  const { locale, riskProfile } = useAppState();
  const message = getMessages(locale);

  return (
    <AppShell title={message.nav.recommendations} subtitle={message.subtitles.recommendations}>
      {riskProfile ? (
        <RecommendationDeck locale={locale} profile={riskProfile} />
      ) : (
        <InsightCard title={locale === "zh-CN" ? "先完成风险评估" : "Complete the risk assessment first"}>
          <p>
            {locale === "zh-CN"
              ? "完成问卷后，这里会根据你的风险偏好展示对应的股票建议。"
              : "Once you finish the questionnaire, this page will show stock ideas matched to your risk profile."}
          </p>
        </InsightCard>
      )}
    </AppShell>
  );
}
```

Modify `src/app/router.tsx`:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { ChineseIndicesPage } from "../features/chinese-indices/ChineseIndicesPage";
import { ChineseStocksPage } from "../features/chinese-stocks/ChineseStocksPage";
import { MarketOverviewPage } from "../features/market-overview/MarketOverviewPage";
import { RecommendationsPage } from "../features/recommendations/RecommendationsPage";
import { RiskAssessmentPage } from "../features/risk-assessment/RiskAssessmentPage";

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MarketOverviewPage />} />
        <Route path="/stocks" element={<ChineseStocksPage />} />
        <Route path="/indices" element={<ChineseIndicesPage />} />
        <Route path="/risk-assessment" element={<RiskAssessmentPage />} />
        <Route path="/recommendations" element={<RecommendationsPage />} />
      </Routes>
    </BrowserRouter>
  );
}
```

Append to `src/styles/app-shell.css`:

```css
.questionnaire-panel {
  max-width: 840px;
}

.questionnaire-options {
  display: grid;
  gap: 12px;
  margin: 20px 0;
}

.questionnaire-option {
  display: flex;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
}

.questionnaire-panel button {
  width: fit-content;
  padding: 12px 18px;
  border: 0;
  border-radius: 12px;
  background: linear-gradient(90deg, #2563eb, #10b981);
  color: white;
}

.recommendation-grid {
  display: grid;
  gap: 20px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
```

- [ ] **Step 4: Run the questionnaire, recommendation, and app-shell tests**

Run:

```bash
npx vitest run src/features/risk-assessment/RiskAssessmentPage.test.tsx src/features/recommendations/RecommendationsPage.test.tsx src/app/App.test.tsx
```

Expected: PASS with the questionnaire producing a risk result and the recommendation page showing the guidance state before completion.

- [ ] **Step 5: Commit the risk and recommendation flow**

Run:

```bash
git add src/features/risk-assessment src/features/recommendations src/styles/app-shell.css
git commit -m "feat: add risk questionnaire and recommendations flow"
```

## Task 8: Final integration coverage and shell polish

**Files:**
- Modify: `src/app/locale.test.tsx`
- Modify: `src/features/recommendations/RecommendationsPage.test.tsx`
- Modify: `src/styles/app-shell.css`

- [ ] **Step 1: Add final integration assertions for English recommendation copy and fallback-safe shell behavior**

Append to `src/features/recommendations/RecommendationsPage.test.tsx`:

```tsx
it("renders English recommendation copy after switching locale and completing the questionnaire", async () => {
  const user = userEvent.setup();

  render(<App />);

  await user.selectOptions(screen.getByLabelText("Language"), "en-US");
  await user.click(screen.getByRole("link", { name: "Risk Assessment" }));

  for (let index = 0; index < 6; index += 1) {
    await user.click(screen.getAllByRole("radio")[2]);
    await user.click(screen.getByRole("button", { name: /Next|Submit/ }));
  }

  await user.click(screen.getByRole("link", { name: "Personalized Recommendations" }));

  expect(screen.getByText(/Higher volatility|High-growth business|Stable earnings/)).toBeInTheDocument();
});
```

Append to `src/app/locale.test.tsx`:

```tsx
it("keeps the shell usable after changing locales multiple times", async () => {
  const user = userEvent.setup();

  render(<App />);

  await user.selectOptions(screen.getByLabelText("Language"), "en-US");
  await user.selectOptions(screen.getByLabelText("Language"), "zh-CN");

  expect(screen.getByRole("link", { name: "市场概览" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the full targeted suite**

Run:

```bash
npx vitest run src/app/App.test.tsx src/app/locale.test.tsx src/components/MetricCard.test.tsx src/features/market-overview/MarketOverviewPage.test.tsx src/features/chinese-stocks/ChineseStocksPage.test.tsx src/features/chinese-indices/ChineseIndicesPage.test.tsx src/features/risk-assessment/RiskAssessmentPage.test.tsx src/features/recommendations/RecommendationsPage.test.tsx
```

Expected: PASS with all targeted page, component, locale, and flow tests green.

- [ ] **Step 3: Run build verification**

Run:

```bash
npm run build
```

Expected: PASS with Vite production build output in `dist/`.

- [ ] **Step 4: Apply final shell polish for layout spacing and responsive guardrails**

Append to `src/styles/app-shell.css`:

```css
@media (max-width: 1280px) {
  .app-shell {
    grid-template-columns: 220px 1fr;
  }

  .metrics-row,
  .overview-lists-row,
  .recommendation-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .sidebar-nav {
    grid-auto-flow: column;
    grid-auto-columns: max-content;
    overflow-x: auto;
  }

  .overview-main-row,
  .metrics-row,
  .overview-lists-row,
  .recommendation-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Re-run the full targeted suite plus build**

Run:

```bash
npx vitest run src/app/App.test.tsx src/app/locale.test.tsx src/components/MetricCard.test.tsx src/features/market-overview/MarketOverviewPage.test.tsx src/features/chinese-stocks/ChineseStocksPage.test.tsx src/features/chinese-indices/ChineseIndicesPage.test.tsx src/features/risk-assessment/RiskAssessmentPage.test.tsx src/features/recommendations/RecommendationsPage.test.tsx
npm run build
```

Expected: PASS on both commands after the final CSS update.

- [ ] **Step 6: Commit the integration pass**

Run:

```bash
git add src/app/locale.test.tsx src/features/recommendations/RecommendationsPage.test.tsx src/styles/app-shell.css
git commit -m "test: finalize finance dashboard shell coverage"
```
