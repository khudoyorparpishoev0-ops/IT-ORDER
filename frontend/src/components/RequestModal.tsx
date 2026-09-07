import { useEffect, useRef } from 'react';
import { Icon } from './Icon';
import { StatusBadge } from './StatusBadge';
import { EXPENSE_LINES } from '@/data/mock';
import { money } from '@/data/format';
import type { ExpenseRequest } from '@/data/types';

type Props = {
  request: ExpenseRequest | null;
  onClose: () => void;
  onOpenApprovals: () => void;
};

export function RequestModal({ request, onClose, onOpenApprovals }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);

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
        aria-label={`Заявка ${request.id}`}
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
              {request.id} · {request.date}
            </div>
            <div className="h3" style={{ marginTop: 4 }}>
              {request.name}
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
            <dd style={{ margin: '4px 0 0' }}>{request.project}</dd>
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
              {EXPENSE_LINES.map((line) => (
                <tr key={line.title}>
                  <td>{line.title}</td>
                  <td className="right num">{line.qty}</td>
                  <td className="right num">{line.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 24, flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-primary" onClick={onOpenApprovals}>
            Открыть в согласовании
          </button>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
}
