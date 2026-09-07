import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';

import './styles/fonts';

import './styles/tokens.css';
import './styles/base.css';
import { App } from './App';
import { AuthProvider } from './api/auth';
import { ApiError } from './api/client';
import { markSessionExpired } from './api/session';
import { ShellProvider } from './shell/ShellContext';

/**
 * Сессия может истечь между запросами, и тогда 401 приходит в любой хук.
 * Обрабатываем это один раз здесь: сбрасываем сведения о входе, и панель
 * сама показывает экран входа — вместо проверки в каждом компоненте.
 *
 * Вместе с этим поднимаем признак «сессия истекла»: без него подмена
 * экрана посреди заполненной формы выглядит как необъяснимо закрывшееся
 * окно, и человек не понимает, сохранилось что-то или нет.
 */
function onUnauthorized(error: unknown): void {
  if (error instanceof ApiError && error.status === 401) {
    queryClient.setQueryData(['auth', 'me'], null);
    markSessionExpired();
  }
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: onUnauthorized }),
  mutationCache: new MutationCache({ onError: onUnauthorized }),
  defaultOptions: {
    queries: {
      // Панель работает в LAN: лишние повторы только маскируют реальную
      // недоступность API. Отказ по правам повторять тем более незачем.
      retry: (count, error) => {
        if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          return false;
        }
        return count < 1;
      },
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

const container = document.getElementById('root');
if (!container) throw new Error('Не найден корневой элемент #root');

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <ShellProvider>
            <App />
          </ShellProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
