interface PageHeaderProps {
  subtitle: string;
  title: string;
}

export function PageHeader({ subtitle, title }: PageHeaderProps) {
  return (
    <section className="page-header">
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </section>
  );
}
