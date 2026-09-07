import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from './client';
import type {
  AuthPolicy,
  CurrentUser,
  LoginInput,
  LoginResult,
  LoginStatus,
  Permission,
  TotpSetup,
} from './types';

type AuthState = {
  user: CurrentUser | null;
  /** true, пока не выяснили, вошёл ли пользователь. */
  isLoading: boolean;
  /** Незавершённый вход: ждём код или обязательную настройку. */
  pending: Exclude<LoginStatus, 'ok'> | null;
  can: (permission: Permission) => boolean;
  login: (data: LoginInput) => Promise<LoginStatus>;
  submitCode: (code: string) => Promise<void>;
  startTotpSetup: () => Promise<TotpSetup>;
  confirmTotpSetup: (code: string) => Promise<string[]>;
  /** Завершает обязательную настройку — вызывается после показа кодов. */
  finishPendingSetup: () => void;
  cancelPending: () => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => void;
  isBusy: boolean;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [pending, setPending] = useState<Exclude<LoginStatus, 'ok'> | null>(null);

  const me = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: () => api<CurrentUser>('/api/auth/me'),
    // 401 — это «не вошёл», а не сбой: повторять запрос бессмысленно.
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    staleTime: 5 * 60_000,
  });

  const applyUser = useCallback(
    (user: CurrentUser) => {
      setPending(null);
      qc.setQueryData(['auth', 'me'], user);
      // Данные предыдущего пользователя видеть нельзя.
      qc.invalidateQueries();
    },
    [qc],
  );

  const loginMutation = useMutation({
    mutationFn: (data: LoginInput) =>
      api<LoginResult>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (result) => {
      if (result.status === 'ok' && result.user) {
        applyUser(result.user);
      } else {
        setPending(result.status as Exclude<LoginStatus, 'ok'>);
      }
    },
  });

  const codeMutation = useMutation({
    mutationFn: (code: string) =>
      api<LoginResult>('/api/auth/2fa', {
        method: 'POST',
        body: JSON.stringify({ code }),
      }),
    onSuccess: (result) => {
      if (result.user) applyUser(result.user);
    },
  });

  const logoutMutation = useMutation({
    mutationFn: () => api<void>('/api/auth/logout', { method: 'POST' }),
    onSettled: () => {
      setPending(null);
      // Кэш чистим в любом случае: если сервер уже забыл сессию,
      // держать его данные на экране тем более нельзя.
      qc.clear();
    },
  });

  const user = me.isError ? null : (me.data ?? null);

  const can = useCallback(
    (permission: Permission) => user?.permissions.includes(permission) ?? false,
    [user],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      isLoading: me.isLoading,
      pending,
      can,
      login: async (data) => (await loginMutation.mutateAsync(data)).status,
      submitCode: async (code) => {
        await codeMutation.mutateAsync(code);
      },
      startTotpSetup: () => api<TotpSetup>('/api/auth/2fa/setup', { method: 'POST' }),
      confirmTotpSetup: async (code) => {
        const result = await api<{ codes: string[] }>('/api/auth/2fa/confirm', {
          method: 'POST',
          body: JSON.stringify({ code }),
        });
        // Сессию сервер выдал сразу, но экран НЕ переключаем: сперва нужно
        // показать коды восстановления. Иначе они исчезнут навсегда —
        // в базе хранятся только их отпечатки.
        return result.codes;
      },
      finishPendingSetup: () => {
        setPending(null);
        qc.invalidateQueries();
      },
      cancelPending: async () => {
        await logoutMutation.mutateAsync();
      },
      logout: async () => {
        await logoutMutation.mutateAsync();
      },
      refresh: () => {
        qc.invalidateQueries({ queryKey: ['auth', 'me'] });
      },
      isBusy: loginMutation.isPending || codeMutation.isPending,
    }),
    [user, me.isLoading, pending, can, loginMutation, codeMutation, logoutMutation, qc],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAuth вызван вне AuthProvider');
  return ctx;
}

/** Политика входа: какие домены почты допускаются. */
export function useAuthPolicy() {
  return useQuery({
    queryKey: ['auth', 'policy'],
    queryFn: () => api<AuthPolicy>('/api/auth/policy'),
    staleTime: 60 * 60_000,
  });
}
