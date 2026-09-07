import { useState } from 'react';
import { Bar } from '@/components/Bar';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import {
  useMonthlyFacts,
  usePaymentsRegister,
  useProjectShares,
  useProjects,
} from '@/api/hooks';
import { formatDate, money, monthAfterZa } from '@/data/format';
import { PAYMENT_METHOD } from '@/data/status';

/** Оттенки зелёной шкалы по порядку долей — из брендбука. */
const SHARE_TINTS = [
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--chart-6)',
];

export function Reports() {
  const [projectId, setProjectId] = useState<number | undefined>();

  const shares = useProjectShares();
  const months = useMonthlyFacts();
  const register = usePaymentsRegister(projectId);
  const projects = useProjects();

  // Ось от нуля обязательна: высота столбца считается от максимума ряда.
  const maxFact = Math.max(1, ...(months.data ?? []).map((m) => m.value));
  const leader = shares.data?.[0];

  return (
    <>
      <PageHeader
        // Заголовок графика — вывод, а не рубрика.
        title={
          leader
            ? `Больше всего расходов за ${monthAfterZa()} — объект «${leader.name}»`
            : `Расходы за ${monthAfterZa()}`
        }
        lead={`Источник: CORE · данные на ${formatDate(new Date().toISOString())}`}
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
          <QueryState
            isLoading={shares.isLoading}
            error={shares.error}
            isEmpty={(shares.data ?? []).length === 0}
            emptyTitle="Расходов за период нет"
            onRetry={() => shares.refetch()}
          >
            <div style={{ display: 'grid', gap: 16, marginTop: 24 }}>
              {shares.data?.map((p, i) => (
                <div key={p.project_id}>
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
                      {money(p.amount)} · {p.pct}%
                    </span>
                  </div>
                  <Bar pct={p.pct} fill={SHARE_TINTS[i % SHARE_TINTS.length]} />
                </div>
              ))}
            </div>
          </QueryState>
        </section>

        <section className="card">
          <div className="label">ФАКТ ПО МЕСЯЦАМ, TJS ТЫС.</div>
          <QueryState
            isLoading={months.isLoading}
            error={months.error}
            onRetry={() => months.refetch()}
          >
            <>
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
                {months.data?.map((m, i) => (
                  <div
                    key={`${m.year}-${m.month}`}
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
                        height: `${(m.value / maxFact) * 82}%`,
                        minHeight: m.value > 0 ? 2 : 0,
                        background:
                          i === (months.data?.length ?? 0) - 1
                            ? 'var(--green)'
                            : 'var(--line)',
                      }}
                    />
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
                {months.data?.map((m) => (
                  <span
                    key={`${m.year}-${m.month}-label`}
                    className="meta"
                    style={{ flex: 1, textAlign: 'center' }}
                  >
                    {m.label}
                  </span>
                ))}
              </div>
            </>
          </QueryState>
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
            <div className="caption">{register.data?.summary ?? ''}</div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <label>
              <span className="sr-only">Объект</span>
              <select
                className="field"
                style={{ width: 'auto' }}
                value={projectId ?? ''}
                onChange={(e) =>
                  setProjectId(e.target.value ? Number(e.target.value) : undefined)
                }
              >
                <option value="">Все объекты</option>
                {projects.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="btn btn-secondary">
              <Icon name="ti-download" />
              Реестр выплат
            </button>
          </div>
        </div>

        <QueryState
          isLoading={register.isLoading}
          error={register.error}
          isEmpty={(register.data?.items ?? []).length === 0}
          emptyTitle="Выплат за период не было"
          emptyNote="Реестр заполнится, когда финансы проведут первую выплату."
          onRetry={() => register.refetch()}
        >
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
                {register.data?.items.map((p) => (
                  <tr key={p.number}>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div className="mono" style={{ fontSize: 14 }}>
                        {p.paid_at}
                      </div>
                      <div className="meta">{p.number}</div>
                    </td>
                    <td>
                      <div>{p.employee_name}</div>
                      <div className="caption">{p.project_name}</div>
                    </td>
                    <td className="right num">{money(p.amount)}</td>
                    <td>
                      <div style={{ fontSize: 13 }}>{PAYMENT_METHOD[p.method]}</div>
                      <div className="meta">{p.document}</div>
                    </td>
                  </tr>
                ))}
                <tr className="total-row">
                  <td colSpan={2}>Итого выплачено за {monthAfterZa()}</td>
                  <td className="right metric-sm">{money(register.data?.total)}</td>
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
        </QueryState>
      </section>
    </>
  );
}
