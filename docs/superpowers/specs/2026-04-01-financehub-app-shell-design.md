# FinanceHub App Shell Design

Date: 2026-04-01
Topic: FinanceHub application shell and navigation system
Language: Chinese-first product experience
Design status: Approved for specification drafting

## 1. Context

FinanceHub is a Chinese-language financial web application that will eventually include five user-facing pages:

- Chinese market overview
- Chinese stocks
- Chinese indices
- Risk assessment questionnaire
- Personalized stock recommendations

The current workspace is empty, so this specification defines the first sub-project: the application shell, navigation structure, layout system, and reusable page framework that will support the rest of the product.

The product should feel like a professional desktop-first finance dashboard and visually stay close to the reference direction shared by the user: a clean, high-density dashboard with dark navigation, layered cards, and strong chart-centric hierarchy.

## 2. Goals

This first-phase design must deliver:

- A desktop-first application shell suitable for a professional finance dashboard
- A consistent navigation system across five primary pages
- A high-fidelity visual foundation that is presentation-ready
- A reusable layout and component structure that keeps all pages within one product language
- A mock-data-first architecture that allows the UI to be built before real market data is connected
- A clean state boundary between shared cross-page state and page-local interaction state
- A locale-switching shell that defaults to Simplified Chinese and supports user-selected language display

## 3. Non-Goals

This design does not include:

- Live market data integration
- Backend services or database architecture
- Production-grade recommendation algorithms
- Full mobile-first interaction design
- SEO or SSR requirements
- Advanced account systems, authentication, or user portfolios
- Region-specific legal/compliance content adaptation beyond UI-language switching

## 4. Product Boundaries

This specification covers only the first sub-project: the shell and navigation layer for the finance application.

Within scope:

- Global shell structure
- Route hierarchy
- Layout rhythm and page composition rules
- Shared UI components
- Page responsibilities
- Mock-data organization
- Cross-page state handling
- Baseline loading, empty, and error state strategy
- Testing expectations for the shell layer

Out of scope for this spec:

- Implementation details for real API integration
- Fine-grained recommendation scoring logic
- Real-time streaming updates
- Detailed design exploration for mobile-first breakpoints

## 5. Chosen Technical Direction

The first phase should use `React + Vite + TypeScript`.

Rationale:

- The workspace is starting from scratch, so the product benefits from a lightweight setup with low initial overhead
- The first milestone is a multi-page desktop dashboard with charts and rich UI, not SEO-heavy public content
- Vite provides fast iteration and keeps the initial foundation simple while preserving a clear path to later extension
- TypeScript helps keep component contracts and mock-data models explicit from the beginning

## 6. Product Experience Principles

The shell and layout system should follow these principles:

- Desktop-first: prioritize large-screen information density and professional dashboard ergonomics
- Unified product language: all five pages should clearly feel like one coherent application
- Chart-centered hierarchy: major chart panels should anchor page composition where appropriate
- Fast scanning: users should be able to understand market state, navigate pages, and identify the next action quickly
- Professional calm: the visual system should feel precise and trustworthy rather than playful or consumer-social
- Mock-first realism: even when backed by local data, the application should look and behave like a mature product
- Chinese-first but locale-aware: the default experience is Simplified Chinese, while shell-level language switching remains available

## 7. Chosen Shell Approach

Chosen approach: a single shared application shell with route-driven page switching and a consistent page rhythm.

This means:

- One persistent left sidebar for primary navigation
- One persistent top status bar for product identity and market-state context
- One shared content container that controls spacing, width, and alignment
- Individual pages swap only the main content area
- One shell-level language switcher exposed in the persistent top status bar

This is the preferred approach because it creates the strongest product consistency, best matches the finance-dashboard reference style, and minimizes duplication when building the five-page experience.

The design intentionally avoids giving each page its own unrelated shell. It also avoids a top-navigation-only structure because side navigation better supports professional dashboard workflows and repeated switching between data-heavy views.

## 8. Primary Navigation Structure

The application should expose five top-level destinations in the left sidebar, in this order:

1. Market Overview
2. Chinese Stocks
3. Chinese Indices
4. Risk Assessment
5. Personalized Recommendations

Navigation behavior:

- The sidebar remains visible across all primary pages on desktop
- The active page is clearly highlighted
- Navigation labels are localized by the current selected locale
- Navigation should support icons plus text labels
- The shell should be designed so a compact responsive variant can exist later, but mobile navigation is not the first-phase focus

Default Simplified Chinese labels:

- 市场概览
- 中国股票
- 中国指数
- 风险评估
- 个性化推荐

## 9. Page Responsibilities

### 9.1 Market Overview

Purpose:
Provide a fast market-wide snapshot and act as the default landing page.

Layout rhythm:

- Top row: key market metric cards
- Middle row: main chart panel plus supporting insight panel
- Lower row: gainers, losers, and quick-access market modules

Content emphasis:

- Key Chinese index snapshots
- Daily movers
- Visual market trend panel
- Fast-scan supporting information

### 9.2 Chinese Stocks

Purpose:
Move the user from high-level market understanding to stock-level browsing.

Layout rhythm:

- Header with search and filter controls
- Primary stock data table occupying the largest content area
- Supporting stock detail or summary region

Content emphasis:

- Search
- Filtering
- Sorting
- Large structured stock list
- Quick summary for the selected stock

### 9.3 Chinese Indices

Purpose:
Provide index-focused analysis rather than single-stock browsing.

Layout rhythm:

- Comparative chart region as the visual anchor
- Supporting cards for index performance context
- Additional panels for grouped comparison or trend interpretation

Content emphasis:

- Major Chinese indices
- Structured comparison views
- Chart-driven market context

### 9.4 Risk Assessment

Purpose:
Collect user risk preference through a focused six-question flow.

Layout rhythm:

- Shared shell remains visible for consistency
- Main content area becomes narrower and more focused
- Questionnaire flow dominates the page instead of dashboard density

Content emphasis:

- Step clarity
- Progress feedback
- Completion confidence
- Result explanation

### 9.5 Personalized Recommendations

Purpose:
Turn risk-assessment output into understandable stock recommendations.

Layout rhythm:

- Top summary of risk profile
- Recommendation cards as the main content
- Supporting explanation panel describing why these suggestions fit the user

Content emphasis:

- Risk profile label
- Recommendation rationale
- Stock cards or grouped recommendation modules
- Empty-state guidance if no questionnaire result exists yet

## 10. Cross-Page User Journey

The five pages should not feel isolated. The intended flow is:

1. User enters the product on Market Overview
2. User explores Chinese Stocks or Chinese Indices for more detail
3. User completes the Risk Assessment
4. User lands on Personalized Recommendations informed by the questionnaire result

This relationship should influence copy, entry points, and empty states. For example, the recommendations page should guide users to the questionnaire if no risk profile has been generated.

## 11. Layout System

The shell should define a consistent layout system with these structural layers:

- `AppShell`: full-screen application wrapper
- `SidebarNav`: persistent left navigation
- `TopStatusBar`: persistent top context band
- `LanguageSwitcher`: locale selector placed within the top status bar
- `MainContent`: primary page container
- `PageHeader`: per-page title and subtitle band
- `ContentGrid`: shared spacing and responsive grid logic for interior page modules

Page composition should follow a stable rhythm:

- Top-level page header
- Summary layer
- Primary analytical layer
- Secondary supporting layer

Not every page must use every layer equally, but most dashboard pages should maintain this hierarchy to preserve product consistency.

## 12. Shared Component System

The reusable component foundation should include:

### 12.1 Shell Components

- `SidebarNav`
- `TopStatusBar`
- `LanguageSwitcher`
- `PageHeader`
- `ContentGrid`

### 12.2 High-Reuse Finance Components

- `MetricCard`: key numbers such as index value, change percent, turnover
- `ChartPanel`: line, bar, or area chart container
- `RankingList`: gainers, losers, popular lists, or other ranked summaries
- `DataTable`: stock browsing table with search and filtering support
- `InsightCard`: explanatory cards for summaries, risk tags, or recommendation reasoning
- `TagBadge`: shared visual badges for labels such as risk level, sector, or market state

### 12.3 Page-Specific Components

- `StockFilters`
- `IndexComparisonPanel`
- `RiskQuestionnaireWizard`
- `RecommendationDeck`

The design goal is to maximize shared shell and display components while keeping page-specific logic in focused modules.

## 13. Visual Direction

The visual system should stay close to the user-provided reference style in these ways:

- Dark or deep-toned navigation region
- Clean, layered card surfaces
- High information density without feeling cluttered
- Strong contrast between navigation chrome and content panels
- Clear emphasis on charts and metrics
- Professional finance-product tone rather than generic startup UI

The design should not copy the reference literally. It should borrow the same professional dashboard character and information hierarchy while adapting the content to Chinese-market finance use cases.

## 14. Mock Data Strategy

The first phase should use local mock data across the product.

Mock data principles:

- Data is organized by page or domain
- Display components receive normalized view models rather than raw file shapes where practical
- Components should not depend on where data comes from
- Replacing local data with real API data later should affect page containers more than presentational components

Suggested mock data domains:

- Market overview data
- Stock list and stock detail summary data
- Index comparison data
- Questionnaire definitions and answer mappings
- Recommendation groups keyed by risk profile
- Localized copy dictionaries for shell text, navigation labels, page headings, empty states, and recommendation explanations

## 14A. Localization Strategy

The application shell must support language selection at the product level.

Localization requirements:

- Default locale is `zh-CN` (Simplified Chinese)
- The first implementation must support at least `zh-CN` and `en-US`
- The shell exposes a visible language selector in the top status bar
- Changing language updates navigation labels, page headers, shell copy, questionnaire text, recommendation explanations, and shared empty/error state copy
- Locale resources should be organized separately from mock market data
- Missing translations should fall back to `zh-CN` rather than showing blank or raw keys

Behavior requirements:

- First visit defaults to `zh-CN`
- If the user changes the language, the selection should persist across route changes within the session
- The architecture should allow adding more locales later without rewriting the shell structure

## 15. State Boundaries

State should be separated into three layers.

### 15.1 Global Shared State

Use shared application state only for information needed across pages:

- Current navigation context
- Application-level constants or mode flags such as mock-data mode
- Risk assessment result
- Current selected locale

### 15.2 Page-Local State

Keep interaction state local when it belongs only to one page:

- Search terms
- Filter selections
- Selected stock
- Chart time-range selection
- Current questionnaire step

### 15.3 Static Data Layer

Mock content should live separately from UI state. This avoids coupling page interaction logic to the source format of the data.

## 16. Risk Assessment to Recommendation Flow

The questionnaire should produce one of five risk-profile categories:

- Conservative
- Stable
- Balanced
- Growth
- Aggressive

These should have Chinese-facing labels in the UI and map directly to recommendation datasets.

Flow requirements:

- User completes six questions
- The application calculates a risk profile
- The result is stored in shared cross-page state
- The recommendations page reads this state and renders the corresponding recommendation set
- If the user has not completed the questionnaire, the recommendations page shows a guided entry state instead of empty content

## 17. View States and Error Handling

Even though the first phase uses local mock data, the UI structure should reserve consistent state handling for future real data integration.

Major data modules should be able to represent:

- `loading`
- `empty`
- `error`

This applies especially to:

- Metric regions
- Ranking lists
- Table content
- Chart panels
- Recommendation blocks

Localization-related fallback behavior should also be defined:

- If a locale resource is unavailable, the shell falls back to `zh-CN`
- If a localized content block is missing, the UI renders the `zh-CN` version for that block

This ensures the shell and component contracts remain stable when live data is introduced.

## 18. Testing Strategy

The first phase should focus on reliable product-shell behavior rather than exhaustive visual automation.

Minimum testing coverage should validate:

- Route switching between all five primary pages
- Correct active-state behavior in the sidebar navigation
- Successful completion of the six-question risk assessment flow
- Correct recommendation rendering for different risk profiles
- Stable rendering of core shared components with representative mock data
- Language switching between `zh-CN` and `en-US`
- Simplified Chinese as the default language on first load
- Stable fallback to `zh-CN` when a localized string is unavailable

Testing should prioritize observable behavior and navigation reliability over pixel-perfect visual assertions.

## 19. Success Criteria

The app-shell first phase is successful when all of the following are true:

- All five pages are accessible through one coherent application shell
- The product visually feels close to the chosen finance-dashboard reference direction
- The left sidebar navigation and shared shell remain stable across page transitions
- Market Overview, Chinese Stocks, and Chinese Indices each have a mature dashboard-style layout
- The Risk Assessment page completes a six-question flow and outputs one of five risk profiles
- The Personalized Recommendations page reads the risk result and shows matching recommendation content
- The application runs entirely on mock data without creating component boundaries that block future real-data integration
- The application defaults to Simplified Chinese and allows the user to switch language from the shared shell

## 20. Implementation Notes for the Next Planning Step

The implementation plan should break work into small, reviewable milestones. Recommended milestone order:

1. Project scaffold and routing foundation
2. Shared shell, layout system, and localization foundation
3. Market Overview page
4. Chinese Stocks page
5. Chinese Indices page
6. Risk Assessment flow
7. Personalized Recommendations page
8. Test coverage and final polish

Each milestone should keep diffs focused and maintain a clean separation between shared shell code, page containers, and reusable components.
