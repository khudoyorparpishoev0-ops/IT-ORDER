import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { NewRequestModal } from '@/components/NewRequestModal';
import { RequestModal } from '@/components/RequestModal';
import { RequestsTable } from '@/components/RequestsTable';
import { useDownload } from '@/hooks/useDownload';
import { useSortedRequests } from '@/hooks/useSortedRequests';
import { useDashboard, useQueueInfo, useRequests } from '@/api/hooks';
import { money, monthAfterZa, periodLabel, plural, somoni } from '@/data/format';
import type { RequestListItem } from '@/api/types';
import { useShell } from '@/shell/ShellContext';
import { useAuth } from '@/api/auth';
import { VARIANTS } from '@/shell/config';

export function Dashboard() {
  const navigate = useNavigate();
  const { variant } = useShell();
  const { user, can } = useAuth();
  const tableFirst = VARIANTS[variant].tableFirst;
  // Сводки по чужим расходам видит только руководитель, финансы и админ.
  const seesReports = can('view_reports');
  const seesQueue = can('decide_request');

  const [modal, setModal] = useState<RequestListItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState('');
  const { download, busy } = useDownload();

  const stats = useDashboard(seesReports);
  const queue = useQueueInfo(seesQueue);
  // Вариант B показывает все заявки периода, вариант C — четыре последние.
  const list = useRequests({ search: search.trim() || undefined, limit: tableFirst ? 50 : 4 });
  const { rows, sort, dir, onSort } = useSortedRequests(list.data?.items ?? []);

  const metrics = (
    <section
      aria-label="Ключевые метрики"
      style={{
        order: tableFirst ? 3 : 1,
        display: 'flex',
        flexWrap: 'wrap',
        background: 'var(--paper)',
        border: '1px solid var(--line)',
      }}
    >
      {[
        {
          label: 'ВСЕГО ЗАЯВОК',
          value: String(stats.data?.total_requests ?? '—'),
          note: stats.data
            ? `за ${monthAfterZa()}, ${stats.data.employees_count} ${plural(
                stats.data.employees_count,
                'сотрудник',
                'сотрудника',
                'сотрудников',
              )}`
            : '',
        },
        {
          label: 'ОДОБРЕНО, TJS',
          value: money(stats.data?.approved_amount),
          note: stats.data
            ? `${stats.data.approved_count} ${plural(
                stats.data.approved_count,
                'заявка',
                'заявки',
                'заявок',
              )}, ждут выплаты`
            : '',
        },
        {
          label: 'НА УТВЕРЖДЕНИИ, TJS',
          value: money(stats.data?.pending_amount),
          note: stats.data
            ? `${stats.data.pending_count} ${plural(
                stats.data.pending_count,
                'заявка ждёт',
                'заявки ждут',
                'заявок ждут',
              )} решения`
            : '',
        },
        {
          label: 'БЮДЖЕТ МЕСЯЦА, TJS',
          value: money(stats.data?.budget_amount),
          note:
            stats.data?.budget_used_pct !== null && stats.data?.budget_used_pct !== undefined
              ? `использовано ${stats.data.budget_used_pct}%`
              : 'бюджет не задан',
        },
      ].map((s, i) => (
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

  const q = queue.data;
  const banner = q && q.count > 0 && (
    <section
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
          <div className="h3">
            {q.count} {plural(q.count, 'заявка ждёт', 'заявки ждут', 'заявок ждут')} вашего
            решения
          </div>
          <div style={{ fontSize: 13, opacity: 0.8, marginTop: 2 }}>
            {/* Имя даём через двоеточие: русская фамилия после предлога
                потребовала бы склонения, а надёжно склонять её мы не можем. */}
            {q.oldest_employee && (
              <>
                Самая давняя заявка: {q.oldest_employee},{' '}
                {q.oldest_days
                  ? `${q.oldest_days} ${plural(q.oldest_days, 'день', 'дня', 'дней')} назад`
                  : 'сегодня'}
                .{' '}
              </>
            )}
            Порог автоодобрения — {somoni(q.auto_approve_threshold)}
          </div>
        </div>
      </div>
      <button type="button" className="btn btn-primary" onClick={() => navigate('/approvals')}>
        Перейти к согласованию
      </button>
    </section>
  );

  const table = (
    <section className="panel" style={{ order: tableFirst ? 1 : 3 }}>
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
        <h2 className="h3">
          {tableFirst ? `Заявки за ${monthAfterZa()}` : 'Последние заявки'}
        </h2>
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
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <button type="button" className="btn btn-secondary" onClick={() => navigate('/requests')}>
            Все заявки
          </button>
        </div>
      </div>

      <QueryState
        isLoading={list.isLoading}
        error={list.error}
        isEmpty={rows.length === 0}
        emptyTitle={search ? 'По запросу заявок нет' : 'Заявок за период пока нет'}
        emptyNote={
          search
            ? 'Проверьте фамилию сотрудника или очистите поиск.'
            : 'Как только сотрудники подадут заявки, они появятся здесь.'
        }
        emptyAction={
          search && (
            <button type="button" className="btn btn-secondary" onClick={() => setSearch('')}>
              Очистить поиск
            </button>
          )
        }
        onRetry={() => list.refetch()}
      >
        <RequestsTable rows={rows} sort={sort} dir={dir} onSort={onSort} onOpen={setModal} />
      </QueryState>
    </section>
  );

  return (
    <>
      <PageHeader
        kicker={periodLabel()}
        title="Панель управления"
        lead={
          !seesReports
            ? `${user?.full_name ?? ''} · ${user?.position ?? ''}`
            : stats.data
            ? `Команда из ${stats.data.employees_count} ${plural(
                stats.data.employees_count,
                'сотрудника',
                'сотрудников',
                'сотрудников',
              )}, ${stats.data.total_requests} ${plural(
                stats.data.total_requests,
                'заявка',
                'заявки',
                'заявок',
              )} за период`
            : undefined
        }
        actions={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy !== null}
              onClick={() => download('requests', '/api/exports/requests.xlsx')}
            >
              <Icon name="ti-download" />
              {busy ? 'Готовим…' : 'Экспорт'}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setCreating(true)}
            >
              <Icon name="ti-plus" />
              Новая заявка
            </button>
          </>
        }
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)' }}>
        {seesReports && metrics}
        {seesQueue && banner}
        {table}
      </div>

      {creating && <NewRequestModal onClose={() => setCreating(false)} />}

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
