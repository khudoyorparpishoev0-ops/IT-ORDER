import { Link } from 'react-router-dom';
import { Kpi } from '@/components/Kpi';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useTeam } from '@/api/hooks';
import { useAuth } from '@/api/auth';
import { money, monthAfterZa, plural } from '@/data/format';

/**
 * Команда: расход по сотрудникам за месяц. Лимитов на людей нет —
 * расход считается по объектам, а здесь видно, кто сколько подал.
 */
export function Team() {
  const team = useTeam();
  const { can } = useAuth();

  const members = team.data ?? [];
  const active = members.filter((m) => m.requests_count > 0).length;
  const total = members.reduce((sum, m) => sum + Number(m.spent), 0);

  return (
    <>
      <PageHeader title="Команда" lead={`Расход по сотрудникам за ${monthAfterZa()}`} />

      <QueryState
        isLoading={team.isLoading}
        error={team.error}
        isEmpty={!team.isLoading && members.length === 0}
        emptyTitle="Сотрудники не заведены"
        emptyNote="Заведите коллег, чтобы они могли входить в систему и подавать заявки."
        emptyAction={
          can('manage_reference') ? (
            <Link className="btn btn-primary" to="/employees">
              Добавить сотрудника
            </Link>
          ) : undefined
        }
        onRetry={() => team.refetch()}
      >
        <div className="kpi-grid">
          <Kpi label="Сотрудников" value={members.length} note="активных в системе" />
          <Kpi
            label="Подали заявки"
            value={active}
            note={`за ${monthAfterZa()}, ${members.length - active} ${plural(members.length - active, 'сотрудник', 'сотрудника', 'сотрудников')} без заявок`}
          />
          <Kpi label="Расход" value={money(total.toFixed(2))} note={`сомони за ${monthAfterZa()}, по оценённым заявкам`} />
        </div>

        <section className="panel">
          <div className="table-wrap">
            <table className="tbl" style={{ ['--tbl-min' as string]: '520px' }}>
              <thead>
                <tr>
                  <th>Сотрудник</th>
                  <th className="right">Расход, TJS</th>
                  <th className="right">Заявок</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <div>{m.full_name}</div>
                      <div className="caption">{m.position}</div>
                    </td>
                    <td className="right">
                      {Number(m.spent) > 0 ? <span className="num">{money(m.spent)}</span> : <span className="muted">—</span>}
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
