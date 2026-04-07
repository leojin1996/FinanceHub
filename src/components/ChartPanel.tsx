import type { PropsWithChildren } from "react";

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
