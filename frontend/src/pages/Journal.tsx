import { useState } from 'react';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { Pager } from '@/components/Pager';
import { QueryState } from '@/components/QueryState';
import { useAudit, useAuditActors, useHealth } from '@/api/hooks';
import type { AuditFilters } from '@/api/hooks';
import { useDownload } from '@/hooks/useDownload';
import {
  ACTION_GROUPS,
  ENTITY_FILTER,
  actionLabel,
  actionTone,
  entityLabel,
} from '@/data/audit';
import { formatDateTime } from '@/data/format';

const PAGE_SIZE = 50;

/**
 * Журнал действий. Только чтение: записи не правятся и не удаляются —
 * ни здесь, ни через API. Журнал ценен тем, что его нельзя переписать.
 */
export function Journal() {
  const [search, setSearch] = useState('');
  const [entity, setEntity] = useState('');
  const [action, setAction] = useState('');
  const [actor, setActor] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(0);
  const { download, busy } = useDownload();
  const health = useHealth();

  const filters: AuditFilters = {
    entity: entity || undefined,
    action: action || undefined,
    employeeId: actor ? Number(actor) : undefined,
    search: search.trim() || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };

  const list = useAudit(filters);
  const actors = useAuditActors();

  const rows = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const filtered = Boolean(entity || action || actor || search.trim() || dateFrom || dateTo);

  // Любое изменение фильтра возвращает на первую страницу: иначе человек
  // видит пустоту и решает, что записей нет.
  const set = <T,>(setter: (v: T) => void) => (value: T) => {
    setter(value);
    setPage(0);
  };

  const reset = () => {
    setSearch('');
    setEntity('');
    setAction('');
    setActor('');
    setDateFrom('');
    setDateTo('');
    setPage(0);
  };

  return (
    <>
      <PageHeader
        title="Журнал"
        lead="История действий по всем заявкам и справочникам"
        actions={
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={busy !== null}
            onClick={() =>
              download('audit', '/api/exports/audit.xlsx', {
                entity: filters.entity,
                action: filters.action,
                employee_id: filters.employeeId,
                search: filters.search,
                date_from: filters.dateFrom,
                date_to: filters.dateTo,
              })
            }
          >
            <Icon name="ti-file-spreadsheet" size={18} />
            {busy ? 'Готовим…' : 'Excel'}
          </button>
        }
      />

      <div className="filter-row">
        <label className="sr-only" htmlFor="j-search">
          Поиск
        </label>
        <input
          id="j-search"
          className="field"
          type="search"
          placeholder="Имя, номер, адрес"
          value={search}
          onChange={(e) => set(setSearch)(e.target.value)}
          style={{ height: 36, fontSize: 14, flex: '1 1 200px', maxWidth: 280 }}
        />

        <label className="sr-only" htmlFor="j-entity">
          Раздел
        </label>
        <select
          id="j-entity"
          className={`filter${entity ? ' is-active' : ''}`}
          value={entity}
          onChange={(e) => set(setEntity)(e.target.value)}
        >
          {ENTITY_FILTER.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        <label className="sr-only" htmlFor="j-action">
          Действие
        </label>
        <select
          id="j-action"
          className={`filter${action ? ' is-active' : ''}`}
          value={action}
          onChange={(e) => set(setAction)(e.target.value)}
        >
          <option value="">Все действия</option>
          {ACTION_GROUPS.map((group) => (
            <optgroup key={group.label} label={group.label}>
              {group.actions.map((a) => (
                <option key={a} value={a}>
                  {actionLabel(a)}
                </option>
              ))}
            </optgroup>
          ))}
        </select>

        <label className="sr-only" htmlFor="j-actor">
          Сотрудник
        </label>
        <select
          id="j-actor"
          className={`filter${actor ? ' is-active' : ''}`}
          value={actor}
          onChange={(e) => set(setActor)(e.target.value)}
        >
          <option value="">Все сотрудники</option>
          {(actors.data ?? [])
            .filter((a) => a.employee_id !== null)
            .map((a) => (
              <option key={a.employee_id} value={String(a.employee_id)}>
                {a.username}
              </option>
            ))}
        </select>

        <label className="sr-only" htmlFor="j-from">
          С даты
        </label>
        <input
          id="j-from"
          className={`filter mono${dateFrom ? ' is-active' : ''}`}
          type="date"
          value={dateFrom}
          max={dateTo || undefined}
          onChange={(e) => set(setDateFrom)(e.target.value)}
        />

        <label className="sr-only" htmlFor="j-to">
          По дату
        </label>
        <input
          id="j-to"
          className={`filter mono${dateTo ? ' is-active' : ''}`}
          type="date"
          value={dateTo}
          min={dateFrom || undefined}
          onChange={(e) => set(setDateTo)(e.target.value)}
        />

        {filtered && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={reset}>
            Сбросить фильтр
          </button>
        )}
      </div>

      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        isEmpty={rows.length === 0}
        emptyTitle={filtered ? 'По фильтру записей нет' : 'Журнал пуст'}
        emptyNote={
          filtered
            ? 'Измените период или снимите ограничения.'
            : 'Записи появятся с первым входом и первым действием в системе.'
        }
        emptyAction={
          filtered && (
            <button type="button" className="btn btn-secondary" onClick={reset}>
              Сбросить фильтр
            </button>
          )
        }
        onRetry={() => list.refetch()}
      >
        <div className="panel">
          <div className="table-wrap">
            <table className="tbl" style={{ ['--tbl-min' as string]: '860px' }}>
              <thead>
                <tr>
                  <th style={{ width: '15%' }}>Дата и время</th>
                  <th style={{ width: '20%' }}>Кто</th>
                  <th style={{ width: '12%' }}>Раздел</th>
                  <th style={{ width: '23%' }}>Действие</th>
                  <th style={{ width: '20%' }}>Запись</th>
                  <th style={{ width: '10%' }}>Адрес</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const tone = actionTone(row.action);
                  return (
                    <tr key={row.id}>
                      <td className="num" style={{ fontWeight: 400 }}>
                        {formatDateTime(row.created_at, health.data?.timezone)}
                      </td>
                      <td className="slate">{row.username ?? '—'}</td>
                      <td className="slate">{entityLabel(row.entity)}</td>
                      <td>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                          {tone && <span className="dot" style={{ ['--dot' as string]: tone }} />}
                          {actionLabel(row.action)}
                        </span>
                      </td>
                      <td>
                        <div className="num">{row.entity_id}</div>
                        {row.details && <div className="caption">{row.details}</div>}
                      </td>
                      <td className="mono" style={{ whiteSpace: 'nowrap' }}>
                        {row.ip ?? '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <Pager total={total} offset={page * PAGE_SIZE} limit={PAGE_SIZE} onChange={(offset) => setPage(offset / PAGE_SIZE)} />
      </QueryState>

      <p className="caption" style={{ margin: 0 }}>
        Записи журнала не редактируются и не удаляются — ни здесь, ни через API.
        Адрес берётся из запроса; за прокси это адрес из заголовка, который
        выставляет наш же сервер.
      </p>
    </>
  );
}
