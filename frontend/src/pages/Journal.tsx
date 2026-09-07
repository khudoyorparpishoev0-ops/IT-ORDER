import { useState } from 'react';
import { Field } from '@/components/Field';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
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
import { formatDateTime, plural } from '@/data/format';

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
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
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
        kicker="БЕЗОПАСНОСТЬ"
        title="Журнал"
        lead="Кто, что и когда делал в системе: входы, решения по заявкам, правки справочников"
        actions={
          <button
            type="button"
            className="btn btn-secondary"
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
            <Icon name="ti-file-spreadsheet" />
            {busy ? 'Готовим…' : 'Excel'}
          </button>
        }
      />

      <section className="panel" style={{ padding: 'var(--pad)', marginBottom: 'var(--gap)' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 16,
          }}
        >
          <Field label="Поиск">
            {(id) => (
              <input
                id={id}
                className="field"
                type="search"
                placeholder="Имя, номер, адрес"
                value={search}
                onChange={(e) => set(setSearch)(e.target.value)}
              />
            )}
          </Field>

          <Field label="Раздел">
            {(id) => (
              <select
                id={id}
                className="field"
                value={entity}
                onChange={(e) => set(setEntity)(e.target.value)}
              >
                {ENTITY_FILTER.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}
          </Field>

          <Field label="Действие">
            {(id) => (
              <select
                id={id}
                className="field"
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
            )}
          </Field>

          <Field label="Сотрудник">
            {(id) => (
              <select
                id={id}
                className="field"
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
            )}
          </Field>

          <Field label="С даты">
            {(id) => (
              <input
                id={id}
                className="field num"
                type="date"
                value={dateFrom}
                onChange={(e) => set(setDateFrom)(e.target.value)}
              />
            )}
          </Field>

          <Field label="По дату">
            {(id) => (
              <input
                id={id}
                className="field num"
                type="date"
                value={dateTo}
                onChange={(e) => set(setDateTo)(e.target.value)}
              />
            )}
          </Field>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            marginTop: 16,
            flexWrap: 'wrap',
          }}
        >
          <span className="caption">
            {total} {plural(total, 'запись', 'записи', 'записей')} по фильтру
          </span>
          {filtered && (
            <button type="button" className="btn btn-ghost" onClick={reset}>
              Сбросить фильтр
            </button>
          )}
        </div>
      </section>

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
        onRetry={() => list.refetch()}
      >
        <section className="panel">
          <div className="table-wrap">
            <table className="tbl" style={{ minWidth: 860 }}>
              <thead>
                <tr>
                  <th style={{ width: '15%' }}>КОГДА</th>
                  <th style={{ width: '20%' }}>КТО</th>
                  <th style={{ width: '12%' }}>РАЗДЕЛ</th>
                  <th style={{ width: '23%' }}>ДЕЙСТВИЕ</th>
                  <th style={{ width: '20%' }}>ЗАПИСЬ</th>
                  <th style={{ width: '10%' }}>АДРЕС</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const tone = actionTone(row.action);
                  return (
                    <tr key={row.id}>
                      <td className="num">
                        {formatDateTime(row.created_at, health.data?.timezone)}
                      </td>
                      <td>{row.username ?? '—'}</td>
                      <td>{entityLabel(row.entity)}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {tone && (
                            <span
                              aria-hidden="true"
                              style={{ width: 8, height: 8, flex: 'none', background: tone }}
                            />
                          )}
                          <span>{actionLabel(row.action)}</span>
                        </div>
                      </td>
                      <td>
                        <div className="num">{row.entity_id}</div>
                        {row.details && <div className="caption">{row.details}</div>}
                      </td>
                      <td className="num">{row.ip ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

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
              СТРАНИЦА {page + 1} ИЗ {pages}
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
        </section>
      </QueryState>

      <p className="caption" style={{ marginTop: 'var(--gap)' }}>
        Записи журнала не редактируются и не удаляются — ни здесь, ни через API.
        Адрес берётся из запроса; за прокси это адрес из заголовка, который
        выставляет наш же сервер.
      </p>
    </>
  );
}
