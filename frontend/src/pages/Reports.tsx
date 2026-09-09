import { useState } from 'react';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useMonthlyFacts, usePaymentsRegister, useProjectShares, useProjects } from '@/api/hooks';
import { useDownload } from '@/hooks/useDownload';
import { money, monthAfterZa, today } from '@/data/format';
import { PAYMENT_METHOD } from '@/data/status';

/** Зелёная шкала графиков: от большей доли к меньшей. */
const CHART = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)'];

/**
 * Отчёты. Заголовок — вывод, а не рубрика: он говорит, куда ушли
 * деньги. Два графика (доли по объектам и факт по месяцам) и реестр
 * выплат с выгрузкой.
 */
export function Reports() {
  const [projectId, setProjectId] = useState<number | undefined>();
  const { download, busy } = useDownload();

  const shares = useProjectShares();
  const months = useMonthlyFacts();
  const register = usePaymentsRegister(projectId);
  const projects = useProjects();

  // Ось от нуля обязательна: высота столбца считается от максимума ряда.
  const facts = months.data ?? [];
  const maxFact = Math.max(1, ...facts.map((m) => m.value));
  const leader = shares.data?.[0];

  return (
    <>
      <PageHeader
        accent
        title={leader ? `Больше всего расходов за ${monthAfterZa()} — объект «${leader.name}»` : `Расходы за ${monthAfterZa()}`}
        lead={`Источник: ORDER · данные на ${today()}`}
        actions={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy !== null}
              onClick={() => download('xlsx', '/api/exports/payments.xlsx', { project_id: projectId })}
            >
              <Icon name="ti-file-spreadsheet" size={18} />
              {busy === 'xlsx' ? 'Готовим…' : 'Excel'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy !== null}
              onClick={() => download('pdf', '/api/exports/payments.pdf', { project_id: projectId })}
            >
              <Icon name="ti-file-type-pdf" size={18} />
              {busy === 'pdf' ? 'Готовим…' : 'PDF'}
            </button>
          </>
        }
      />

      <div className="grid-auto">
        <section className="card" style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
          <div className="label-mono">Доли по объектам, TJS</div>
          <QueryState
            isLoading={shares.isLoading}
            error={shares.error}
            isEmpty={!shares.isLoading && (shares.data ?? []).length === 0}
            emptyTitle="Расходов за период нет"
            emptyNote={`Доли появятся после первой оценённой заявки за ${monthAfterZa()}.`}
            onRetry={() => shares.refetch()}
          >
            <div style={{ display: 'grid', gap: 12 }}>
              {shares.data?.map((p, i) => (
                <div key={p.project_id} className="hbar-row">
                  <div className="hbar-line">
                    <span>{p.name}</span>
                    <span className="num">
                      {money(p.amount)} · {p.pct}%
                    </span>
                  </div>
                  <div className="hbar">
                    <span style={{ width: `${p.pct}%`, background: CHART[Math.min(i, CHART.length - 1)] }} />
                  </div>
                </div>
              ))}
            </div>
          </QueryState>
        </section>

        <section className="card" style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
          <div className="label-mono">Факт по месяцам, TJS тыс.</div>
          <QueryState
            isLoading={months.isLoading}
            error={months.error}
            isEmpty={!months.isLoading && facts.length === 0}
            emptyTitle="Данных по месяцам нет"
            onRetry={() => months.refetch()}
          >
            <div>
              <div className="vbars">
                {facts.map((m, i) => (
                  <div key={`${m.year}-${m.month}`} className="vbar">
                    <span className="num">{m.value}</span>
                    <span
                      style={{
                        // 82% — под значение над столбцом остаётся место.
                        height: `${(m.value / maxFact) * 82}%`,
                        minHeight: m.value > 0 ? 2 : 0,
                        background: i === facts.length - 1 ? 'var(--chart-3)' : 'var(--chart-5)',
                      }}
                    />
                  </div>
                ))}
              </div>
              <div className="vbar-labels">
                {facts.map((m) => (
                  <span key={`${m.year}-${m.month}-label`} className="label-mono">
                    {m.label}
                  </span>
                ))}
              </div>
            </div>
          </QueryState>
        </section>
      </div>

      <section className="panel">
        <div className="panel-head" style={{ padding: '20px 24px' }}>
          <div style={{ minWidth: 0 }}>
            <h2 className="h3">История оплаченных заявок</h2>
            {register.data?.summary && <div className="caption">{register.data.summary}</div>}
          </div>
          <div className="filter-row">
            <label>
              <span className="sr-only">Объект</span>
              <select
                className="filter"
                value={projectId ?? ''}
                onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : undefined)}
              >
                <option value="">Все объекты</option>
                {projects.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy !== null}
              onClick={() => download('register', '/api/exports/payments.xlsx', { project_id: projectId })}
            >
              <Icon name="ti-download" size={18} />
              {busy === 'register' ? 'Готовим…' : 'Реестр выплат'}
            </button>
          </div>
        </div>

        <QueryState
          isLoading={register.isLoading}
          error={register.error}
          isEmpty={!register.isLoading && (register.data?.items ?? []).length === 0}
          emptyTitle="Выплат за период не было"
          emptyNote="Реестр заполнится, когда финансы проведут первую выплату."
          onRetry={() => register.refetch()}
        >
          <div className="table-wrap">
            <table className="tbl tbl-forest tall" style={{ ['--tbl-min' as string]: '640px' }}>
              <thead>
                <tr>
                  <th>Оплачена</th>
                  <th>Сотрудник · объект</th>
                  <th>Способ</th>
                  <th className="right">Сумма, TJS</th>
                </tr>
              </thead>
              <tbody>
                {register.data?.items.map((p) => (
                  <tr key={p.number}>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div className="num">{p.paid_at}</div>
                      <div className="meta">{p.number}</div>
                    </td>
                    <td>
                      <div>{p.employee_name}</div>
                      <div className="caption">{p.project_name}</div>
                    </td>
                    <td>
                      <div className="small">{PAYMENT_METHOD[p.method]}</div>
                      <div className="meta">{p.document}</div>
                    </td>
                    <td className="right num-lg">{money(p.amount)}</td>
                  </tr>
                ))}
                <tr className="total-row">
                  <td colSpan={3}>
                    <span className="h3">Итого выплачено за {monthAfterZa()}</span>
                  </td>
                  <td className="right num-lg">{money(register.data?.total)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </QueryState>
      </section>
    </>
  );
}
