import { useMemo, useState } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { money, somoni } from '@/data/format';
import {
  APPROVAL_TABS,
  EXPENSE_LINES,
  HISTORY,
  PERIOD_LABEL,
  REQUESTS,
  REQUEST_LIMITS,
} from '@/data/mock';
import type { ExpenseRequest } from '@/data/types';
import { useShell } from '@/shell/ShellContext';

type Decision = 'approve' | 'reject';

export function Approvals() {
  const { flash } = useShell();
  const queue = useMemo(() => REQUESTS.filter((r) => r.status === 'pending'), []);
  const [tab, setTab] = useState(APPROVAL_TABS[0].key);
  const [active, setActive] = useState<ExpenseRequest>(queue[0]);
  const [decision, setDecision] = useState<Decision>('approve');
  const [comment, setComment] = useState('');
  const [error, setError] = useState(false);

  const approve = decision === 'approve';

  const submit = () => {
    // Комментарий обязателен только при отклонении: факт → причина → что делаем → срок.
    if (!approve && comment.trim() === '') {
      setError(true);
      return;
    }
    setError(false);
    flash(
      approve ? `Заявка ${active.id} одобрена` : `Заявка ${active.id} отклонена`,
      approve ? 'var(--dot-ok)' : 'var(--dot-err)',
    );
    setComment('');
  };

  const pick = (r: ExpenseRequest) => {
    setActive(r);
    setDecision('approve');
    setComment('');
    setError(false);
  };

  return (
    <>
      <PageHeader
        kicker={PERIOD_LABEL}
        title="Согласование"
        lead="Решения по заявкам сотрудников, комментарий к отклонению обязателен"
      />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 'var(--gap)' }}>
        {APPROVAL_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className="chip"
            aria-pressed={tab === t.key}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--gap)', alignItems: 'flex-start' }}>
        <section
          className="panel"
          aria-label="Очередь заявок"
          style={{ flex: '1 1 240px', maxWidth: 320, minWidth: 0 }}
        >
          <div style={{ padding: 'var(--pad)', borderBottom: '1px solid var(--line)' }}>
            <span className="label">ОЧЕРЕДЬ · {queue.length}</span>
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {queue.map((r) => {
              const isActive = r.id === active.id;
              return (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => pick(r)}
                    aria-current={isActive}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      padding: '12px 16px',
                      border: 'none',
                      borderBottom: '1px solid var(--line)',
                      borderLeft: `2px solid ${isActive ? 'var(--green)' : 'transparent'}`,
                      background: isActive ? 'var(--mist)' : 'transparent',
                      cursor: 'pointer',
                      transition: 'background 150ms ease-out',
                    }}
                  >
                    <div
                      style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}
                    >
                      <span style={{ fontWeight: isActive ? 700 : 400 }}>{r.name}</span>
                      <span className="num">{money(r.amount)}</span>
                    </div>
                    <div className="meta">
                      {r.id} · {r.date}
                    </div>
                    <div className="caption">{r.project}</div>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <div style={{ flex: '1 1 460px', minWidth: 0, display: 'grid', gap: 'var(--gap)' }}>
          <section className="card">
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 16,
                flexWrap: 'wrap',
              }}
            >
              <div style={{ display: 'flex', gap: 12 }}>
                <div
                  aria-hidden="true"
                  style={{
                    width: 44,
                    height: 44,
                    display: 'grid',
                    placeItems: 'center',
                    background: 'var(--st-ok-bg)',
                    color: 'var(--st-ok-fg)',
                    borderRadius: 'var(--r-field)',
                    fontWeight: 700,
                  }}
                >
                  {initials(active.name)}
                </div>
                <div>
                  <div className="h3">{active.name}</div>
                  <div className="caption">
                    {active.role} · объект «{active.project}»
                  </div>
                  <div className="meta">
                    {mailbox(active.name)} · +992 __ ___ __ __
                  </div>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <StatusBadge status={active.status} />
                <div className="meta" style={{ marginTop: 4 }}>
                  {active.id} · {active.date}
                </div>
              </div>
            </div>

            <div className="table-wrap" style={{ marginTop: 24 }}>
              <table className="tbl" style={{ minWidth: 380 }}>
                <thead>
                  <tr>
                    <th>ОПИСАНИЕ</th>
                    <th className="right" style={{ width: 64 }}>
                      КОЛ-ВО
                    </th>
                    <th className="right" style={{ width: 84 }}>
                      ЦЕНА, TJS
                    </th>
                    <th className="right" style={{ width: 100 }}>
                      СУММА, TJS
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {EXPENSE_LINES.map((l) => (
                    <tr key={l.title}>
                      <td>{l.title}</td>
                      <td className="right num">{l.qty}</td>
                      <td className="right num">{l.price}</td>
                      <td className="right num">{l.total}</td>
                    </tr>
                  ))}
                  <tr className="total-row">
                    <td colSpan={3}>Итого к возмещению</td>
                    <td className="right metric-sm">{money(active.amount)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <hr className="divider" />

            <dl
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                gap: 16,
                margin: 0,
              }}
            >
              {REQUEST_LIMITS.map((l) => (
                <div key={l.k}>
                  <dt className="label">{l.k}</dt>
                  <dd className="num" style={{ margin: '4px 0 0' }}>
                    {l.v}
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="card">
            <h2 className="h3" style={{ marginBottom: 16 }}>
              История изменений
            </h2>
            <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 16 }}>
              {HISTORY.map((h) => (
                <li
                  key={h.meta}
                  style={{
                    borderLeft: `2px solid ${h.current ? 'var(--green)' : 'var(--line)'}`,
                    paddingLeft: 12,
                  }}
                >
                  <div>{h.text}</div>
                  <div className="meta">{h.meta}</div>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <section
          className="card"
          aria-label="Решение по заявке"
          style={{ flex: '1 1 300px', minWidth: 0, position: 'sticky', top: 88 }}
        >
          <div className="label">РЕШЕНИЕ</div>
          <div
            role="radiogroup"
            aria-label="Решение"
            style={{ display: 'grid', gap: 8, marginTop: 16 }}
          >
            <DecisionOption
              label="Одобрить"
              accent="var(--dot-ok)"
              active={approve}
              onSelect={() => {
                setDecision('approve');
                setError(false);
              }}
            />
            <DecisionOption
              label="Отклонить"
              accent="var(--dot-err)"
              active={!approve}
              onSelect={() => setDecision('reject')}
            />
          </div>

          <label>
            <div className="label" style={{ margin: '24px 0 8px' }}>
              КОММЕНТАРИЙ
            </div>
            <textarea
              className={`field${error ? ' field-error' : ''}`}
              value={comment}
              onChange={(e) => {
                setComment(e.target.value);
                if (error) setError(false);
              }}
              aria-invalid={error}
              placeholder={
                approve
                  ? 'Необязательно'
                  : 'Укажите причину отклонения: факт, причина, что делаем, срок'
              }
            />
          </label>
          {error && (
            <div className="field-error-text" role="alert">
              Комментарий обязателен при отклонении заявки
            </div>
          )}

          <div style={{ display: 'grid', gap: 8, marginTop: 24 }}>
            <button
              type="button"
              className={approve ? 'btn btn-primary' : 'btn btn-danger'}
              onClick={submit}
            >
              {approve ? `Одобрить ${somoni(active.amount)}` : 'Отклонить заявку'}
            </button>
            <button type="button" className="btn btn-secondary">
              Отмена
            </button>
            <button type="button" className="btn btn-ghost">
              Запросить уточнение у сотрудника
            </button>
          </div>
        </section>
      </div>
    </>
  );
}

function DecisionOption({
  label,
  accent,
  active,
  onSelect,
}: {
  label: string;
  accent: string;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onSelect}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        minHeight: 44,
        padding: '0 12px',
        border: active ? `2px solid ${accent}` : '1px solid var(--grey)',
        borderRadius: 'var(--r-field)',
        background: active ? 'var(--mist)' : 'transparent',
        textAlign: 'left',
        cursor: 'pointer',
        transition: 'background 150ms ease-out',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 18,
          height: 18,
          flex: 'none',
          display: 'grid',
          placeItems: 'center',
          border: active ? `2px solid ${accent}` : '1px solid var(--grey)',
        }}
      >
        <span
          style={{ width: 10, height: 10, background: active ? accent : 'transparent' }}
        />
      </span>
      <span style={{ fontWeight: 600 }}>{label}</span>
    </button>
  );
}

function initials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((p) => p[0])
    .join('');
}

/** Заглушка рабочей почты до подключения справочника сотрудников. */
function mailbox(name: string): string {
  const [first = '', last = ''] = name.split(' ');
  return `${translit(first[0] ?? '')}.${translit(last)}@it-hona.tj`.toLowerCase();
}

const MAP: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i',
  й: 'i', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't',
  у: 'u', ф: 'f', х: 'h', ц: 'c', ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '',
  э: 'e', ю: 'yu', я: 'ya',
};

function translit(s: string): string {
  return s
    .toLowerCase()
    .split('')
    .map((ch) => MAP[ch] ?? ch)
    .join('');
}
