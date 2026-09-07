import { Bar } from '@/components/Bar';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import {
  BY_PROJECT,
  DATA_AS_OF,
  MONTHS,
  PAID_HISTORY,
  PAID_SUMMARY,
  PAID_TOTAL,
  PROJECTS,
} from '@/data/mock';

/** Ось от нуля обязательна, поэтому высота считается от максимума ряда. */
const MAX = Math.max(...MONTHS.map((m) => m.value));

export function Reports() {
  return (
    <>
      {/* Заголовок графика — вывод, а не рубрика. Данные всегда с источником и датой. */}
      <PageHeader
        title="Расходы по объектам растут второй месяц"
        lead={DATA_AS_OF}
        actions={
          <>
            <button type="button" className="btn btn-secondary">
              <Icon name="ti-file-spreadsheet" />
              Excel
            </button>
            <button type="button" className="btn btn-secondary">
              <Icon name="ti-file-type-pdf" />
              PDF
            </button>
          </>
        }
      />

      <div className="grid-auto">
        <section className="card">
          <div className="label">ДОЛИ ПО ОБЪЕКТАМ, TJS</div>
          <div style={{ display: 'grid', gap: 16, marginTop: 24 }}>
            {BY_PROJECT.map((p) => (
              <div key={p.name}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 16,
                    marginBottom: 6,
                  }}
                >
                  <span>{p.name}</span>
                  <span className="num">
                    {p.sum} · {p.pct}%
                  </span>
                </div>
                <Bar pct={p.pct} fill={p.fill} />
              </div>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="label">ФАКТ ПО МЕСЯЦАМ, TJS ТЫС.</div>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-end',
              gap: 12,
              height: 196,
              marginTop: 24,
              borderBottom: '1px solid var(--ink)',
            }}
          >
            {MONTHS.map((m) => (
              <div
                key={m.label}
                style={{
                  flex: 1,
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'flex-end',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span className="meta">{m.value}</span>
                <div
                  style={{
                    width: '100%',
                    height: `${(m.value / MAX) * 82}%`,
                    background: m.current ? 'var(--green)' : 'var(--line)',
                  }}
                />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
            {MONTHS.map((m) => (
              <span key={m.label} className="meta" style={{ flex: 1, textAlign: 'center' }}>
                {m.label}
              </span>
            ))}
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 'var(--gap)' }}>
        <div
          style={{
            padding: 'var(--pad)',
            borderBottom: '1px solid var(--line)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            flexWrap: 'wrap',
          }}
        >
          <div>
            <h2 className="h3">История оплаченных заявок</h2>
            <div className="caption">{PAID_SUMMARY}</div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <label>
              <span className="sr-only">Объект</span>
              <select className="field" style={{ width: 'auto' }} defaultValue="Все объекты">
                <option>Все объекты</option>
                {PROJECTS.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
            <button type="button" className="btn btn-secondary">
              <Icon name="ti-download" />
              Реестр выплат
            </button>
          </div>
        </div>

        <div className="table-wrap">
          <table className="tbl" style={{ minWidth: 520 }}>
            <thead>
              <tr>
                <th style={{ width: '22%' }}>ОПЛАЧЕНА</th>
                <th style={{ width: '34%' }}>СОТРУДНИК · ОБЪЕКТ</th>
                <th className="right" style={{ width: '22%' }}>
                  СУММА, TJS
                </th>
                <th style={{ width: '22%' }}>ВЫПЛАТА</th>
              </tr>
            </thead>
            <tbody>
              {PAID_HISTORY.map((p) => (
                <tr key={p.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <div className="mono" style={{ fontSize: 14 }}>
                      {p.paidAt}
                    </div>
                    <div className="meta">{p.id}</div>
                  </td>
                  <td>
                    <div>{p.name}</div>
                    <div className="caption">{p.project}</div>
                  </td>
                  <td className="right num">{p.sum}</td>
                  <td>
                    <div style={{ fontSize: 13 }}>{p.method}</div>
                    <div className="meta">{p.doc}</div>
                  </td>
                </tr>
              ))}
              <tr className="total-row">
                <td colSpan={2}>Итого выплачено за сентябрь</td>
                <td className="right metric-sm">{PAID_TOTAL}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
