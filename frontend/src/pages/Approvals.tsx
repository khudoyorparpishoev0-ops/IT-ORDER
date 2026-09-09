import { useState } from 'react';
import { Link } from 'react-router-dom';
import { DecisionModal } from '@/components/DecisionModal';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useAuth } from '@/api/auth';
import { useRequests } from '@/api/hooks';
import { DELAY_DAYS } from '@/data/status';
import { money, plural } from '@/data/format';
import type { RequestListItem } from '@/api/types';

/**
 * Очередь руководителя: заявки на согласование покупки и на утверждение
 * суммы одним списком, самые давние сверху. Решение — в модалке прямо
 * из списка; свою заявку человек видит без кнопок.
 */
export function Approvals() {
  const { user } = useAuth();
  const pending = useRequests({ status: 'pending', limit: 200, allPeriods: true });
  const priced = useRequests({ status: 'priced', limit: 200, allPeriods: true });
  const [decision, setDecision] = useState<{ request: RequestListItem; approve: boolean } | null>(null);

  const rows = [...(pending.data?.items ?? []), ...(priced.data?.items ?? [])].sort(
    (a, b) => (b.awaiting_days ?? 0) - (a.awaiting_days ?? 0),
  );
  const isLoading = pending.isLoading || priced.isLoading;
  const error = pending.error ?? priced.error;

  return (
    <>
      <PageHeader
        title="Согласование"
        lead={isLoading ? undefined : `${rows.length} ${plural(rows.length, 'заявка ждёт', 'заявки ждут', 'заявок ждут')} вашего решения`}
      />

      <QueryState
        isLoading={isLoading}
        error={error}
        isEmpty={!isLoading && rows.length === 0}
        emptyTitle="Все заявки рассмотрены"
        emptyNote="Новые заявки появятся здесь сразу после подачи, оценённые — когда закуп проставит цены."
        onRetry={() => {
          void pending.refetch();
          void priced.refetch();
        }}
      >
        <div className="stack" style={{ gap: 12 }}>
          {rows.map((r) => {
            const d = r.awaiting_days ?? 0;
            const own = r.employee_id === user?.id;
            const stage = r.status === 'priced' ? 'согласование суммы' : 'согласование покупки';
            return (
              <article
                key={r.id}
                className={`card${d >= DELAY_DAYS ? ' card-accent' : ''}`}
                style={{ ['--accent' as string]: 'var(--yellow)', padding: '16px 24px', borderRadius: 'var(--r-field)', display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}
              >
                <div style={{ flex: '1 1 320px', minWidth: 0, display: 'grid', gap: 4 }}>
                  <Link to={`/requests/${r.id}`} style={{ display: 'flex', alignItems: 'baseline', gap: 12, color: 'var(--ink)' }}>
                    <span className="num" style={{ color: 'var(--slate)' }}>{r.number}</span>
                    <span style={{ fontSize: 16, fontWeight: 600 }}>{r.title}</span>
                  </Link>
                  <div className="caption">
                    {r.employee_name} · {r.project_name} · {stage} · {d > 0 ? `ждёт ${d} ${plural(d, 'день', 'дня', 'дней')}` : 'поступила сегодня'}
                  </div>
                </div>
                <div style={{ minWidth: 120, textAlign: 'right' }}>
                  {r.priced ? <span className="num-lg">{money(r.amount)}</span> : <span className="unpriced">не оценена</span>}
                </div>
                {own ? (
                  <span className="caption" style={{ flex: '0 0 auto' }}>Ваша заявка — решит другой руководитель</span>
                ) : (
                  <div className="sticky-actions" style={{ flex: '0 0 auto' }}>
                    <button type="button" className="btn btn-danger" onClick={() => setDecision({ request: r, approve: false })}>
                      Отклонить
                    </button>
                    <button type="button" className="btn btn-primary" onClick={() => setDecision({ request: r, approve: true })}>
                      {r.status === 'priced' ? 'Утвердить' : 'Согласовать'}
                    </button>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </QueryState>

      {decision && (
        <DecisionModal request={decision.request} approve={decision.approve} onClose={() => setDecision(null)} />
      )}
    </>
  );
}
