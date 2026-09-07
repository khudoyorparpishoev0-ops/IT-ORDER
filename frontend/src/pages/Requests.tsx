import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { RequestModal } from '@/components/RequestModal';
import { RequestsTable } from '@/components/RequestsTable';
import { useSortedRequests } from '@/hooks/useSortedRequests';
import { useRequests } from '@/api/hooks';
import { monthAfterZa, periodLabel, plural } from '@/data/format';
import { STATUS, STATUS_ORDER } from '@/data/status';
import type { RequestListItem, RequestStatus } from '@/api/types';

type Filter = RequestStatus | 'all';

const PAGE_SIZE = 20;

export function Requests() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<Filter>('all');
  const [page, setPage] = useState(0);
  const [allPeriods, setAllPeriods] = useState(false);
  const [modal, setModal] = useState<RequestListItem | null>(null);

  const list = useRequests({
    status: filter === 'all' ? undefined : filter,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    allPeriods,
  });
  const { rows, sort, dir, onSort } = useSortedRequests(list.data?.items ?? []);

  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const chips: { key: Filter; label: string }[] = [
    { key: 'all', label: 'Все' },
    ...STATUS_ORDER.map((k) => ({ key: k as Filter, label: STATUS[k].label })),
  ];

  const setFilterAndReset = (key: Filter) => {
    setFilter(key);
    setPage(0);
  };

  return (
    <>
      <PageHeader
        kicker={periodLabel()}
        title="Заявки"
        lead={`${total} ${plural(total, 'заявка', 'заявки', 'заявок')} ${
          allPeriods ? 'за всё время' : `за ${monthAfterZa()}`
        }`}
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
            onClick={() => setFilterAndReset(c.key)}
          >
            {c.label}
          </button>
        ))}
        <label style={{ marginLeft: 'auto' }}>
          <span className="sr-only">Период</span>
          <select
            className="field"
            style={{ width: 'auto' }}
            value={allPeriods ? 'all' : 'current'}
            onChange={(e) => {
              setAllPeriods(e.target.value === 'all');
              setPage(0);
            }}
          >
            <option value="current">Текущий месяц</option>
            <option value="all">Все периоды</option>
          </select>
        </label>
      </div>

      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        isEmpty={rows.length === 0}
        emptyTitle="По выбранному фильтру заявок нет"
        emptyNote="Измените статус или период — или сбросьте фильтр и посмотрите все заявки."
        emptyAction={
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setFilterAndReset('all')}
          >
            Сбросить фильтр
          </button>
        }
        onRetry={() => list.refetch()}
      >
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
              ПОКАЗАНО {rows.length} ИЗ {total}
            </span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="btn btn-icon"
                aria-label="Предыдущая страница"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                <Icon name="ti-chevron-left" />
              </button>
              {Array.from({ length: pages }, (_, i) => i)
                .slice(Math.max(0, page - 1), Math.max(0, page - 1) + 3)
                .map((i) => (
                  <button
                    key={i}
                    type="button"
                    className={`btn btn-icon${i === page ? ' btn-primary' : ''}`}
                    aria-current={i === page ? 'page' : undefined}
                    onClick={() => setPage(i)}
                  >
                    {i + 1}
                  </button>
                ))}
              <button
                type="button"
                className="btn btn-icon"
                aria-label="Следующая страница"
                disabled={page >= pages - 1}
                onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
              >
                <Icon name="ti-chevron-right" />
              </button>
            </div>
          </nav>
        </div>
      </QueryState>

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
