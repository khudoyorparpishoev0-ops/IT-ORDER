import { useEffect, useState } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { StatusBadge } from '@/components/StatusBadge';
import { useDecision, useRequest, useRequests } from '@/api/hooks';
import { money, periodLabel, somoni } from '@/data/format';
import type { RequestStatus } from '@/api/types';
import { useShell } from '@/shell/ShellContext';
import { useAuth } from '@/api/auth';

type Decision = 'approve' | 'reject';

const PAGE_SIZE = 50;

//: Статусы, в которых руководителю есть что решать.
const DECIDABLE: RequestStatus[] = ['pending', 'priced'];

const TABS: { key: RequestStatus; label: string }[] = [
  // Два решения руководителя — две очереди: сперва нужна ли покупка,
  // потом согласен ли он с суммой, которую назвал закуп.
  { key: 'pending', label: 'Покупка' },
  { key: 'priced', label: 'Сумма' },
  { key: 'sourcing', label: 'У закупа' },
  { key: 'approved', label: 'К оплате' },
  { key: 'rejected', label: 'Отклонены' },
];

export function Approvals() {
  const { flash } = useShell();
  const { user } = useAuth();
  const [tab, setTab] = useState<RequestStatus>('pending');
  // Очередь бывает длиннее страницы. Раньше лишние заявки просто не
  // показывались, и о них никто не узнавал.
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [decision, setDecision] = useState<Decision>('approve');
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);

  const list = useRequests({ status: tab, limit, allPeriods: true });
  const items = list.data?.items ?? [];
  const detail = useRequest(activeId);
  const decide = useDecision();

  // Первая заявка вкладки выбирается сама: очередь без выбранной карточки
  // выглядит сломанной.
  useEffect(() => {
    if (items.length === 0) {
      setActiveId(null);
    } else if (!items.some((r) => r.id === activeId)) {
      setActiveId(items[0].id);
    }
  }, [items, activeId]);

  const reset = () => {
    setDecision('approve');
    setComment('');
    setError(null);
  };

  const approve = decision === 'approve';
  const active = detail.data;

  const submit = () => {
    if (!active) return;
    if (!approve && comment.trim() === '') {
      setError('Комментарий обязателен при отклонении заявки');
      return;
    }
    // actor не передаём: сервер берёт имя согласующего из сессии.
    decide.mutate(
      {
        id: active.id,
        approve,
        comment: comment.trim() || null,
      },
      {
        onSuccess: () => {
          flash(
            !approve
              ? `Заявка ${active.number} отклонена`
              : active.priced
                ? `Заявка ${active.number} утверждена к оплате`
                : `Заявка ${active.number} передана в отдел закупа`,
            approve ? 'var(--dot-ok)' : 'var(--dot-err)',
          );
          reset();
        },
        onError: (e) => setError(e instanceof Error ? e.message : 'Не удалось сохранить решение'),
      },
    );
  };

  return (
    <>
      <PageHeader
        kicker={periodLabel()}
        title="Согласование"
        lead="Сперва согласуйте саму покупку, после оценки закупа — сумму. Комментарий к отклонению обязателен"
      />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 'var(--gap)' }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className="chip"
            aria-pressed={tab === t.key}
            onClick={() => {
              setTab(t.key);
              setActiveId(null);
              setLimit(PAGE_SIZE);
              reset();
            }}
          >
            {t.label}
            {tab === t.key && list.data ? ` · ${list.data.total}` : ''}
          </button>
        ))}
      </div>

      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        isEmpty={items.length === 0}
        emptyTitle={
          tab === 'pending'
            ? 'Все заявки рассмотрены'
            : tab === 'priced'
              ? 'Оценённых заявок нет'
              : 'В этой вкладке заявок нет'
        }
        emptyNote={
          tab === 'pending'
            ? 'Новые заявки появятся здесь сразу после подачи.'
            : tab === 'priced'
              ? 'Здесь появятся заявки, которые вернул отдел закупа с ценами.'
              : undefined
        }
        onRetry={() => list.refetch()}
      >
        <div
          style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--gap)', alignItems: 'flex-start' }}
        >
          <section
            className="panel"
            aria-label="Очередь заявок"
            style={{ flex: '1 1 240px', maxWidth: 320, minWidth: 0 }}
          >
            <div style={{ padding: 'var(--pad)', borderBottom: '1px solid var(--line)' }}>
              <span className="label">ОЧЕРЕДЬ · {items.length}</span>
            </div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {items.map((r) => {
                const isActive = r.id === activeId;
                return (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveId(r.id);
                        reset();
                      }}
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
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                        <span style={{ fontWeight: isActive ? 700 : 400 }}>
                          {r.employee_name}
                        </span>
                        <span className="num">{money(r.amount)}</span>
                      </div>
                      <div className="meta">
                        {r.number} · {r.date}
                      </div>
                      <div className="caption">{r.project_name}</div>
                    </button>
                  </li>
                );
              })}
            </ul>

            {list.data && items.length < list.data.total && (
              <div style={{ padding: 'var(--pad)', borderTop: '1px solid var(--line)' }}>
                <div className="caption" style={{ marginBottom: 8 }}>
                  Показано {items.length} из {list.data.total}
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setLimit((v) => v + PAGE_SIZE)}
                >
                  Показать ещё
                </button>
              </div>
            )}
          </section>

          <div style={{ flex: '1 1 460px', minWidth: 0, display: 'grid', gap: 'var(--gap)' }}>
            {active && (
              <>
                <section className="card">
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      gap: 16,
                      flexWrap: 'wrap',
                    }}
                  >
                    {/* minWidth: 0 обязателен: без него длинная почта не даёт
                        блоку сжаться, и карточка вылезает за экран телефона. */}
                    <div style={{ display: 'flex', gap: 12, minWidth: 0 }}>
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
                          flex: 'none',
                        }}
                      >
                        {initials(active.employee_name)}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div className="h3">{active.employee_name}</div>
                        <div className="caption">
                          {active.employee_position} · объект «{active.project_name}»
                        </div>
                        <div className="meta">
                          {[active.employee_email, active.employee_phone]
                            .filter(Boolean)
                            .join(' · ') || 'Контакты не заполнены'}
                        </div>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <StatusBadge status={active.status} />
                      <div className="meta" style={{ marginTop: 4 }}>
                        {active.number} · {active.date}
                      </div>
                    </div>
                  </div>

                  <div className="table-wrap" style={{ marginTop: 24 }}>
                    <table
                  className="tbl fit"
                  style={{ ['--tbl-min' as string]: '380px' }}
                >
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
                        {active.lines.map((l) => (
                          <tr key={l.id}>
                            <td>{l.title}</td>
                            <td className="right num">
                              {l.quantity}
                              {l.unit ? ` ${l.unit}` : ''}
                            </td>
                            <td className="right">
                              {l.from_stock ? (
                                <span className="caption">со склада</span>
                              ) : l.price === null ? (
                                <span className="caption">—</span>
                              ) : (
                                <span className="num">{money(l.price)}</span>
                              )}
                            </td>
                            <td className="right">
                              {l.from_stock || l.total === null ? (
                                <span className="caption">—</span>
                              ) : (
                                <span className="num">{money(l.total)}</span>
                              )}
                            </td>
                          </tr>
                        ))}
                        <tr className="total-row">
                          <td colSpan={3}>
                            {active.priced ? 'Итого к оплате' : 'Сумму назовёт закуп'}
                          </td>
                          <td className="right metric-sm">
                            {active.priced ? money(active.amount) : '—'}
                          </td>
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
                    <div>
                      <dt className="label">ЛИМИТ СОТРУДНИКА</dt>
                      <dd className="num" style={{ margin: '4px 0 0' }}>
                        {active.employee_limit ? somoni(active.employee_limit) : 'не задан'}
                      </dd>
                    </div>
                    <div>
                      <dt className="label">ИЗРАСХОДОВАНО</dt>
                      <dd className="num" style={{ margin: '4px 0 0' }}>
                        {somoni(active.employee_spent)}
                      </dd>
                    </div>
                    <div>
                      <dt className="label">ПОЗИЦИЙ В ЗАЯВКЕ</dt>
                      <dd className="num" style={{ margin: '4px 0 0' }}>
                        {active.lines.length}
                      </dd>
                    </div>
                  </dl>
                </section>

                <section className="card">
                  <h2 className="h3" style={{ marginBottom: 16 }}>
                    История изменений
                  </h2>
                  <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 16 }}>
                    {active.events.map((h, i) => (
                      <li
                        key={`${h.created_at}-${i}`}
                        style={{
                          borderLeft: `2px solid ${
                            i === active.events.length - 1 ? 'var(--green)' : 'var(--line)'
                          }`,
                          paddingLeft: 12,
                        }}
                      >
                        <div>{h.text}</div>
                        <div className="meta">{h.meta}</div>
                      </li>
                    ))}
                  </ol>
                </section>
              </>
            )}
          </div>

          {active && DECIDABLE.includes(active.status) && active.employee_id === user?.id && (
            <section
              className="card"
              style={{ flex: '1 1 300px', minWidth: 0, position: 'sticky', top: 88 }}
            >
              <div className="label">ВАША ЗАЯВКА</div>
              <p style={{ marginTop: 16, color: 'var(--slate)' }}>
                Собственную заявку согласовать нельзя. Решение примет другой
                руководитель.
              </p>
            </section>
          )}

          {active && DECIDABLE.includes(active.status) && active.employee_id !== user?.id && (
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
                  label={active.priced ? 'Утвердить сумму' : 'Согласовать покупку'}
                  accent="var(--dot-ok)"
                  active={approve}
                  onSelect={() => {
                    setDecision('approve');
                    setError(null);
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
                    if (error) setError(null);
                  }}
                  aria-invalid={Boolean(error)}
                  placeholder={
                    approve
                      ? 'Необязательно'
                      : 'Укажите причину отклонения: факт, причина, что делаем, срок'
                  }
                />
              </label>
              {error && (
                <div className="field-error-text" role="alert">
                  {error}
                </div>
              )}

              <div style={{ display: 'grid', gap: 8, marginTop: 24 }}>
                <button
                  type="button"
                  className={approve ? 'btn btn-primary' : 'btn btn-danger'}
                  onClick={submit}
                  disabled={decide.isPending}
                >
                  {decide.isPending
                    ? 'Сохраняем…'
                    : !approve
                      ? 'Отклонить заявку'
                      : active.priced
                        ? `Утвердить ${somoni(active.amount)}`
                        : 'Согласовать покупку'}
                </button>
                <button type="button" className="btn btn-secondary" onClick={reset}>
                  Отмена
                </button>
              </div>
            </section>
          )}

          {active && active.status !== 'pending' && (
            <section
              className="card"
              style={{ flex: '1 1 300px', minWidth: 0, position: 'sticky', top: 88 }}
            >
              <div className="label">РЕШЕНИЕ ПРИНЯТО</div>
              <div style={{ marginTop: 16 }}>
                <StatusBadge status={active.status} />
              </div>
              {active.decided_by && (
                <div className="meta" style={{ marginTop: 12 }}>
                  {active.decided_by.toUpperCase()}
                </div>
              )}
              {active.decision_comment && (
                <p
                  style={{
                    borderLeft: '2px solid var(--line)',
                    paddingLeft: 12,
                    marginTop: 12,
                    color: 'var(--slate)',
                  }}
                >
                  {active.decision_comment}
                </p>
              )}
              {active.payment && (
                <div style={{ marginTop: 16 }}>
                  <div className="label">ВЫПЛАТА</div>
                  <div className="num" style={{ marginTop: 4 }}>
                    {money(active.payment.amount)} · {active.payment.document}
                  </div>
                </div>
              )}
            </section>
          )}
        </div>
      </QueryState>
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
        <span style={{ width: 10, height: 10, background: active ? accent : 'transparent' }} />
      </span>
      <span style={{ fontWeight: 600 }}>{label}</span>
    </button>
  );
}

function initials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((p) => p[0] ?? '')
    .join('');
}
