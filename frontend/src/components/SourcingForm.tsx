import { useMemo, useState } from 'react';
import { Field } from './Field';
import { Icon } from './Icon';
import { useAuth } from '@/api/auth';
import { useSourcing } from '@/api/hooks';
import type { RequestDetail, SourcingLineInput } from '@/api/types';
import { money, plural } from '@/data/format';
import { useShell } from '@/shell/ShellContext';

/**
 * Что закуп решил по строке: покупаем по цене, берём со склада или
 * снимаем совсем.
 *
 * Название и количество здесь правятся — единственное место, где состав
 * поданной заявки меняется. Закуп ищет товар в жизни, а не в справочнике:
 * позиции может не быть в продаже вовсе или она продаётся другим объёмом.
 * Раньше на такой случай оставалось отклонить всю заявку из-за одной
 * строки из восьми. Правка пишется в историю «было → стало».
 */
type Answer = {
  from_stock: boolean;
  price: string;
  title: string;
  quantity: string;
  drop: boolean;
};

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
    Object.fromEntries(
      detail.lines.map((line) => [
        line.id,
        {
          from_stock: false,
          price: '',
          title: line.title,
          quantity: String(line.quantity),
          drop: false,
        },
      ]),
    ),
  );
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);

  const own = detail.employee_id === user?.id;

  const setAnswer = (id: number, patch: Partial<Answer>) =>
    setAnswers((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));

  const kept = detail.lines.filter((line) => !answers[line.id]?.drop);
  const dropped = detail.lines.length - kept.length;

  const total = useMemo(
    () =>
      detail.lines.reduce((sum, line) => {
        const answer = answers[line.id];
        if (!answer || answer.from_stock || answer.drop) return sum;
        const price = Number(answer.price.replace(',', '.'));
        const quantity = Number(answer.quantity.replace(',', '.'));
        return Number.isFinite(price) && Number.isFinite(quantity)
          ? sum + price * quantity
          : sum;
      }, 0),
    [detail.lines, answers],
  );
  const fromStock = kept.filter((line) => answers[line.id]?.from_stock).length;
  const allFromStock = kept.length > 0 && fromStock === kept.length;
  const nothingLeft = kept.length === 0;

  const submit = async () => {
    if (nothingLeft) {
      // Снять всё — это не оценка, а «покупать нечего»: у такого исхода
      // свой способ, отмена с причиной. Пустая заявка не должна доехать
      // до руководителя и заставлять его утверждать ноль.
      setError('Сняты все позиции. Если покупать нечего — отмените заявку');
      return;
    }
    const empty = kept.find((line) => !answers[line.id].title.trim());
    if (empty) {
      setError('У позиции не может быть пустого названия');
      return;
    }
    const missing = kept.find((line) => {
      const answer = answers[line.id];
      return !answer.from_stock && !answer.price.trim();
    });
    if (missing) {
      setError(`Строка «${missing.title}»: укажите цену или отметьте, что есть на складе`);
      return;
    }
    setError(null);
    const lines: SourcingLineInput[] = detail.lines.map((line) => {
      const answer = answers[line.id];
      if (answer.drop) return { id: line.id, drop: true, from_stock: false, price: null };
      const quantity = Number(answer.quantity.replace(',', '.'));
      return {
        id: line.id,
        from_stock: answer.from_stock,
        price: answer.from_stock ? null : answer.price.trim().replace(',', '.'),
        // Отправляем только изменённое: «правка без изменений» засоряет
        // историю строками, по которым ничего не произошло.
        title: answer.title.trim() !== line.title ? answer.title.trim() : null,
        quantity:
          Number.isFinite(quantity) && quantity >= 1 && quantity !== line.quantity
            ? Math.trunc(quantity)
            : null,
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
        <span className="caption">
          Цена за единицу или отметка «со склада». Не нашли — поправьте
          название и количество или снимите позицию
        </span>
      </div>
      <div className="table-wrap">
        <table className="tbl fit" style={{ ['--tbl-min' as string]: '720px' }}>
          <thead>
            <tr>
              <th>Позиция</th>
              <th style={{ width: 110 }}>Кол-во</th>
              <th style={{ width: 150 }}>Цена, TJS</th>
              <th style={{ width: 140 }}>Со склада</th>
              {/* Заголовок без текста: у кнопок в строках своя подпись.
                  Пустой `.sr-only` здесь ставить нельзя — он абсолютный и
                  вылезает за таблицу, растягивая страницу вбок. */}
              <th style={{ width: 52 }} aria-label="Снять позицию" />
            </tr>
          </thead>
          <tbody>
            {detail.lines.map((line) => {
              const answer = answers[line.id] ?? { from_stock: false, price: '' };
              return (
                <tr key={line.id} style={{ height: 'auto', opacity: answer.drop ? 0.5 : 1 }}>
                  <td>
                    <input
                      className="field"
                      aria-label={`Позиция: ${line.title}`}
                      maxLength={200}
                      disabled={answer.drop || own}
                      value={answer.title}
                      onChange={(e) => setAnswer(line.id, { title: e.target.value })}
                      style={{ height: 36 }}
                    />
                  </td>
                  <td>
                    <input
                      className="field mono"
                      inputMode="numeric"
                      aria-label={`Количество: ${line.title}`}
                      disabled={answer.drop || own}
                      value={answer.quantity}
                      onChange={(e) => setAnswer(line.id, { quantity: e.target.value })}
                      style={{ height: 36 }}
                    />
                    {line.unit && <div className="caption">{line.unit}</div>}
                  </td>
                  <td>
                    <input
                      className="field mono"
                      inputMode="decimal"
                      placeholder="0,00"
                      aria-label={`Цена за единицу: ${line.title}`}
                      disabled={answer.from_stock || answer.drop || own}
                      value={answer.price}
                      onChange={(e) => setAnswer(line.id, { price: e.target.value })}
                      style={{ height: 36 }}
                    />
                  </td>
                  <td>
                    <span
                      className="check-row"
                      onClick={() =>
                        !own &&
                        !answer.drop &&
                        setAnswer(line.id, { from_stock: !answer.from_stock, price: '' })
                      }
                    >
                      <button
                        type="button"
                        role="checkbox"
                        aria-checked={answer.from_stock}
                        aria-label={`Есть на складе: ${line.title}`}
                        className="check"
                        disabled={own || answer.drop}
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
                  <td>
                    <button
                      type="button"
                      className="btn btn-icon"
                      disabled={own}
                      aria-label={answer.drop ? `Вернуть позицию: ${line.title}` : `Снять позицию: ${line.title}`}
                      title={answer.drop ? 'Вернуть позицию' : 'Снять: не нашли'}
                      onClick={() =>
                        setAnswer(line.id, { drop: !answer.drop, from_stock: false, price: '' })
                      }
                    >
                      <Icon name={answer.drop ? 'ti-plus' : 'ti-x'} size={18} />
                    </button>
                  </td>
                </tr>
              );
            })}
            <tr className="total-row">
              <td colSpan={3}>
                {nothingLeft
                  ? 'Все позиции сняты'
                  : allFromStock
                    ? 'Всё со склада'
                    : [
                        'К покупке',
                        fromStock ? `${fromStock} со склада` : '',
                        dropped ? `${dropped} снято` : '',
                      ]
                        .filter(Boolean)
                        .join(' · ')}
              </td>
              <td className="num-lg" colSpan={2}>
                {money(total)}
              </td>
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
          <button
            type="button"
            className="btn btn-primary"
            disabled={sourcing.isPending || own || nothingLeft}
            onClick={submit}
          >
            {sourcing.isPending ? 'Сохраняем…' : allFromStock ? 'Закрыть складом' : 'Отправить руководителю'}
          </button>
        </div>
        <p className="caption" style={{ margin: 0 }}>
          {own
            ? 'Свою заявку оценивает кто-то другой.'
            : nothingLeft
              ? 'Снято всё. Если покупать нечего — отмените заявку кнопкой в шапке карточки.'
              : allFromStock
              ? 'Покупать нечего: заявка закроется, оплаты не будет.'
                : `Руководитель увидит сумму и ${kept.length - fromStock} ${plural(kept.length - fromStock, 'строку', 'строки', 'строк')} с ценами.`}
        </p>
      </div>
    </section>
  );
}
