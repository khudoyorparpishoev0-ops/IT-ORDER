import { Bar, barTint } from '@/components/Bar';
import { PageHeader } from '@/components/PageHeader';
import { PERIOD_LABEL, TEAM } from '@/data/mock';

export function Team() {
  return (
    <>
      <PageHeader
        kicker={PERIOD_LABEL}
        title="Команда"
        lead="Лимиты сотрудников и расход по ним за текущий месяц"
      />

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
              {TEAM.map((m) => (
                <tr key={m.name}>
                  <td>
                    <div>{m.name}</div>
                    <div className="caption">{m.role}</div>
                  </td>
                  <td className="right num">{m.limit}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ flex: 1, minWidth: 80 }}>
                        <Bar pct={m.pct} />
                      </div>
                      <span className="num" style={{ color: barTint(m.pct) }}>
                        {m.spent} · {m.pct}%
                      </span>
                    </div>
                  </td>
                  <td className="right num">{m.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
