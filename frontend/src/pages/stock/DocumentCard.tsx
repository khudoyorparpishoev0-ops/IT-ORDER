import { useState } from 'react';
import { ConfirmModal } from '@/components/ConfirmModal';
import { Modal } from '@/components/Modal';
import { useAuth } from '@/api/auth';
import { useStockDocument, useStockDocumentCancel } from '@/api/hooks';
import type { StockDocKind } from '@/api/types';
import { formatDateTime, money, withUnit } from '@/data/format';

const LABEL: Record<StockDocKind, string> = {
  RECEIPT: 'Приход',
  ISSUE: 'Выдача',
  RETURN: 'Возврат',
};

/**
 * Складской документ. Правки здесь нет и не будет: проведённый документ
 * неизменяем. Ошибка исправляется отменой, которая добавляет обратные
 * движения, — прежние остаются в ленте.
 */
export function DocumentCard({
  documentId,
  onClose,
  onFlash,
}: {
  documentId: number;
  onClose: () => void;
  onFlash: (text: string, color: string) => void;
}) {
  const { can } = useAuth();
  const document = useStockDocument(documentId);
  const cancel = useStockDocumentCancel();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const data = document.data;
  const seesCost = can('view_stock_cost');
  const canCancel = can('manage_stock') && data?.status === 'POSTED';

  const confirm = async () => {
    setError(null);
    try {
      await cancel.mutateAsync({ id: documentId, reason: reason.trim() });
      onFlash('Документ отменён', 'var(--dot-ok)');
      setAsking(false);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось отменить документ');
      setAsking(false);
    }
  };

  return (
    <>
      <Modal
        title={data ? `${LABEL[data.kind]} ${data.number}` : 'Документ'}
        onClose={onClose}
        wide
        footer={
          <>
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Закрыть
            </button>
            {canCancel && (
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => setAsking(true)}
                disabled={!reason.trim()}
              >
                Отменить документ
              </button>
            )}
          </>
        }
      >
        {data && (
          <div style={{ display: 'grid', gap: 16 }}>
            <dl className="tl-details">
              <div>
                <dt>Склад</dt>
                <dd>{data.warehouse_name}</dd>
              </div>
              <div>
                <dt>Оформил</dt>
                <dd>
                  {data.created_by ?? 'Система'} · {formatDateTime(data.created_at)}
                </dd>
              </div>
              {data.recipient_name && (
                <div>
                  <dt>
                    {data.kind === 'ISSUE' ? 'Получил' : 'Вернул'}
                  </dt>
                  <dd>{data.recipient_name}</dd>
                </div>
              )}
              {data.project_name && (
                <div>
                  <dt>Объект</dt>
                  <dd>{data.project_name}</dd>
                </div>
              )}
              {data.supplier && (
                <div>
                  <dt>От кого</dt>
                  <dd>{data.supplier}</dd>
                </div>
              )}
            </dl>

            <table className="tbl compact">
              <thead>
                <tr>
                  <th>Позиция</th>
                  <th className="right">Количество</th>
                  {seesCost && <th className="right">Цена</th>}
                  {seesCost && <th className="right">Сумма</th>}
                </tr>
              </thead>
              <tbody>
                {data.lines.map((line) => (
                  <tr key={line.id}>
                    <td>{line.item_name}</td>
                    <td className="right mono">{withUnit(line.quantity, line.unit)}</td>
                    {seesCost && <td className="right mono">{money(line.price)}</td>}
                    {seesCost && <td className="right mono">{money(line.total)}</td>}
                  </tr>
                ))}
                {seesCost && data.total && (
                  <tr className="total-row">
                    <td colSpan={3}>Итого, TJS</td>
                    <td className="right mono">{money(data.total)}</td>
                  </tr>
                )}
              </tbody>
            </table>

            {data.comment && <p className="small">{data.comment}</p>}

            {data.status === 'CANCELLED' ? (
              <p className="small" style={{ margin: 0 }}>
                Отменён: {data.cancelled_by ?? 'Система'},{' '}
                {data.cancelled_at ? formatDateTime(data.cancelled_at) : ''}. Причина:
                «{data.cancel_reason}».
              </p>
            ) : (
              canCancel && (
                <div>
                  <label className="label field-label" htmlFor="cancel-reason">
                    Причина отмены
                  </label>
                  <input
                    id="cancel-reason"
                    className="field"
                    maxLength={500}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                  <div className="caption" style={{ marginTop: 4 }}>
                    Документ не удаляется: отмена добавляет обратные движения, а
                    прежние остаются. Без причины отмена — та же правка задним
                    числом, только через другую кнопку.
                  </div>
                </div>
              )
            )}

            {error && (
              <div className="field-error-text" role="alert">
                {error}
              </div>
            )}
          </div>
        )}
      </Modal>

      {asking && data && (
        <ConfirmModal
          title={`Отменить ${LABEL[data.kind].toLowerCase()} ${data.number}?`}
          text="Остаток вернётся к прежнему значению. Движения останутся в ленте — по ним будет видно и ошибку, и исправление."
          confirmLabel="Отменить документ"
          danger
          onConfirm={confirm}
          onClose={() => setAsking(false)}
        />
      )}
    </>
  );
}
