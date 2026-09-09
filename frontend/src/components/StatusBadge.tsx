import { STATUS } from '@/data/status';
import type { RequestStatus } from '@/api/types';

/** Статус всегда цвет + слово: точка 6 px и подпись в рамке статусного цвета. */
export function StatusBadge({ status, inline = false }: { status: RequestStatus; inline?: boolean }) {
  const s = STATUS[status];
  return (
    <span className={inline ? 'status-inline' : 'status'} style={{ ['--st' as string]: s.color }}>
      <span className="dot" aria-hidden="true" />
      {s.label}
    </span>
  );
}
