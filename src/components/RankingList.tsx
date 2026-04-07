export interface RankingItem {
  name: string;
  value: string;
}

interface RankingListProps {
  title: string;
  items: RankingItem[];
}

export function RankingList({ title, items }: RankingListProps) {
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
