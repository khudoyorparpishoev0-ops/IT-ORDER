import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icon';
import { StatusBadge } from './StatusBadge';
import { Field } from './Field';
import { useAuth } from '@/api/auth';
import { usePayRequest, useRequest } from '@/api/hooks';
import { useShell } from '@/shell/ShellContext';
import type { PaymentMethod } from '@/api/types';
import { useDownload } from '@/hooks/useDownload';
import { money } from '@/data/format';
import type { RequestListItem } from '@/api/types';

type Props = {
  request: RequestListItem | null;
  onClose: () => void;
  onOpenApprovals: () => void;
};

export function RequestModal({ request, onClose, onOpenApprovals }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const { can } = useAuth();
  const { data: detail, isLoading } = useRequest(request?.id ?? null);
  const { download, busy } = useDownload();

  useEffect(() => {
    if (!request) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [request, onClose]);

  if (!request) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        background: 'rgba(16,22,19,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Заявка ${request.number}`}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 600,
          maxHeight: '82vh',
          overflowY: 'auto',
          background: 'var(--paper)',
          borderRadius: 'var(--r-card)',
          boxShadow: 'var(--sh2)',
          padding: 'var(--pad)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <div className="meta">
              {request.number} · {request.date}
            </div>
            <div className="h3" style={{ marginTop: 4 }}>
              {request.employee_name}
            </div>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="btn btn-icon"
            onClick={onClose}
            aria-label="Закрыть"
            style={{ border: 'none' }}
          >
            <Icon name="ti-x" />
          </button>
        </div>

        <dl
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 16,
            margin: '24px 0',
          }}
        >
          <div>
            <dt className="label">ОБЪЕКТ</dt>
            <dd style={{ margin: '4px 0 0' }}>{request.project_name}</dd>
          </div>
          <div>
            <dt className="label">СУММА, TJS</dt>
            <dd
              style={{
                margin: '4px 0 0',
                fontFamily: 'var(--font-mono)',
                fontSize: 16,
                fontWeight: 600,
              }}
            >
              {money(request.amount)}
            </dd>
          </div>
          <div>
            <dt className="label">СТАТУС</dt>
            <dd style={{ margin: '4px 0 0' }}>
              <StatusBadge status={request.status} />
            </dd>
          </div>
        </dl>

        {isLoading && <div className="label">ЗАГРУЗКА СОСТАВА</div>}

        {detail && (
          <div className="table-wrap">
            <table className="tbl" style={{ minWidth: 340 }}>
              <thead>
                <tr>
                  <th>ОПИСАНИЕ</th>
                  <th style={{ width: 64 }} className="right">
                    КОЛ-ВО
                  </th>
                  <th style={{ width: 110 }} className="right">
                    СУММА, TJS
                  </th>
                </tr>
              </thead>
              <tbody>
                {detail.lines.map((line) => (
                  <tr key={line.id}>
                    <td>{line.title}</td>
                    <td className="right num">{line.quantity}</td>
                    <td className="right num">{money(line.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {detail?.decision_comment && (
          <p
            style={{
              borderLeft: '2px solid var(--line)',
              paddingLeft: 12,
              margin: '16px 0 0',
              color: 'var(--slate)',
            }}
          >
            {detail.decision_comment}
          </p>
        )}

        {request.status === 'approved' && can('pay_request') && (
          <PaymentForm id={request.id} onDone={onClose} />
        )}

        {detail?.payment && (
          <p className="caption" style={{ margin: '16px 0 0' }}>
            Выплачено {money(detail.payment.amount)} TJS, документ{' '}
            <span className="num">{detail.payment.document}</span>.
          </p>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 24, flexWrap: 'wrap' }}>
          {request.status === 'pending' && (
            <button type="button" className="btn btn-primary" onClick={onOpenApprovals}>
              Открыть в согласовании
            </button>
          )}
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy !== null}
            onClick={() =>
              download('pdf', `/api/exports/requests/${request.id}.pdf`)
            }
          >
            <Icon name="ti-file-type-pdf" />
            {busy ? 'Готовим…' : 'PDF'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Проведение выплаты. Доступно финансам и администратору по одобренной
 * заявке. Номер документа обязателен: без него в реестре выплат нечего
 * сверять с банковской выпиской.
 */
function PaymentForm({ id, onDone }: { id: number; onDone: () => void }) {
  const { flash } = useShell();
  const pay = usePayRequest();
  const [method, setMethod] = useState<PaymentMethod>('card');
  const [document, setDocument] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await pay.mutateAsync({ id, method, document: document.trim() });
      flash('Выплата проведена', 'var(--dot-ok)');
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось провести выплату');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      style={{ marginTop: 24, borderTop: '1px solid var(--line)', paddingTop: 24, display: 'grid', gap: 16 }}
    >
      <div className="label">ВЫПЛАТА</div>

      <Field label="Способ">
        {(fieldId) => (
          <select
            id={fieldId}
            className="field"
            value={method}
            onChange={(e) => setMethod(e.target.value as PaymentMethod)}
          >
            <option value="card">Перевод на карту</option>
            <option value="cash">Наличные</option>
          </select>
        )}
      </Field>

      <Field label="Документ" note="Номер платёжного поручения или расходного ордера.">
        {(fieldId) => (
          <input
            id={fieldId}
            className="field num"
            required
            maxLength={64}
            placeholder="ПП-0412"
            value={document}
            onChange={(e) => setDocument(e.target.value)}
          />
        )}
      </Field>

      {error && (
        <div className="field-error-text" role="alert">
          {error}
        </div>
      )}

      <button
        type="submit"
        className="btn btn-primary"
        disabled={saving || !document.trim()}
        style={{ justifySelf: 'start' }}
      >
        {saving ? 'Проводим…' : 'Провести выплату'}
      </button>
    </form>
  );
}
