import { useNavigate, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { Pager } from '@/components/Pager';
import { QueryState } from '@/components/QueryState';
import { RequestsTable } from '@/components/RequestsTable';
import { useDownload } from '@/hooks/useDownload';
import { useProjects, useRequests } from '@/api/hooks';
import { monthTitle, plural } from '@/data/format';
import { STATUS, STATUS_ORDER } from '@/data/status';
import type { RequestStatus } from '@/api/types';

const PAGE_SIZE = 20;

/**
 * Все заявки. Фильтры живут в адресе: ссылку с фильтром можно переслать,
 * а поиск из топбара приходит сюда параметром q.
 */
export function Requests() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = params.get('status') as RequestStatus | null;
  const validStatus = status && (STATUS_ORDER as readonly string[]).includes(status) ? status : undefined;
  const projectId = Number(params.get('project')) || undefined;
  const q = params.get('q') ?? '';
  const allPeriods = params.get('all') === '1' || Boolean(q);
  const page = Math.max(0, Number(params.get('page')) || 0);

  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') next.delete(k);
      else next.set(k, v);
    }
    if (!('page' in patch)) next.delete('page');
    setParams(next, { replace: true });
  };

  const list = useRequests({
    status: validStatus,
    projectId,
    search: q || undefined,
    allPeriods,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });
  const projects = useProjects();
  const { download, busy } = useDownload();

  const total = list.data?.total ?? 0;
  const items = list.data?.items ?? [];
  const filtered = Boolean(validStatus || projectId || q);

  return (
    <>
      <PageHeader
        title="Все заявки"
        lead={
          list.data
            ? `${total} ${plural(total, 'запись', 'записи', 'записей')} · ${allPeriods ? 'за всё время' : monthTitle()}`
            : undefined
        }
        actions={
          <button type="button" className="btn btn-primary" onClick={() => navigate('/requests/new')}>
            <Icon name="ti-plus" size={18} />
            Создать заявку
          </button>
        }
      />

      <div className="filter-row">
        <label className="sr-only" htmlFor="f-status">
          Статус
        </label>
        <select
          id="f-status"
          className={`filter${validStatus ? ' is-active' : ''}`}
          value={validStatus ?? ''}
          onChange={(e) => set({ status: e.target.value || null })}
        >
          <option value="">Все статусы</option>
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {STATUS[s].label}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="f-project">
          Объект
        </label>
        <select
          id="f-project"
          className={`filter${projectId ? ' is-active' : ''}`}
          value={projectId ?? ''}
          onChange={(e) => set({ project: e.target.value || null })}
        >
          <option value="">Объект: все</option>
          {(projects.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="f-period">
          Период
        </label>
        <select
          id="f-period"
          className="filter mono"
          value={allPeriods ? 'all' : 'month'}
          onChange={(e) => set({ all: e.target.value === 'all' ? '1' : null })}
          disabled={Boolean(q)}
        >
          <option value="month">{monthTitle()}</option>
          <option value="all">все периоды</option>
        </select>
        {q && (
          <button type="button" className="filter is-active" onClick={() => set({ q: null, all: null })} aria-label={`Убрать поиск «${q}»`}>
            <Icon name="ti-search" size={14} />
            {q}
            <Icon name="ti-x" size={14} />
          </button>
        )}
        <span style={{ flex: 1 }} />
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={busy !== null}
          onClick={() =>
            download('xlsx', '/api/exports/requests.xlsx', {
              status: validStatus,
              project_id: projectId,
              search: q || undefined,
              all_periods: allPeriods || undefined,
            })
          }
        >
          <Icon name="ti-file-spreadsheet" size={18} />
          {busy ? 'Готовим…' : 'Excel'}
        </button>
      </div>

      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        isEmpty={!list.isLoading && items.length === 0}
        emptyTitle={filtered ? 'По выбранному фильтру заявок нет' : 'Заявок пока нет'}
        emptyNote={filtered ? 'Измените статус, объект или период — или сбросьте фильтр.' : 'Создайте первую заявку: объект и позиции, цены назовёт закуп.'}
        emptyAction={
          filtered ? (
            <button type="button" className="btn btn-secondary" onClick={() => setParams({}, { replace: true })}>
              Сбросить фильтр
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => navigate('/requests/new')}>
              Создать заявку
            </button>
          )
        }
        onRetry={() => list.refetch()}
      >
        <div className="panel">
          <RequestsTable rows={items} />
        </div>
        <Pager total={total} offset={page * PAGE_SIZE} limit={PAGE_SIZE} onChange={(offset) => set({ page: String(offset / PAGE_SIZE) })} />
      </QueryState>
    </>
  );
}
