import { Link } from 'react-router-dom';
import { Bar } from '@/components/Bar';
import { Kpi } from '@/components/Kpi';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useTeam } from '@/api/hooks';
import { useAuth } from '@/api/auth';
import { money, monthAfterZa, plural } from '@/data/format';

/** С этой доли лимит считается почти выбранным: перед процентом — жёлтая точка. */
const NEAR_LIMIT_PCT = 85;

/**
 * Команда: лимиты сотрудников и расход по ним за месяц. Кто близок к
 * лимиту, помечен точкой — цифры остаются чёрными, цвет только у метки.
 */
export function Team() {
  const team = useTeam();
  const { can } = useAuth();

  const members = team.data ?? [];
  const withLimit = members.filter((m) => m.limit !== null).length;
  const nearLimit = members.filter((m) => m.pct !== null && m.pct > NEAR_LIMIT_PCT).length;

  return (
    <>
      <PageHeader title="Команда" lead={`Лимиты сотрудников и расход по ним за ${monthAfterZa()}`} />

      <QueryState
        isLoading={team.isLoading}
        error={team.error}
        isEmpty={!team.isLoading && members.length === 0}
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
        <div className="kpi-grid">
          <Kpi label="Сотрудников" value={members.length} note={`подают заявки за ${monthAfterZa()}`} />
          <Kpi
            label="С лимитом"
            value={withLimit}
            note={
              withLimit === members.length
                ? 'лимит задан всем'
                : `${members.length - withLimit} ${plural(members.length - withLimit, 'сотрудник', 'сотрудника', 'сотрудников')} без лимита`
            }
          />
          <Kpi
            label={`Выше ${NEAR_LIMIT_PCT}%`}
            value={nearLimit}
            dot={nearLimit > 0 ? 'var(--yellow)' : undefined}
            note={nearLimit > 0 ? 'лимит почти выбран' : 'к лимиту никто не приблизился'}
          />
        </div>

        <section className="panel">
          <div className="table-wrap">
            <table className="tbl" style={{ ['--tbl-min' as string]: '640px' }}>
              <thead>
                <tr>
                  <th style={{ width: '32%' }}>Сотрудник</th>
                  <th className="right" style={{ width: '18%' }}>
                    Лимит, TJS
                  </th>
                  <th style={{ width: '38%' }}>Израсходовано</th>
                  <th className="right" style={{ width: '12%' }}>
                    Заявок
                  </th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => {
                  const near = m.pct !== null && m.pct > NEAR_LIMIT_PCT;
                  return (
                    <tr key={m.id}>
                      <td>
                        <div>{m.full_name}</div>
                        <div className="caption">{m.position}</div>
                      </td>
                      <td className="right">
                        {m.limit ? <span className="num">{money(m.limit)}</span> : <span className="muted">—</span>}
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <div style={{ flex: 1, minWidth: 80 }}>
                            <Bar pct={m.pct ?? 0} fill={near ? 'var(--yellow)' : 'var(--green)'} />
                          </div>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                            <span className="num">{money(m.spent)}</span>
                            {m.pct !== null && (
                              <>
                                <span className="num" style={{ color: 'var(--slate)' }}>
                                  ·
                                </span>
                                {near && <span className="dot" style={{ ['--dot' as string]: 'var(--yellow)' }} aria-hidden="true" />}
                                <span className="num">{m.pct}%</span>
                              </>
                            )}
                          </span>
                        </div>
                      </td>
                      <td className="right num">{m.requests_count}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </QueryState>
    </>
  );
}
