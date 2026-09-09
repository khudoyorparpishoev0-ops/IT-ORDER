import { useNavigate } from 'react-router-dom';
import { StatusBadge } from './StatusBadge';
import { waitingShort } from './Waiting';
import { money } from '@/data/format';
import type { RequestListItem } from '@/api/types';

/**
 * Таблица заявок по UI-киту: Номер · Наименование · Объект · Статус ·
 * Сейчас ждёт · Дата · Сумма. Клик по строке ведёт в карточку.
 * На телефоне строка становится карточкой: наименование → метаданные
 * моно → статус и сумма.
 */
export function RequestsTable({
  rows,
  compact = false,
  showWaiting = true,
  showProject = true,
}: {
  rows: RequestListItem[];
  /** Короткая версия для дашборда: без объекта и «сейчас ждёт». */
  compact?: boolean;
  showWaiting?: boolean;
  showProject?: boolean;
}) {
  const navigate = useNavigate();
  const project = showProject && !compact;
  const waiting = showWaiting && !compact;
  const open = (r: RequestListItem) => navigate(`/requests/${r.id}`);

  return (
    <div className="table-wrap">
      <table className="tbl cards" style={{ ['--tbl-min' as string]: compact ? '520px' : '860px' }}>
        <thead>
          <tr>
            <th>Номер</th>
            <th>Наименование</th>
            {project && <th>Объект</th>}
            <th>Статус</th>
            {waiting && <th>Сейчас ждёт</th>}
            {!compact && <th>Дата</th>}
            <th className="right">Сумма, TJS</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              className="clickable"
              tabIndex={0}
              onClick={() => open(r)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  open(r);
                }
              }}
              aria-label={`Заявка ${r.number}`}
            >
              <td className="num desktop-only">{r.number}</td>
              <td>
                <div style={{ fontWeight: 500 }} className="row-title">
                  {r.title}
                </div>
                <div className="meta mobile-meta">
                  {r.number} · {r.date} · {r.project_name}
                </div>
              </td>
              {project && (
                <td className="slate desktop-only">{r.project_name}</td>
              )}
              <td className="desktop-only">
                <StatusBadge status={r.status} />
              </td>
              {waiting && (
                <td className="desktop-only" style={{ color: r.awaiting_stage === 'closed' ? 'var(--grey)' : 'var(--slate)', fontSize: 13 }}>
                  {waitingShort(r)}
                </td>
              )}
              {!compact && <td className="mono desktop-only" style={{ color: 'var(--slate)', fontSize: 14 }}>{r.date}</td>}
              <td className="right">
                {/* На телефоне статус и сумма в одну строку под метаданными. */}
                <span className="mobile-only">
                  <StatusBadge status={r.status} inline />
                  {r.awaiting_stage !== 'closed' && r.awaiting_days ? (
                    <span className="caption">· {r.awaiting_days} дн.</span>
                  ) : null}
                </span>
                <Amount request={r} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Сумма в списке: до оценки закупа — «не оценена», со склада — 0,00. */
export function Amount({ request }: { request: RequestListItem }) {
  if (request.status === 'fulfilled') return <span className="num">0,00</span>;
  if (!request.priced) return <span className="unpriced">не оценена</span>;
  return <span className="num">{money(request.amount)}</span>;
}
