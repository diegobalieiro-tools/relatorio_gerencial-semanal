type KpiCardProps = {
  label: string;
  value: string | number;
  description?: string;
};

export function KpiCard({ label, value, description }: KpiCardProps) {
  return (
    <article className="kpi-card">
      <p className="kpi-card__label">{label}</p>
      <p className="kpi-card__value">{value}</p>
      {description ? <p className="kpi-card__desc">{description}</p> : null}
    </article>
  );
}
