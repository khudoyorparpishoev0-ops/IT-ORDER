import type { IconName } from '@/components/Icon';

/** Вариант шелла. Вариант A «Воздух» в разработку не идёт (решение заказчика). */
export type ShellVariant = 'dispatch' | 'light';
export type Theme = 'light' | 'dark';
export type Density = 'compact' | 'mid' | 'airy';

export const VARIANTS: Record<
  ShellVariant,
  {
    label: string;
    density: Density;
    /** Светлый сайдбар вместо Deep Forest */
    lightSidebar: boolean;
    /** Таблица заявок первым блоком на панели */
    tableFirst: boolean;
  }
> = {
  dispatch: { label: 'Диспетчер', density: 'compact', lightSidebar: false, tableFirst: true },
  light: { label: 'Светлый', density: 'mid', lightSidebar: true, tableFirst: false },
};

export type NavItem = { to: string; label: string; icon: IconName };

/** Порядок разделов зафиксирован хендоффом. */
export const NAV: NavItem[] = [
  { to: '/', label: 'Панель', icon: 'ti-layout-dashboard' },
  { to: '/requests', label: 'Заявки', icon: 'ti-file-text' },
  { to: '/approvals', label: 'Согласование', icon: 'ti-circle-check' },
  { to: '/reports', label: 'Отчёты', icon: 'ti-chart-bar' },
  { to: '/team', label: 'Команда', icon: 'ti-users' },
  { to: '/finance', label: 'Финансы', icon: 'ti-wallet' },
  { to: '/settings', label: 'Параметры', icon: 'ti-settings' },
  { to: '/help', label: 'Справка', icon: 'ti-help-circle' },
];

export const APP_VERSION = 'v1.0';
