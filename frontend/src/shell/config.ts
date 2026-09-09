import type { IconName } from '@/components/Icon';
import type { Permission } from '@/api/types';

export type Theme = 'light' | 'dark';

export type NavItem = {
  to: string;
  label: string;
  icon: IconName;
  /** Право, без которого раздел не показывается. */
  need?: Permission;
  /** Счётчик справа: очередь согласования. */
  counter?: 'queue';
};

/** Порядок разделов зафиксирован хендоффом UI-кита. Разделы без нужного
 *  права отсутствуют в разметке вовсе — сервер закрывает их независимо. */
export const NAV: NavItem[] = [
  { to: '/', label: 'Дашборд', icon: 'ti-layout-dashboard' },
  { to: '/requests', label: 'Заявки', icon: 'ti-file-text' },
  { to: '/approvals', label: 'Согласование', icon: 'ti-checklist', need: 'decide_request', counter: 'queue' },
  { to: '/sourcing', label: 'Закуп', icon: 'ti-shopping-cart', need: 'source_request' },
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

export const APP_VERSION = 'v2.0';
