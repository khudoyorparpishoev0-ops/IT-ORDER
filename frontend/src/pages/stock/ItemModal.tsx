import { useId, useState } from 'react';
import { Field } from '@/components/Field';
import { Modal } from '@/components/Modal';
import { useAuth } from '@/api/auth';
import { useStockItemCard, useStockItemSave } from '@/api/hooks';
import { formatDateTime, quantity, withUnit } from '@/data/format';

/**
 * Карточка позиции: где лежит, что с ней происходило и настройки.
 *
 * Остатка в форме нет и быть не может: он показывается справа как факт,
 * а меняется только приходом, выдачей и возвратом.
 */
export function ItemModal({
  itemId,
  onClose,
  onFlash,
}: {
  itemId: number | null;
  onClose: () => void;
  onFlash: (text: string, color: string) => void;
}) {
  const { can } = useAuth();
  const manages = can('manage_stock');
  const card = useStockItemCard(itemId);
  const save = useStockItemSave();
  const formId = useId();

  const item = card.data?.item ?? null;
  const [name, setName] = useState('');
  const [unit, setUnit] = useState('шт.');
  const [article, setArticle] = useState('');
  const [minQuantity, setMinQuantity] = useState('');
  const [loaded, setLoaded] = useState(itemId === null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (item && !loaded) {
    setName(item.name);
    setUnit(item.unit);
    setArticle(item.article ?? '');
    setMinQuantity(Number(item.min_quantity) > 0 ? quantity(item.min_quantity) : '');
    setLoaded(true);
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await save.mutateAsync({
        id: itemId ?? undefined,
        name: name.trim(),
        unit: unit.trim() || 'шт.',
        article: article.trim() || null,
        min_quantity: minQuantity.trim() ? minQuantity.replace(',', '.').trim() : '0',
      });
      onFlash(itemId ? 'Позиция сохранена' : 'Позиция заведена', 'var(--dot-ok)');
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить позицию');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={item ? item.name : 'Новая позиция'}
      onClose={onClose}
      dirty={manages}
      wide
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Закрыть
          </button>
          {manages && (
            <button
              type="submit"
              form={formId}
              className="btn btn-primary"
              disabled={saving || !name.trim()}
            >
              {saving ? 'Сохраняем…' : itemId ? 'Сохранить' : 'Завести'}
            </button>
          )}
        </>
      }
    >
      <div style={{ display: 'grid', gap: 16 }}>
        {manages ? (
          <form id={formId} onSubmit={submit} style={{ display: 'grid', gap: 16 }}>
            <Field
              label="Название"
              required
              note="Так позицию увидят в документах и остатках."
            >
              {(id) => (
                <input
                  id={id}
                  className="field"
                  required
                  maxLength={200}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              )}
            </Field>
            <Field label="Единица" note="«шт.», «м», «кг» — как принято у вас.">
              {(id) => (
                <input
                  id={id}
                  className="field"
                  maxLength={32}
                  value={unit}
                  onChange={(e) => setUnit(e.target.value)}
                />
              )}
            </Field>
            <Field label="Артикул">
              {(id) => (
                <input
                  id={id}
                  className="field"
                  maxLength={64}
                  value={article}
                  onChange={(e) => setArticle(e.target.value)}
                />
              )}
            </Field>
            <Field
              label="Минимальный остаток"
              note="Ниже этого числа позиция считается заканчивающейся. Пусто — не следим."
            >
              {(id) => (
                <input
                  id={id}
                  className="field"
                  inputMode="decimal"
                  value={minQuantity}
                  onChange={(e) => setMinQuantity(e.target.value)}
                />
              )}
            </Field>
            {error && (
              <div className="field-error-text" role="alert">
                {error}
              </div>
            )}
          </form>
        ) : (
          item && (
            <p className="small" style={{ margin: 0 }}>
              {item.name} · {item.unit}
              {item.article ? ` · артикул ${item.article}` : ''}
            </p>
          )
        )}

        {card.data && (
          <>
            <div>
              <div className="label field-label">Где лежит</div>
              {card.data.balances.length === 0 ? (
                <p className="caption" style={{ margin: 0 }}>
                  Остатка нет ни на одном складе.
                </p>
              ) : (
                <table className="tbl compact">
                  <tbody>
                    {card.data.balances.map((row) => (
                      <tr key={row.warehouse_id}>
                        <td>{row.warehouse_name}</td>
                        <td className="right mono">{withUnit(row.quantity, row.unit)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div>
              <div className="label field-label">Что происходило</div>
              {card.data.moves.length === 0 ? (
                <p className="caption" style={{ margin: 0 }}>
                  Движений не было.
                </p>
              ) : (
                <ul className="timeline">
                  {card.data.moves.slice(0, 12).map((move) => (
                    <li key={move.id} className="tl-item">
                      <div className="small">
                        {Number(move.quantity) > 0 ? '+' : ''}
                        {withUnit(move.quantity, move.unit)} · {move.warehouse_name}
                      </div>
                      <div className="caption">
                        {move.document_number} · {move.actor ?? 'Система'} ·{' '}
                        {formatDateTime(move.created_at)}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
