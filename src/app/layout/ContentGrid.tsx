import type { ReactNode } from "react";

interface ContentGridProps {
  children: ReactNode;
}

export function ContentGrid({ children }: ContentGridProps) {
  return <section className="content-grid">{children}</section>;
}
