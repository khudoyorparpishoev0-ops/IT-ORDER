import { useState } from 'react';
import { Field } from './Field';
import { Modal } from './Modal';
import { usePayRequest } from '@/api/hooks';
import { somoni } from '@/data/format';
import { useShell } from '@/shell/ShellContext';
import type { PaymentMethod, RequestListItem } from '@/api/types';

/** Проведение выплаты: способ и номер документа. Без номера в реестре
 *  выплат нечего сверять с банковской выпиской. */
export function PaymentModal({
  request,
  onClose,
  onDone,
}: {
  request: RequestListItem;
  onClose: () => void;
  onDone?: () => void;
}) {
  const { flash } = useShell();
  const pay = usePayRequest();
  const [method, setMethod] = useState<PaymentMethod>('card');
  const [document, setDocument] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!document.trim()) {
      setError('Укажите номер документа');
      return;
    }
    setError(null);
    try {
      await pay.mutateAsync({ id: request.id, method, document: document.trim() });
      flash(`Выплата по заявке ${request.number} проведена`, 'var(--dot-ok)');
      onDone?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось провести выплату');
    }
  };

  return (
    <Modal
      title="Провести выплату"
      onClose={onClose}
      dirty={document.trim().length > 0}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={pay.isPending}>
            Отмена
          </button>
          <button type="button" className="btn btn-primary" onClick={submit} disabled={pay.isPending}>
            {pay.isPending ? 'Проводим…' : 'Провести выплату'}
          </button>
        </>
      }
    >
      <div style={{ display: 'grid', gap: 4 }}>
        <div className="meta">
          {request.number} · {request.project_name}
        </div>
        <div style={{ fontWeight: 600 }}>{request.title}</div>
        <div className="num-lg">{somoni(request.amount)}</div>
      </div>
      <Field label="Способ" required>
        {(id) => (
          <select id={id} className="field" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
            <option value="card">Перевод на карту</option>
            <option value="cash">Наличные</option>
          </select>
        )}
      </Field>
      <Field label="Документ" required note="Номер платёжного поручения или расходного ордера." error={error}>
        {(id) => (
          <input
            id={id}
            className={`field mono${error ? ' field-error' : ''}`}
            maxLength={64}
            placeholder="ПП-0412"
            value={document}
            onChange={(e) => setDocument(e.target.value)}
            autoFocus
          />
        )}
      </Field>
    </Modal>
  );
}
