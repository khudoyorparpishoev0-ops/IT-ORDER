/**
 * Типы ответов API. Зеркалят pydantic-схемы из backend/app/schemas.
 * При изменении схемы на бэкенде обновлять здесь же.
 */

export type RequestStatus =
  | 'draft'
  /** Потребность на согласовании у руководителя. */
  | 'pending'
  /** У отдела закупа: проверка склада и цены. */
  | 'sourcing'
  /** Закуп оценил, сумма ждёт решения руководителя. */
  | 'priced'
  /** Сумма утверждена, ждёт оплаты. */
  | 'approved'
  | 'paid'
  /** Всё нашлось на складе — денег не потребовалось. */
  | 'fulfilled'
  | 'rejected';
export type PaymentMethod = 'card' | 'cash';
export type EmployeeRole =
  | 'employee'
  | 'manager'
  /** Отдел закупа: склад и цены. */
  | 'procurement'
  | 'finance'
  | 'admin';

export type EventKind =
  | 'created'
  | 'submitted'
  | 'commented'
  | 'viewed'
  | 'sourcing'
  | 'priced'
  | 'fulfilled'
  | 'approved'
  | 'auto_approved'
  | 'rejected'
  | 'paid';

/** Суммы приходят строками: Decimal нельзя переводить в number без потерь. */
export type Money = string;

export type Health = {
  status: 'ok' | 'degraded';
  app: string;
  timezone: string;
  database: 'ok' | 'unavailable';
  migrations: 'applied' | 'not_applied' | 'empty' | 'unknown';
  db_revision: string | null;
  time: string;
};

export type Project = {
  id: number;
  name: string;
  active: boolean;
  /** Сколько заявок ссылается на объект — по нему видно, что в работе. */
  requests_count: number;
  /** Потрачено по объекту за всё время. */
  spent: Money;
};

/** Подсказка для поля «что нужно»: как это называли раньше. */
export type Material = {
  title: string;
  unit: string | null;
  uses: number;
};

export type ProjectInput = {
  name: string;
  active: boolean;
};

export type Employee = {
  id: number;
  full_name: string;
  position: string;
  email: string | null;
  phone: string | null;
  role: EmployeeRole;
  monthly_limit: Money | null;
  active: boolean;
};

/** Состояние доступа сотрудника. Отдаётся только по праву
 *  manage_reference — обычный сотрудник этого не видит. */
export type EmployeeAccess = {
  id: number;
  can_sign_in: boolean;
  has_password: boolean;
  two_factor_enabled: boolean;
  two_factor_required: boolean;
  recovery_codes_left: number;
  last_login_at: string | null;
  /** Заполнено — вход закрыт до этого времени после неудачных попыток. */
  locked_until: string | null;
};

/** Поля карточки сотрудника при заведении и правке. */
export type EmployeeInput = {
  full_name: string;
  position: string;
  email: string | null;
  phone: string | null;
  role: EmployeeRole;
  monthly_limit: Money | null;
  active: boolean;
  /** Только при заведении: пароль уходит вместе с карточкой одним запросом. */
  password?: string | null;
};

/** Строка журнала действий. Подписи собирает панель — см. src/data/audit.ts. */
export type AuditEntry = {
  id: number;
  created_at: string;
  entity: string;
  entity_id: string;
  action: string;
  username: string | null;
  employee_id: number | null;
  ip: string | null;
  details: string | null;
};

export type AuditActor = {
  employee_id: number | null;
  username: string;
};

export type TeamMember = {
  id: number;
  full_name: string;
  position: string;
  limit: Money | null;
  spent: Money;
  /** Доля израсходованного, 0..100. null — лимит не задан. */
  pct: number | null;
  requests_count: number;
};

export type ExpenseLine = {
  id: number;
  title: string;
  quantity: number;
  unit: string | null;
  /** null — строку ещё не оценил закуп. */
  price: Money | null;
  total: Money | null;
  /** Нашлось на складе: покупать не нужно, в сумму не входит. */
  from_stock: boolean;
};

/** Ответ закупа по строке: со склада или почём купить. */
export type SourcingLineInput = {
  id: number;
  from_stock: boolean;
  price: Money | null;
};

export type SourcingInput = {
  lines: SourcingLineInput[];
  comment?: string | null;
};

/** Строка сметы при заведении заявки. Сумма считается сервером. */
export type ExpenseLineInput = {
  title: string;
  quantity: number;
  /** «шт.», «мешок», «м²» — словами. Цен у сотрудника нет. */
  unit: string | null;
};

export type RequestInput = {
  employee_id: number;
  project_id: number;
  lines: ExpenseLineInput[];
  /** true — сразу на согласование, false — оставить черновиком. */
  submit: boolean;
};

export type PaymentInput = {
  method: PaymentMethod;
  document: string;
};

export type RequestEvent = {
  kind: EventKind;
  text: string;
  actor: string;
  /** Готовая метка: «ИВАН ПЕТРОВ · 04.09.2026, 18:12». */
  meta: string;
  created_at: string;
};

export type PaymentInfo = {
  amount: Money;
  method: PaymentMethod;
  document: string;
  paid_at: string;
};

export type RequestListItem = {
  id: number;
  number: string;
  employee_id: number;
  employee_name: string;
  employee_position: string;
  project_id: number;
  project_name: string;
  amount: Money;
  /** false — заявку ещё не оценил закуп, сумма пока ничего не значит. */
  priced: boolean;
  status: RequestStatus;
  /** У кого заявка сейчас лежит. */
  awaiting_stage: 'author' | 'manager' | 'procurement' | 'finance' | 'closed';
  /** То же словами: «У отдела закупа: склад и цены». */
  awaiting_label: string;
  /** Сколько полных суток она лежит на текущем шаге. null — закрыта. */
  awaiting_days: number | null;
  /** Дата уже в поясе компании, строкой 04.09.2026. */
  date: string;
};

export type RequestDetail = RequestListItem & {
  employee_email: string | null;
  employee_phone: string | null;
  employee_limit: Money | null;
  employee_spent: Money;
  lines: ExpenseLine[];
  events: RequestEvent[];
  payment: PaymentInfo | null;
  decision_comment: string | null;
  decided_by: string | null;
  /** Кто из закупа оценил заявку. */
  sourced_by: string | null;
  /** Пояснение закупа: почему такие цены, что нашлось на складе. */
  sourcing_comment: string | null;
  /** Кто именно может сделать следующий шаг. */
  awaiting_people: string[];
};

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type DashboardStats = {
  total_requests: number;
  employees_count: number;
  approved_amount: Money;
  approved_count: number;
  pending_amount: Money;
  pending_count: number;
  budget_amount: Money | null;
  budget_used_pct: number | null;
};

export type ApprovalQueueInfo = {
  /** Сколько заявок ждёт согласования самой покупки. */
  count: number;
  oldest_employee: string | null;
  oldest_days: number | null;
  /** Сколько вернулось из закупа и ждёт решения по сумме. */
  priced_count: number;
};

export type ProjectShare = {
  project_id: number;
  name: string;
  amount: Money;
  pct: number;
};

export type MonthFact = {
  year: number;
  month: number;
  label: string;
  /** Значение в тысячах сомони. */
  value: number;
};

export type PaidRecord = {
  number: string;
  employee_name: string;
  project_name: string;
  amount: Money;
  method: PaymentMethod;
  document: string;
  paid_at: string;
};

export type PaymentsRegister = {
  items: PaidRecord[];
  total: Money;
  summary: string;
};

export type BudgetInfo = {
  month_limit: Money | null;
  used: Money;
  remaining: Money | null;
  used_pct: number | null;
  week_payout: Money;
  week_requests: number;
};

/** Права, которые сервер выдаёт роли. Панель по ним прячет разделы;
 *  решение всё равно принимает сервер на каждом запросе. */
export type Permission =
  | 'view_all_requests'
  | 'create_request'
  | 'create_request_for_others'
  | 'decide_request'
  | 'pay_request'
  | 'view_reports'
  | 'manage_reference'
  | 'source_request'
  | 'view_audit';

export type CurrentUser = {
  id: number;
  full_name: string;
  position: string;
  email: string | null;
  role: EmployeeRole;
  permissions: Permission[];
  last_login_at: string | null;
  two_factor_enabled: boolean;
  /** Роль обязана иметь второй фактор: отключить его нельзя. */
  two_factor_required: boolean;
  recovery_codes_left: number;
  notifications: NotificationPrefs;
};

export type NotificationPrefs = {
  new_requests: boolean;
  stale_requests: boolean;
  weekly_budget: boolean;
  /** false — почта не настроена, письма не уйдут при любых переключателях. */
  mail_configured: boolean;
};

export type LoginInput = {
  email: string;
  password: string;
};

/**
 * Итог первого шага входа:
 * `ok` — сессия выдана; `2fa_required` — нужен код из приложения;
 * `2fa_setup_required` — роль обязывает включить второй фактор.
 */
export type LoginStatus = 'ok' | '2fa_required' | '2fa_setup_required';

export type LoginResult = {
  status: LoginStatus;
  user: CurrentUser | null;
};

export type TotpSetup = {
  secret: string;
  uri: string;
  /** QR-код целиком, в SVG. */
  qr_svg: string;
};

export type AuthPolicy = {
  email_domains: string[];
  /** Подсказка вида «@it-hona.tj». */
  domains_hint: string;
  /** Без настроенной почты письмо отправить некуда. */
  password_reset_available: boolean;
};

export type DecisionInput = {
  approve: boolean;
  comment?: string | null;
  actor?: string | null;
};
