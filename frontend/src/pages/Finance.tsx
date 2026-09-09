import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Field } from '@/components/Field';
import { Kpi } from '@/components/Kpi';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useAuth } from '@/api/auth';
import { useBudget, useRequests, useSetBudget } from '@/api/hooks';
import type { RequestListItem } from '@/api/types';
import { useShell } from '@/shell/ShellContext';
import { money, plural } from '@/data/format';

/**
 * Финансы: сколько ждёт выплаты, как расходуется бюджет месяца и очередь
 * одобренных заявок. Выплату проводят в карточке заявки — клик по строке.
 */
export function Finance() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const budget = useBudget();
  const approved = useRequests({ status: 'approved', allPeriods: true, limit: 50 });

  const b = budget.data;
  const items = approved.data?.items ?? [];
  const open = (r: RequestListItem) => navigate(`/requests/${r.id}`);

  const weekCount = b?.week_requests ?? 0;
  const budgetNote = !b
    ? 'загрузка'
    : b.month_limit
      ? `использовано ${money(b.used)} · осталось ${money(b.remaining)}`
      : 'сумму на месяц ставит бухгалтерия';
  const usedNote = !b
    ? 'загрузка'
    : b.used_pct !== null
      ? `${b.used_pct}% бюджета месяца`
      : 'сомони за текущий месяц';

  return (
    <>
      <PageHeader title="Финансы" lead="Заявки к оплате и оплаченные" />

      <div className="kpi-grid">
        <Kpi
          label="К оплате"
          value={b ? money(b.week_payout) : '—'}
          note={b ? `сомони, ${weekCount} ${plural(weekCount, 'заявка', 'заявки', 'заявок')}` : 'загрузка'}
        />
        <Kpi
          label="Бюджет месяца"
          value={!b ? '—' : b.month_limit ? money(b.month_limit) : <span className="muted">не задан</span>}
          note={budgetNote}
        />
        <Kpi
          label="Использовано"
          value={b ? money(b.used) : '—'}
          dot={b && b.used_pct !== null && b.used_pct > 85 ? 'var(--yellow)' : undefined}
          note={usedNote}
        />
      </div>

      {can('pay_request') && (
        <QueryState isLoading={budget.isLoading} error={budget.error} onRetry={() => budget.refetch()}>
          <BudgetEditor current={b?.month_limit ?? null} />
        </QueryState>
      )}

      <section className="panel">
        <div className="panel-head">
          <h2 className="h3">К оплате</h2>
          <Link to="/requests?status=approved&all=1" className="small">
            Все заявки
          </Link>
        </div>
        <QueryState
          isLoading={approved.isLoading}
          error={approved.error}
          isEmpty={!approved.isLoading && items.length === 0}
          emptyTitle="Одобренных заявок в очереди нет"
          emptyNote="Заявка появится здесь, когда руководитель утвердит сумму."
          onRetry={() => approved.refetch()}
        >
          <div className="table-wrap">
            <table className="tbl cards" style={{ ['--tbl-min' as string]: '820px' }}>
              <thead>
                <tr>
                  <th>Номер</th>
                  <th>Наименование</th>
                  <th>Сотрудник</th>
                  <th>Объект</th>
                  <th>Дата</th>
                  <th className="right">Сумма, TJS</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr
                    key={r.id}
                    className="clickable"
                    tabIndex={0}
                    onClick={() => open(r)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        open(r);
                      }
                    }}
                    aria-label={`Заявка ${r.number}`}
                  >
                    <td className="num desktop-only">{r.number}</td>
                    <td>
                      <div className="row-title" style={{ fontWeight: 500 }}>
                        {r.title}
                      </div>
                      <div className="meta mobile-meta">
                        {r.number} · {r.date} · {r.project_name}
                      </div>
                    </td>
                    <td className="desktop-only">{r.employee_name}</td>
                    <td className="slate desktop-only">{r.project_name}</td>
                    <td className="mono desktop-only" style={{ color: 'var(--slate)', fontSize: 14 }}>
                      {r.date}
                    </td>
                    <td className="right">
                      <span className="mobile-only caption">{r.employee_name}</span>
                      <span className="num">{money(r.amount)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </QueryState>
      </section>
    </>
  );
}

/**
 * Сумма месяца. Ставит бухгалтерия: руководитель бюджет видит, но не
 * назначает — это распоряжение деньгами, а не отчёт. Каждая правка
 * попадает в журнал вместе со старым значением.
 */
function BudgetEditor({ current }: { current: string | null }) {
  const { flash } = useShell();
  const save = useSetBudget();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');

  const start = () => {
    setValue(current ?? '');
    setOpen(true);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    // Люди пишут сумму как удобно: «150 000,00». Приводим к тому, что
    // ждёт сервер, а не отказываем из-за запятой.
    const normalized = value.replace(/\s/g, '').replace(',', '.');
    if (!normalized || Number.isNaN(Number(normalized))) {
      flash('Введите сумму числом', 'var(--dot-err)');
      return;
    }
    try {
      await save.mutateAsync(normalized);
      setOpen(false);
      flash('Бюджет месяца сохранён', 'var(--dot-ok)');
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Не удалось сохранить бюджет', 'var(--dot-err)');
    }
  };

  if (!open) {
    return (
      <section className="card">
        <div className="row-between" style={{ alignItems: 'center' }}>
          <div style={{ display: 'grid', gap: 4 }}>
            <div className="label">Бюджет на месяц</div>
            <div className="small" style={{ color: 'var(--slate)' }}>
              {current
                ? `Задан ${money(current)} сомони. От него считаются проценты, остаток и недельная сводка.`
                : 'Пока не задан: проценты и остаток появятся после того, как вы укажете сумму.'}
            </div>
          </div>
          <button type="button" className="btn btn-secondary" onClick={start}>
            {current ? 'Изменить бюджет' : 'Задать бюджет'}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="card">
      <form onSubmit={submit} style={{ display: 'grid', gap: 16, maxWidth: 440 }}>
        <Field label="Бюджет на месяц, TJS" note="Считается от него: проценты, остаток и недельная сводка.">
          {(id) => (
            <input
              id={id}
              className="field num"
              inputMode="decimal"
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="150 000,00"
            />
          )}
        </Field>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? 'Сохраняем…' : 'Сохранить'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => setOpen(false)}>
            Отмена
          </button>
        </div>
      </form>
    </section>
  );
}
