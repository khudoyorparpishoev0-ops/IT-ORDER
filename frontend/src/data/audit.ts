/**
 * Подписи для журнала действий. Зеркалит `app/core/audit_labels.py` —
 * добавили действие на сервере, добавьте и здесь, иначе в таблице
 * останется голый код.
 */

export const ENTITY_LABEL: Record<string, string> = {
  employee: 'Сотрудник',
  project: 'Объект',
  request: 'Заявка',
};

export const ACTION_LABEL: Record<string, string> = {
  login: 'Вход в систему',
  logout: 'Выход',
  login_failed: 'Неудачный вход',
  login_locked: 'Вход заблокирован',
  password_changed: 'Сменил себе пароль',
  set_password: 'Пароль выдан администратором',
  password_reset_requested: 'Запрошено восстановление пароля',
  password_reset_applied: 'Пароль восстановлен по ссылке',
  totp_enabled: 'Второй фактор включён',
  totp_disabled: 'Второй фактор выключен',
  totp_reset_by_admin: 'Второй фактор сброшен администратором',
  recovery_code_used: 'Вход по коду восстановления',
  recovery_codes_reissued: 'Коды восстановления перевыпущены',
  telegram_linked: 'Telegram подключён',
  telegram_unlinked: 'Telegram отключён',
  bootstrap_admin: 'Создан стартовый администратор',
  create: 'Создание',
  update: 'Изменение',
  delete: 'Удаление',
  submit: 'Отправлена на согласование',
  approve: 'Одобрена',
  reject: 'Отклонена',
  auto_approve: 'Одобрена автоматически',
  pay: 'Выплата проведена',
};

/** Что показывать в фильтре «Раздел». */
export const ENTITY_FILTER = [
  { value: '', label: 'Все разделы' },
  { value: 'employee', label: 'Сотрудники' },
  { value: 'request', label: 'Заявки' },
  { value: 'project', label: 'Объекты' },
];

/** Действия в фильтре сгруппированы: доступ отдельно, работа отдельно. */
export const ACTION_GROUPS: { label: string; actions: string[] }[] = [
  {
    label: 'Доступ',
    actions: [
      'login',
      'logout',
      'login_failed',
      'login_locked',
      'password_changed',
      'set_password',
      'password_reset_requested',
      'password_reset_applied',
      'totp_enabled',
      'totp_disabled',
      'totp_reset_by_admin',
      'recovery_code_used',
      'recovery_codes_reissued',
      'telegram_linked',
      'telegram_unlinked',
    ],
  },
  {
    label: 'Заявки',
    actions: ['submit', 'approve', 'auto_approve', 'reject', 'pay'],
  },
  { label: 'Справочники', actions: ['create', 'update', 'delete'] },
];

/** Тревожные события подсвечиваются: их ищут в журнале первым делом. */
const ALARMING = new Set(['login_failed', 'login_locked', 'totp_reset_by_admin']);

export function actionTone(action: string): string | undefined {
  if (ALARMING.has(action)) return 'var(--dot-err)';
  if (action === 'login' || action === 'logout') return 'var(--dot-off)';
  return undefined;
}

export function entityLabel(entity: string): string {
  return ENTITY_LABEL[entity] ?? entity;
}

export function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? action;
}
