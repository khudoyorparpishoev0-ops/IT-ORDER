import { useEffect, useMemo, useState } from 'react';
import { Field } from '@/components/Field';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { StatusBadge } from '@/components/StatusBadge';
import { useAuth } from '@/api/auth';
import { useRequest, useRequests, useSourcing } from '@/api/hooks';
import type { SourcingLineInput } from '@/api/types';
import { money, plural } from '@/data/format';
import { useShell } from '@/shell/ShellContext';

/** Что закуп решил по строке: покупаем по цене или берём со склада. */
type Answer = { from_stock: boolean; price: string };

/**
 * Отдел закупа. Сюда попадают заявки, чью потребность согласовал
 * руководитель: проверить склад, а на то, чего нет, поставить цену.
 * После ответа заявка возвращается руководителю — утверждать сумму.
 */
export function Sourcing() {
  const { flash } = useShell();
  const { user } = useAuth();
  const list = useRequests({ status: 'sourcing', limit: 50, allPeriods: true });
  const [activeId, setActiveId] = useState<number | null>(null);
  const detail = useRequest(activeId);
  const sourcing = useSourcing();

  const [answers, setAnswers] = useState<Record<number, Answer>>({});
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);

  const items = list.data?.items ?? [];

  // Первая заявка выбирается сама: очередь без открытой карточки выглядит
  // сломанной.
  useEffect(() => {
    if (items.length === 0) setActiveId(null);
    else if (!items.some((r) => r.id === activeId)) setActiveId(items[0].id);
  }, [items, activeId]);

  const active = detail.data;

  // Ответы заводим заново на каждую открытую заявку.
  useEffect(() => {
    if (!active) return;
    setAnswers(
      Object.fromEntries(
        active.lines.map((line) => [line.id, { from_stock: false, price: '' }]),
      ),
    );
    setComment('');
    setError(null);
  }, [active?.id, active?.lines.length]);

  const total = useMemo(() => {
    if (!active) return 0;
    return active.lines.reduce((sum, line) => {
      const answer = answers[line.id];
      if (!answer || answer.from_stock) return sum;
      const price = Number(answer.price.replace(',', '.'));
      return Number.isFinite(price) ? sum + price * line.quantity : sum;
    }, 0);
  }, [active, answers]);

  const stockCount = active
    ? active.lines.filter((line) => answers[line.id]?.from_stock).length
    : 0;
  const allFromStock = Boolean(active) && stockCount === active?.lines.length;

  const setAnswer = (id: number, patch: Partial<Answer>) =>
    setAnswers((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));

  const submit = () => {
    if (!active) return;
    const missing = active.lines.find((line) => {
      const answer = answers[line.id];
      return !answer?.from_stock && !answer?.price.trim();
    });
    if (missing) {
      setError(
        `Строка «${missing.title}»: укажите цену или отметьте, что есть на складе`,
      );
      return;
    }
    setError(null);

    const lines: SourcingLineInput[] = active.lines.map((line) => {
      const answer = answers[line.id];
      return {
        id: line.id,
        from_stock: answer.from_stock,
        // Запятую из русской раскладки сервер не поймёт — переводим в точку.
        price: answer.from_stock ? null : answer.price.trim().replace(',', '.'),
      };
    });

    sourcing.mutate(
      { id: active.id, lines, comment: comment.trim() || null },
      {
        onSuccess: (result) => {
          flash(
            result.status === 'fulfilled'
              ? `Заявка ${result.number} закрыта складом`
              : `Заявка ${result.number} оценена на ${money(result.amount)} и ушла руководителю`,
            'var(--dot-ok)',
          );
        },
        onError: (e) =>
          setError(e instanceof Error ? e.message : 'Не удалось сохранить оценку'),
      },
    );
  };

  return (
    <>
      <PageHeader
        kicker="ЗАКУПКИ"
        title="Оценка заявок"
        lead="Проверьте склад и проставьте цены на то, чего нет. Сумму утверждает руководитель"
      />

      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        isEmpty={items.length === 0}
        emptyTitle="Заявок на оценку нет"
        emptyNote="Сюда попадают заявки, чью покупку уже согласовал руководитель."
        onRetry={() => list.refetch()}
      >
        <div style={{ display: 'flex', gap: 'var(--gap)', flexWrap: 'wrap' }}>
          <section className="panel" style={{ flex: '1 1 320px', minWidth: 0 }}>
            <div className="label" style={{ padding: 'var(--pad)', paddingBottom: 8 }}>
              ЖДУТ ОЦЕНКИ · {items.length}
            </div>
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {items.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => setActiveId(r.id)}
                    aria-current={r.id === activeId}
                    style={{
                      display: 'block',
                      width: '100%',
                      textAlign: 'left',
                      padding: 'var(--pad)',
                      border: 'none',
                      borderTop: '1px solid var(--line)',
                      background: r.id === activeId ? 'var(--mist)' : 'transparent',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{r.employee_name}</div>
                    <div className="caption">
                      {r.project_name} · {r.number} · {r.date}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          {active && (
            <section className="card" style={{ flex: '1 1 460px', minWidth: 0 }}>
              <div className="row-between">
                <div>
                  <div className="meta">
                    {active.number} · {active.date}
                  </div>
                  <div className="h3" style={{ marginTop: 4 }}>
                    {active.employee_name}
                  </div>
                  <div className="caption">
                    {active.employee_position} · объект «{active.project_name}»
                  </div>
                </div>
                <StatusBadge status={active.status} />
              </div>

              <div className="table-wrap" style={{ marginTop: 24 }}>
                <table
                  className="tbl fit"
                  style={{ ['--tbl-min' as string]: '420px' }}
                >
                  <thead>
                    <tr>
                      <th style={{ width: '40%' }}>ЧТО НУЖНО</th>
                      <th className="right" style={{ width: '14%' }}>
                        КОЛ-ВО
                      </th>
                      <th style={{ width: '26%' }}>ЦЕНА ЗА ЕДИНИЦУ</th>
                      <th style={{ width: '20%' }}>ЕСТЬ НА СКЛАДЕ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {active.lines.map((line) => {
                      const answer = answers[line.id] ?? { from_stock: false, price: '' };
                      return (
                        <tr key={line.id}>
                          <td>{line.title}</td>
                          <td className="right num">
                            {line.quantity}
                            {line.unit ? ` ${line.unit}` : ''}
                          </td>
                          <td>
                            <input
                              className="field num"
                              inputMode="decimal"
                              aria-label={`Цена за единицу: ${line.title}`}
                              placeholder="0,00"
                              disabled={answer.from_stock}
                              value={answer.price}
                              onChange={(e) =>
                                setAnswer(line.id, { price: e.target.value })
                              }
                            />
                          </td>
                          <td>
                            <button
                              type="button"
                              role="checkbox"
                              aria-checked={answer.from_stock}
                              aria-label={`Есть на складе: ${line.title}`}
                              onClick={() =>
                                setAnswer(line.id, {
                                  from_stock: !answer.from_stock,
                                  price: '',
                                })
                              }
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 8,
                                minHeight: 44,
                                border: 'none',
                                background: 'transparent',
                                cursor: 'pointer',
                              }}
                            >
                              <span
                                aria-hidden="true"
                                style={{
                                  width: 20,
                                  height: 20,
                                  flex: 'none',
                                  display: 'grid',
                                  placeItems: 'center',
                                  borderRadius: 'var(--r-field)',
                                  border: answer.from_stock
                                    ? '1px solid var(--green)'
                                    : '1px solid var(--grey)',
                                  background: answer.from_stock
                                    ? 'var(--green)'
                                    : 'transparent',
                                  color: '#FFFFFF',
                                }}
                              >
                                <Icon
                                  name="ti-check"
                                  size={14}
                                  style={{ opacity: answer.from_stock ? 1 : 0 }}
                                />
                              </span>
                              {answer.from_stock ? 'Со склада' : 'Покупаем'}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="row-between" style={{ marginTop: 16 }}>
                <span className="label">
                  {allFromStock
                    ? 'ВСЁ СО СКЛАДА'
                    : `К ПОКУПКЕ${stockCount ? ` · ${stockCount} со склада` : ''}`}
                </span>
                <span className="num" style={{ fontSize: 18, fontWeight: 600 }}>
                  {money(total)} TJS
                </span>
              </div>

              <div style={{ marginTop: 16 }}>
                <Field
                  label="Пояснение"
                  note="Необязательно: срок действия цены, поставщик, что нашлось на складе."
                >
                  {(id) => (
                    <textarea
                      id={id}
                      className="field"
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                    />
                  )}
                </Field>
              </div>

              {error && (
                <div className="field-error-text" role="alert" style={{ marginTop: 12 }}>
                  {error}
                </div>
              )}

              <div style={{ display: 'grid', gap: 8, marginTop: 24 }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={sourcing.isPending || active.employee_id === user?.id}
                  onClick={submit}
                >
                  {sourcing.isPending
                    ? 'Сохраняем…'
                    : allFromStock
                      ? 'Закрыть складом'
                      : 'Отправить руководителю'}
                </button>
                <p className="caption" style={{ margin: 0 }}>
                  {allFromStock
                    ? 'Покупать нечего: заявка закроется, оплаты не будет.'
                    : `Руководитель увидит сумму и ${plural(
                        active.lines.length,
                        'строку',
                        'строки',
                        'строк',
                      )} с ценами.`}
                  {active.employee_id === user?.id &&
                    ' Свою заявку оценивает кто-то другой.'}
                </p>
              </div>
            </section>
          )}
        </div>
      </QueryState>
    </>
  );
}
