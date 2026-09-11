import { useId, useMemo, useState } from 'react';
import { Field } from '@/components/Field';
import { Icon } from '@/components/Icon';
import { Modal } from '@/components/Modal';
import { useEmployees, useProjects, useStockDocumentCreate, useStockItems } from '@/api/hooks';
import type { StockLineIn, Warehouse } from '@/api/types';
import { money } from '@/data/format';

export type DocKind = 'receipts' | 'issues' | 'returns';

const TITLE: Record<DocKind, string> = {
  receipts: 'Приход на склад',
  issues: 'Выдача со склада',
  returns: 'Возврат на склад',
};

const SUBMIT: Record<DocKind, string> = {
  receipts: 'Оприходовать',
  issues: 'Выдать',
  returns: 'Принять возврат',
};

type Row = { title: string; itemId: number | null; quantity: string; price: string };

const EMPTY: Row = { title: '', itemId: null, quantity: '', price: '' };

/**
 * Один документ склада: приход, выдача или возврат.
 *
 * Черновика нет намеренно — документ оформляется по факту и сразу
 * проводится. Ошибку исправляет отмена, а не правка: склад с «почти
 * оформленным приходом» — это остаток, которому нельзя верить.
 *
 * Итог считается на сервере и здесь только показывается. Если бы панель
 * считала свой, однажды две цифры разошлись бы, и верить было бы нечему.
 */
export function DocumentModal({
  kind,
  warehouses,
  onClose,
  onDone,
}: {
  kind: DocKind;
  warehouses: Warehouse[];
  onClose: () => void;
  onDone: (text: string) => void;
}) {
  const create = useStockDocumentCreate(kind);
  const items = useStockItems({ onlyActive: true });
  const employees = useEmployees();
  const projects = useProjects();
  const formId = useId();

  const [warehouseId, setWarehouseId] = useState(warehouses[0]?.id ?? 0);
  const [recipientId, setRecipientId] = useState<number | ''>('');
  const [projectId, setProjectId] = useState<number | ''>('');
  const [supplier, setSupplier] = useState('');
  const [comment, setComment] = useState('');
  const [rows, setRows] = useState<Row[]>([{ ...EMPTY }]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const needsRecipient = kind !== 'receipts';
  const showsPrice = kind === 'receipts';

  const known = useMemo(
    () => new Map((items.data ?? []).map((item) => [item.name.toLowerCase(), item])),
    [items.data],
  );

  const total = useMemo(() => {
    if (!showsPrice) return null;
    let sum = 0;
    for (const row of rows) {
      const quantity = Number(row.quantity.replace(',', '.'));
      const price = Number(row.price.replace(',', '.'));
      if (Number.isFinite(quantity) && Number.isFinite(price)) sum += quantity * price;
    }
    return sum;
  }, [rows, showsPrice]);

  const patch = (index: number, next: Partial<Row>) =>
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...next } : row)));

  const filled = rows.filter((row) => row.title.trim() && row.quantity.trim());
  const ready = warehouseId > 0 && filled.length > 0 && (!needsRecipient || recipientId !== '');

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const lines: StockLineIn[] = filled.map((row) => {
        const match = known.get(row.title.trim().toLowerCase());
        return {
          item_id: row.itemId ?? match?.id ?? null,
          title: row.title.trim(),
          quantity: row.quantity.replace(',', '.').trim(),
          price: showsPrice && row.price.trim() ? row.price.replace(',', '.').trim() : null,
        };
      });
      const document = await create.mutateAsync({
        warehouse_id: warehouseId,
        recipient_id: needsRecipient ? Number(recipientId) : undefined,
        project_id: projectId === '' ? null : Number(projectId),
        supplier: kind === 'receipts' ? supplier.trim() || null : null,
        comment: comment.trim() || null,
        lines,
      });
      onDone(`${TITLE[kind]}: ${document.number}`);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось провести документ');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={TITLE[kind]}
      onClose={onClose}
      dirty
      wide
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Отмена
          </button>
          <button
            type="submit"
            form={formId}
            className="btn btn-primary"
            disabled={saving || !ready}
          >
            {saving ? 'Проводим…' : SUBMIT[kind]}
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={submit} style={{ display: 'grid', gap: 16 }}>
        <Field label="Склад" required>
          {(id) => (
            <select
              id={id}
              className="field"
              value={warehouseId}
              onChange={(e) => setWarehouseId(Number(e.target.value))}
            >
              {warehouses.map((warehouse) => (
                <option key={warehouse.id} value={warehouse.id}>
                  {warehouse.name}
                </option>
              ))}
            </select>
          )}
        </Field>

        {needsRecipient && (
          <Field
            label={kind === 'issues' ? 'Кому выдаём' : 'Кто возвращает'}
            required
            note="Выдача «никому» ничего не объясняет: через месяц спросить будет не с кого."
          >
            {(id) => (
              <select
                id={id}
                className="field"
                value={recipientId}
                onChange={(e) => setRecipientId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                <option value="">Выберите сотрудника</option>
                {(employees.data ?? []).map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
              </select>
            )}
          </Field>
        )}

        {kind !== 'receipts' && (
          <Field label="Объект" note="На какой объект ушло. Можно не указывать.">
            {(id) => (
              <select
                id={id}
                className="field"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                <option value="">Не указан</option>
                {(projects.data ?? [])
                  .filter((project) => project.active)
                  .map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
              </select>
            )}
          </Field>
        )}

        {kind === 'receipts' && (
          <Field label="От кого" note="Поставщик или магазин — словами.">
            {(id) => (
              <input
                id={id}
                className="field"
                maxLength={200}
                value={supplier}
                onChange={(e) => setSupplier(e.target.value)}
              />
            )}
          </Field>
        )}

        <div>
          <div className="label field-label">Позиции</div>
          <datalist id={`${formId}-items`}>
            {(items.data ?? []).map((item) => (
              <option key={item.id} value={item.name} />
            ))}
          </datalist>
          <div style={{ display: 'grid', gap: 8 }}>
            {rows.map((row, index) => (
              <div key={index} className="stock-line">
                <input
                  className="field"
                  list={`${formId}-items`}
                  placeholder="Что именно"
                  aria-label={`Позиция ${index + 1}`}
                  maxLength={200}
                  value={row.title}
                  onChange={(e) => patch(index, { title: e.target.value, itemId: null })}
                />
                <input
                  className="field"
                  inputMode="decimal"
                  placeholder="Кол-во"
                  aria-label={`Количество ${index + 1}`}
                  value={row.quantity}
                  onChange={(e) => patch(index, { quantity: e.target.value })}
                />
                {showsPrice && (
                  <input
                    className="field"
                    inputMode="decimal"
                    placeholder="Цена"
                    aria-label={`Цена ${index + 1}`}
                    value={row.price}
                    onChange={(e) => patch(index, { price: e.target.value })}
                  />
                )}
                <button
                  type="button"
                  className="btn btn-icon"
                  aria-label={`Убрать строку ${index + 1}`}
                  disabled={rows.length === 1}
                  onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                >
                  <Icon name="ti-x" size={18} />
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-dashed"
            style={{ marginTop: 8 }}
            onClick={() => setRows((prev) => [...prev, { ...EMPTY }])}
          >
            <Icon name="ti-plus" size={18} />
            Ещё позиция
          </button>
          <div className="caption" style={{ marginTop: 8 }}>
            Незнакомая позиция заводится сама: приёмка не должна ждать
            администратора. Написание сходится с уже заведённым — «Цемент М500»
            и «цемент м-500» попадут в одну кучу.
          </div>
        </div>

        {showsPrice && total !== null && total > 0 && (
          <p className="small" style={{ margin: 0 }}>
            Ориентировочно: {money(total.toFixed(2))} TJS. Итог посчитает сервер.
          </p>
        )}

        <Field label="Комментарий">
          {(id) => (
            <input
              id={id}
              className="field"
              maxLength={500}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          )}
        </Field>

        {error && (
          <div className="field-error-text" role="alert">
            {error}
          </div>
        )}
      </form>
    </Modal>
  );
}
