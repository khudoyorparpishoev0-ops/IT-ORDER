import type { RequestStatus } from '@/api/types';

/** Оформление статусов. Точка-индикатор одинакова в обеих темах,
 *  фон и текст плашки — токены, переключаемые темой. */
export const STATUS: Record<
  RequestStatus,
  { label: string; dot: string; bg: string; fg: string }
> = {
  pending: {
    label: 'На утверждении',
    dot: 'var(--dot-warn)',
    bg: 'var(--st-warn-bg)',
    fg: 'var(--st-warn-fg)',
  },
  approved: {
    label: 'Одобрена',
    dot: 'var(--dot-info)',
    bg: 'var(--st-info-bg)',
    fg: 'var(--st-info-fg)',
  },
  paid: {
    label: 'Оплачена',
    dot: 'var(--dot-ok)',
    bg: 'var(--st-ok-bg)',
    fg: 'var(--st-ok-fg)',
  },
  rejected: {
    label: 'Отклонена',
    dot: 'var(--dot-err)',
    bg: 'var(--st-err-bg)',
    fg: 'var(--st-err-fg)',
  },
  draft: {
    label: 'Черновик',
    dot: 'var(--dot-off)',
    bg: 'var(--st-off-bg)',
    fg: 'var(--st-off-fg)',
  },
};

/** Порядок фильтров в разделе «Заявки». */
export const STATUS_ORDER: RequestStatus[] = [
  'pending',
  'approved',
  'paid',
  'rejected',
  'draft',
];

/** Способ выплаты словом. */
export const PAYMENT_METHOD: Record<'card' | 'cash', string> = {
  card: 'На карту',
  cash: 'Наличными',
};
