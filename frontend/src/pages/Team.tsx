import { Link } from 'react-router-dom';
import { Bar, barTint } from '@/components/Bar';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useTeam } from '@/api/hooks';
import { useAuth } from '@/api/auth';
import { money, periodLabel } from '@/data/format';

export function Team() {
  const team = useTeam();
  const { can } = useAuth();

  return (
    <>
      <PageHeader
        kicker={periodLabel()}
        title="Команда"
        lead="Лимиты сотрудников и расход по ним за текущий месяц"
      />

      <QueryState
        isLoading={team.isLoading}
        error={team.error}
        isEmpty={(team.data ?? []).length === 0}
        emptyTitle="Сотрудники не заведены"
        emptyNote="Добавьте сотрудников, чтобы назначать им лимиты расходов."
        emptyAction={
          can('manage_reference') ? (
            <Link className="btn btn-primary" to="/employees">
              Добавить сотрудника
            </Link>
          ) : undefined
        }
        onRetry={() => team.refetch()}
      >
        <section className="panel">
          <div className="table-wrap">
            <table className="tbl" style={{ minWidth: 540 }}>
              <thead>
                <tr>
                  <th style={{ width: '34%' }}>СОТРУДНИК</th>
                  <th className="right" style={{ width: '18%' }}>
                    ЛИМИТ, TJS
                  </th>
                  <th style={{ width: '36%' }}>ИЗРАСХОДОВАНО</th>
                  <th className="right" style={{ width: '12%' }}>
                    ЗАЯВОК
                  </th>
                </tr>
              </thead>
              <tbody>
                {team.data?.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <div>{m.full_name}</div>
                      <div className="caption">{m.position}</div>
                    </td>
                    <td className="right num">{m.limit ? money(m.limit) : '—'}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ flex: 1, minWidth: 80 }}>
                          <Bar pct={m.pct ?? 0} />
                        </div>
                        <span
                          className="num"
                          style={{ color: m.pct === null ? 'var(--slate)' : barTint(m.pct) }}
                        >
                          {money(m.spent)}
                          {m.pct !== null ? ` · ${m.pct}%` : ''}
                        </span>
                      </div>
                    </td>
                    <td className="right num">{m.requests_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </QueryState>
    </>
  );
}
