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

/** Строка формы, которую помощник видит как контекст. */
export type AssistantContextLine = { title: string; quantity: number | null; unit: string | null };

/** Реплика диалога с помощником: историю хранит панель. */
export type AssistantTurn = { role: 'user' | 'assistant'; text: string };

/** Уточняющий вопрос помощника; варианты рисуются кнопками. */
export type AssistantQuestion = { field: string; question: string; options: string[] };

/** Позиция, предложенная помощником. Применяет её человек. */
export type AssistantLine = {
  title: string;
  quantity: number;
  unit: string | null;
  /** Назначение: «подключение наружных IP-камер». */
  purpose: string | null;
};

export type AssistantReply = {
  /** false — модель недоступна; панель показывает это словами. */
  available: boolean;
  status: 'need_clarification' | 'ready' | 'warning' | 'recommendation';
  message: string;
  questions: AssistantQuestion[];
  lines: AssistantLine[];
  warnings: string[];
  recommendations: string[];
  /** Номер записи в журнале обращений: по нему отмечается «Применить». */
  interaction_id: number | null;
};

/** Настроен ли помощник по материалам (ключ Claude API на сервере). */
export type AssistantStatus = {
  enabled: boolean;
  model: string | null;
};

/** Совет помощника по одной строке заявки. Решение — за человеком. */
export type MaterialAdvice = {
  enabled: boolean;
  /** false — модель не ответила; форма работает без подсказки. */
  available: boolean;
  title: string;
  suggested: string | null;
  changed: boolean;
  unit: string | null;
  /** Так это уже заказывали: предложено написание из каталога. */
  matches_existing: boolean;
  notes: string[];
  interaction_id: number | null;
};

/** Сколько помощником пользовались за период. Раздел администратора. */
export type AiReasonCount = { reason: string; label: string; count: number };

export type AiUsage = {
  days: number;
  total: number;
  failed: number;
  error_pct: number | null;
  applied: number;
  apply_rate_pct: number | null;
  avg_seconds: number | null;
  by_kind: Record<string, number>;
  total_week: number;
  input_tokens: number | null;
  output_tokens: number | null;
  useful: number;
  useless: number;
  useless_pct: number | null;
  top_reasons: AiReasonCount[];
};

/** Показатели расхода на AI за отрезок времени. */
export type AiPeriod = {
  label: string;
  days: number;
  requests: number;
  /** Доллары строкой: перевод в number теряет доли цента. */
  cost_usd: string;
  /** Сумма посчитана по нынешней цене, а не по снимку (старые записи). */
  estimated: boolean;
  input_tokens: number;
  output_tokens: number;
  avg_seconds: number | null;
  error_pct: number | null;
  /** Обращений, на которые ответили без модели. */
  avoided: number;
  avoided_pct: number | null;
};

export type AiModelCost = {
  model: string | null;
  requests: number;
  cost_usd: string;
  avg_seconds: number | null;
  /** Цена модели известна. false — сумма занижена. */
  price_known: boolean;
};

export type AiUsageType = {
  key: string;
  label: string;
  requests: number;
  cost_usd: string;
  avg_tokens: number | null;
  apply_rate_pct: number | null;
  offered: number;
};

export type AiEmployeeCost = {
  employee: string;
  requests: number;
  tokens: number;
  cost_usd: string;
};

/** Бюджет месяца. Помощник по нему не выключается. */
export type AiBudget = {
  limit_usd: string | null;
  spent_usd: string;
  used_pct: number | null;
  warning_percent: number;
  warning: boolean;
};

export type AiFeedbackSummary = {
  useful: number;
  useless: number;
  feedback_rate_pct: number | null;
  useless_pct: number | null;
  top_reasons: AiReasonCount[];
};

/** Раздел «Расход AI» целиком. */
export type AiUsageReport = {
  periods: AiPeriod[];
  models: AiModelCost[];
  usage_types: AiUsageType[];
  employees: AiEmployeeCost[];
  feedback: AiFeedbackSummary;
  budget: AiBudget;
  apply_rate_pct: number | null;
  applied: number;
  offered: number;
  prices_checked: string;
};

/** Строка журнала обращений к AI. */
export type AiEntry = {
  id: number;
  kind: string;
  source: string;
  username: string | null;
  question: string | null;
  answer: string | null;
  ok: boolean;
  error: string | null;
  applied: boolean | null;
  duration_ms: number | null;
  created_at: string;
};

/** Состояние помощника для администратора. Ключ — только маска. */
export type AiSettings = {
  enabled: boolean;
  model: string;
  key_mask: string | null;
  timeout_seconds: number;
  prompt_overridden: boolean;
  analytics_prompt_overridden: boolean;
  usage: AiUsage;
  /** Автоматические сводки ORDER Intelligence за последний месяц. */
  deliveries: DeliveryStats;
  recent: AiEntry[];
};

/** Метрики автоматической рассылки. Раздел администратора. */
export type DeliveryStats = {
  days: number;
  morning_sent: number;
  evening_sent: number;
  critical_sent: number;
  failed: number;
  ai_digests: number;
  fallback_digests: number;
  subscribers: number;
};

/**
 * Настройки автоматических сводок ORDER Intelligence.
 *
 * Время местное: у каждого своё утро, общий час на всех означал бы, что
 * кому-то сводка приходит ночью.
 */
export type IntelligenceSubscription = {
  enabled: boolean;
  morning_enabled: boolean;
  evening_enabled: boolean;
  /** «09:00» — местное время получателя. */
  morning_time: string;
  evening_time: string;
  critical_alerts_enabled: boolean;
  /** Слать ли вечернюю сводку, когда за день ничего не изменилось. */
  when_no_changes: boolean;
  /** null — корпоративный пояс (timezone_hint). */
  timezone: string | null;
  timezone_hint: string;
  /** Есть ли куда доставлять: без Telegram сводка не уйдёт. */
  telegram_connected: boolean;
  /** Как часто повторяется неустранённый срочный сигнал, часов. */
  repeat_hours: number;
};

/** Изменение настроек рассылки: присылается только изменённое. */
export type IntelligenceSubscriptionIn = Partial<
  Omit<IntelligenceSubscription, 'timezone_hint' | 'telegram_connected' | 'repeat_hours'>
>;

/** Запуск фоновой задачи — строка в списке «Фоновые задачи». */
export type JobRun = {
  id: number;
  job: string;
  label: string;
  /** RUNNING | DONE | FAILED | SKIPPED */
  status: string;
  started_at: string;
  finished_at: string | null;
  details: string | null;
};

export type JobRunResult = {
  job: string;
  label: string;
  details: string;
};

/** Состояние привязки Telegram у текущего сотрудника. */
export type TelegramStatus = {
  /** Бот настроен администратором сервера: есть токен и имя бота. */
  configured: boolean;
  linked: boolean;
  username: string | null;
  bot_username: string | null;
};

export type TelegramLink = {
  url: string;
  expires_in_minutes: number;
};

/** Push-уведомления на телефон: настроено ли на сервере и сколько устройств у меня. */
export type PushConfig = {
  enabled: boolean;
  /** Открытый ключ VAPID для подписки браузера. */
  public_key: string | null;
  devices: number;
};

export type PushSubscribeInput = {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent?: string | null;
};

export type TelegramSetup = {
  webhook_url: string;
  bot_username: string | null;
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
  spent: Money;
  requests_count: number;
};

export type ExpenseLine = {
  id: number;
  title: string;
  /** Что набрал человек до правки помощником. */
  original_text: string;
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
  /** Что набрал человек до правки. Не передано — исходным считается title. */
  original_text?: string;
  quantity: number;
  /** «шт.», «мешок», «м²» — словами. Цен у сотрудника нет. */
  unit: string | null;
};

export type RequestInput = {
  employee_id: number;
  project_id: number;
  /** null — категория не указана, и это честнее, чем «Другое». */
  category?: RequestCategory | null;
  lines: ExpenseLineInput[];
  /** true — сразу на согласование, false — оставить черновиком. */
  submit: boolean;
};

/** Правка черновика: что не передано — не меняется. */
export type RequestUpdateInput = {
  project_id?: number;
  category?: RequestCategory | null;
  lines?: ExpenseLineInput[];
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
  /** Бизнес-категория расхода. null — не указана. */
  category: RequestCategory | null;
  /** Наименование для списка: первая позиция сметы (+ «и ещё N»). */
  title: string;
  lines_count: number;
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

export type OverviewStage = {
  key: 'draft' | 'pending' | 'sourcing' | 'priced' | 'approved';
  label: string;
  count: number;
  /** Хотя бы одна заявка стоит на этапе дольше порога задержки. */
  delayed: boolean;
  avg_days: number | null;
};

/** Дашборд: очередь решений, где стоят заявки, справочные цифры месяца.
 *  Сотрудник получает всё это по своим заявкам, руководитель — по всем. */
export type Overview = {
  decisions: number;
  delayed_decisions: number;
  queue: RequestListItem[];
  in_work: number;
  delayed_total: number;
  stages: OverviewStage[];
  slowest_stage: string | null;
  slowest_days: number | null;
  to_pay_amount: Money;
  to_pay_count: number;
  paid_amount: Money;
  paid_count: number;
  avg_cycle_days: number | null;
  rejected_count: number;
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

// --- Аналитика для руководителя -------------------------------------------

/** Насколько заявка требует внимания. */
export type AttentionLevel = 'critical' | 'attention' | 'normal';

export type AttentionItem = {
  id: number;
  number: string;
  title: string;
  project: string;
  employee: string;
  /** Кто держит заявку сейчас: «Отдел закупа». */
  holder: string;
  stage: string;
  stage_label: string;
  hours: number;
  norm_hours: number | null;
  level: AttentionLevel;
  /** Причины пометки: «стоит 31 ч при норме 8 ч». */
  reasons: string[];
  amount: Money;
  priced: boolean;
};

export type RequestBrief = {
  id: number;
  number: string;
  title: string;
  project: string;
  employee: string;
  holder: string;
  hours: number;
  amount: Money;
  priced: boolean;
};

export type StageStat = {
  key: string;
  label: string;
  count: number;
  avg_hours: number | null;
  over_norm: number;
  norm_hours: number | null;
  done_avg_hours: number | null;
  done_prev_avg_hours: number | null;
};

export type AnalyticsProject = {
  id: number;
  name: string;
  active_count: number;
  month_count: number;
  month_amount: Money;
  over_norm: number;
  top_materials: string[];
};

export type AnalyticsPerson = {
  id: number;
  name: string;
  role: string;
  holding: number;
  over_norm: number;
  created_month: number;
};

export type DuplicatePair = {
  first_id: number;
  first_number: string;
  second_id: number;
  second_number: string;
  project: string;
  materials: string[];
  hours_apart: number;
};

export type AnalyticsTrend = {
  label: string;
  current: number;
  previous: number;
  change_pct: number | null;
  unit: string;
};

export type AnalyticsTotals = {
  active: number;
  drafts: number;
  created_today: number;
  created_week: number;
  created_month: number;
  done_today: number;
  done_month: number;
  rejected_month: number;
  critical: number;
  attention: number;
  over_norm: number;
  to_pay_amount: Money;
  to_pay_count: number;
  paid_month_amount: Money;
  paid_month_count: number;
  budget_amount: Money | null;
  budget_used_pct: number | null;
  avg_cycle_days: number | null;
};

/** Слова модели поверх готовых цифр. */
export type AiText = {
  enabled: boolean;
  available: boolean;
  headline: string | null;
  summary: string[];
  recommendations: string[];
};

export type Digest = {
  generated_at: string;
  ai: AiText;
  totals: AnalyticsTotals;
  attention: AttentionItem[];
  in_work: RequestBrief[];
  stages: StageStat[];
  projects: AnalyticsProject[];
  people: AnalyticsPerson[];
  duplicates: DuplicatePair[];
  trends: AnalyticsTrend[];
  /** Чего система не знает: накладных, отделов, приоритетов. */
  blind_spots: string[];
};

export type AnalyticsTurn = { role: 'user' | 'assistant'; text: string };

export type AnalyticsRequestRef = { id: number; number: string; why: string };

export type AnalyticsReply = {
  enabled: boolean;
  available: boolean;
  answer: string;
  bullets: string[];
  requests: AnalyticsRequestRef[];
  recommendations: string[];
};


/** Подсказка из истории заявок. Считает база, модель не участвует. */
export type MemoryItem = {
  title: string;
  unit: string | null;
  times: number;
  last_number: string | null;
  last_date: string | null;
};

/** Что ORDER помнит о заявках: частое, своё, недавнее и по объекту. */
export type Memory = {
  frequent: MemoryItem[];
  mine: MemoryItem[];
  recent: MemoryItem[];
  project: MemoryItem[];
};

/** Недавняя заявка с теми же позициями. */
export type SimilarRequest = {
  id: number;
  number: string;
  title: string;
  project: string;
  employee: string;
  status: RequestStatus;
  days_ago: number;
  materials: string[];
};

/** Ответ проверки на повтор. */
export type DuplicateCheck = {
  requests: SimilarRequest[];
  days: number;
};


/** Позиция шаблона. Форма та же, что у строки формы заявки. */
export type TemplateLine = {
  title: string;
  quantity: number;
  unit: string | null;
};

/** Шаблон заявки: повторяющееся дело в одно нажатие. */
export type RequestTemplate = {
  id: number;
  name: string;
  project_id: number | null;
  project_name: string | null;
  lines: TemplateLine[];
  usage_count: number;
  last_used_at: string | null;
};

/** Шаблон, готовый к подстановке. Заявку применение не создаёт. */
export type TemplateApply = {
  template: RequestTemplate;
  /** Объект шаблона отключён или удалён. */
  warning: string | null;
};

/** Найденный прошлый вариант для «как в прошлый раз». */
export type RepeatOption = {
  request_id: number;
  number: string;
  title: string;
  project_id: number;
  project: string;
  days_ago: number;
  lines: TemplateLine[];
  reasons: string[];
};

export type RepeatResult = { options: RepeatOption[] };


/** Бизнес-категория заявки. Не справочник материалов: их одиннадцать. */
export type RequestCategory =
  | 'MATERIALS'
  | 'EQUIPMENT'
  | 'TRANSPORT'
  | 'FUEL'
  | 'MEALS'
  | 'LODGING'
  | 'TRIP'
  | 'DELIVERY'
  | 'SERVICES'
  | 'HOUSEHOLD'
  | 'OTHER';

/** Подписи категорий. Порядок — от частого к редкому. */
export const CATEGORY_LABEL: Record<RequestCategory, string> = {
  MATERIALS: 'Материалы',
  EQUIPMENT: 'Оборудование',
  TRANSPORT: 'Транспорт',
  FUEL: 'Топливо',
  MEALS: 'Питание',
  LODGING: 'Проживание',
  TRIP: 'Командировка',
  DELIVERY: 'Доставка',
  SERVICES: 'Услуги',
  HOUSEHOLD: 'Хозяйственные расходы',
  OTHER: 'Другое',
};

/** Строка блока «требует внимания» на дашборде директора. */
export type Problem = { code: string; label: string; count: number; severity: Severity };

/** Насколько всё плохо в разделе ORDER Intelligence. */
export type Severity = 'critical' | 'warning' | 'info';

/** Состояние компании одним экраном. Все числа считает сервер. */
export type ExecutiveOverview = {
  generated_at: string;
  active_requests: number;
  created_today: number;
  completed_today: number;
  overdue: number;
  stuck: number;
  requires_attention: number;
  amount_active: string;
  problems: Problem[];
};

/** Заявка в очереди внимания со всеми причинами разом. */
export type AttentionRow = {
  request_id: number;
  number: string;
  title: string;
  project: string;
  employee: string;
  status: RequestStatus;
  stage_label: string;
  hours_in_status: number;
  norm_hours: number | null;
  amount: string;
  priced: boolean;
  severity: Severity;
  reasons: string[];
  codes: string[];
};

/** Заявка без движения. */
export type StuckRequest = {
  request_id: number;
  number: string;
  title: string;
  project: string;
  employee: string;
  status: RequestStatus;
  stage_label: string;
  hours_in_status: number;
  norm_hours: number | null;
  assignee: string;
  severity: Severity;
  overdue: boolean;
  reason: string;
};

/** Нестыковка в заявке. Факт, а не обвинение. */
export type Issue = {
  request_id: number;
  number: string;
  title: string;
  project: string;
  employee: string;
  severity: Severity;
  code: string;
  detail: string;
};

/** Показатель, отличающийся от обычного уровня. */
export type Anomaly = {
  code: string;
  subject: string;
  current: number;
  previous: number;
  change_pct: number;
  unit: string;
  detail: string;
  severity: Severity;
};

/** Раздел ORDER Intelligence целиком. */
export type Intelligence = {
  overview: ExecutiveOverview;
  attention: AttentionRow[];
  stuck: StuckRequest[];
  issues: Issue[];
  anomalies: Anomaly[];
  ai: AiText;
  blind_spots: string[];
};
