/** Полоса прогресса 10 px без радиуса. Цвет по порогу: норма/внимание/перерасход. */
export function Bar({ pct, fill }: { pct: number; fill?: string }) {
  const width = Math.max(0, Math.min(100, pct));
  const color = fill ?? barTint(width);
  return (
    <div
      className="bar"
      role="progressbar"
      aria-valuenow={width}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${width}%`, background: color }} />
    </div>
  );
}

/** Пороги из хендоффа: от 90% — внимание, от 95% — перерасход. */
export function barTint(pct: number): string {
  if (pct >= 95) return 'var(--dot-err)';
  if (pct >= 90) return 'var(--dot-warn)';
  return 'var(--green)';
}
