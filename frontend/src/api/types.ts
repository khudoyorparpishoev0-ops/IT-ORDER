/**
 * Типы ответов API. Зеркалят pydantic-схемы из backend/app/schemas.
 * При изменении схемы на бэкенде обновлять здесь же.
 */

export type RequestStatus = 'draft' | 'pending' | 'approved' | 'paid' | 'rejected';
export type PaymentMethod = 'card' | 'cash';
export type EmployeeRole = 'employee' | 'manager' | 'finance' | 'admin';

export type EventKind =
  | 'created'
  | 'submitted'
  | 'commented'
  | 'viewed'
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
  price: Money;
  total: Money;
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
  status: RequestStatus;
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
  count: number;
  oldest_employee: string | null;
  oldest_days: number | null;
  auto_approve_threshold: Money;
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

export type DecisionInput = {
  approve: boolean;
  comment?: string | null;
  actor?: string | null;
};
