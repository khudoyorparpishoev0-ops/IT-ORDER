import type { RequestStatus } from '@/api/types';

/** Оформление статусов. Точка-индикатор одинакова в обеих темах,
 *  фон и текст плашки — токены, переключаемые темой. */
export const STATUS: Record<
  RequestStatus,
  { label: string; dot: string; bg: string; fg: string }
> = {
  pending: {
    label: 'Согласование покупки',
    dot: 'var(--dot-warn)',
    bg: 'var(--st-warn-bg)',
    fg: 'var(--st-warn-fg)',
  },
  sourcing: {
    label: 'У закупа',
    dot: 'var(--dot-info)',
    bg: 'var(--st-info-bg)',
    fg: 'var(--st-info-fg)',
  },
  priced: {
    label: 'Согласование суммы',
    dot: 'var(--dot-warn)',
    bg: 'var(--st-warn-bg)',
    fg: 'var(--st-warn-fg)',
  },
  approved: {
    label: 'К оплате',
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
  fulfilled: {
    label: 'Выдано со склада',
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
  author: 'у автора',
  manager: 'у руководителя',
  procurement: 'у закупа',
  finance: 'в бухгалтерии',
  closed: '',
};
