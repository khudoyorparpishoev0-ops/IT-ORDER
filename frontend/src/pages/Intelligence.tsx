import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { Kpi } from '@/components/Kpi';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useAnalyticsAsk, useDigest, useIntelligence } from '@/api/hooks';
import { money, plural } from '@/data/format';
import type {
  AiText,
  AnalyticsReply,
  AnalyticsTurn,
  AttentionLevel,
  Digest,
  Intelligence as IntelligenceData,
} from '@/api/types';

/** Уровень внимания: цвет и слово. Эмодзи в интерфейсе запрещены. */
const LEVEL: Record<AttentionLevel, { label: string; color: string }> = {
  critical: { label: 'Критично', color: 'var(--dot-err)' },
  attention: { label: 'Внимание', color: 'var(--dot-warn)' },
  normal: { label: 'Норма', color: 'var(--dot-ok)' },
};

/** Готовые вопросы: печатать их каждый раз незачем. */
const QUICK = [
  'Что требует моего внимания?',
  'Какие заявки зависли?',
  'Что изменилось за неделю?',
  'Есть ли дубликаты?',
  'Какой объект создаёт больше всего заявок?',
];

/** «31 ч» или «2 дня 7 ч» — часы в сутках читать неудобно. */
function hours(value: number): string {
  if (value < 24) return `${value} ч`;
  const days = Math.floor(value / 24);
  const rest = value % 24;
  return `${days} ${plural(days, 'день', 'дня', 'дней')}${rest ? ` ${rest} ч` : ''}`;
}

function decimal(value: number | null, unit: string): string {
  if (value === null) return '—';
  // Округлённый до нуля этап — не «0 ч», а «меньше часа»: ноль часов
  // читается как «данных нет».
  if (value === 0) return unit ? 'меньше часа' : '0';
  return `${value.toFixed(1).replace('.0', '').replace('.', ',')} ${unit}`;
}

/**
 * Аналитика для руководителя. Все цифры считает сервер, модель их только
 * объясняет: раздел работает и без AI, просто без текста.
 */
export function Intelligence() {
  // Объяснение модели берём из раздела ORDER Intelligence, а цифры
  // разделов — из сводки без AI: иначе один заход в раздел стоил бы двух
  // обращений к Claude вместо одного.
  const intel = useIntelligence(true);
  const digest = useDigest(true, false);
  const data = digest.data;
  const brief = intel.data;

  const refresh = () => {
    void intel.refetch();
    void digest.refetch();
  };

  return (
    <>
      <PageHeader
        accent
        title={brief?.ai.headline ?? 'Что происходит в ORDER'}
        lead={
          brief
            ? `Активных ${brief.overview.active_requests} · просрочено ${
                brief.overview.overdue
              } · требуют внимания ${brief.overview.requires_attention}`
            : 'Собираем данные…'
        }
        actions={
          <button
            type="button"
            className="btn btn-secondary"
            onClick={refresh}
            disabled={intel.isFetching || digest.isFetching}
          >
            <Icon name="ti-sparkles" size={18} />
            {intel.isFetching || digest.isFetching ? 'Обновляем…' : 'Обновить'}
          </button>
        }
      />

      <QueryState isLoading={digest.isLoading} error={digest.error} onRetry={() => digest.refetch()}>
        {data && (
          <>
            <Ask />
            {brief && <Summary ai={brief.ai} />}
            {brief && <Executive data={brief} />}

            <div className="kpi-grid">
              <Kpi label="В работе" value={data.totals.active} note={`черновиков ${data.totals.drafts}`} />
              <Kpi
                label="Вышли за норматив"
                value={data.totals.over_norm}
                dot={data.totals.over_norm > 0 ? 'var(--dot-warn)' : undefined}
                note={`критичных ${data.totals.critical}`}
              />
              <Kpi
                label="К оплате"
                value={money(data.totals.to_pay_amount)}
                note={`сомони, ${data.totals.to_pay_count} ${plural(data.totals.to_pay_count, 'заявка', 'заявки', 'заявок')}`}
              />
              <Kpi
                label="Средний цикл"
                value={decimal(data.totals.avg_cycle_days, '')}
                note={data.totals.avg_cycle_days === null ? 'выплат за месяц не было' : 'суток от подачи до оплаты'}
              />
            </div>

            <Attention data={data} />
            <Stages data={data} />

            <div className="grid-auto">
              <Duplicates data={data} />
              <Trends data={data} />
            </div>
            <div className="grid-auto">
              <Projects data={data} />
              <People data={data} />
            </div>

            <section className="card">
              <div className="label" style={{ marginBottom: 8 }}>
                Чего ORDER не знает
              </div>
              <ul className="plain-list">
                {data.blind_spots.map((spot) => (
                  <li key={spot} className="caption">
                    {spot}
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </QueryState>
    </>
  );
}

/** Диалог с аналитиком. История живёт в панели: на сервере её нет. */
function Ask() {
  const ask = useAnalyticsAsk();
  const [history, setHistory] = useState<AnalyticsTurn[]>([]);
  const [text, setText] = useState('');
  const [reply, setReply] = useState<AnalyticsReply | null>(null);

  const send = async (question: string) => {
    const clean = question.trim();
    if (!clean || ask.isPending) return;
    const asked: AnalyticsTurn[] = [...history, { role: 'user', text: clean }];
    setHistory(asked);
    setText('');
    try {
      const answer = await ask.mutateAsync({ question: clean, history });
      setReply(answer);
      if (answer.available && answer.answer) {
        setHistory([...asked, { role: 'assistant', text: answer.answer }]);
      }
    } catch {
      setReply(null);
    }
  };

  return (
    <section className="card" style={{ display: 'grid', gap: 12 }}>
      <div className="row-between" style={{ alignItems: 'center' }}>
        <h2 className="h3">Спросить ORDER AI</h2>
        {history.length > 0 && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setHistory([]); setReply(null); }}>
            Очистить
          </button>
        )}
      </div>

      {history.length === 0 && (
        <p className="caption" style={{ margin: 0 }}>
          Спросите обычными словами: аналитик отвечает по данным ORDER и называет номера заявок.
        </p>
      )}

      <div className="chat">
        {history.map((turn, i) => (
          <div key={i} className={turn.role === 'user' ? 'chat-row own' : 'chat-row'}>
            <div className="chat-bubble">{turn.text}</div>
          </div>
        ))}
        {ask.isPending && (
          <div className="chat-row">
            <div className="chat-bubble muted" aria-live="polite">
              Смотрю данные…
            </div>
          </div>
        )}
      </div>

      {reply && !reply.enabled && (
        <p className="caption" style={{ margin: 0 }} role="alert">
          Помощник не подключён: администратор задаёт ключ Claude в параметрах сервера. Цифры ниже
          посчитаны и без него.
        </p>
      )}
      {reply && reply.enabled && !reply.available && !ask.isPending && (
        <div className="chat-options" role="alert">
          <p className="caption" style={{ margin: 0 }}>
            Аналитик не ответил. Цифры ниже на месте — они считаются на сервере.
          </p>
          <div className="chat-chips">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => void send(history.at(-1)?.text ?? '')}>
              Повторить
            </button>
          </div>
        </div>
      )}

      {reply?.available && (reply.bullets.length > 0 || reply.requests.length > 0 || reply.recommendations.length > 0) && (
        <div className="chat-options">
          {reply.bullets.length > 0 && (
            <ul className="plain-list">
              {reply.bullets.map((line) => (
                <li key={line} className="small">
                  {line}
                </li>
              ))}
            </ul>
          )}
          {reply.requests.length > 0 && (
            <div className="chat-lines">
              {reply.requests.map((ref) => (
                <div key={ref.number} className="chat-line">
                  <Link to={`/requests/${ref.id}`} className="small">
                    {ref.number}
                  </Link>
                  <span className="caption">{ref.why}</span>
                </div>
              ))}
            </div>
          )}
          {reply.recommendations.map((line) => (
            <div key={line} className="caption">
              {line}
            </div>
          ))}
        </div>
      )}

      <form
        className="chat-ask"
        onSubmit={(e) => {
          e.preventDefault();
          void send(text);
        }}
      >
        <label className="sr-only" htmlFor="analytics-question">
          Вопрос аналитику
        </label>
        <input
          id="analytics-question"
          className="field"
          placeholder="Например: какие заявки зависли?"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={ask.isPending}
        />
        <button type="submit" className="btn btn-primary" disabled={ask.isPending || !text.trim()}>
          <Icon name="ti-chevron-right" size={18} />
          <span className="sr-only">Спросить</span>
        </button>
      </form>

      <div className="chat-chips">
        {QUICK.map((question) => (
          <button
            key={question}
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={ask.isPending}
            onClick={() => void send(question)}
          >
            {question}
          </button>
        ))}
      </div>
    </section>
  );
}

function Summary({ ai }: { ai: AiText }) {
  if (!ai.enabled) {
    return (
      <p className="caption" style={{ margin: 0 }}>
        Пояснений от AI нет: ключ Claude не задан. Все цифры ниже посчитаны сервером.
      </p>
    );
  }
  if (!ai.available) {
    return (
      <p className="caption" style={{ margin: 0 }} role="alert">
        AI сейчас не ответил, поэтому сводка без пояснений. Цифры ниже на месте.
      </p>
    );
  }
  if (ai.summary.length === 0 && ai.recommendations.length === 0) return null;
  return (
    <section className="card card-accent" style={{ ['--accent' as string]: 'var(--green)' }}>
      <div className="label" style={{ marginBottom: 8 }}>
        Сводка
      </div>
      <ul className="plain-list">
        {ai.summary.map((line) => (
          <li key={line} className="small">
            {line}
          </li>
        ))}
      </ul>
      {ai.recommendations.length > 0 && (
        <>
          <div className="label" style={{ margin: '16px 0 8px' }}>
            С чего начать
          </div>
          <ul className="plain-list">
            {ai.recommendations.map((line) => (
              <li key={line} className="small">
                {line}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function Attention({ data }: { data: Digest }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="h3">Требует внимания</h2>
        <span className="num">{data.attention.length}</span>
      </div>
      {data.attention.length === 0 ? (
        <div className="empty">
          <div className="label">Всё в норме</div>
          <p className="caption" style={{ margin: 0 }}>
            Ни одна заявка не вышла за норматив этапа.
          </p>
        </div>
      ) : (
        data.attention.map((item) => (
          <div key={item.id} className="queue-row">
            <span
              className="queue-mark"
              style={{ background: LEVEL[item.level].color }}
              aria-hidden="true"
            />
            <div className="queue-text">
              <div>
                <span className="meta">{item.number}</span>{' '}
                <span className="caption">{LEVEL[item.level].label}</span>
              </div>
              <div className="queue-title">
                <Link to={`/requests/${item.id}`}>{item.title}</Link>
              </div>
              <div className="queue-meta">
                <span>
                  {item.project} · у: {item.holder} · {hours(item.hours)}
                  {item.norm_hours ? ` при норме ${item.norm_hours} ч` : ''}
                </span>
              </div>
              <ul className="plain-list">
                {item.reasons.map((reason) => (
                  <li key={reason} className="caption">
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
            {item.priced ? (
              <span className="num-lg">{money(item.amount)}</span>
            ) : (
              <span className="unpriced">не оценена</span>
            )}
          </div>
        ))
      )}
    </section>
  );
}

function Stages({ data }: { data: Digest }) {
  return (
    <section className="card">
      <div className="label" style={{ marginBottom: 12 }}>
        Этапы: где стоят заявки
      </div>
      <div className="table-wrap">
        <table className="tbl fit" style={{ ['--tbl-min' as string]: '640px' }}>
          <thead>
            <tr>
              <th>Этап</th>
              <th className="right">Заявок</th>
              <th className="right">Ждут</th>
              <th className="right">Норматив</th>
              <th className="right">За нормой</th>
              <th className="right">Факт за месяц</th>
            </tr>
          </thead>
          <tbody>
            {data.stages.map((stage) => (
              <tr key={stage.key}>
                <td>{stage.label}</td>
                <td className="right num">{stage.count}</td>
                <td className="right num">{decimal(stage.avg_hours, 'ч')}</td>
                <td className="right num">{stage.norm_hours ? `${stage.norm_hours} ч` : '—'}</td>
                <td className="right num">
                  {stage.over_norm > 0 && (
                    <span className="dot" style={{ ['--dot' as string]: 'var(--dot-warn)' }} aria-hidden="true" />
                  )}{' '}
                  {stage.over_norm}
                </td>
                <td className="right num">
                  {decimal(stage.done_avg_hours, 'ч')}
                  {stage.done_prev_avg_hours !== null && (
                    <span className="caption"> (было {decimal(stage.done_prev_avg_hours, 'ч')})</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Duplicates({ data }: { data: Digest }) {
  return (
    <section className="card">
      <div className="label" style={{ marginBottom: 8 }}>
        Похожие заявки
      </div>
      {data.duplicates.length === 0 ? (
        <p className="caption" style={{ margin: 0 }}>
          Повторов среди заявок в работе не видно.
        </p>
      ) : (
        <div className="chat-lines">
          {data.duplicates.map((pair) => (
            <div key={`${pair.first_id}-${pair.second_id}`} className="chat-line">
              <span className="small">
                <Link to={`/requests/${pair.first_id}`}>{pair.first_number}</Link> и{' '}
                <Link to={`/requests/${pair.second_id}`}>{pair.second_number}</Link>
              </span>
              <span className="caption">
                {pair.project} · {pair.materials.join(', ')} · разница {hours(pair.hours_apart)}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function Projects({ data }: { data: Digest }) {
  return (
    <section className="card">
      <div className="label" style={{ marginBottom: 8 }}>
        Объекты
      </div>
      <div className="table-wrap">
        <table className="tbl fit compact" style={{ ['--tbl-min' as string]: '380px' }}>
          <thead>
            <tr>
              <th>Объект</th>
              <th className="right">В работе</th>
              <th className="right">За месяц</th>
              <th className="right">Расход, TJS</th>
            </tr>
          </thead>
          <tbody>
            {data.projects.map((project) => (
              <tr key={project.id}>
                <td>
                  {project.name}
                  {project.top_materials.length > 0 && (
                    <div className="caption">чаще всего: {project.top_materials[0]}</div>
                  )}
                </td>
                <td className="right num">{project.active_count}</td>
                <td className="right num">{project.month_count}</td>
                <td className="right num">{money(project.month_amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function People({ data }: { data: Digest }) {
  return (
    <section className="card">
      <div className="label" style={{ marginBottom: 8 }}>
        У кого сейчас заявки
      </div>
      <div className="table-wrap">
        <table className="tbl fit compact" style={{ ['--tbl-min' as string]: '380px' }}>
          <thead>
            <tr>
              <th>Сотрудник</th>
              <th className="right">Держит</th>
              <th className="right">За нормой</th>
              <th className="right">Подал</th>
            </tr>
          </thead>
          <tbody>
            {data.people.map((person) => (
              <tr key={person.id}>
                <td>{person.name}</td>
                <td className="right num">{person.holding}</td>
                <td className="right num">{person.over_norm}</td>
                <td className="right num">{person.created_month}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption" style={{ margin: '8px 0 0' }}>
        Только факты. У задержки бывают причины, которых нет в данных.
      </p>
    </section>
  );
}

function Trends({ data }: { data: Digest }) {
  return (
    <section className="card">
      <div className="label" style={{ marginBottom: 8 }}>
        К прошлой неделе
      </div>
      <div style={{ display: 'grid', gap: 12 }}>
        {data.trends.map((trend) => (
          <div key={trend.label} className="hbar-row">
            <div className="hbar-line">
              <span>{trend.label}</span>
              <span className="num">
                {trend.unit === 'сомони' ? money(String(trend.current)) : trend.current}
              </span>
            </div>
            <div className="caption">
              неделей раньше{' '}
              {trend.unit === 'сомони' ? money(String(trend.previous)) : trend.previous}
              {trend.change_pct !== null && `, изменение ${trend.change_pct > 0 ? '+' : ''}${String(trend.change_pct).replace('.', ',')}%`}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}


/**
 * Сводка руководителя и очередь внимания.
 *
 * Всё, что здесь показано, посчитала база. Модель эти числа не
 * пересчитывает: по ним распоряжаются деньгами, а правдоподобная выдумка
 * дороже отсутствия цифры.
 */
function Executive({ data }: { data: IntelligenceData }) {
  const o = data.overview;
  return (
    <>
      <div className="kpi-grid">
        <Kpi label="Активных заявок" value={o.active_requests} note={`создано сегодня ${o.created_today}`} />
        <Kpi
          label="Просрочено"
          value={o.overdue}
          dot={o.overdue > 0 ? 'var(--dot-err)' : undefined}
          note={`без движения ${o.stuck}`}
        />
        <Kpi
          label="Требуют внимания"
          value={o.requires_attention}
          dot={o.requires_attention > 0 ? 'var(--dot-warn)' : undefined}
          note={o.problems.map((p) => `${p.count} ${p.label}`).join(' · ') || 'всё в порядке'}
        />
        <Kpi
          label="Сумма активных"
          value={money(o.amount_active)}
          note={`сомони · закрыто сегодня ${o.completed_today}`}
        />
      </div>

      {data.attention.length > 0 && (
        <section className="panel">
          <div className="panel-head">
            <h2 className="h3">Требуют внимания</h2>
            <span className="num">{data.attention.length}</span>
          </div>
          <div className="table-wrap">
            <table className="tbl fit">
              <thead>
                <tr>
                  <th>Заявка</th>
                  <th>Объект</th>
                  <th>Где стоит</th>
                  <th>Почему</th>
                </tr>
              </thead>
              <tbody>
                {data.attention.map((item) => (
                  <tr key={item.request_id} className="clickable">
                    <td>
                      <span
                        className="dot"
                        style={{ ['--dot' as string]: SEVERITY[item.severity] }}
                        aria-hidden="true"
                      />{' '}
                      <Link to={`/requests/${item.request_id}`}>{item.number}</Link>
                    </td>
                    <td>{item.project}</td>
                    <td className="caption">{item.stage_label}</td>
                    <td className="caption">{item.reasons.join(' · ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {data.anomalies.length > 0 && (
        <section className="card">
          <div className="label" style={{ marginBottom: 8 }}>
            Отличается от обычного уровня
          </div>
          {/* Отклонение — не нарушение: объект мог войти в активную фазу.
              Вывод делает руководитель, мы называем факт. */}
          <ul className="plain-list">
            {data.anomalies.map((a) => (
              <li key={a.code + a.subject} className="small">
                <span
                  className="dot"
                  style={{ ['--dot' as string]: SEVERITY[a.severity] }}
                  aria-hidden="true"
                />{' '}
                {a.detail}
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.issues.length > 0 && (
        <section className="card">
          <div className="label" style={{ marginBottom: 8 }}>
            Нестыковки
          </div>
          <ul className="plain-list">
            {data.issues.slice(0, 8).map((issue) => (
              <li key={`${issue.request_id}-${issue.code}`} className="small">
                <span
                  className="dot"
                  style={{ ['--dot' as string]: SEVERITY[issue.severity] }}
                  aria-hidden="true"
                />{' '}
                <Link to={`/requests/${issue.request_id}`}>{issue.number}</Link> — {issue.detail}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** Цвет уровня. Цвет никогда не идёт без слова рядом. */
const SEVERITY: Record<string, string> = {
  critical: 'var(--dot-err)',
  warning: 'var(--dot-warn)',
  info: 'var(--dot-off)',
};
