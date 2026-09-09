import type { ReactNode } from 'react';

/**
 * Показатель: рубрика → значение моно 30 → контекст. Никаких цветных
 * фонов; если значение статусное — перед ним точка 6 px.
 */
export function Kpi({
  label,
  value,
  note,
  dot,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  /** Цвет точки перед значением: var(--yellow) и т. п. */
  dot?: string;
}) {
  return (
    <section className="card kpi">
      <div className="label">{label}</div>
      <div className="kpi-value-row">
        {dot && <span className="dot" style={{ ['--dot' as string]: dot }} aria-hidden="true" />}
        <div className="kpi-value">{value}</div>
      </div>
      {note && <div className="kpi-note">{note}</div>}
    </section>
  );
}
