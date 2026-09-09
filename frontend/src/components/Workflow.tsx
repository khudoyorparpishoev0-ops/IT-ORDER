import { STATUS } from '@/data/status';
import { days } from '@/data/format';
import type { RequestDetail, RequestStatus } from '@/api/types';

/** Основной путь заявки. Ветви «Выдано со склада» и «Отклонена» — отдельно. */
const MAIN: RequestStatus[] = ['draft', 'pending', 'sourcing', 'priced', 'approved', 'paid'];

const STAGE_INDEX: Record<RequestStatus, number> = {
  draft: 0,
  pending: 1,
  sourcing: 2,
  priced: 3,
  approved: 4,
  paid: 5,
  fulfilled: 3,
  rejected: -1,
};

/** Даты входа в этап — из событий истории (первое подходящее событие). */
const EVENT_OF_STAGE: Record<RequestStatus, string[]> = {
  draft: ['created'],
  pending: ['submitted'],
  sourcing: ['sourcing'],
  priced: ['priced'],
  approved: ['approved', 'auto_approved'],
  paid: ['paid'],
  fulfilled: ['fulfilled'],
  rejected: ['rejected'],
};

function stageDate(detail: RequestDetail, stage: RequestStatus): string | null {
  const kinds = EVENT_OF_STAGE[stage];
  const event = detail.events.find((e) => kinds.includes(e.kind));
  if (!event) return stage === 'draft' ? detail.date.slice(0, 5) : null;
  // «ИВАН ПЕТРОВ · 04.09.2026, 18:12» → 04.09
  const m = /(\d{2})\.(\d{2})\.\d{4}/.exec(event.meta);
  return m ? `${m[1]}.${m[2]}` : null;
}

/**
 * Лента этапов заявки. Пройденные — зелёная полоса и дата, текущий —
 * статусный цвет и «СЕЙЧАС · 2 ДНЯ», будущие — серые. Закрытая складом
 * заявка заканчивается на своей ветви, отклонённая — красным на том
 * шаге, где её остановили.
 */
export function Workflow({ detail, vertical = false }: { detail: RequestDetail; vertical?: boolean }) {
  const status = detail.status;
  const current = STAGE_INDEX[status];
  const rejectedAt = status === 'rejected' ? (detail.sourced_by ? 3 : 1) : -1;

  const steps: { key: RequestStatus; state: 'done' | 'now' | 'next' | 'rejected'; sub: string }[] = [];
  const path: RequestStatus[] = status === 'fulfilled' ? ['draft', 'pending', 'sourcing', 'fulfilled'] : MAIN;
  path.forEach((stage, i) => {
    let state: 'done' | 'now' | 'next' | 'rejected';
    if (status === 'rejected') {
      state = i < rejectedAt ? 'done' : i === rejectedAt ? 'rejected' : 'next';
    } else if (status === 'fulfilled') {
      state = stage === 'fulfilled' ? 'done' : 'done';
    } else {
      state = i < current ? 'done' : i === current ? 'now' : 'next';
    }
    let sub = '—';
    if (state === 'done') sub = stageDate(detail, stage) ?? '—';
    if (state === 'now') {
      const d = detail.awaiting_days ?? 0;
      sub = d > 0 ? `Сейчас · ${days(d)}` : 'Сейчас';
    }
    if (state === 'rejected') sub = stageDate(detail, 'rejected') ?? 'Отклонена';
    steps.push({ key: stage, state, sub });
  });
  // Закрытые благополучно: последний этап — тоже done с датой
  if (status === 'paid') steps[steps.length - 1].state = 'done';

  return (
    <ol className={`wf${vertical ? ' vertical' : ''}`} aria-label="Этапы заявки" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {steps.map((s) => (
        <li
          key={s.key}
          className={`wf-step ${s.state}`}
          style={{ ['--st' as string]: STATUS[s.key].color }}
          aria-current={s.state === 'now' ? 'step' : undefined}
        >
          <div className="wf-bar" />
          <div className="wf-name">
            {(s.state === 'now' || s.state === 'rejected') && <span className="dot" aria-hidden="true" />}
            {s.state === 'rejected' ? 'Отклонена' : STATUS[s.key].label}
          </div>
          <div className="wf-sub">{s.sub}</div>
        </li>
      ))}
    </ol>
  );
}
