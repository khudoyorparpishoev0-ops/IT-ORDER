import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import './styles/fonts';

import './styles/tokens.css';
import './styles/base.css';
import { App } from './App';
import { ShellProvider } from './shell/ShellContext';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Панель работает в LAN: лишние повторы только маскируют реальную
      // недоступность API, поэтому один повтор и без перезапроса по фокусу.
      retry: 1,
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
        <ShellProvider>
          <App />
        </ShellProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
