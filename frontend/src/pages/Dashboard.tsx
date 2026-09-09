import { Link, useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { Kpi } from '@/components/Kpi';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { RequestsTable } from '@/components/RequestsTable';
import { useAuth } from '@/api/auth';
import { useDashboard, useProjectShares, useQueueInfo, useRequests } from '@/api/hooks';
import { days, money, monthAfterZa, periodRange, plural, today } from '@/data/format';

const CHART = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)'];

/**
 * Дашборд. Руководитель видит очередь на решение и показатели месяца,
 * сотрудник — свои последние заявки: показателей у него нет, а таблица
 * та же самая.
 */
export function Dashboard() {
  const navigate = useNavigate();
  const { user, can } = useAuth();
  const reports = can('view_reports');
  const stats = useDashboard(reports);
  const queue = useQueueInfo(can('decide_request'));
  const shares = useProjectShares(reports);
  const list = useRequests({ limit: 5 });

  const q = queue.data;
  const waiting = (q?.count ?? 0) + (q?.priced_count ?? 0);
  const s = stats.data;

  return (
    <>
      <PageHeader
        title="Дашборд"
        lead={periodRange()}
        actions={
          <button type="button" className="btn btn-primary" onClick={() => navigate('/requests/new')}>
            <Icon name="ti-plus" size={18} />
            Создать заявку
          </button>
        }
      />

      {q && waiting > 0 && (
        <section className="card card-accent" style={{ ['--accent' as string]: 'var(--yellow)' }}>
          <div className="row-between" style={{ alignItems: 'center' }}>
            <div style={{ display: 'grid', gap: 4 }}>
              <div className="label">Требует вашего решения</div>
              <h2 className="h3">
                {waiting} {plural(waiting, 'заявка ждёт', 'заявки ждут', 'заявок ждут')} вашего решения
              </h2>
              <div className="small" style={{ color: 'var(--slate)' }}>
                {q.oldest_employee
                  ? `Самая давняя ожидает ${q.oldest_days ? days(q.oldest_days) : 'меньше дня'} — ${q.oldest_employee}`
                  : 'Все заявки поступили сегодня'}
                {q.priced_count > 0 && ` · ${q.priced_count} ${plural(q.priced_count, 'заявка', 'заявки', 'заявок')} с ценами от закупа`}
              </div>
            </div>
            <Link to="/approvals" className="btn btn-secondary">
              Открыть очередь
            </Link>
          </div>
        </section>
      )}

      {reports && (
        <div className="kpi-grid">
          <Kpi label="Всего заявок" value={s ? s.total_requests : '—'} note={`за ${monthAfterZa()}, ${s?.employees_count ?? 0} ${plural(s?.employees_count ?? 0, 'сотрудник', 'сотрудника', 'сотрудников')}`} />
          <Kpi label="Ждут решения" value={s ? s.pending_count : '—'} dot={s && s.pending_count > 0 ? 'var(--yellow)' : undefined} note="на согласовании" />
          <Kpi label="К оплате" value={s ? money(s.approved_amount) : '—'} note={`сомони, ${s?.approved_count ?? 0} ${plural(s?.approved_count ?? 0, 'заявка', 'заявки', 'заявок')}`} />
          <Kpi
            label="Бюджет месяца"
            value={s?.budget_amount ? money(s.budget_amount) : '—'}
            note={s?.budget_amount ? `сомони, использовано ${s.budget_used_pct ?? 0}%` : 'бюджет не задан'}
          />
        </div>
      )}

      <div className={reports ? 'grid-2-1' : 'stack'}>
        <section className="panel">
          <div className="panel-head">
            <h2 className="h3">{reports ? 'Последние заявки' : 'Мои заявки'}</h2>
            <Link to="/requests" className="small">
              Все заявки
            </Link>
          </div>
          <QueryState
            isLoading={list.isLoading}
            error={list.error}
            isEmpty={!list.isLoading && (list.data?.items.length ?? 0) === 0}
            emptyTitle="Заявок за период пока нет"
            emptyNote={reports ? 'Как только сотрудники подадут заявки, они появятся здесь.' : 'Нажмите «Создать заявку» — объект и позиции, цены назовёт закуп.'}
            onRetry={() => list.refetch()}
          >
            <RequestsTable rows={list.data?.items ?? []} compact />
          </QueryState>
        </section>

        {reports && (
          <section className="card" style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
            {shares.data && shares.data.length > 0 ? (
              <>
                <h2 className="h3">
                  {shares.data[0].name} — крупнейший объект по расходам за {monthAfterZa()}
                </h2>
                <div style={{ display: 'grid', gap: 12 }}>
                  {shares.data.map((row, i) => (
                    <div key={row.project_id} className="hbar-row">
                      <div className="hbar-line">
                        <span>{row.name}</span>
                        <span className="num">{money(row.amount)}</span>
                      </div>
                      <div className="hbar">
                        <span style={{ width: `${row.pct}%`, background: CHART[Math.min(i, CHART.length - 1)] }} />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="caption">Источник: ORDER · данные на {today()}</div>
              </>
            ) : (
              <>
                <div className="label">Расходы по объектам</div>
                <p className="caption" style={{ margin: 0 }}>
                  Расходов за {monthAfterZa()} пока нет: доли появятся после первой оценённой заявки.
                </p>
              </>
            )}
          </section>
        )}
      </div>
      {user && !reports && (
        <p className="caption" style={{ margin: 0 }}>
          {user.full_name} · {user.position}
        </p>
      )}
    </>
  );
}
