import { useNavigate } from 'react-router-dom';
import { Kpi } from '@/components/Kpi';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { waitingShort } from '@/components/Waiting';
import { useRequests } from '@/api/hooks';
import type { RequestListItem } from '@/api/types';
import { monthAfterZa, plural } from '@/data/format';

/**
 * Отдел закупа: очередь заявок, чью покупку согласовал руководитель.
 * Здесь только список — проверить склад и проставить цены можно в
 * карточке заявки, куда ведёт клик по строке.
 */
export function Sourcing() {
  const navigate = useNavigate();
  const queue = useRequests({ status: 'sourcing', allPeriods: true, limit: 200 });
  // Нужен только счётчик: строки не показываем.
  const fulfilled = useRequests({ status: 'fulfilled', limit: 1 });

  const items = queue.data?.items ?? [];
  const waiting = queue.data?.total ?? 0;
  const stock = fulfilled.data?.total ?? 0;
  const open = (r: RequestListItem) => navigate(`/requests/${r.id}`);

  return (
    <>
      <PageHeader title="Закуп" lead="Заявки в работе отдела закупа" />

      <div className="kpi-grid">
        <Kpi
          label="Ждут оценки"
          value={queue.data ? waiting : '—'}
          dot={waiting > 0 ? 'var(--yellow)' : undefined}
          note={queue.data ? 'без суммы: склад и цены ещё не проставлены' : 'загрузка'}
        />
        <Kpi
          label="Со склада за месяц"
          value={fulfilled.data ? stock : '—'}
          note={fulfilled.data ? `за ${monthAfterZa()} закуп не потребовался` : 'загрузка'}
        />
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2 className="h3">Очередь на оценку</h2>
          {queue.data && (
            <span className="caption">
              {waiting} {plural(waiting, 'заявка', 'заявки', 'заявок')}
            </span>
          )}
        </div>
        <QueryState
          isLoading={queue.isLoading}
          error={queue.error}
          isEmpty={!queue.isLoading && items.length === 0}
          emptyTitle="Заявок на оценку нет"
          emptyNote="Сюда попадают заявки, чью покупку уже согласовал руководитель."
          onRetry={() => queue.refetch()}
        >
          <div className="table-wrap">
            <table className="tbl cards" style={{ ['--tbl-min' as string]: '760px' }}>
              <thead>
                <tr>
                  <th>Номер</th>
                  <th>Наименование</th>
                  <th>Сотрудник</th>
                  <th>Объект</th>
                  <th>На этапе</th>
                  <th className="right">Позиций</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr
                    key={r.id}
                    className="clickable"
                    tabIndex={0}
                    onClick={() => open(r)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        open(r);
                      }
                    }}
                    aria-label={`Заявка ${r.number}`}
                  >
                    <td className="num desktop-only">{r.number}</td>
                    <td>
                      <div className="row-title" style={{ fontWeight: 500 }}>
                        {r.title}
                      </div>
                      <div className="meta mobile-meta">
                        {r.number} · {r.date} · {r.project_name}
                      </div>
                    </td>
                    <td className="desktop-only">{r.employee_name}</td>
                    <td className="slate desktop-only">{r.project_name}</td>
                    <td style={{ color: 'var(--slate)', fontSize: 13 }}>{waitingShort(r)}</td>
                    <td className="right">
                      <span className="mobile-only caption">Позиций</span>
                      <span className="num">{r.lines_count}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </QueryState>
      </section>
    </>
  );
}
