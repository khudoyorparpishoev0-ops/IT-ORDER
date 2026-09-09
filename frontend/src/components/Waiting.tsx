import { DELAY_DAYS, HOLDER, STATUS } from '@/data/status';
import { plural } from '@/data/format';
import type { RequestDetail, RequestListItem } from '@/api/types';

/**
 * Блок «Сейчас ждёт»: кто держит заявку и сколько дней. После порога
 * рубрика меняется на «задержка», рамка становится жёлтой — это не
 * ошибка, заявка просто задерживается.
 */
export function Waiting({ request }: { request: RequestListItem | RequestDetail }) {
  if (request.awaiting_stage === 'closed') return null;
  const d = request.awaiting_days ?? 0;
  const delayed = d >= DELAY_DAYS;
  const people = 'awaiting_people' in request ? request.awaiting_people : [];
  return (
    <div
      className={`waiting${delayed ? ' delayed' : ''}`}
      style={{ ['--st' as string]: STATUS[request.status].color }}
    >
      <div className="label">{delayed ? 'Сейчас ждёт · задержка' : 'Сейчас ждёт'}</div>
      <div className="waiting-who">{HOLDER[request.awaiting_stage] || request.awaiting_label}</div>
      <div className="small" style={{ color: 'var(--slate)' }}>
        {d > 0 ? `На этапе ${d} ${plural(d, 'день', 'дня', 'дней')}` : 'Поступила сегодня'}
        {people.length > 0 && ` · ${people.join(', ')}`}
      </div>
    </div>
  );
}

/** Короткая форма для колонки списка: «Отдел закупа · 2 дня». */
export function waitingShort(request: RequestListItem): string {
  if (request.awaiting_stage === 'closed') return '—';
  const who = HOLDER[request.awaiting_stage] || request.awaiting_label;
  const d = request.awaiting_days ?? 0;
  return d > 0 ? `${who} · ${d} ${plural(d, 'день', 'дня', 'дней')}` : `${who} · сегодня`;
}
