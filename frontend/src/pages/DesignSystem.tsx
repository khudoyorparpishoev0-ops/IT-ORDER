import { useState } from 'react';
import type { ReactNode } from 'react';
import { Bar } from '@/components/Bar';
import { Icon } from '@/components/Icon';
import { Kpi } from '@/components/Kpi';
import { IthonaLogo, IthonaLogoStacked, IthonaMark } from '@/components/Logo';
import { Modal } from '@/components/Modal';
import { PageHeader } from '@/components/PageHeader';
import { StatusBadge } from '@/components/StatusBadge';
import { Waiting } from '@/components/Waiting';
import { Workflow } from '@/components/Workflow';
import { money, somoni } from '@/data/format';
import { STATUS_ORDER } from '@/data/status';
import type { RequestDetail } from '@/api/types';

/**
 * Страница-эталон UI-кита. Служит визуальным regression-тестом: если
 * правка класса или компонента ломает правило хендоффа, это видно здесь.
 * Все образцы собраны из тех же классов и компонентов, что и экраны.
 */

/** Основные токены поверхности и текста: имя, назначение. */
const SURFACE = [
  { token: '--paper', use: 'карточки, таблицы, поля' },
  { token: '--mist', use: 'фон страницы, дорожка графика' },
  { token: '--line', use: 'границы 1 px' },
  { token: '--zebra', use: 'шапка таблицы, hover строки' },
  { token: '--ink', use: 'основной текст' },
  { token: '--slate', use: 'вторичный текст, рубрики' },
  { token: '--grey', use: 'placeholder, «не оценена»' },
  { token: '--green', use: 'primary, активный пункт' },
  { token: '--green-d', use: 'hover primary, ссылки' },
  { token: '--forest', use: 'сайдбар, шапка реестра' },
];

/** Статусные цвета одинаковы в обеих темах. */
const STATUS_COLORS = [
  { token: '--yellow', use: 'ждёт решения, задержка' },
  { token: '--blue', use: 'в работе службы' },
  { token: '--red', use: 'отклонение, ошибка' },
];

const CHART = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6'];

/** Заявка-образец для workflow и блока «Сейчас ждёт». Данные из ТЗ. */
const SAMPLE: RequestDetail = {
  id: 48,
  number: 'РЗ-0048',
  employee_id: 7,
  employee_name: 'Иван Петров',
  employee_position: 'Сотрудник отдела АХО',
  project_id: 1,
  project_name: 'Регар',
  title: 'Закуп кабеля UTP Cat6',
  lines_count: 2,
  amount: '0.00',
  priced: false,
  status: 'sourcing',
  awaiting_stage: 'procurement',
  awaiting_label: 'У отдела закупа: склад и цены',
  awaiting_days: 2,
  date: '01.09.2026',
  employee_email: 'i.petrov@it-hona.tj',
  employee_phone: null,
  employee_limit: '20000.00',
  employee_spent: '8400.00',
  lines: [
    { id: 1, title: 'Кабель UTP Cat6, бухта 305 м', quantity: 2, unit: 'шт.', price: null, total: null, from_stock: false },
    { id: 2, title: 'Коннектор RJ-45', quantity: 100, unit: 'шт.', price: null, total: null, from_stock: false },
  ],
  events: [
    { kind: 'created', text: 'Черновик создан', actor: 'Иван Петров', meta: 'ИВАН ПЕТРОВ · 01.09.2026, 09:40', created_at: '2026-09-01T04:40:00Z' },
    { kind: 'submitted', text: 'Отправлена на согласование', actor: 'Иван Петров', meta: 'ИВАН ПЕТРОВ · 01.09.2026, 09:52', created_at: '2026-09-01T04:52:00Z' },
    { kind: 'sourcing', text: 'Покупка согласована, передана в закуп', actor: 'Мария Сидорова', meta: 'МАРИЯ СИДОРОВА · 04.09.2026, 18:12', created_at: '2026-09-04T13:12:00Z' },
  ],
  payment: null,
  decision_comment: null,
  decided_by: 'Мария Сидорова',
  sourced_by: null,
  sourcing_comment: null,
  awaiting_people: ['Отдел закупа'],
};

/** Та же заявка, но задержавшаяся на согласовании суммы. */
const DELAYED: RequestDetail = {
  ...SAMPLE,
  status: 'priced',
  amount: '3355.00',
  priced: true,
  awaiting_stage: 'manager',
  awaiting_label: 'У руководителя: согласование суммы',
  awaiting_days: 5,
  awaiting_people: ['Мария Сидорова'],
};

/** Отклонена на первом согласовании. */
const REJECTED: RequestDetail = {
  ...SAMPLE,
  status: 'rejected',
  awaiting_stage: 'closed',
  awaiting_label: 'Закрыта',
  awaiting_days: null,
  awaiting_people: [],
  decision_comment: 'Превышение бюджета объекта',
  events: [
    ...SAMPLE.events.slice(0, 2),
    { kind: 'rejected', text: 'Отклонена — превышение бюджета объекта', actor: 'Мария Сидорова', meta: 'МАРИЯ СИДОРОВА · 05.09.2026, 10:02', created_at: '2026-09-05T05:02:00Z' },
  ],
};

const TABLE_ROWS = [
  { number: 'РЗ-0048', title: 'Закуп кабеля UTP Cat6', project: 'Регар', status: 'sourcing', date: '08.09.2026', amount: null },
  { number: 'РЗ-0047', title: 'Расходные материалы для серверной', project: 'Душанбе', status: 'priced', date: '05.09.2026', amount: '12400.00' },
  { number: 'РЗ-0046', title: 'Замена ИБП в узле связи', project: 'Худжанд', status: 'paid', date: '02.09.2026', amount: '28900.00' },
] as const;

const SHARES = [
  { name: 'Регар', amount: '86400.00', pct: 41 },
  { name: 'Душанбе', amount: '52100.00', pct: 25 },
  { name: 'Худжанд', amount: '38900.00', pct: 18 },
  { name: 'Бохтар', amount: '21300.00', pct: 10 },
  { name: 'Куляб', amount: '9800.00', pct: 5 },
];

const MONTHS = [
  { label: 'апр', value: 68 },
  { label: 'май', value: 74 },
  { label: 'июн', value: 59 },
  { label: 'июл', value: 81 },
  { label: 'авг', value: 92 },
  { label: 'сен', value: 103 },
];

/** Из раздела хендоффа «Не переносить в реализацию». */
const FORBIDDEN = [
  'Фотографии кабеля и объектов, блок «Файлы», категории, комментарии к заявке',
  'Нижнее мобильное меню (таб-бар)',
  'Pie и donut диаграммы',
  'Произвольные KPI и действия, которых нет в API',
  'Хардкод цветов: только var(--token), никогда #fff / #111 напрямую',
  'Emoji, 3D-иконки, градиентные фоны, parallax, scroll-анимации',
];

export function DesignSystem() {
  const [modalOpen, setModalOpen] = useState(false);
  const [toggleOn, setToggleOn] = useState(true);
  const [checked, setChecked] = useState(false);
  const maxMonth = Math.max(1, ...MONTHS.map((m) => m.value));

  return (
    <>
      <PageHeader
        title="Дизайн-система"
        lead="Токены, классы и компоненты HONA ORDER по хендоффу UI-кита · сентябрь 2026"
      />

      <Section title="Логотип" note="Только официальные композиции из components/Logo.tsx. Имя шрифтом не набирать.">
        <div style={{ display: 'flex', alignItems: 'center', gap: 32, flexWrap: 'wrap' }}>
          <IthonaLogoStacked height={72} style={{ color: 'var(--logo)' }} />
          <IthonaLogo height={34} style={{ color: 'var(--logo)' }} />
          <IthonaMark size={40} style={{ color: 'var(--logo)' }} />
          <div
            style={{
              background: 'var(--forest)',
              padding: '16px 24px',
              borderRadius: 'var(--r-card)',
              display: 'flex',
              alignItems: 'center',
              gap: 24,
            }}
          >
            <IthonaLogoStacked height={56} style={{ color: 'var(--forest-ink)' }} />
            <IthonaLogo height={28} style={{ color: 'var(--forest-ink)' }} />
            <IthonaMark size={28} style={{ color: 'var(--forest-ink)' }} />
          </div>
        </div>
      </Section>

      <Section
        title="Палитра"
        note="Light и Dark проектируются отдельно: переключите тему в шапке, образцы возьмут значения из токенов. Пропорция 70% paper/mist · 20% ink/forest · 10% green."
      >
        <div className="label">Поверхности и текст</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 12 }}>
          {SURFACE.map((c) => (
            <Swatch key={c.token} token={c.token} use={c.use} />
          ))}
        </div>
        <div className="label">Статусные цвета</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 12 }}>
          {STATUS_COLORS.map((c) => (
            <Swatch key={c.token} token={c.token} use={c.use} />
          ))}
        </div>
        <div className="label-mono">Зелёная шкала графиков</div>
        <div>
          <div style={{ display: 'flex' }}>
            {CHART.map((t) => (
              <div key={t} style={{ flex: 1, height: 48, background: `var(${t})` }} />
            ))}
          </div>
          <div className="meta" style={{ marginTop: 8 }}>
            {CHART.join(' · ')} — от большего значения к меньшему
          </div>
        </div>
      </Section>

      <Section title="Статусы" note="Статус всегда цвет и слово: точка 6 px плюс подпись. Рамка — в таблицах, без рамки — в карточках на телефоне.">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {STATUS_ORDER.map((s) => (
            <StatusBadge key={s} status={s} />
          ))}
        </div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {STATUS_ORDER.map((s) => (
            <StatusBadge key={s} status={s} inline />
          ))}
        </div>
      </Section>

      <Section title="Типографика" note="Manrope для текста, JetBrains Mono для всего, что сравнивают глазами: номера, суммы, даты, KPI.">
        <div style={{ display: 'grid', gap: 12 }}>
          <Type spec="H1 · 30/700/1.16">
            <div className="h1">Все заявки</div>
          </Type>
          <Type spec="H2 · 24/700">
            <div className="h2">Позиции заявки</div>
          </Type>
          <Type spec="H3 · 19/700">
            <div className="h3">Согласование суммы</div>
          </Type>
          <Type spec="Body · 16/400/1.56">
            <div>Заявка передана в отдел закупа. После оценки сумма уходит на согласование руководителю.</div>
          </Type>
          <Type spec="Small · 14/400">
            <div className="small">Объект: Регар · Автор: Сотрудник отдела АХО</div>
          </Type>
          <Type spec="Caption · 13/400">
            <div className="caption">Обновлено 08.09.2026 в 14:20</div>
          </Type>
          <Type spec="Rubric · 11/600">
            <div className="label">Сейчас ждёт</div>
          </Type>
          <Type spec="Label mono · 11/600">
            <div className="label-mono">Доли по объектам, TJS</div>
          </Type>
          <Type spec="Num · mono 14/600">
            <span className="num">РЗ-0048 · 3 355,00 · 08.09.2026</span>
          </Type>
          <Type spec="Meta · mono 13">
            <span className="meta">РЗ-0048 · 08.09.2026 · Регар</span>
          </Type>
          <Type spec="KPI · mono 30/600">
            <div className="kpi-value">42 180,00</div>
          </Type>
          <Type spec="Unpriced · mono 14 grey">
            <span className="unpriced">не оценена</span>
          </Type>
        </div>
      </Section>

      <Section title="Кнопки" note="Высота 44 px, на телефоне 48. На экране одно доминирующее primary-действие.">
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" className="btn btn-primary">
            <Icon name="ti-plus" size={18} />
            Создать заявку
          </button>
          <button type="button" className="btn btn-secondary">
            Сохранить черновиком
          </button>
          <button type="button" className="btn btn-ghost">
            Отмена
          </button>
          <button type="button" className="btn btn-danger">
            Отклонить
          </button>
          <button type="button" className="btn btn-icon" aria-label="Фильтры">
            <Icon name="ti-filter" size={18} />
          </button>
          <button type="button" className="btn btn-primary" disabled>
            Недоступно
          </button>
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="label-mono">btn-sm · 36</span>
          <button type="button" className="btn btn-primary btn-sm">
            Да
          </button>
          <button type="button" className="btn btn-secondary btn-sm">
            Отмена
          </button>
          <button type="button" className="btn btn-icon btn-sm" aria-label="Закрыть">
            <Icon name="ti-x" size={18} />
          </button>
        </div>
        <div style={{ maxWidth: 320 }}>
          <button type="button" className="btn btn-dashed">
            <Icon name="ti-plus" size={18} />
            Добавить позицию
          </button>
        </div>
      </Section>

      <Section title="Поля" note="Высота 44 px, радиус 2 px, фокус — рамка 2 px green. Подпись над полем — рубрика.">
        <div className="grid-auto">
          <div>
            <label className="label field-label" htmlFor="ds-normal">
              Обычное
            </label>
            <input id="ds-normal" className="field" placeholder="Выберите объект" />
          </div>
          <div>
            <label className="label field-label" htmlFor="ds-filled">
              Заполненное
            </label>
            <input id="ds-filled" className="field" defaultValue="Кабель UTP Cat6" />
          </div>
          <div>
            <label className="label field-label" htmlFor="ds-error">
              Ошибка
            </label>
            <input id="ds-error" className="field field-error" defaultValue="—" aria-invalid />
            <div className="field-error-text">Укажите объект: поле обязательное</div>
          </div>
          <div>
            <label className="label field-label" htmlFor="ds-disabled">
              Недоступное
            </label>
            <input id="ds-disabled" className="field" placeholder="Недоступно для роли" disabled />
          </div>
          <div>
            <label className="label field-label" htmlFor="ds-select">
              Выбор
            </label>
            <select id="ds-select" className="field" defaultValue="regar">
              <option value="regar">Регар</option>
              <option value="dushanbe">Душанбе</option>
              <option value="khujand">Худжанд</option>
            </select>
          </div>
          <div>
            <label className="label field-label" htmlFor="ds-textarea">
              Многострочное
            </label>
            <textarea id="ds-textarea" className="field" placeholder="Причина отклонения" />
          </div>
        </div>

        <div>
          <div className="label" style={{ marginBottom: 8 }}>
            Переключатель и чекбокс
          </div>
          <div className="toggle-row">
            <label htmlFor="ds-toggle" style={{ cursor: 'pointer' }}>
              Новая заявка на согласование
            </label>
            <button
              id="ds-toggle"
              type="button"
              role="switch"
              aria-checked={toggleOn}
              className="toggle"
              onClick={() => setToggleOn((v) => !v)}
            />
          </div>
          <div className="check-row" onClick={() => setChecked((v) => !v)}>
            <button
              type="button"
              role="checkbox"
              aria-checked={checked}
              aria-label="Работает в компании"
              className="check"
              onClick={(e) => {
                e.stopPropagation();
                setChecked((v) => !v);
              }}
            >
              <Icon name="ti-check" size={14} style={{ opacity: checked ? 1 : 0 }} />
            </button>
            <span className="small">Работает в компании</span>
          </div>
        </div>

        <div>
          <div className="label" style={{ marginBottom: 8 }}>
            Фильтры · 36 px
          </div>
          <div className="filter-row">
            <button type="button" className="filter" aria-pressed="true">
              Все статусы
            </button>
            <button type="button" className="filter">
              Объект: все
            </button>
            <button type="button" className="filter mono">
              01.09 — 08.09
            </button>
          </div>
        </div>
      </Section>

      <Section title="KPI" note="Рубрика → значение моно 30 → контекст. Цветных фонов нет; статусное значение помечается точкой.">
        <div className="kpi-grid">
          <Kpi label="Всего заявок" value="128" note="за текущий период" />
          <Kpi label="Ждут решения" value="14" dot="var(--yellow)" note="на согласовании" />
          <Kpi label="К оплате" value={money('42180.00')} note="сомони, 9 заявок" />
          <Kpi label="Средний цикл" value="6,4" note="дня от заявки до оплаты" />
        </div>
      </Section>

      <Section title="Таблица" note="Строка 44 px, шапка моно 11 uppercase на zebra, суммы вправо, объект — slate.">
        <div className="panel">
          <div className="table-wrap">
            <table className="tbl" style={{ ['--tbl-min' as string]: '720px' }}>
              <thead>
                <tr>
                  <th>Номер</th>
                  <th>Наименование</th>
                  <th>Объект</th>
                  <th>Статус</th>
                  <th>Дата</th>
                  <th className="right">Сумма, TJS</th>
                </tr>
              </thead>
              <tbody>
                {TABLE_ROWS.map((r) => (
                  <tr key={r.number} className="clickable">
                    <td className="num">{r.number}</td>
                    <td>{r.title}</td>
                    <td className="slate">{r.project}</td>
                    <td>
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="mono" style={{ color: 'var(--slate)' }}>
                      {r.date}
                    </td>
                    <td className="right">
                      {r.amount ? <span className="num">{money(r.amount)}</span> : <span className="unpriced">не оценена</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="label" style={{ marginBottom: 8 }}>
            Тёмная шапка · только реестр выплат
          </div>
          <div className="panel">
            <div className="table-wrap">
              <table className="tbl tbl-forest tall" style={{ ['--tbl-min' as string]: '560px' }}>
                <thead>
                  <tr>
                    <th>Оплачена</th>
                    <th>Сотрудник · объект</th>
                    <th className="right">Сумма, TJS</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div className="num">08.09.2026</div>
                      <div className="meta">РЗ-0046</div>
                    </td>
                    <td>
                      <div>Иван Петров</div>
                      <div className="caption">Худжанд</div>
                    </td>
                    <td className="right num-lg">{money('28900.00')}</td>
                  </tr>
                  <tr>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <div className="num">03.09.2026</div>
                      <div className="meta">РЗ-0044</div>
                    </td>
                    <td>
                      <div>Мария Сидорова</div>
                      <div className="caption">Регар</div>
                    </td>
                    <td className="right num-lg">{money('4100.00')}</td>
                  </tr>
                  <tr className="total-row">
                    <td colSpan={2}>
                      <span className="h3">Итого выплачено за сентябрь</span>
                    </td>
                    <td className="right">
                      <span className="h3 mono">{money('33000.00')}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </Section>

      <Section title="Workflow" note="Пройденные — зелёная полоса и дата, текущий — статусный цвет и «Сейчас · N дней», будущие — серые. Отклонённая — красным на том шаге, где её остановили.">
        <Workflow detail={SAMPLE} />
        <div className="label">Отклонена</div>
        <Workflow detail={REJECTED} />
        <div className="label">Вертикальный · телефон</div>
        <div style={{ maxWidth: 320 }}>
          <Workflow detail={SAMPLE} vertical />
        </div>
      </Section>

      <Section title="Сейчас ждёт" note="После трёх дней рубрика меняется на «задержка», рамка становится жёлтой. Это не ошибка — красным не окрашивается.">
        <div className="grid-auto">
          <Waiting request={SAMPLE} />
          <Waiting request={DELAYED} />
        </div>
      </Section>

      <Section title="Графики" note="Только горизонтальные и вертикальные полосы. Один график — один вывод, он же заголовок. Ось от нуля обязательна.">
        <div className="grid-auto">
          <div style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
            <div className="h3">Регар — крупнейший объект по расходам за сентябрь</div>
            <div style={{ display: 'grid', gap: 12 }}>
              {SHARES.map((p, i) => (
                <div key={p.name} className="hbar-row">
                  <div className="hbar-line">
                    <span>{p.name}</span>
                    <span className="num">
                      {money(p.amount)} · {p.pct}%
                    </span>
                  </div>
                  <div className="hbar">
                    <span style={{ width: `${p.pct}%`, background: `var(${CHART[Math.min(i, CHART.length - 1)]})` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
            <div className="label-mono">Факт по месяцам, TJS тыс.</div>
            <div>
              <div className="vbars">
                {MONTHS.map((m, i) => (
                  <div key={m.label} className="vbar">
                    <span className="num">{m.value}</span>
                    <span
                      style={{
                        height: `${(m.value / maxMonth) * 82}%`,
                        background: i === MONTHS.length - 1 ? 'var(--chart-3)' : 'var(--chart-5)',
                      }}
                    />
                  </div>
                ))}
              </div>
              <div className="vbar-labels">
                {MONTHS.map((m) => (
                  <span key={m.label} className="label-mono">
                    {m.label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
        <div>
          <div className="label" style={{ marginBottom: 8 }}>
            Полоса лимита · 10 px
          </div>
          <div style={{ display: 'grid', gap: 8, maxWidth: 420 }}>
            <Bar pct={42} />
            <Bar pct={91} />
            <Bar pct={100} />
          </div>
        </div>
      </Section>

      <Section title="Модалка" note="Панель 440 px (wide — 640), шапка 56 px, единственное место с тенью второго уровня. Закрытие по Escape и клику мимо.">
        <div>
          <button type="button" className="btn btn-secondary" onClick={() => setModalOpen(true)}>
            Открыть окно
          </button>
        </div>
        {modalOpen && (
          <Modal
            title="Согласовать сумму"
            onClose={() => setModalOpen(false)}
            footer={
              <>
                <button type="button" className="btn btn-secondary" onClick={() => setModalOpen(false)}>
                  Отмена
                </button>
                <button type="button" className="btn btn-primary" onClick={() => setModalOpen(false)}>
                  Согласовать
                </button>
              </>
            }
          >
            <div className="meta">РЗ-0048 · Регар</div>
            <div className="h3">{somoni('3355.00')}</div>
            <div>
              <label className="label field-label" htmlFor="ds-modal-comment">
                Комментарий
              </label>
              <textarea id="ds-modal-comment" className="field" placeholder="Необязательно" />
            </div>
          </Modal>
        )}
      </Section>

      <Section title="Формат денег" note="Разряды — пробел, копейки — запятая, всегда два знака. Знак валюты в число не ставится.">
        <div className="grid-auto">
          <div style={{ display: 'grid', gap: 8 }}>
            <div className="label" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <span className="dot" style={{ ['--dot' as string]: 'var(--green)' }} aria-hidden="true" />
              Верно
            </div>
            <div className="metric-sm">{money('3355.00')}</div>
            <div className="small">
              В интерфейсе: <span className="num">{somoni('3355.00')}</span>
            </div>
            <div className="small">
              В шапке таблицы: <span className="num">Сумма, TJS</span>
            </div>
            <div className="small">
              Большие значения: <span className="num">{money('1250000.50')}</span>
            </div>
            <div className="small">
              До оценки: <span className="unpriced">не оценена</span>
            </div>
            <div className="small">
              Выдано со склада: <span className="num">{money('0')}</span>
            </div>
          </div>
          <div style={{ display: 'grid', gap: 8 }}>
            <div className="label" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <span className="dot" style={{ ['--dot' as string]: 'var(--red)' }} aria-hidden="true" />
              Неверно
            </div>
            <div className="metric-sm muted" style={{ textDecoration: 'line-through' }}>
              3355
            </div>
            <div className="metric-sm muted" style={{ textDecoration: 'line-through' }}>
              3,355.00
            </div>
            <div className="metric-sm muted" style={{ textDecoration: 'line-through' }}>
              0,00
            </div>
            <div className="caption">
              Ноль вместо «не оценена» недопустим: ноль означает, что закуп не требуется.
            </div>
          </div>
        </div>
      </Section>

      <Section title="Запреты" note="Из раздела хендоффа «Не переносить в реализацию».">
        <ul style={{ margin: 0, paddingLeft: 20, display: 'grid', gap: 8 }}>
          {FORBIDDEN.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>
    </>
  );
}

/** Раздел эталона: карточка с заголовком, коротким пояснением и образцами. */
function Section({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return (
    <section className="card" style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
      <div>
        <h2 className="h3">{title}</h2>
        <p className="caption" style={{ margin: '4px 0 0' }}>
          {note}
        </p>
      </div>
      {children}
    </section>
  );
}

/** Образец цвета: заливка токеном, имя и назначение. */
function Swatch({ token, use }: { token: string; use: string }) {
  return (
    <div>
      <div
        style={{
          height: 48,
          background: `var(${token})`,
          border: '1px solid var(--line)',
          borderRadius: 'var(--r-field)',
        }}
      />
      <div className="meta" style={{ marginTop: 8, color: 'var(--ink)' }}>
        {token}
      </div>
      <div className="caption">{use}</div>
    </div>
  );
}

/** Строка типографики: спецификация слева, образец справа. */
function Type({ spec, children }: { spec: string; children: ReactNode }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(120px, 180px) 1fr',
        gap: 16,
        alignItems: 'baseline',
        paddingBottom: 12,
        borderBottom: '1px solid var(--line)',
      }}
    >
      <span className="label-mono">{spec}</span>
      <div style={{ minWidth: 0 }}>{children}</div>
    </div>
  );
}
