import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { RequestModal } from '@/components/RequestModal';
import { RequestsTable } from '@/components/RequestsTable';
import { useSortedRequests } from '@/hooks/useSortedRequests';
import { DASHBOARD_STATS, PERIOD_LABEL, REQUESTS } from '@/data/mock';
import type { ExpenseRequest } from '@/data/types';
import { useShell } from '@/shell/ShellContext';
import { VARIANTS } from '@/shell/config';

export function Dashboard() {
  const navigate = useNavigate();
  const { variant } = useShell();
  const tableFirst = VARIANTS[variant].tableFirst;
  const [modal, setModal] = useState<ExpenseRequest | null>(null);
  const [query, setQuery] = useState('');

  // Вариант B показывает все заявки периода, вариант C — четыре последние.
  const source = tableFirst ? REQUESTS : REQUESTS.slice(0, 4);
  const filtered = query.trim()
    ? source.filter((r) => r.name.toLowerCase().includes(query.trim().toLowerCase()))
    : source;
  const { rows, sort, dir, onSort } = useSortedRequests(filtered);

  const metrics = (
    <section
      key="metrics"
      aria-label="Ключевые метрики"
      style={{
        order: tableFirst ? 3 : 1,
        display: 'flex',
        flexWrap: 'wrap',
        background: 'var(--paper)',
        border: '1px solid var(--line)',
      }}
    >
      {DASHBOARD_STATS.map((s, i) => (
        <div
          key={s.label}
          style={{
            flex: '1 1 180px',
            padding: '12px 16px',
            borderLeft: i === 0 ? 'none' : '1px solid var(--line)',
          }}
        >
          <div className="label">{s.label}</div>
          <div className="metric-sm" style={{ marginTop: 4 }}>
            {s.value}
          </div>
          <div className="caption">{s.note}</div>
        </div>
      ))}
    </section>
  );

  const banner = (
    <section
      key="banner"
      className="clip-corner"
      style={{
        order: 2,
        background: 'var(--forest)',
        color: '#FFFFFF',
        padding: 'var(--pad)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        flexWrap: 'wrap',
      }}
    >
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <span
          aria-hidden="true"
          style={{ width: 8, height: 8, background: 'var(--dot-warn)', marginTop: 10 }}
        />
        <div>
          <div className="h3">4 заявки ждут вашего решения</div>
          <div style={{ fontSize: 13, opacity: 0.8, marginTop: 2 }}>
            Самая давняя — от Ивана Петрова, 3 дня назад. Порог автоодобрения — 500,00 сомони
          </div>
        </div>
      </div>
      <button type="button" className="btn btn-primary" onClick={() => navigate('/approvals')}>
        Перейти к согласованию
      </button>
    </section>
  );

  const table = (
    <section key="table" className="panel" style={{ order: tableFirst ? 1 : 3 }}>
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
        <h2 className="h3">{tableFirst ? 'Заявки за сентябрь' : 'Последние заявки'}</h2>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <label style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <span className="sr-only">Поиск по сотруднику</span>
            <Icon
              name="ti-search"
              style={{ position: 'absolute', left: 12, color: 'var(--slate)' }}
            />
            <input
              className="field"
              style={{ paddingLeft: 40, width: 240 }}
              placeholder="Поиск по сотруднику"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/requests')}>
            Все заявки
          </button>
        </div>
      </div>
      <RequestsTable rows={rows} sort={sort} dir={dir} onSort={onSort} onOpen={setModal} />
    </section>
  );

  return (
    <>
      <PageHeader
        kicker={PERIOD_LABEL}
        title="Панель управления"
        lead="Команда из 12 сотрудников, 24 заявки за период"
        actions={
          <>
            <button type="button" className="btn btn-secondary">
              <Icon name="ti-download" />
              Экспорт
            </button>
            <button type="button" className="btn btn-primary">
              <Icon name="ti-plus" />
              Новая заявка
            </button>
          </>
        }
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)' }}>
        {metrics}
        {banner}
        {table}
      </div>

      <RequestModal
        request={modal}
        onClose={() => setModal(null)}
        onOpenApprovals={() => {
          setModal(null);
          navigate('/approvals');
        }}
      />
    </>
  );
}
