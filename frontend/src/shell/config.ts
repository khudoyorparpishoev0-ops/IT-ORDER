import type { IconName } from '@/components/Icon';
import type { Permission } from '@/api/types';

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

export type NavItem = {
  to: string;
  label: string;
  icon: IconName;
  /** Право, без которого раздел не показывается. */
  need?: Permission;
};

/** Порядок разделов зафиксирован хендоффом. Разделы без нужного права
 *  скрываются — сервер закрывает их независимо от этого. */
export const NAV: NavItem[] = [
  { to: '/', label: 'Панель', icon: 'ti-layout-dashboard' },
  { to: '/requests', label: 'Заявки', icon: 'ti-file-text' },
  { to: '/approvals', label: 'Согласование', icon: 'ti-circle-check', need: 'decide_request' },
  { to: '/sourcing', label: 'Закуп', icon: 'ti-package', need: 'source_request' },
  { to: '/reports', label: 'Отчёты', icon: 'ti-chart-bar', need: 'view_reports' },
  { to: '/team', label: 'Команда', icon: 'ti-users', need: 'view_reports' },
  { to: '/finance', label: 'Финансы', icon: 'ti-wallet', need: 'view_reports' },
  { to: '/employees', label: 'Сотрудники', icon: 'ti-user-plus', need: 'manage_reference' },
  { to: '/projects', label: 'Объекты', icon: 'ti-building', need: 'manage_reference' },
  { to: '/journal', label: 'Журнал', icon: 'ti-history', need: 'view_audit' },
  { to: '/settings', label: 'Параметры', icon: 'ti-settings' },
  { to: '/help', label: 'Справка', icon: 'ti-help-circle' },
];

/** Название роли для интерфейса. */
export const ROLE_LABEL: Record<string, string> = {
  employee: 'Сотрудник',
  manager: 'Руководитель',
  procurement: 'Отдел закупа',
  finance: 'Финансы',
  admin: 'Администратор',
};

export const APP_VERSION = 'v1.0';
