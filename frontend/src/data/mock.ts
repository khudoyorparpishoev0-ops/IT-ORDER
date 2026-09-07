/**
 * Данные-примеры из дизайн-прототипа (docs/prototype_expense_platform.dc.html).
 * ВНИМАНИЕ: значения условные. При подключении бэкенда этот модуль заменяется
 * запросами к API, а файл удаляется. Реальные реестр выплат, лимиты и коды
 * платёжных документов — открытый вопрос к заказчику (docs/DESIGN_HANDOFF.md).
 */
import type {
  ExpenseLine,
  ExpenseRequest,
  FaqItem,
  HistoryEntry,
  MonthFact,
  PaidRecord,
  ProjectShare,
  TeamMember,
} from './types';

export const PERIOD_LABEL = 'РАСХОДЫ · СЕНТЯБРЬ 2026';
export const DATA_AS_OF = 'Источник: CORE · данные на 07.09.2026';

export const REQUESTS: ExpenseRequest[] = [
  { id: 'РЗ-2419', name: 'Иван Петров', role: 'Мастер-отделочник', project: 'Вилла Колхозная', amount: 1850, status: 'pending', date: '04.09.2026' },
  { id: 'РЗ-2420', name: 'Мария Сидорова', role: 'Дизайнер', project: 'Офис на 7 этаже', amount: 950, status: 'pending', date: '05.09.2026' },
  { id: 'РЗ-2417', name: 'Сергей Никитин', role: 'Прораб', project: 'Рекова 132', amount: 2400, status: 'approved', date: '02.09.2026' },
  { id: 'РЗ-2411', name: 'Екатерина Волкова', role: 'Менеджер проекта', project: 'Речь', amount: 3100, status: 'paid', date: '28.08.2026' },
  { id: 'РЗ-2421', name: 'Алексей Морозов', role: 'Электрик', project: 'Рекова 132', amount: 1240, status: 'pending', date: '05.09.2026' },
  { id: 'РЗ-2415', name: 'Ольга Кузнецова', role: 'Снабженец', project: 'Вилла Колхозная', amount: 5600, status: 'rejected', date: '01.09.2026' },
  { id: 'РЗ-2422', name: 'Дмитрий Соколов', role: 'Инженер', project: 'Офис на 7 этаже', amount: 780, status: 'pending', date: '06.09.2026' },
  { id: 'РЗ-2413', name: 'Анна Лебедева', role: 'Архитектор', project: 'Речь', amount: 2050, status: 'approved', date: '29.08.2026' },
];

/** Всего заявок за период — включая те, что не попали в выборку выше. */
export const TOTAL_REQUESTS = 24;

export const DASHBOARD_STATS = [
  { label: 'ВСЕГО ЗАЯВОК', value: '24', note: 'за сентябрь, 12 сотрудников' },
  { label: 'ОДОБРЕНО, TJS', value: '18 500,00', note: '12 заявок, ждут выплаты' },
  { label: 'НА УТВЕРЖДЕНИИ, TJS', value: '3 200,00', note: '4 заявки ждут решения' },
  { label: 'БЮДЖЕТ МЕСЯЦА, TJS', value: '156 000,00', note: 'использовано 62%' },
];

export const EXPENSE_LINES: ExpenseLine[] = [
  { title: 'Проездной туда и обратно', qty: 1, price: '150,00', total: '150,00' },
  { title: 'Обед на одного', qty: 1, price: '30,00', total: '30,00' },
  { title: 'Материалы для работы', qty: 5, price: '120,00', total: '600,00' },
  { title: 'Такси до объекта', qty: 2, price: '535,00', total: '1 070,00' },
];

export const REQUEST_LIMITS = [
  { k: 'ЛИМИТ СОТРУДНИКА', v: '5 000,00 сомони' },
  { k: 'ИЗРАСХОДОВАНО', v: '3 150,00 сомони' },
  { k: 'ЧЕКИ', v: '4 вложения' },
];

export const HISTORY: HistoryEntry[] = [
  { text: 'Заявка отправлена на утверждение', meta: 'ИВАН ПЕТРОВ · 04.09.2026, 18:12' },
  { text: 'Комментарий: «Чеки приложены»', meta: 'ИВАН ПЕТРОВ · 04.09.2026, 18:14' },
  { text: 'Заявка просмотрена супервайзером', meta: 'ОЛЬГА КУЗНЕЦОВА · 05.09.2026, 09:40' },
  { text: 'Предыдущая заявка РЗ-2402 оплачена', meta: 'ФИНАНСЫ · 30.08.2026, 12:05', current: true },
];

export const APPROVAL_TABS: { key: string; label: string }[] = [
  { key: 'pending', label: 'На утверждении · 4' },
  { key: 'approved', label: 'Утверждены · 12' },
  { key: 'rejected', label: 'Отклонены · 2' },
];

export const BY_PROJECT: ProjectShare[] = [
  { name: 'Вилла Колхозная', sum: '42 300,00', pct: 44, fill: 'var(--chart-3)' },
  { name: 'Рекова 132', sum: '31 800,00', pct: 33, fill: 'var(--chart-4)' },
  { name: 'Офис на 7 этаже', sum: '15 200,00', pct: 16, fill: 'var(--chart-5)' },
  { name: 'Речь', sum: '7 420,00', pct: 7, fill: 'var(--chart-6)' },
];

/** Ось от нуля обязательна: высота столбца считается от максимума шкалы. */
export const MONTHS: MonthFact[] = [
  { label: 'АПР', value: 58 },
  { label: 'МАЙ', value: 66 },
  { label: 'ИЮН', value: 74 },
  { label: 'ИЮЛ', value: 92 },
  { label: 'АВГ', value: 71 },
  { label: 'СЕН', value: 97, current: true },
];

export const PAID_HISTORY: PaidRecord[] = [
  { paidAt: '05.09.2026', id: 'РЗ-2411', name: 'Екатерина Волкова', project: 'Речь', sum: '3 100,00', method: 'На карту', doc: 'ПП-0412' },
  { paidAt: '03.09.2026', id: 'РЗ-2408', name: 'Сергей Никитин', project: 'Рекова 132', sum: '1 480,00', method: 'На карту', doc: 'ПП-0409' },
  { paidAt: '02.09.2026', id: 'РЗ-2405', name: 'Дмитрий Соколов', project: 'Офис на 7 этаже', sum: '640,00', method: 'Наличными', doc: 'РКО-118' },
  { paidAt: '30.08.2026', id: 'РЗ-2402', name: 'Иван Петров', project: 'Вилла Колхозная', sum: '2 260,00', method: 'На карту', doc: 'ПП-0398' },
  { paidAt: '28.08.2026', id: 'РЗ-2396', name: 'Мария Сидорова', project: 'Офис на 7 этаже', sum: '870,00', method: 'На карту', doc: 'ПП-0391' },
  { paidAt: '27.08.2026', id: 'РЗ-2390', name: 'Анна Лебедева', project: 'Речь', sum: '1 930,00', method: 'Наличными', doc: 'РКО-112' },
];

export const PAID_TOTAL = '10 280,00';
export const PAID_SUMMARY =
  '6 выплат с 27.08 по 05.09.2026 · средний срок от одобрения до выплаты 2 дня';

export const TEAM: TeamMember[] = [
  { name: 'Иван Петров', role: 'Мастер-отделочник', limit: '5 000,00', spent: '3 150,00', pct: 63, count: 6 },
  { name: 'Мария Сидорова', role: 'Дизайнер', limit: '4 000,00', spent: '1 900,00', pct: 48, count: 4 },
  { name: 'Сергей Никитин', role: 'Прораб', limit: '8 000,00', spent: '7 600,00', pct: 95, count: 9 },
  { name: 'Екатерина Волкова', role: 'Менеджер проекта', limit: '6 000,00', spent: '3 100,00', pct: 52, count: 5 },
  { name: 'Ольга Кузнецова', role: 'Снабженец', limit: '10 000,00', spent: '9 800,00', pct: 98, count: 12 },
];

export const PROJECTS = ['Вилла Колхозная', 'Рекова 132', 'Офис на 7 этаже', 'Речь'];

export const PROFILE = [
  { label: 'Имя и фамилия', value: 'Артём Ковалёв' },
  { label: 'Рабочая почта', value: 'a.kovalev@it-hona.tj' },
  { label: 'Порог автоодобрения, TJS', value: '500,00' },
];

export const NOTIFICATIONS = [
  { label: 'Новые заявки на утверждение', on: true },
  { label: 'Напоминание о заявках старше 3 дней', on: true },
  { label: 'Еженедельный отчёт по бюджету', on: false },
];

export const FAQ: FaqItem[] = [
  {
    q: 'Как одобрить заявку сотрудника?',
    a: 'Раздел «Согласование» → заявка → отметьте решение и нажмите «Одобрить». Заявки до порога автоодобрения закрываются без вашего участия.',
  },
  {
    q: 'Что означают статусы заявок?',
    a: 'На утверждении — требует решения. Одобрена — утверждена, ждёт выплаты. Оплачена — возмещение перечислено. Отклонена — отказано с комментарием. Черновик — сотрудник не отправил заявку.',
  },
  {
    q: 'Как изменить лимит сотрудника?',
    a: 'Раздел «Команда» → сотрудник → поле «Лимит», в сомони. Изменения действуют с начала следующего месяца.',
  },
  {
    q: 'Как выгрузить реестр в Excel?',
    a: 'В разделе «Отчёты» нажмите «Excel». Артикулы и коды выгружаются моно-гарнитурой, числа — с разделителем разрядов и запятой в копейках.',
  },
  {
    q: 'Кто видит комментарии к заявке?',
    a: 'Сотрудник-автор и все согласующие в цепочке утверждения. Комментарий к отклонению обязателен.',
  },
];

export const BUDGET = {
  monthLimit: '156 000,00',
  usedPct: 62,
  usedNote: 'Использовано 96 720,00 · осталось 59 280,00',
  weekPayout: '12 480,00',
  weekNote: '7 одобренных заявок, срок — до 12.09.2026',
};
