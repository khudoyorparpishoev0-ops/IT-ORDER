import { Bar } from '@/components/Bar';
import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';
import { BUDGET, PERIOD_LABEL } from '@/data/mock';

export function Finance() {
  return (
    <>
      <PageHeader
        kicker={PERIOD_LABEL}
        title="Финансы"
        lead="Бюджет месяца и очередь выплат по одобренным заявкам"
      />

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
            {BUDGET.monthLimit}
          </div>
          <Bar pct={BUDGET.usedPct} />
          <div className="caption" style={{ marginTop: 8 }}>
            {BUDGET.usedNote}
          </div>
        </section>

        <section className="card">
          <div className="label">К ВЫПЛАТЕ НА ЭТОЙ НЕДЕЛЕ, TJS</div>
          <div className="metric" style={{ margin: '8px 0 8px' }}>
            {BUDGET.weekPayout}
          </div>
          <div className="caption">{BUDGET.weekNote}</div>
          <button type="button" className="btn btn-primary" style={{ marginTop: 24 }}>
            Отправить в оплату
          </button>
        </section>
      </div>

      {/* Реквизиты остаются черновиком до подтверждения владельцем бренда
          и финансовым отделом — требование брендбука. */}
      <div style={{ marginTop: 'var(--gap)' }}>
        <EmptyState
          kicker="ЧЕРНОВИК · В РАБОТЕ"
          title="Банковские реквизиты не подключены"
          note="Реквизиты заполняются после подтверждения владельцем бренда и финансовым отделом."
          action={
            <button type="button" className="btn btn-secondary">
              Подключить счёт
            </button>
          }
        />
      </div>
    </>
  );
}
