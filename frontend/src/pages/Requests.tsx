import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';
import { RequestModal } from '@/components/RequestModal';
import { RequestsTable } from '@/components/RequestsTable';
import { useSortedRequests } from '@/hooks/useSortedRequests';
import { PERIOD_LABEL, REQUESTS, TOTAL_REQUESTS } from '@/data/mock';
import { STATUS, STATUS_ORDER } from '@/data/status';
import type { ExpenseRequest, RequestStatus } from '@/data/types';

type Filter = RequestStatus | 'all';

export function Requests() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>('all');
  const [modal, setModal] = useState<ExpenseRequest | null>(null);

  const filtered = filter === 'all' ? REQUESTS : REQUESTS.filter((r) => r.status === filter);
  const { rows, sort, dir, onSort } = useSortedRequests(filtered);

  const chips: { key: Filter; label: string }[] = [
    { key: 'all', label: 'Все' },
    ...STATUS_ORDER.map((k) => ({ key: k as Filter, label: STATUS[k].label })),
  ];

  return (
    <>
      <PageHeader
        kicker={PERIOD_LABEL}
        title="Заявки"
        lead={`${rows.length} из ${TOTAL_REQUESTS} заявок показано · сентябрь 2026`}
        actions={
          <button type="button" className="btn btn-primary">
            <Icon name="ti-plus" />
            Новая заявка
          </button>
        }
      />

      <div
        style={{
          display: 'flex',
          gap: 8,
          flexWrap: 'wrap',
          alignItems: 'center',
          marginBottom: 'var(--gap)',
        }}
      >
        {chips.map((c) => (
          <button
            key={c.key}
            type="button"
            className="chip"
            aria-pressed={filter === c.key}
            onClick={() => setFilter(c.key)}
          >
            {c.label}
          </button>
        ))}
        <label style={{ marginLeft: 'auto' }}>
          <span className="sr-only">Период</span>
          <select className="field" style={{ width: 'auto' }} defaultValue="Сентябрь 2026">
            <option>Сентябрь 2026</option>
            <option>Август 2026</option>
            <option>Июль 2026</option>
          </select>
        </label>
      </div>

      {rows.length > 0 ? (
        <div className="panel">
          <RequestsTable
            rows={rows}
            sort={sort}
            dir={dir}
            onSort={onSort}
            onOpen={setModal}
            withRole
          />
          <nav
            aria-label="Страницы"
            style={{
              padding: 'var(--pad)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 16,
              flexWrap: 'wrap',
            }}
          >
            <span className="label">
              ПОКАЗАНО {rows.length} ИЗ {TOTAL_REQUESTS}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn btn-icon" aria-label="Предыдущая страница">
                <Icon name="ti-chevron-left" />
              </button>
              <button type="button" className="btn btn-primary btn-icon" aria-current="page">
                1
              </button>
              <button type="button" className="btn btn-icon" aria-label="Страница 2">
                2
              </button>
              <button type="button" className="btn btn-icon" aria-label="Следующая страница">
                <Icon name="ti-chevron-right" />
              </button>
            </div>
          </nav>
        </div>
      ) : (
        <EmptyState
          kicker="НЕТ ДАННЫХ"
          title="По выбранному фильтру заявок нет"
          note="Измените статус или период — или сбросьте фильтр и посмотрите все заявки месяца."
          action={
            <button type="button" className="btn btn-secondary" onClick={() => setFilter('all')}>
              Сбросить фильтр
            </button>
          }
        />
      )}

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
