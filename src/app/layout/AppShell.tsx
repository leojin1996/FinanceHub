import type { ReactNode } from "react";

import { ContentGrid } from "./ContentGrid";
import { PageHeader } from "./PageHeader";
import { TopStatusBar } from "./TopStatusBar";

interface AppShellProps {
  pageTitle: string;
  pageSubtitle: string;
  children: ReactNode;
}

export function AppShell({ pageSubtitle, pageTitle, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <div className="app-shell__workspace">
        <TopStatusBar />
        <main className="app-shell__main">
          <PageHeader subtitle={pageSubtitle} title={pageTitle} />
          <ContentGrid>{children}</ContentGrid>
        </main>
      </div>
    </div>
  );
}
