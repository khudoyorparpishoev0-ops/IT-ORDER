import type { RequestStatus } from '@/api/types';

/**
 * Оформление статусов по UI-киту: у каждого один цвет — он идёт в точку
 * 6 px и в рамку плашки. Семантика: серый — черновик, жёлтый — ждёт
 * решения человека, синий — в работе службы, зелёный — завершена,
 * красный — отклонена.
 */
export const STATUS: Record<RequestStatus, { label: string; color: string }> = {
  draft: { label: 'Черновик', color: 'var(--grey)' },
  pending: { label: 'Согласование покупки', color: 'var(--yellow)' },
  sourcing: { label: 'У закупа', color: 'var(--blue)' },
  priced: { label: 'Согласование суммы', color: 'var(--yellow)' },
  approved: { label: 'К оплате', color: 'var(--blue)' },
  paid: { label: 'Оплачена', color: 'var(--green)' },
  fulfilled: { label: 'Выдано со склада', color: 'var(--green)' },
  rejected: { label: 'Отклонена', color: 'var(--red)' },
};

/** Порядок статусов в фильтрах. */
export const STATUS_ORDER: RequestStatus[] = [
  'pending',
  'sourcing',
  'priced',
  'approved',
  'paid',
  'fulfilled',
  'rejected',
  'draft',
];

/** Способ выплаты словом. */
export const PAYMENT_METHOD: Record<'card' | 'cash', string> = {
  card: 'На карту',
  cash: 'Наличными',
};

/** Кто держит заявку — коротко, для строки списка. */
export const HOLDER: Record<string, string> = {
  author: 'Автор',
  manager: 'Руководитель',
  procurement: 'Отдел закупа',
  finance: 'Бухгалтерия',
  closed: '',
};

/** Порог задержки на этапе, дней: с него блок «Сейчас ждёт» подсвечивается. */
export const DELAY_DAYS = 3;
