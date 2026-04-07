interface DataStatusNoticeProps {
  body?: string;
  title: string;
  tone: "info" | "warning" | "danger";
}

export function DataStatusNotice({ body, title, tone }: DataStatusNoticeProps) {
  const role = tone === "danger" ? "alert" : "status";

  return (
    <section className={`data-status-notice data-status-notice--${tone}`} role={role}>
      <strong>{title}</strong>
      {body ? <p>{body}</p> : null}
    </section>
  );
}
