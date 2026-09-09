import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { Theme } from './config';
import type { ToastData } from '@/components/Toast';

type ShellState = {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  toast: ToastData | null;
  flash: (text: string, color: string) => void;
  hideToast: () => void;
};

const Ctx = createContext<ShellState | null>(null);

const KEY_THEME = 'hona-core:theme';

/** Чтение настроек не должно ронять приложение в приватном окне. */
function read<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return allowed.includes(v as T) ? (v as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* приватное окно или заблокированные site data — не мешаем работе */
  }
}

export function ShellProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() =>
    read(KEY_THEME, ['light', 'dark'] as const, 'light'),
  );
  const [toast, setToast] = useState<ToastData | null>(null);

  // Тема живёт на корне документа — так её видят все стили. Плотность
  // одна на всю панель, вариантов шелла больше нет.
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    write(KEY_THEME, t);
  }, []);

  const toggleTheme = useCallback(
    () => setTheme(theme === 'dark' ? 'light' : 'dark'),
    [theme, setTheme],
  );

  const flash = useCallback((text: string, color: string) => setToast({ text, color }), []);
  const hideToast = useCallback(() => setToast(null), []);

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme, toast, flash, hideToast }),
    [theme, setTheme, toggleTheme, toast, flash, hideToast],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useShell(): ShellState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useShell вызван вне ShellProvider');
  return ctx;
}
