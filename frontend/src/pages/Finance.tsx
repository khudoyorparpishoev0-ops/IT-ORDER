import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar } from '@/components/Bar';
import { EmptyState } from '@/components/EmptyState';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { Field } from '@/components/Field';
import { useAuth } from '@/api/auth';
import { useBudget, useSetBudget } from '@/api/hooks';
import { useShell } from '@/shell/ShellContext';
import { money, periodLabel, plural } from '@/data/format';

export function Finance() {
  const budget = useBudget();
  const data = budget.data;
  const { can } = useAuth();

  return (
    <>
      <PageHeader
        kicker={periodLabel()}
        title="Финансы"
        lead="Бюджет месяца и очередь выплат по одобренным заявкам"
      />

      <QueryState isLoading={budget.isLoading} error={budget.error} onRetry={() => budget.refetch()}>
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
              {money(data?.month_limit)}
            </div>
            {data?.month_limit ? (
              <>
                <Bar pct={data.used_pct ?? 0} />
                <div className="caption" style={{ marginTop: 8 }}>
                  Использовано {money(data.used)} · осталось {money(data.remaining)}
                </div>
              </>
            ) : (
              <div className="caption">
                Бюджет на месяц не задан. Израсходовано {money(data?.used)}.
              </div>
            )}

            {can('pay_request') && <BudgetEditor current={data?.month_limit ?? null} />}
          </section>

          <section className="card">
            <div className="label">К ВЫПЛАТЕ, TJS</div>
            <div className="metric" style={{ margin: '8px 0 8px' }}>
              {money(data?.week_payout)}
            </div>
            <div className="caption">
              {data?.week_requests ?? 0}{' '}
              {plural(
                data?.week_requests ?? 0,
                'одобренная заявка',
                'одобренные заявки',
                'одобренных заявок',
              )}{' '}
              ждут перечисления
            </div>
            {data?.week_requests ? (
              <Link className="btn btn-primary" style={{ marginTop: 24 }} to="/requests?status=approved">
                Перейти к одобренным
              </Link>
            ) : (
              <p className="caption" style={{ margin: '24px 0 0' }}>
                Одобренных заявок в очереди нет.
              </p>
            )}
          </section>
        </div>
      </QueryState>

      {/* Реквизиты остаются черновиком до подтверждения владельцем бренда
          и финансовым отделом — требование брендбука. */}
      <div style={{ marginTop: 'var(--gap)' }}>
        <EmptyState
          kicker="ЧЕРНОВИК · В РАБОТЕ"
          title="Банковские реквизиты не подключены"
          note="Реквизиты заполняются после подтверждения владельцем бренда и финансовым отделом."
        />
      </div>
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
    const normalized = value.replace(/\s|\u00a0/g, '').replace(',', '.');
    if (!normalized || Number.isNaN(Number(normalized))) {
      flash('Введите сумму числом', 'var(--dot-err)');
      return;
    }
    try {
      await save.mutateAsync(normalized);
      setOpen(false);
      flash('Бюджет месяца сохранён', 'var(--dot-ok)');
    } catch (err) {
      flash(
        err instanceof Error ? err.message : 'Не удалось сохранить бюджет',
        'var(--dot-err)',
      );
    }
  };

  if (!open) {
    return (
      <button type="button" className="btn btn-secondary" style={{ marginTop: 16 }} onClick={start}>
        {current ? 'Изменить бюджет' : 'Задать бюджет'}
      </button>
    );
  }

  return (
    <form onSubmit={submit} style={{ marginTop: 16, display: 'grid', gap: 12 }}>
      <Field label="Бюджет на месяц, TJS" note="Считается от него: проценты, остаток и недельная сводка.">
        {(id) => (
          <input
            id={id}
            className="input num"
            inputMode="decimal"
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="150000.00"
          />
        )}
      </Field>
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>
          {save.isPending ? 'Сохраняем…' : 'Сохранить'}
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => setOpen(false)}>
          Отмена
        </button>
      </div>
    </form>
  );
}
