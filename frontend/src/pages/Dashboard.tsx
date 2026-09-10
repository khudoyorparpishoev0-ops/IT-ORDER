import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { DecisionModal } from '@/components/DecisionModal';
import { Icon } from '@/components/Icon';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { RequestsTable } from '@/components/RequestsTable';
import { useAuth } from '@/api/auth';
import { useExecutiveOverview, useOverview, useRequests } from '@/api/hooks';
import { ROLE_LABEL } from '@/shell/config';
import { DELAY_DAYS, STATUS } from '@/data/status';
import { days, money, monthAfterZa, plural, today } from '@/data/format';
import type { Overview, RequestListItem } from '@/api/types';

/** Цвет уровня в блоке ORDER Intelligence. Цвет всегда идёт со словом. */
const SEVERITY: Record<string, string> = {
  critical: 'var(--dot-err)',
  warning: 'var(--dot-warn)',
  info: 'var(--dot-off)',
};

/** Зелёная шкала по этапам: черновик светлый, оплата — forest. */
const CHART = ['var(--chart-5)', 'var(--chart-4)', 'var(--chart-3)', 'var(--chart-2)', 'var(--chart-1)'];

/** Числительные словами для заголовка: «три решения», а не «3 решения». */
const NEUTER = ['', 'одно', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять', 'десять'];
const FEMININE = ['', 'одна', 'две', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять', 'десять'];

function inWords(n: number, table: string[]): string {
  return n > 0 && n < table.length ? table[n] : String(n);
}

/** Этап в предложном падеже для подвала «Дольше всего заявки стоят …». */
const STAGE_WHERE: Record<string, string> = {
  Черновик: 'в черновиках',
  'Согласование покупки': 'на согласовании покупки',
  'У закупа': 'у закупа',
  'Согласование суммы': 'на согласовании суммы',
  'К оплате': 'в бухгалтерии',
};

/** Что именно ждёт решения: подпись под строкой очереди. */
const DECISION_STAGE: Record<string, string> = {
  pending: 'согласование покупки',
  priced: 'согласование суммы',
};

/** «3,4 дня» — дробные сутки, «3 дня» — целые. */
function daysDecimal(value: number): string {
  if (value < 1) return 'меньше дня';
  if (Number.isInteger(value)) return days(value);
  return `${value.toFixed(1).replace('.', ',')} дня`;
}

/**
 * Заголовок-вывод: собирается из числа решений в очереди и числа
 * задержавшихся заявок — цифры живые, а не подпись «Дашборд».
 */
function headline(data: Overview | undefined, canDecide: boolean): string {
  if (!data) return 'Дашборд';
  const delayed =
    data.delayed_total > 0
      ? `${inWords(data.delayed_total, FEMININE)} ${plural(data.delayed_total, 'заявка', 'заявки', 'заявок')} ${
          data.delayed_total === 1 ? 'задержалась' : 'задержались'
        }`
      : '';
  let head: string;
  if (canDecide) {
    head =
      data.decisions > 0
        ? `На вас ${inWords(data.decisions, NEUTER)} ${plural(data.decisions, 'решение', 'решения', 'решений')}`
        : 'Решений на вас нет';
  } else {
    head =
      data.in_work > 0
        ? `В работе ${inWords(data.in_work, FEMININE)} ${plural(data.in_work, 'заявка', 'заявки', 'заявок')}`
        : 'Заявок в работе нет';
  }
  if (delayed) return `${head}, ${delayed}`;
  if (data.in_work > 0) return `${head}, всё идёт в срок`;
  return head;
}

/**
 * Дашборд — рабочая очередь, а не витрина цифр. Отвечает на два вопроса:
 * что требует моего решения и где сейчас стоят заявки. Сотрудник видит
 * то же по своим заявкам, очереди решений у него нет.
 */
export function Dashboard() {
  const navigate = useNavigate();
  const { user, can } = useAuth();
  const canDecide = can('decide_request');
  const overview = useOverview();
  // Только цифры: платить за текст модели на каждом заходе на дашборд
  // незачем — объяснения живут в разделе «Аналитика AI».
  // Только цифры: карточка на дашборде не должна стоить денег на
  // каждом заходе — объяснения живут в разделе «Аналитика AI».
  const exec = useExecutiveOverview(can('view_reports'));
  const list = useRequests({ limit: 5 });
  const [decision, setDecision] = useState<RequestListItem | null>(null);

  const d = overview.data;
  const scope = can('view_all_requests') ? 'все объекты' : 'мои заявки';
  const role = user ? (ROLE_LABEL[user.role] ?? user.role) : '';
  const maxStage = d ? Math.max(1, ...d.stages.map((s) => s.count)) : 1;

  return (
    <>
      <PageHeader
        accent
        title={headline(d, canDecide)}
        lead={[today(), role, scope, d ? `${d.in_work} ${plural(d.in_work, 'заявка', 'заявки', 'заявок')} в работе` : null]
          .filter(Boolean)
          .join(' · ')}
        actions={
          <button type="button" className="btn btn-primary" onClick={() => navigate('/requests/new')}>
            <Icon name="ti-plus" size={18} />
            Создать заявку
          </button>
        }
      />

      {exec.data && exec.data.requires_attention > 0 && (
        <section className="card card-accent" style={{ ['--accent' as string]: 'var(--dot-warn)' }}>
          <div className="row-between" style={{ alignItems: 'center' }}>
            <div style={{ display: 'grid', gap: 4, minWidth: 0 }}>
              <div className="label">ORDER Intelligence</div>
              <div className="h3">
                Сегодня требуют внимания: {exec.data.requires_attention}
              </div>
              {/* Разбивка по причинам, а не общий счётчик: директору важно,
                  что именно случилось, — просрочка и дубль лечатся
                  по-разному. */}
              <ul className="plain-list small" style={{ color: 'var(--slate)' }}>
                {exec.data.problems.map((problem) => (
                  <li key={problem.code} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      className="dot"
                      style={{ ['--dot' as string]: SEVERITY[problem.severity] }}
                      aria-hidden="true"
                    />
                    {problem.count} {problem.label}
                  </li>
                ))}
              </ul>
            </div>
            <Link to="/intelligence" className="btn btn-secondary">
              Посмотреть все
            </Link>
          </div>
        </section>
      )}

      <QueryState isLoading={overview.isLoading} error={overview.error} onRetry={() => overview.refetch()}>
        {d && (
          <>
            <div className="dash-grid">
              {canDecide && d.decisions > 0 && (
                <section className="panel">
                  <div className="panel-head">
                    <h2 className="h3">Требует решения</h2>
                    <span className="num">{d.decisions}</span>
                  </div>
                  {d.queue.map((r) => {
                    const wait = r.awaiting_days ?? 0;
                    const delayed = wait >= DELAY_DAYS;
                    return (
                      <div key={r.id} className="queue-row">
                        <span className={delayed ? 'queue-mark delayed' : 'queue-mark'} aria-hidden="true" />
                        <div className="queue-text">
                          <div>
                            <span className="meta">{r.number}</span>
                          </div>
                          <div className="queue-title">
                            <Link to={`/requests/${r.id}`}>{r.title}</Link>
                          </div>
                          <div className="queue-meta">
                            <span className="dot" style={{ ['--dot' as string]: STATUS[r.status].color }} aria-hidden="true" />
                            <span>
                              {r.project_name} · {DECISION_STAGE[r.status] ?? r.awaiting_label} ·{' '}
                              {wait > 0 ? `ждёт ${days(wait)}` : 'подана сегодня'}
                            </span>
                          </div>
                        </div>
                        {r.priced ? <span className="num-lg">{money(r.amount)}</span> : <span className="unpriced">не оценена</span>}
                        <button type="button" className="btn btn-primary" onClick={() => setDecision(r)}>
                          Согласовать
                        </button>
                      </div>
                    );
                  })}
                  <Link to="/approvals" className="panel-foot-link">
                    Вся очередь согласования
                    <Icon name="ti-chevron-right" size={18} />
                  </Link>
                </section>
              )}

              <section className="card" style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
                <div>
                  <div className="rubric" style={{ marginBottom: 8 }}>
                    {d.in_work > 0
                      ? `Где стоят ${d.in_work} ${plural(d.in_work, 'заявка', 'заявки', 'заявок')}`
                      : 'Где стоят заявки'}
                  </div>
                  <div className="caption">Количество заявок на каждом этапе</div>
                </div>
                <div style={{ display: 'grid', gap: 12 }}>
                  {d.stages.map((s, i) => (
                    <div key={s.key} className="hbar-row">
                      <div className="hbar-line">
                        <span>{s.label}</span>
                        <span className="num" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                          {s.delayed && <span className="dot" style={{ ['--dot' as string]: 'var(--yellow)' }} aria-label="есть задержки" />}
                          {s.count}
                        </span>
                      </div>
                      <div className="hbar">
                        <span style={{ width: `${(s.count / maxStage) * 100}%`, background: CHART[i] }} />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="caption" style={{ borderTop: '1px solid var(--line)', paddingTop: 12 }}>
                  {d.slowest_stage && d.slowest_days !== null
                    ? `Дольше всего заявки стоят ${STAGE_WHERE[d.slowest_stage] ?? d.slowest_stage} — ${daysDecimal(d.slowest_days)}.`
                    : 'В работе ничего нет: очередь пуста.'}
                </div>
              </section>
            </div>

            <section className="card metrics">
              <div className="metric">
                <div className="rubric">К оплате</div>
                <div className="metric-value">{money(d.to_pay_amount)}</div>
                <div className="caption">{d.to_pay_count} {plural(d.to_pay_count, 'заявка', 'заявки', 'заявок')}</div>
              </div>
              <div className="metric">
                <div className="rubric">Оплачено за {monthAfterZa()}</div>
                <div className="metric-value">{money(d.paid_amount)}</div>
                <div className="caption">{d.paid_count} {plural(d.paid_count, 'заявка', 'заявки', 'заявок')}</div>
              </div>
              <div className="metric">
                <div className="rubric">Средний цикл</div>
                <div className="metric-value">{d.avg_cycle_days === null ? '—' : d.avg_cycle_days.toFixed(1).replace('.', ',')}</div>
                <div className="caption">{d.avg_cycle_days === null ? 'выплат за месяц не было' : 'дня от подачи до оплаты'}</div>
              </div>
              <div className="metric">
                <div className="rubric">Отклонено</div>
                <div className="metric-value">{d.rejected_count}</div>
                <div className="caption">за {monthAfterZa()}</div>
              </div>
            </section>
          </>
        )}
      </QueryState>

      <section className="panel">
        <div className="panel-head">
          <h2 className="h3">{can('view_all_requests') ? 'Последние заявки' : 'Мои заявки'}</h2>
          <Link to="/requests" className="small">
            Все заявки
          </Link>
        </div>
        <QueryState
          isLoading={list.isLoading}
          error={list.error}
          isEmpty={!list.isLoading && (list.data?.items.length ?? 0) === 0}
          emptyTitle="Заявок за период пока нет"
          emptyNote={
            can('view_all_requests')
              ? 'Как только сотрудники подадут заявки, они появятся здесь.'
              : 'Нажмите «Создать заявку» — объект и позиции, цены назовёт закуп.'
          }
          onRetry={() => list.refetch()}
        >
          <RequestsTable rows={list.data?.items ?? []} compact />
        </QueryState>
      </section>

      {decision && <DecisionModal request={decision} approve onClose={() => setDecision(null)} />}
    </>
  );
}
