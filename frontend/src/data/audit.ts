/**
 * Подписи для журнала действий. Зеркалит `app/core/audit_labels.py` —
 * добавили действие на сервере, добавьте и здесь, иначе в таблице
 * останется голый код.
 */

export const ENTITY_LABEL: Record<string, string> = {
  employee: 'Сотрудник',
  project: 'Объект',
  job: 'Фоновая задача',
  budget: 'Бюджет месяца',
  request: 'Заявка',
  analytics: 'AI-аналитика',
  template: 'Шаблон заявки',
};

export const ACTION_LABEL: Record<string, string> = {
  template_created: 'Шаблон создан',
  template_updated: 'Шаблон изменён',
  template_deleted: 'Шаблон удалён',
  login: 'Вход в систему',
  logout: 'Выход',
  login_failed: 'Неудачный вход',
  login_locked: 'Вход заблокирован',
  password_changed: 'Сменил себе пароль',
  set_password: 'Пароль выдан администратором',
  admin_password_reset: 'Сброс пароля администратором',
  admin_password_reset_failed: 'Сброс пароля: неверный код',
  password_reset_requested: 'Запрошено восстановление пароля',
  password_reset_applied: 'Пароль восстановлен по ссылке',
  totp_enabled: 'Второй фактор включён',
  totp_disabled: 'Второй фактор выключен',
  totp_reset_by_admin: 'Второй фактор сброшен администратором',
  recovery_code_used: 'Вход по коду восстановления',
  recovery_codes_reissued: 'Коды восстановления перевыпущены',
  telegram_linked: 'Telegram подключён',
  telegram_unlinked: 'Telegram отключён',
  push_subscribed: 'Уведомления на телефон включены',
  push_unsubscribed: 'Уведомления на телефон отключены',
  bootstrap_admin: 'Создан стартовый администратор',
  ai_question: 'Вопрос AI-аналитику',
  create: 'Создание',
  update: 'Изменение',
  delete: 'Удаление',
  submit: 'Отправлена на согласование',
  sourcing: 'Покупка согласована, передана в закуп',
  priced: 'Оценена закупом',
  fulfilled: 'Закрыта складом',
  approve: 'Одобрена',
  reject: 'Отклонена',
  auto_approve: 'Одобрена автоматически',
  pay: 'Выплата проведена',
  job_run: 'Задача запущена вручную',
};

/** Что показывать в фильтре «Раздел». */
export const ENTITY_FILTER = [
  { value: '', label: 'Все разделы' },
  { value: 'employee', label: 'Сотрудники' },
  { value: 'request', label: 'Заявки' },
  { value: 'project', label: 'Объекты' },
  { value: 'job', label: 'Фоновые задачи' },
  { value: 'budget', label: 'Бюджет' },
  { value: 'template', label: 'Шаблоны' },
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
      'admin_password_reset',
      'admin_password_reset_failed',
      'password_reset_requested',
      'password_reset_applied',
      'totp_enabled',
      'totp_disabled',
      'totp_reset_by_admin',
      'recovery_code_used',
      'recovery_codes_reissued',
      'telegram_linked',
      'telegram_unlinked',
      'push_subscribed',
      'push_unsubscribed',
    ],
  },
  {
    label: 'Заявки',
    actions: ['submit', 'sourcing', 'priced', 'fulfilled', 'approve', 'auto_approve', 'reject', 'pay'],
  },
  { label: 'Справочники', actions: ['create', 'update', 'delete'] },
  {
    label: 'Шаблоны',
    actions: ['template_created', 'template_updated', 'template_deleted'],
  },
  { label: 'AI', actions: ['ai_question'] },
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
