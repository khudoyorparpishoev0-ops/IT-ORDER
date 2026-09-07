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
  DashboardStats,
  DecisionInput,
  Employee,
  EmployeeAccess,
  EmployeeInput,
  Health,
  MonthFact,
  Page,
  PaymentInput,
  PaymentsRegister,
  Project,
  ProjectShare,
  RequestDetail,
  RequestInput,
  RequestListItem,
  RequestStatus,
  TeamMember,
} from './types';

export const keys = {
  health: ['health'] as const,
  projects: ['projects'] as const,
  employees: ['employees'] as const,
  employeeAccess: ['employees', 'access'] as const,
  team: ['team'] as const,
  requests: ['requests'] as const,
  request: (id: number) => ['requests', id] as const,
  dashboard: ['reports', 'dashboard'] as const,
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
      for (const key of [keys.employees, keys.employeeAccess, keys.team, keys.dashboard]) {
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

/** `enabled` выключает запрос, когда у роли нет права на отчёты:
 *  иначе панель стучалась бы в закрытый эндпоинт и получала 403. */
export function useDashboard(enabled = true) {
  return useQuery({
    queryKey: keys.dashboard,
    queryFn: () => api<DashboardStats>('/api/reports/dashboard'),
    enabled,
  });
}

export function useQueueInfo(enabled = true) {
  return useQuery({
    queryKey: keys.queue,
    queryFn: () => api<ApprovalQueueInfo>('/api/reports/queue'),
    enabled,
  });
}

export function useProjectShares() {
  return useQuery({
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

/** Всё, что зависит от заявок и их статусов. Сбрасываем разом: заявка
 *  меняет и списки, и сводки, и бюджет, и расход по сотруднику. */
function invalidateRequests(qc: ReturnType<typeof useQueryClient>) {
  for (const key of [
    keys.requests,
    keys.dashboard,
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
