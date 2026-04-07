import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface IndexComparisonPanelProps {
  ariaLabel: string;
  data: { name: string; value: number }[];
}

export function IndexComparisonPanel({ ariaLabel, data }: IndexComparisonPanelProps) {
  return (
    <div aria-label={ariaLabel} className="index-comparison-panel" role="img">
      <ResponsiveContainer height={280} width="100%">
        <BarChart data={data}>
          <CartesianGrid opacity={0.4} stroke="var(--fh-border)" strokeDasharray="3 3" />
          <XAxis dataKey="name" stroke="var(--fh-text-muted)" tickLine={false} />
          <YAxis stroke="var(--fh-text-muted)" tickLine={false} />
          <Tooltip />
          <Bar dataKey="value" fill="#4d8fff" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
