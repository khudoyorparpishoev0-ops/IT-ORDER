/**
 * Запросы к API. Компоненты ходят в бэкенд только через эти хуки —
 * так кэш и инвалидация лежат в одном месте.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, query } from './client';
import type {
  ApprovalQueueInfo,
  AuditActor,
  AuditEntry,
  BudgetInfo,
  DecisionInput,
  Employee,
  EmployeeAccess,
  EmployeeInput,
  Health,
  JobRun,
  JobRunResult,
  AssistantStatus,
  Material,
  MaterialAdvice,
  MonthFact,
  Overview,
  Page,
  PaymentInput,
  PaymentsRegister,
  Project,
  ProjectInput,
  ProjectShare,
  RequestDetail,
  RequestInput,
  RequestUpdateInput,
  RequestListItem,
  RequestStatus,
  SourcingInput,
  TeamMember,
  PushConfig,
  PushSubscribeInput,
  TelegramLink,
  TelegramSetup,
  TelegramStatus,
} from './types';

export const keys = {
  health: ['health'] as const,
  projects: ['projects'] as const,
  materials: ['materials'] as const,
  assistant: ['materials', 'assistant'] as const,
  telegram: ['telegram'] as const,
  push: ['push'] as const,
  jobs: ['jobs'] as const,
  employees: ['employees'] as const,
  employeeAccess: ['employees', 'access'] as const,
  team: ['team'] as const,
  requests: ['requests'] as const,
  request: (id: number) => ['requests', id] as const,
  // Под префиксом заявок: любое решение сбрасывает и дашборд.
  overview: ['requests', 'overview'] as const,
  queue: ['reports', 'queue'] as const,
  byProject: ['reports', 'by-project'] as const,
  monthly: ['reports', 'monthly'] as const,
  payments: ['reports', 'payments'] as const,
  budget: ['reports', 'budget'] as const,
  audit: ['audit'] as const,
  auditActors: ['audit', 'actors'] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: () => api<Health>('/health'),
    staleTime: 60_000,
  });
}

export function useProjects() {
  return useQuery({
    queryKey: keys.projects,
    queryFn: () => api<Project[]>('/api/projects'),
    staleTime: 5 * 60_000,
    // Форму заявки открывают ровно тогда, когда список нужен свежим:
    // администратор мог завести объект минуту назад, а вкладка у
    // сотрудника открыта с утра. Запрос дешёвый — несколько строк.
    refetchOnMount: 'always',
  });
}

export function useEmployees() {
  return useQuery({
    queryKey: keys.employees,
    queryFn: () => api<Employee[]>('/api/employees'),
    staleTime: 5 * 60_000,
  });
}

/** Состояние доступа сотрудников. `enabled` выключает запрос там, где
 *  права нет: иначе панель стучалась бы в закрытый эндпоинт и ловила 403. */
export function useEmployeeAccess(enabled = true) {
  return useQuery({
    queryKey: keys.employeeAccess,
    queryFn: () => api<EmployeeAccess[]>('/api/employees/access'),
    enabled,
  });
}

/** После правки справочника сотрудников устаревает всё, где показано имя,
 *  роль или лимит. Сбрасываем разом, чтобы не искать по экранам. */
function useEmployeeMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of [keys.employees, keys.employeeAccess, keys.team, keys.overview]) {
        qc.invalidateQueries({ queryKey: key });
      }
    },
  });
}

export function useCreateEmployee() {
  return useEmployeeMutation((data: EmployeeInput) =>
    api<Employee>('/api/employees', { method: 'POST', body: JSON.stringify(data) }),
  );
}

export function useUpdateEmployee() {
  return useEmployeeMutation(({ id, ...data }: Partial<EmployeeInput> & { id: number }) =>
    api<Employee>(`/api/employees/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  );
}

export function useSetEmployeePassword() {
  return useEmployeeMutation(({ id, password }: { id: number; password: string }) =>
    api<Employee>(`/api/employees/${id}/password`, {
      method: 'PUT',
      body: JSON.stringify({ password }),
    }),
  );
}

export function useResetEmployee2fa() {
  return useEmployeeMutation((id: number) =>
    api<Employee>(`/api/employees/${id}/reset-2fa`, { method: 'POST' }),
  );
}

export function useDeleteEmployee() {
  return useEmployeeMutation((id: number) =>
    api<void>(`/api/employees/${id}`, { method: 'DELETE' }),
  );
}

/** Правка справочника объектов задевает списки и сводки по объектам. */
function useProjectMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of [keys.projects, keys.byProject, keys.requests]) {
        qc.invalidateQueries({ queryKey: key });
      }
    },
  });
}

export function useCreateProject() {
  return useProjectMutation((data: ProjectInput) =>
    api<Project>('/api/projects', { method: 'POST', body: JSON.stringify(data) }),
  );
}

export function useUpdateProject() {
  return useProjectMutation(({ id, ...data }: Partial<ProjectInput> & { id: number }) =>
    api<Project>(`/api/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  );
}

/**
 * Что уже заказывали — подсказки для поля «что нужно».
 *
 * Забираем список целиком и фильтруем в браузере силами datalist:
 * позиций сотни, а не тысячи, зато нет запроса на каждую букву и
 * подсказка появляется мгновенно.
 */
export function useMaterials() {
  return useQuery({
    queryKey: keys.materials,
    queryFn: () => api<Material[]>('/api/materials'),
    staleTime: 5 * 60_000,
    refetchOnMount: 'always',
  });
}

/** Настроен ли помощник по материалам. Перепрашиваем при каждом
 *  открытии формы: администратор включил ключ днём, а приложение на
 *  телефоне живёт открытым сутками и иначе помнило бы «выключен». */
export function useAssistantStatus() {
  return useQuery({
    queryKey: keys.assistant,
    queryFn: () => api<AssistantStatus>('/api/materials/assistant'),
    staleTime: 60_000,
    refetchOnMount: 'always',
  });
}

/** Совет по написанию материала. Мутация, а не запрос: зовётся по
 *  событию (поле потеряло фокус), а не при каждом рендере. */
export function useMaterialAdvice() {
  return useMutation({
    mutationFn: (data: { title: string; unit: string | null }) =>
      api<MaterialAdvice>('/api/materials/advice', { method: 'POST', body: JSON.stringify(data) }),
  });
}

/**
 * Привязка Telegram. `poll` включается, пока человек ходит по ссылке к
 * боту: привязка случается на стороне Telegram, и панель узнаёт о ней
 * только опросом.
 */
export function useTelegramStatus(poll = false) {
  return useQuery({
    queryKey: keys.telegram,
    queryFn: () => api<TelegramStatus>('/api/telegram/status'),
    refetchInterval: poll ? 3000 : false,
  });
}

export function useTelegramLink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<TelegramLink>('/api/telegram/link', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.telegram }),
  });
}

export function useTelegramUnlink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<TelegramStatus>('/api/telegram/unlink', { method: 'POST' }),
    onSuccess: (data) => qc.setQueryData(keys.telegram, data),
  });
}

/** Установка вебхука: администратор говорит Telegram, куда слать обновления. */
export function useTelegramSetup() {
  return useMutation({
    mutationFn: () => api<TelegramSetup>('/api/telegram/setup', { method: 'POST' }),
  });
}

/** Push на телефон: ключ сервера и число подписанных устройств. */
export function usePushConfig() {
  return useQuery({
    queryKey: keys.push,
    queryFn: () => api<PushConfig>('/api/push/config'),
  });
}

export function usePushSubscribe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PushSubscribeInput) =>
      api<PushConfig>('/api/push/subscribe', { method: 'POST', body: JSON.stringify(data) }),
    onSuccess: (data) => qc.setQueryData(keys.push, data),
  });
}

export function usePushUnsubscribe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (endpoint: string) =>
      api<PushConfig>('/api/push/unsubscribe', {
        method: 'POST',
        body: JSON.stringify({ endpoint }),
      }),
    onSuccess: (data) => qc.setQueryData(keys.push, data),
  });
}

/** Проверочное уведомление на свои устройства. Ошибка идёт наружу. */
export function usePushTest() {
  return useMutation({
    mutationFn: () => api<void>('/api/push/test', { method: 'POST' }),
  });
}

/** Фоновые задачи: что и когда отработало. Только для администратора. */
export function useJobRuns(enabled = true) {
  return useQuery({
    queryKey: keys.jobs,
    queryFn: () => api<JobRun[]>('/api/jobs'),
    enabled,
  });
}

/** Ручной запуск задачи — проверка настройки почты и бота без ожидания утра. */
export function useRunJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (job: string) =>
      api<JobRunResult>(`/api/jobs/${job}/run`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.jobs }),
  });
}

export function useTeam() {
  return useQuery({
    queryKey: keys.team,
    queryFn: () => api<TeamMember[]>('/api/team'),
  });
}

export type RequestFilters = {
  status?: RequestStatus;
  search?: string;
  projectId?: number;
  employeeId?: number;
  limit?: number;
  offset?: number;
  allPeriods?: boolean;
};

export function useRequests(filters: RequestFilters = {}) {
  return useQuery({
    queryKey: [...keys.requests, filters] as const,
    queryFn: () =>
      api<Page<RequestListItem>>(
        `/api/requests${query({
          status: filters.status,
          search: filters.search,
          project_id: filters.projectId,
          employee_id: filters.employeeId,
          limit: filters.limit,
          offset: filters.offset,
          all_periods: filters.allPeriods,
        })}`,
      ),
    // Список обновляется после решений — держим свежим недолго.
    staleTime: 10_000,
  });
}

export function useRequest(id: number | null) {
  return useQuery({
    queryKey: keys.request(id ?? 0),
    queryFn: () => api<RequestDetail>(`/api/requests/${id}`),
    enabled: id !== null,
  });
}

/** Дашборд. Открыт всем вошедшим: сервер сам сужает цифры до своих заявок. */
export function useOverview() {
  return useQuery({
    queryKey: keys.overview,
    queryFn: () => api<Overview>('/api/requests/overview'),
    staleTime: 10_000,
  });
}

export function useQueueInfo(enabled = true) {
  return useQuery({
    queryKey: keys.queue,
    queryFn: () => api<ApprovalQueueInfo>('/api/reports/queue'),
    enabled,
  });
}

export function useProjectShares(enabled = true) {
  return useQuery({
    enabled,
    queryKey: keys.byProject,
    queryFn: () => api<ProjectShare[]>('/api/reports/by-project'),
  });
}

export function useMonthlyFacts() {
  return useQuery({
    queryKey: keys.monthly,
    queryFn: () => api<MonthFact[]>('/api/reports/monthly?months=6'),
  });
}

export function usePaymentsRegister(projectId?: number) {
  return useQuery({
    queryKey: [...keys.payments, projectId ?? null] as const,
    queryFn: () =>
      api<PaymentsRegister>(`/api/reports/payments${query({ project_id: projectId })}`),
  });
}

export function useBudget() {
  return useQuery({
    queryKey: keys.budget,
    queryFn: () => api<BudgetInfo>('/api/reports/budget'),
  });
}

/** Бюджет месяца задаёт бухгалтерия. Сводки от него зависят — сбрасываем их. */
export function useSetBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (amount: string) =>
      api<BudgetInfo>('/api/reports/budget', {
        method: 'PUT',
        body: JSON.stringify({ amount }),
      }),
    onSuccess: (data) => {
      qc.setQueryData(keys.budget, data);
      qc.invalidateQueries({ queryKey: keys.overview });
    },
  });
}

/** Всё, что зависит от заявок и их статусов. Сбрасываем разом: заявка
 *  меняет и списки, и сводки, и бюджет, и расход по сотруднику. */
function invalidateRequests(qc: ReturnType<typeof useQueryClient>) {
  for (const key of [
    keys.requests,
    keys.queue,
    keys.byProject,
    keys.monthly,
    keys.payments,
    keys.budget,
    keys.team,
  ]) {
    qc.invalidateQueries({ queryKey: key });
  }
}

export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RequestInput) =>
      api<RequestDetail>('/api/requests', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => invalidateRequests(qc),
  });
}

/** Правка черновика. Поданную заявку сервер править не даст. */
export function useUpdateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: RequestUpdateInput & { id: number }) =>
      api<RequestDetail>(`/api/requests/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: (data, variables) => {
      invalidateRequests(qc);
      qc.setQueryData(keys.request(variables.id), data);
    },
  });
}

/** Отправка черновика на согласование. */
export function useSubmitRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      api<RequestDetail>(`/api/requests/${id}/submit`, { method: 'POST' }),
    onSuccess: (data, id) => {
      invalidateRequests(qc);
      qc.setQueryData(keys.request(id), data);
    },
  });
}

/** Удаление черновика. Номер в оборот не возвращается. */
export function useDeleteRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/api/requests/${id}`, { method: 'DELETE' }),
    onSuccess: (_data, id) => {
      // Сначала убрать карточку из кэша, потом сбрасывать списки: иначе
      // сброс перезапросил бы уже удалённую заявку и получил 404.
      qc.removeQueries({ queryKey: keys.request(id) });
      invalidateRequests(qc);
    },
  });
}

/** Проведение выплаты. Заявка меняет статус, поэтому сбрасываем то же самое. */
export function usePayRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: PaymentInput & { id: number }) =>
      api<RequestDetail>(`/api/requests/${id}/payment`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (_data, variables) => {
      invalidateRequests(qc);
      qc.invalidateQueries({ queryKey: keys.request(variables.id) });
    },
  });
}

/** Ответ отдела закупа: что со склада, что почём купить. */
export function useSourcing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: SourcingInput & { id: number }) =>
      api<RequestDetail>(`/api/requests/${id}/sourcing`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (_data, variables) => {
      invalidateRequests(qc);
      qc.invalidateQueries({ queryKey: keys.request(variables.id) });
    },
  });
}

/** Решение по заявке. После успеха сбрасываем всё, что зависит от статусов. */
export function useDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: DecisionInput & { id: number }) =>
      api<RequestDetail>(`/api/requests/${id}/decision`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => invalidateRequests(qc),
  });
}

export type AuditFilters = {
  entity?: string;
  action?: string;
  employeeId?: number;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  offset?: number;
};

/** Журнал действий. Доступен только с правом view_audit — иначе запрос
 *  не отправляем вовсе, чтобы не ловить 403. */
export function useAudit(filters: AuditFilters, enabled = true) {
  return useQuery({
    queryKey: [...keys.audit, filters] as const,
    queryFn: () =>
      api<Page<AuditEntry>>(
        `/api/audit${query({
          entity: filters.entity,
          action: filters.action,
          employee_id: filters.employeeId,
          search: filters.search,
          date_from: filters.dateFrom,
          date_to: filters.dateTo,
          limit: filters.limit,
          offset: filters.offset,
        })}`,
      ),
    enabled,
    // Журнал дописывается постоянно, но читают его глазами — обновлять
    // на каждый фокус окна незачем.
    staleTime: 30_000,
  });
}

export function useAuditActors(enabled = true) {
  return useQuery({
    queryKey: keys.auditActors,
    queryFn: () => api<AuditActor[]>('/api/audit/actors'),
    enabled,
    staleTime: 5 * 60_000,
  });
}
