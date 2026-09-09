import { useState } from 'react';
import { Field } from './Field';
import { Modal } from './Modal';
import { useDecision } from '@/api/hooks';
import { somoni } from '@/data/format';
import { useShell } from '@/shell/ShellContext';
import type { RequestListItem } from '@/api/types';

/**
 * Два окна решения по UI-киту. «Согласовать» — номер, сумма, необязательный
 * комментарий. «Отклонить» — текст последствия и обязательная причина:
 * без неё кнопка не срабатывает, поле в состоянии ошибки.
 */
export function DecisionModal({
  request,
  approve,
  onClose,
  onDone,
}: {
  request: RequestListItem;
  approve: boolean;
  onClose: () => void;
  onDone?: () => void;
}) {
  const { flash } = useShell();
  const decide = useDecision();
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const priced = request.status === 'priced';

  const submit = async () => {
    if (!approve && !comment.trim()) {
      setError('Без причины отклонить нельзя');
      return;
    }
    setError(null);
    try {
      await decide.mutateAsync({ id: request.id, approve, comment: comment.trim() || null });
      flash(
        approve
          ? priced
            ? `Заявка ${request.number} утверждена к оплате`
            : `Заявка ${request.number} передана в отдел закупа`
          : `Заявка ${request.number} отклонена`,
        approve ? 'var(--dot-ok)' : 'var(--dot-err)',
      );
      onDone?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить решение');
    }
  };

  const title = approve ? (priced ? 'Утвердить сумму' : 'Согласовать покупку') : 'Отклонить заявку';

  return (
    <Modal
      title={title}
      onClose={onClose}
      dirty={comment.trim().length > 0}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={decide.isPending}>
            Отмена
          </button>
          <button
            type="button"
            className={`btn ${approve ? 'btn-primary' : 'btn-danger'}`}
            onClick={submit}
            disabled={decide.isPending}
          >
            {decide.isPending ? 'Сохраняем…' : approve ? (priced ? 'Утвердить' : 'Согласовать') : 'Отклонить'}
          </button>
        </>
      }
    >
      <div style={{ display: 'grid', gap: 4 }}>
        <div className="meta">
          {request.number} · {request.project_name}
        </div>
        <div style={{ fontWeight: 600 }}>{request.title}</div>
        {priced ? (
          <div className="num-lg">{somoni(request.amount)}</div>
        ) : (
          <div className="unpriced">сумму назовёт отдел закупа</div>
        )}
      </div>
      {!approve && (
        <p className="small" style={{ margin: 0, color: 'var(--slate)' }}>
          Заявка закроется, автор увидит причину. Обратного хода нет: понадобится новая заявка.
        </p>
      )}
      <Field
        label={approve ? 'Комментарий' : 'Причина отклонения'}
        required={!approve}
        error={error}
      >
        {(id) => (
          <textarea
            id={id}
            className={`field${error ? ' field-error' : ''}`}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={approve ? 'Необязательно' : 'Факт, причина, что делаем, срок'}
            autoFocus
          />
        )}
      </Field>
    </Modal>
  );
}
