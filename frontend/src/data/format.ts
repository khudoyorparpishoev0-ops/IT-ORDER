/**
 * Формат чисел — ru-RU: разделитель разрядов пробел, копейки запятая
 * (1 250 000,00). Валюта указывается в заголовке столбца («СУММА, TJS»)
 * или словом «сомони»; знак валюты в число не входит.
 *
 * Суммы приходят из API строками (Decimal), в number их не переводим —
 * форматируем саму строку, чтобы не терять копейки на больших значениях.
 */

const NBSP = ' ';

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';

  const raw = typeof value === 'number' ? value.toFixed(2) : value.trim();
  const negative = raw.startsWith('-');
  const [wholeRaw = '0', fracRaw = ''] = raw.replace('-', '').split('.');

  const frac = (fracRaw + '00').slice(0, 2);
  const groups: string[] = [];
  let whole = wholeRaw;
  while (whole.length > 3) {
    groups.unshift(whole.slice(-3));
    whole = whole.slice(0, -3);
  }
  groups.unshift(whole);

  return `${negative ? '-' : ''}${groups.join(NBSP)},${frac}`;
}

/** Сумма со словом «сомони» — для текста, не для колонок таблиц. */
export function somoni(value: string | number | null | undefined): string {
  const formatted = money(value);
  return formatted === '—' ? formatted : `${formatted} сомони`;
}

/** Сортировка по имени с русской локалью. */
export function byName(a: string, b: string): number {
  return a.localeCompare(b, 'ru');
}

/** Сравнение денежных строк по величине, без перевода в number. */
export function compareMoney(a: string, b: string): number {
  const diff = Number(a) - Number(b);
  return diff === 0 ? 0 : diff > 0 ? 1 : -1;
}

/** Винительный падеж — форма после предлога «за»: «за сентябрь».
 *  У месяцев мужского рода она совпадает с именительным. */
const MONTHS_ACCUSATIVE = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
];
const MONTHS_NOMINATIVE = [
  'ЯНВАРЬ', 'ФЕВРАЛЬ', 'МАРТ', 'АПРЕЛЬ', 'МАЙ', 'ИЮНЬ',
  'ИЮЛЬ', 'АВГУСТ', 'СЕНТЯБРЬ', 'ОКТЯБРЬ', 'НОЯБРЬ', 'ДЕКАБРЬ',
];

/** Рубрика периода: «РАСХОДЫ · СЕНТЯБРЬ 2026». */
export function periodLabel(date = new Date()): string {
  return `РАСХОДЫ · ${MONTHS_NOMINATIVE[date.getMonth()]} ${date.getFullYear()}`;
}

/** Название месяца для оборота «за <месяц>»: «за сентябрь». */
export function monthAfterZa(date = new Date()): string {
  return MONTHS_ACCUSATIVE[date.getMonth()];
}

/** Дата ISO → 07.09.2026. */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

/** Метка времени UTC → «07.09.2026, 18:12» в поясе компании.
 *  Пояс берём из /health: расчёты идут в нём, и браузер бухгалтера
 *  в другом часовом поясе не должен показывать другое время. */
export function formatDateTime(iso: string, timeZone?: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZone,
    }).format(d);
  } catch {
    // Неизвестное имя пояса — показываем в местном, но не падаем.
    return d.toLocaleString('ru-RU');
  }
}

/** Склонение числительного: 1 заявка, 2 заявки, 5 заявок. */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}
