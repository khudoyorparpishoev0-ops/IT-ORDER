import { useMemo, useState } from 'react';
import { Field } from './Field';
import { Icon } from './Icon';
import { useAuth } from '@/api/auth';
import { useSourcing } from '@/api/hooks';
import type { RequestDetail, SourcingLineInput } from '@/api/types';
import { money, plural } from '@/data/format';
import { useShell } from '@/shell/ShellContext';

/** Что закуп решил по строке: покупаем по цене или берём со склада. */
type Answer = { from_stock: boolean; price: string };

/**
 * Оценка заявки отделом закупа прямо в карточке: по каждой позиции либо
 * цена за единицу, либо отметка «со склада». Итог считается на глазах,
 * в базу идёт расчёт сервера.
 */
export function SourcingForm({ detail, onDone }: { detail: RequestDetail; onDone?: () => void }) {
  const { flash } = useShell();
  const { user } = useAuth();
  const sourcing = useSourcing();
  const [answers, setAnswers] = useState<Record<number, Answer>>(() =>
    Object.fromEntries(detail.lines.map((line) => [line.id, { from_stock: false, price: '' }])),
  );
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);

  const own = detail.employee_id === user?.id;

  const setAnswer = (id: number, patch: Partial<Answer>) =>
    setAnswers((prev) => ({ ...prev, [id]: { ...(prev[id] ?? { from_stock: false, price: '' }), ...patch } }));

  const total = useMemo(
    () =>
      detail.lines.reduce((sum, line) => {
        const answer = answers[line.id];
        if (!answer || answer.from_stock) return sum;
        const price = Number(answer.price.replace(',', '.'));
        return Number.isFinite(price) ? sum + price * line.quantity : sum;
      }, 0),
    [detail.lines, answers],
  );
  const fromStock = detail.lines.filter((line) => answers[line.id]?.from_stock).length;
  const allFromStock = fromStock === detail.lines.length;

  const submit = async () => {
    const missing = detail.lines.find((line) => {
      const answer = answers[line.id];
      return !answer?.from_stock && !answer?.price.trim();
    });
    if (missing) {
      setError(`Строка «${missing.title}»: укажите цену или отметьте, что есть на складе`);
      return;
    }
    setError(null);
    const lines: SourcingLineInput[] = detail.lines.map((line) => {
      const answer = answers[line.id];
      return {
        id: line.id,
        from_stock: answer.from_stock,
        price: answer.from_stock ? null : answer.price.trim().replace(',', '.'),
      };
    });
    try {
      const saved = await sourcing.mutateAsync({ id: detail.id, lines, comment: comment.trim() || null });
      flash(
        saved.status === 'fulfilled'
          ? `Заявка ${saved.number} закрыта складом`
          : `Заявка ${saved.number} оценена на ${money(saved.amount)} и ушла руководителю`,
        'var(--dot-ok)',
      );
      onDone?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить оценку');
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="h3">Оценка позиций</h2>
        <span className="caption">Цена за единицу или отметка «со склада»</span>
      </div>
      <div className="table-wrap">
        <table className="tbl fit" style={{ ['--tbl-min' as string]: '520px' }}>
          <thead>
            <tr>
              <th>Позиция</th>
              <th className="right">Кол-во</th>
              <th>Цена, TJS</th>
              <th>Со склада</th>
            </tr>
          </thead>
          <tbody>
            {detail.lines.map((line) => {
              const answer = answers[line.id] ?? { from_stock: false, price: '' };
              return (
                <tr key={line.id} style={{ height: 'auto' }}>
                  <td>{line.title}</td>
                  <td className="right num">
                    {line.quantity}
                    {line.unit ? ` ${line.unit}` : ''}
                  </td>
                  <td style={{ width: 160 }}>
                    <input
                      className="field mono"
                      inputMode="decimal"
                      placeholder="0,00"
                      aria-label={`Цена за единицу: ${line.title}`}
                      disabled={answer.from_stock || own}
                      value={answer.price}
                      onChange={(e) => setAnswer(line.id, { price: e.target.value })}
                      style={{ height: 36 }}
                    />
                  </td>
                  <td style={{ width: 150 }}>
                    <span
                      className="check-row"
                      onClick={() => !own && setAnswer(line.id, { from_stock: !answer.from_stock, price: '' })}
                    >
                      <button
                        type="button"
                        role="checkbox"
                        aria-checked={answer.from_stock}
                        aria-label={`Есть на складе: ${line.title}`}
                        className="check"
                        disabled={own}
                        onClick={(e) => {
                          // Сам квадрат переключает и не даёт строке-подписи
                          // переключить второй раз.
                          e.stopPropagation();
                          setAnswer(line.id, { from_stock: !answer.from_stock, price: '' });
                        }}
                      >
                        <Icon name="ti-check" size={14} style={{ opacity: answer.from_stock ? 1 : 0 }} />
                      </button>
                      <span className="small">{answer.from_stock ? 'Со склада' : 'Покупаем'}</span>
                    </span>
                  </td>
                </tr>
              );
            })}
            <tr className="total-row">
              <td colSpan={3}>
                {allFromStock ? 'Всё со склада' : fromStock ? `К покупке · ${fromStock} со склада` : 'К покупке'}
              </td>
              <td className="num-lg">{money(total)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: 16 }}>
        <Field label="Пояснение" note="Необязательно: срок действия цены, поставщик, что нашлось на складе.">
          {(id) => (
            <textarea id={id} className="field" value={comment} onChange={(e) => setComment(e.target.value)} disabled={own} />
          )}
        </Field>
        {error && (
          <div className="field-error-text" role="alert">
            {error}
          </div>
        )}
        <div className="sticky-actions">
          <button type="button" className="btn btn-primary" disabled={sourcing.isPending || own} onClick={submit}>
            {sourcing.isPending ? 'Сохраняем…' : allFromStock ? 'Закрыть складом' : 'Отправить руководителю'}
          </button>
        </div>
        <p className="caption" style={{ margin: 0 }}>
          {own
            ? 'Свою заявку оценивает кто-то другой.'
            : allFromStock
              ? 'Покупать нечего: заявка закроется, оплаты не будет.'
              : `Руководитель увидит сумму и ${detail.lines.length - fromStock} ${plural(detail.lines.length - fromStock, 'строку', 'строки', 'строк')} с ценами.`}
        </p>
      </div>
    </section>
  );
}
