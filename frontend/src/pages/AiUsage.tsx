import { Kpi } from '@/components/Kpi';
import { PageHeader } from '@/components/PageHeader';
import { QueryState } from '@/components/QueryState';
import { useAiUsage } from '@/api/hooks';
import { useAuth } from '@/api/auth';
import { money, plural } from '@/data/format';

/**
 * Расход на AI: сколько стоит помощник и приносит ли он пользу.
 *
 * Раздел отвечает на один вопрос — продолжать за это платить или нет.
 * Поэтому наверху шесть цифр, а ниже три таблицы: за что платим, чем
 * платим и чем ответы не подошли. Графиков нет: эти цифры читают, а не
 * разглядывают.
 *
 * Стоимость в долларах: счёт от Anthropic приходит в них, и перевод в
 * сомони по выдуманному курсу сверить со счётом было бы нечем.
 */
export function AiUsage() {
  const { can } = useAuth();
  const allowed = can('manage_reference');
  const report = useAiUsage(allowed);

  const data = report.data;
  const [today, week, month] = data?.periods ?? [];

  return (
    <>
      <PageHeader
        title="Расход AI"
        lead="Стоимость помощника, польза от него и бюджет месяца"
      />

      <QueryState
        isLoading={report.isLoading}
        error={report.error}
        isEmpty={Boolean(data) && month?.requests === 0}
        emptyTitle="Обращений к помощнику пока не было"
        emptyNote="Раздел наполнится, как только сотрудники начнут пользоваться помощником. Он читает журнал обращений и не зависит от доступности Anthropic."
        onRetry={() => report.refetch()}
      >
        {data && month && (
          <>
            <div className="kpi-grid">
              <Kpi
                label="Расход за месяц"
                value={money(data.budget.spent_usd)}
                note={
                  data.budget.limit_usd
                    ? `USD из ${money(data.budget.limit_usd)} бюджета${data.budget.used_pct !== null ? ` · ${data.budget.used_pct}%` : ''}`
                    : 'USD, календарный месяц'
                }
                dot={data.budget.warning ? 'var(--yellow)' : undefined}
              />
              <Kpi
                label="Обращений"
                value={month.requests}
                note={`за 30 дней · сегодня ${today?.requests ?? 0} · за неделю ${week?.requests ?? 0}`}
              />
              <Kpi
                label="Ответом воспользовались"
                value={data.apply_rate_pct === null ? '—' : `${data.apply_rate_pct}%`}
                note={
                  data.offered === 0
                    ? 'нечего было применять'
                    : `${data.applied} из ${data.offered}, где кнопка «Применить» была`
                }
              />
              <Kpi
                label="Оценили полезным"
                value={
                  data.feedback.useful + data.feedback.useless === 0
                    ? '—'
                    : `${data.feedback.useful} из ${data.feedback.useful + data.feedback.useless}`
                }
                note={
                  data.feedback.useful + data.feedback.useless === 0
                    ? 'оценок пока нет'
                    : `оценили ${data.feedback.feedback_rate_pct ?? 0}% ответов`
                }
              />
              <Kpi
                label="Без модели"
                value={month.avoided}
                note={
                  month.avoided_pct === null
                    ? 'ORDER отвечал сам'
                    : `${month.avoided_pct}% обращений закрыты алиасом или кэшем`
                }
              />
              <Kpi
                label="Отказов"
                value={month.error_pct === null ? '—' : `${month.error_pct}%`}
                note={
                  month.avg_seconds === null
                    ? 'модель не отвечала'
                    : `среднее время ответа ${month.avg_seconds.toFixed(1).replace('.', ',')} с`
                }
                dot={month.error_pct !== null && month.error_pct > 20 ? 'var(--dot-err)' : undefined}
              />
            </div>

            {data.budget.warning && (
              <section className="card card-accent">
                <div style={{ fontWeight: 600 }}>
                  Израсходовано {data.budget.used_pct}% месячного бюджета на AI
                </div>
                <p className="caption" style={{ margin: '4px 0 0' }}>
                  Помощник продолжает работать: порог — повод решить, а не причина
                  выключить то, чем люди пользуются посреди рабочего дня. Бюджет
                  задаётся переменной <span className="num">AI_MONTHLY_BUDGET_USD</span>.
                </p>
              </section>
            )}

            <Periods periods={data.periods} />

            <section className="panel">
              <div className="panel-head">
                <h2 className="h3">Модели</h2>
              </div>
              <div className="table-wrap">
                <table className="tbl fit" style={{ ['--tbl-min' as string]: '520px' }}>
                  <thead>
                    <tr>
                      <th>Модель</th>
                      <th className="right">Обращений</th>
                      <th className="right">Стоимость, USD</th>
                      <th className="right">Среднее время</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.models.map((row) => (
                      <tr key={row.model ?? 'unknown'}>
                        <td>
                          <span className="num">{row.model ?? 'не названа'}</span>
                          {!row.price_known && (
                            <div className="caption">
                              цена неизвестна — сумма занижена
                            </div>
                          )}
                        </td>
                        <td className="right num">{row.requests}</td>
                        <td className="right num">
                          {row.price_known ? money(row.cost_usd) : '—'}
                        </td>
                        <td className="right num">
                          {row.avg_seconds === null
                            ? '—'
                            : `${row.avg_seconds.toFixed(1).replace('.', ',')} с`}
                        </td>
                      </tr>
                    ))}
                    {data.models.length === 0 && (
                      <tr>
                        <td colSpan={4} className="muted">
                          Ни одного оплаченного ответа: обращения закрыты без модели
                          либо не дошли до неё.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="caption" style={{ margin: 0 }}>
                Отказы сюда не входят: ответа не получили, платить не за что — их
                видно долей отказов выше. Прайс Anthropic сверялся {data.prices_checked}. Меняется файлом из{' '}
                <span className="num">AI_PRICES_FILE</span> — без пересборки.
              </p>
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2 className="h3">За что платим</h2>
              </div>
              <div className="table-wrap">
                <table className="tbl fit" style={{ ['--tbl-min' as string]: '640px' }}>
                  <thead>
                    <tr>
                      <th>Тип использования</th>
                      <th className="right">Обращений</th>
                      <th className="right">Стоимость, USD</th>
                      <th className="right">Токенов в среднем</th>
                      <th className="right">Применили</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.usage_types.map((row) => (
                      <tr key={row.key}>
                        <td>{row.label}</td>
                        <td className="right num">{row.requests}</td>
                        <td className="right num">{money(row.cost_usd)}</td>
                        <td className="right num">{row.avg_tokens ?? '—'}</td>
                        <td className="right num">
                          {row.apply_rate_pct === null ? (
                            <span className="muted">не применяется</span>
                          ) : (
                            `${row.apply_rate_pct}%`
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {data.feedback.top_reasons.length > 0 && (
              <section className="panel">
                <div className="panel-head">
                  <h2 className="h3">Чем ответы не подошли</h2>
                </div>
                <div className="table-wrap">
                  <table className="tbl fit" style={{ ['--tbl-min' as string]: '420px' }}>
                    <tbody>
                      {data.feedback.top_reasons.map((reason) => (
                        <tr key={reason.reason}>
                          <td>{reason.label}</td>
                          <td className="right num">{reason.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {data.employees.length > 0 && (
              <section className="panel">
                <div className="panel-head">
                  <h2 className="h3">Кто обращается</h2>
                </div>
                <div className="table-wrap">
                  <table className="tbl fit" style={{ ['--tbl-min' as string]: '520px' }}>
                    <thead>
                      <tr>
                        <th>Сотрудник</th>
                        <th className="right">Обращений</th>
                        <th className="right">Токенов</th>
                        <th className="right">Стоимость, USD</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.employees.map((row) => (
                        <tr key={row.employee}>
                          <td>{row.employee}</td>
                          <td className="right num">{row.requests}</td>
                          <td className="right num">{row.tokens}</td>
                          <td className="right num">{money(row.cost_usd)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="caption" style={{ margin: 0 }}>
                  Это метрика использования, а не оценка работы: помощник нужен тем,
                  у кого много заявок, и частые обращения означают именно это.
                </p>
              </section>
            )}
          </>
        )}
      </QueryState>
    </>
  );
}

/** Три периода одной таблицей: сегодня, неделя, месяц. */
function Periods({ periods }: { periods: NonNullable<ReturnType<typeof useAiUsage>['data']>['periods'] }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2 className="h3">По периодам</h2>
      </div>
      <div className="table-wrap">
        <table className="tbl fit" style={{ ['--tbl-min' as string]: '680px' }}>
          <thead>
            <tr>
              <th>Период</th>
              <th className="right">Обращений</th>
              <th className="right">Стоимость, USD</th>
              <th className="right">Токенов на вход</th>
              <th className="right">На выход</th>
              <th className="right">Среднее время</th>
              <th className="right">Отказов</th>
            </tr>
          </thead>
          <tbody>
            {periods.map((row) => (
              <tr key={row.label}>
                <td>
                  {row.label}
                  {row.estimated && (
                    <div className="caption">часть сумм — оценка по нынешней цене</div>
                  )}
                </td>
                <td className="right num">{row.requests}</td>
                <td className="right num">{money(row.cost_usd)}</td>
                <td className="right num">{row.input_tokens}</td>
                <td className="right num">{row.output_tokens}</td>
                <td className="right num">
                  {row.avg_seconds === null
                    ? '—'
                    : `${row.avg_seconds.toFixed(1).replace('.', ',')} с`}
                </td>
                <td className="right num">
                  {row.error_pct === null ? '—' : `${row.error_pct}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption" style={{ margin: 0 }}>
        «Без модели» за 30 дней: {periods[2]?.avoided ?? 0}{' '}
        {plural(periods[2]?.avoided ?? 0, 'обращение', 'обращения', 'обращений')} закрыты
        принятым написанием или кэшем — за них не заплачено ничего. Подсказки из памяти
        заявок, шаблоны и проверка повторов сюда не входят: это обычные запросы к базе,
        обращениями к помощнику они никогда не были.
      </p>
    </section>
  );
}
