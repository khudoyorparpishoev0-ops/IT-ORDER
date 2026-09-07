import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { ShellVariant, Theme } from './config';
import { VARIANTS } from './config';
import type { ToastData } from '@/components/Toast';

type ShellState = {
  variant: ShellVariant;
  setVariant: (v: ShellVariant) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  toast: ToastData | null;
  flash: (text: string, color: string) => void;
  hideToast: () => void;
};

const Ctx = createContext<ShellState | null>(null);

const KEY_THEME = 'hona-core:theme';
const KEY_VARIANT = 'hona-core:variant';

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
  const [variant, setVariantState] = useState<ShellVariant>(() =>
    read(KEY_VARIANT, ['dispatch', 'light'] as const, 'dispatch'),
  );
  const [theme, setThemeState] = useState<Theme>(() =>
    read(KEY_THEME, ['light', 'dark'] as const, 'light'),
  );
  const [toast, setToast] = useState<ToastData | null>(null);

  // Тема и плотность живут на корне документа — так их видят все стили.
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.density = VARIANTS[variant].density;
  }, [theme, variant]);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    write(KEY_THEME, t);
  }, []);

  const setVariant = useCallback((v: ShellVariant) => {
    setVariantState(v);
    write(KEY_VARIANT, v);
  }, []);

  const toggleTheme = useCallback(
    () => setTheme(theme === 'dark' ? 'light' : 'dark'),
    [theme, setTheme],
  );

  const flash = useCallback((text: string, color: string) => setToast({ text, color }), []);
  const hideToast = useCallback(() => setToast(null), []);

  const value = useMemo(
    () => ({ variant, setVariant, theme, setTheme, toggleTheme, toast, flash, hideToast }),
    [variant, setVariant, theme, setTheme, toggleTheme, toast, flash, hideToast],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useShell(): ShellState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useShell вызван вне ShellProvider');
  return ctx;
}
