/**
 * Формат чисел — ru-RU: разделитель разрядов пробел, копейки запятая (1 250 000,00).
 * Валюта указывается в заголовке столбца («СУММА, TJS») или словом «сомони»,
 * знак валюты в числе не ставится.
 */
export function money(value: number): string {
  return value.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Сумма со словом «сомони» — для текста, а не для колонок таблиц. */
export function somoni(value: number): string {
  return `${money(value)} сомони`;
}

/** Сортировка по имени с русской локалью. */
export function byName(a: string, b: string): number {
  return a.localeCompare(b, 'ru');
}
