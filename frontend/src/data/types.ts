/** Статусы заявки. Цвет всегда дублируется словом — требование брендбука. */
export type RequestStatus = 'pending' | 'approved' | 'paid' | 'rejected' | 'draft';

export type ExpenseRequest = {
  /** Номер заявки, например РЗ-2419 */
  id: string;
  name: string;
  role: string;
  project: string;
  /** Сумма в сомони (TJS), в целых сомони на уровне данных */
  amount: number;
  status: RequestStatus;
  /** Дата в формате 00.00.0000 */
  date: string;
};

export type ExpenseLine = {
  title: string;
  qty: number;
  price: string;
  total: string;
};

export type HistoryEntry = {
  text: string;
  meta: string;
  /** true — последняя запись, левая линия зелёная */
  current?: boolean;
};

export type TeamMember = {
  name: string;
  role: string;
  limit: string;
  spent: string;
  /** Доля израсходованного, 0..100 */
  pct: number;
  count: number;
};

export type PaidRecord = {
  paidAt: string;
  id: string;
  name: string;
  project: string;
  sum: string;
  method: string;
  doc: string;
};

export type ProjectShare = {
  name: string;
  sum: string;
  pct: number;
  fill: string;
};

export type MonthFact = {
  label: string;
  value: number;
  /** true — текущий период, столбец акцентный */
  current?: boolean;
};

export type FaqItem = {
  q: string;
  a: string;
};
