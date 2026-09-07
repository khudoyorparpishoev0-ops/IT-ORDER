import { STATUS } from '@/data/status';
import type { RequestStatus } from '@/api/types';

/** Статус всегда цвет + слово: точка-индикатор и подпись. */
export function StatusBadge({ status }: { status: RequestStatus }) {
  const s = STATUS[status];
  return (
    <span className="badge" style={{ background: s.bg, color: s.fg }}>
      <span className="dot" style={{ background: s.dot }} aria-hidden="true" />
      {s.label}
    </span>
  );
}
