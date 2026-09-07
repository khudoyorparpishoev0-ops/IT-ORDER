import { Link } from 'react-router-dom';
import { Bar } from '@/components/Bar';
import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useBudget } from '@/api/hooks';
import { money, periodLabel, plural } from '@/data/format';

export function Finance() {
  const budget = useBudget();
  const data = budget.data;

  return (
    <>
      <PageHeader
        kicker={periodLabel()}
        title="Финансы"
        lead="Бюджет месяца и очередь выплат по одобренным заявкам"
      />

      <QueryState isLoading={budget.isLoading} error={budget.error} onRetry={() => budget.refetch()}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 'var(--gap)',
          }}
        >
          <section className="card">
            <div className="label">БЮДЖЕТ НА МЕСЯЦ, TJS</div>
            <div className="metric" style={{ margin: '8px 0 16px' }}>
              {money(data?.month_limit)}
            </div>
            {data?.month_limit ? (
              <>
                <Bar pct={data.used_pct ?? 0} />
                <div className="caption" style={{ marginTop: 8 }}>
                  Использовано {money(data.used)} · осталось {money(data.remaining)}
                </div>
              </>
            ) : (
              <div className="caption">
                Бюджет на месяц не задан. Израсходовано {money(data?.used)}.
              </div>
            )}
          </section>

          <section className="card">
            <div className="label">К ВЫПЛАТЕ, TJS</div>
            <div className="metric" style={{ margin: '8px 0 8px' }}>
              {money(data?.week_payout)}
            </div>
            <div className="caption">
              {data?.week_requests ?? 0}{' '}
              {plural(
                data?.week_requests ?? 0,
                'одобренная заявка',
                'одобренные заявки',
                'одобренных заявок',
              )}{' '}
              ждут перечисления
            </div>
            {data?.week_requests ? (
              <Link className="btn btn-primary" style={{ marginTop: 24 }} to="/requests?status=approved">
                Перейти к одобренным
              </Link>
            ) : (
              <p className="caption" style={{ margin: '24px 0 0' }}>
                Одобренных заявок в очереди нет.
              </p>
            )}
          </section>
        </div>
      </QueryState>

      {/* Реквизиты остаются черновиком до подтверждения владельцем бренда
          и финансовым отделом — требование брендбука. */}
      <div style={{ marginTop: 'var(--gap)' }}>
        <EmptyState
          kicker="ЧЕРНОВИК · В РАБОТЕ"
          title="Банковские реквизиты не подключены"
          note="Реквизиты заполняются после подтверждения владельцем бренда и финансовым отделом."
        />
      </div>
    </>
  );
}
