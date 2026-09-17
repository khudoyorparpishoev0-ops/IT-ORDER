import { useState } from 'react';
import { Field } from './Field';
import { Modal } from './Modal';
import { useCancelRequest } from '@/api/hooks';
import { useShell } from '@/shell/ShellContext';
import type { RequestListItem } from '@/api/types';

/**
 * Отмена заявки: потребность отпала или товар не нашли.
 *
 * Отдельно от отклонения намеренно. Отклоняет руководитель — «компания
 * этого не покупает»; отменяют автор и закуп — «покупать больше нечего».
 * Причина обязательна: через месяц «отменена» без объяснения не скажет
 * ничего ни автору, ни руководителю.
 */
export function CancelModal({
  request,
  onClose,
  onDone,
}: {
  request: RequestListItem;
  onClose: () => void;
  onDone?: () => void;
}) {
  const { flash } = useShell();
  const cancel = useCancelRequest();
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (reason.trim().length < 3) {
      setError('Без причины отменить нельзя');
      return;
    }
    setError(null);
    try {
      await cancel.mutateAsync({ id: request.id, reason: reason.trim() });
      flash(`Заявка ${request.number} отменена`, 'var(--dot-off)');
      onDone?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось отменить заявку');
    }
  };

  return (
    <Modal
      title="Отменить заявку"
      onClose={onClose}
      dirty={reason.trim().length > 0}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Не отменять
          </button>
          <button
            type="button"
            className="btn btn-danger"
            disabled={cancel.isPending}
            onClick={submit}
          >
            {cancel.isPending ? 'Отменяем…' : 'Отменить заявку'}
          </button>
        </>
      }
    >
      <div style={{ display: 'grid', gap: 16 }}>
        <p className="small" style={{ margin: 0 }}>
          Заявка {request.number} закроется без оплаты. Вернуть её в работу будет
          нельзя — если потребность вернётся, подайте новую.
        </p>
        <Field
          label="Причина"
          required
          error={error}
          note="Например: «товар снят с производства», «нашли на складе», «объект закрыт»."
        >
          {(id) => (
            <textarea
              id={id}
              className="field"
              rows={3}
              maxLength={2000}
              autoFocus
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          )}
        </Field>
      </div>
    </Modal>
  );
}
