interface MetricCardProps {
  label: string;
  value: string;
  delta: string;
  tone: "positive" | "negative" | "neutral";
}

export function MetricCard({ label, value, delta, tone }: MetricCardProps) {
  return (
    <article className="metric-card">
      <p>{label}</p>
      <strong>{value}</strong>
      <span data-tone={tone}>{delta}</span>
    </article>
  );
}
