import { createContext, useCallback, useContext, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from './client';
import type { CurrentUser, LoginInput, Permission } from './types';

type AuthState = {
  user: CurrentUser | null;
  /** true, пока не выяснили, вошёл ли пользователь. */
  isLoading: boolean;
  can: (permission: Permission) => boolean;
  login: (data: LoginInput) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  isLoggingIn: boolean;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();

  const me = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: () => api<CurrentUser>('/api/auth/me'),
    // 401 — это «не вошёл», а не сбой: повторять запрос бессмысленно.
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
    staleTime: 5 * 60_000,
  });

  const loginMutation = useMutation({
    mutationFn: (data: LoginInput) =>
      api<CurrentUser>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: (user) => {
      qc.setQueryData(['auth', 'me'], user);
      // Данные предыдущего пользователя видеть нельзя.
      qc.invalidateQueries();
    },
  });

  const logoutMutation = useMutation({
    mutationFn: () => api<void>('/api/auth/logout', { method: 'POST' }),
    onSettled: () => {
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
      can,
      login: (data) => loginMutation.mutateAsync(data),
      logout: async () => {
        await logoutMutation.mutateAsync();
      },
      isLoggingIn: loginMutation.isPending,
    }),
    [user, me.isLoading, can, loginMutation, logoutMutation],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useAuth вызван вне AuthProvider');
  return ctx;
}
