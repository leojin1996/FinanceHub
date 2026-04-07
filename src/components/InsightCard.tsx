import type { PropsWithChildren } from "react";

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
