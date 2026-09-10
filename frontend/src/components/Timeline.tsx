import { useState } from 'react';
import { PAYMENT_METHOD } from '@/data/status';
import type { EventDetails, EventKind, RequestEvent, RequestViewer } from '@/api/types';

/**
 * История заявки: кто что сделал, когда и что именно изменилось.
 *
 * Лента идёт сверху вниз от свежего к старому — так её и читают: «что
 * случилось последним». Каждое событие показывает не только фразу, но и
 * «было → стало»: текст пишется для человека и меняется свободно, а
 * подробности приходят полями и не зависят от формулировки.
 *
 * Просмотры в ленту не попадают: карточку открывают десятки раз, и
 * события, ради которых её открыли, утонули бы. Они лежат отдельной
 * вкладкой «Кто видел».
 */

type Tab = 'all' | 'decisions' | 'changes' | 'money' | 'comments' | 'viewers';

const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'Все' },
  { key: 'decisions', label: 'Решения' },
  { key: 'changes', label: 'Изменения' },
  { key: 'money', label: 'Деньги' },
  { key: 'comments', label: 'Комментарии' },
  { key: 'viewers', label: 'Кто видел' },
];

const OF_TAB: Record<Exclude<Tab, 'all' | 'viewers'>, EventKind[]> = {
  decisions: ['submitted', 'sourcing', 'approved', 'auto_approved', 'rejected', 'fulfilled'],
  changes: ['created', 'edited'],
  money: ['priced', 'paid'],
  comments: ['commented'],
};

/** Цвет точки события. Отказ — красный, деньги — зелёный, остальное серое. */
const TONE: Partial<Record<EventKind, string>> = {
  rejected: 'var(--dot-err)',
  paid: 'var(--green)',
  approved: 'var(--green)',
  auto_approved: 'var(--green)',
  fulfilled: 'var(--green)',
};

export function Timeline({
  events,
  viewers,
}: {
  events: RequestEvent[];
  viewers: RequestViewer[];
}) {
  const [tab, setTab] = useState<Tab>('all');

  const shown =
    tab === 'all' || tab === 'viewers'
      ? events
      : events.filter((e) => OF_TAB[tab].includes(e.kind));

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="h3">История</h2>
      </div>

      <div className="filter-row" role="tablist" aria-label="Что показывать в истории">
        {TABS.map((t) => {
          // Вкладку без единой записи не показываем: пустая вкладка
          // обещает содержимое, которого нет, и её нажимают зря.
          const count =
            t.key === 'viewers'
              ? viewers.length
              : t.key === 'all'
                ? events.length
                : events.filter((e) => OF_TAB[t.key as keyof typeof OF_TAB].includes(e.kind)).length;
          if (count === 0 && t.key !== 'all') return null;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              className="filter"
              aria-pressed={tab === t.key}
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
            >
              {t.label}
              <span className="num" style={{ color: 'var(--slate)' }}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {tab === 'viewers' ? (
        <Viewers viewers={viewers} />
      ) : (
        <ol className="timeline">
          {[...shown].reverse().map((e, i) => (
            <li key={`${e.created_at}-${i}`} className="tl-item">
              <span className="dot" style={{ background: TONE[e.kind] ?? 'var(--dot-off)' }} />
              <div className="tl-body">
                <div className="tl-head">
                  <span className="tl-actor">
                    {e.actor_type === 'system' ? 'ORDER' : e.actor}
                  </span>
                  <span className="meta num">{when(e)}</span>
                </div>
                <div className="small">{e.text}</div>
                <Details details={e.details} />
              </div>
            </li>
          ))}
          {shown.length === 0 && (
            <li className="muted small">Записей этого вида по заявке нет.</li>
          )}
        </ol>
      )}
    </section>
  );
}

/** «ИВАН ПЕТРОВ · 04.09.2026, 18:12» → «04.09.2026, 18:12». */
function when(event: RequestEvent): string {
  const m = /(\d{2}\.\d{2}\.\d{4},\s*\d{2}:\d{2})/.exec(event.meta);
  return m ? m[1] : event.meta;
}

/**
 * «Было → стало». Показываем только то, что действительно менялось:
 * строка «статус: pending → pending» ничего не сообщает, а место
 * занимает.
 */
function Details({ details }: { details: EventDetails }) {
  const rows: { k: string; v: React.ReactNode }[] = [];

  // Пара «было → стало» показывается, только если пришли обе половины:
  // «Сумма →» с пустыми краями сообщает читателю ровно ничего. Так
  // выглядели бы записи, сделанные до появления истории.
  if (details.amount?.from && details.amount?.to) {
    rows.push({
      k: 'Сумма',
      v: (
        <>
          <span className="num">{details.amount.from}</span> → <b className="num">{details.amount.to}</b>
        </>
      ),
    });
  }
  if (details.project && (details.project.from || details.project.to)) {
    rows.push({
      k: 'Объект',
      v: (
        <>
          {details.project.from ?? '—'} → <b>{details.project.to ?? '—'}</b>
        </>
      ),
    });
  }
  for (const line of details.changed ?? []) {
    rows.push({
      k: line.title,
      v: (
        <>
          <span className="num">{line.from}</span> → <b className="num">{line.to}</b>
        </>
      ),
    });
  }
  for (const line of details.added ?? []) {
    rows.push({ k: 'Добавлено', v: `${line.title} — ${line.amount}` });
  }
  for (const line of details.removed ?? []) {
    rows.push({ k: 'Удалено', v: `${line.title} — ${line.amount}` });
  }
  if (details.amount_total && !details.amount?.to) {
    rows.push({ k: 'Сумма', v: <b className="num">{details.amount_total}</b> });
  }
  if (details.method) {
    const method = PAYMENT_METHOD[details.method as 'card' | 'cash'];
    rows.push({ k: 'Способ', v: method ?? details.method });
  }
  if (details.document) {
    rows.push({ k: 'Документ', v: <span className="num">{details.document}</span> });
  }

  if (rows.length === 0) return null;
  return (
    <dl className="tl-details">
      {rows.map((row, i) => (
        <div key={i}>
          <dt>{row.k}</dt>
          <dd>{row.v}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Кто открывал заявку. Отвечает автору на вопрос, которого раньше нельзя
 * было задать: она просто лежит в очереди или её действительно смотрели.
 *
 * Адреса и браузера здесь нет намеренно: сотруднику они ничего не
 * объясняют, а показывать их «на всякий случай» — это уже слежка за
 * людьми, а не история заявки.
 */
function Viewers({ viewers }: { viewers: RequestViewer[] }) {
  if (viewers.length === 0) {
    return (
      <p className="small muted" style={{ margin: 0 }}>
        Карточку ещё никто не открывал. Это не значит, что заявку не
        видели в списке, — только то, что внутрь не заходили.
      </p>
    );
  }
  return (
    <div className="table-wrap">
      <table className="tbl fit compact" style={{ ['--tbl-min' as string]: '420px' }}>
        <thead>
          <tr>
            <th>Кто</th>
            <th>Впервые</th>
            <th>В последний раз</th>
            <th className="right">Раз</th>
          </tr>
        </thead>
        <tbody>
          {viewers.map((v) => (
            <tr key={v.employee_id}>
              <td>{v.employee_name}</td>
              <td className="num">{v.first_viewed_at}</td>
              <td className="num">{v.last_viewed_at}</td>
              <td className="right num">{v.times}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
