import type { ReactNode } from 'react';
import { EmptyState } from './EmptyState';

type Props = {
  isLoading: boolean;
  error: unknown;
  /** true — данных нет, показываем пустое состояние вместо контента. */
  isEmpty?: boolean;
  emptyTitle?: string;
  emptyNote?: string;
  emptyAction?: ReactNode;
  onRetry?: () => void;
  children: ReactNode;
};

/**
 * Единая обёртка загрузки, ошибки и пустоты. Без неё каждая страница
 * рисует эти три состояния по-своему, и они расходятся.
 */
export function QueryState({
  isLoading,
  error,
  isEmpty = false,
  emptyTitle = 'Данных пока нет',
  emptyNote,
  emptyAction,
  onRetry,
  children,
}: Props) {
  if (isLoading) {
    return (
      <div
        className="hatch"
        style={{
          padding: '48px var(--pad)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--r-card)',
          background: 'var(--paper)',
          textAlign: 'center',
        }}
        role="status"
        aria-live="polite"
      >
        <div className="label">ЗАГРУЗКА</div>
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        kicker="ОШИБКА"
        title={errorText(error)}
        note="Проверьте, что сервер запущен. Если ошибка повторяется, обратитесь к администратору."
        action={
          onRetry && (
            <button type="button" className="btn btn-secondary" onClick={onRetry}>
              Повторить
            </button>
          )
        }
      />
    );
  }

  if (isEmpty) {
    return (
      <EmptyState
        kicker="НЕТ ДАННЫХ"
        title={emptyTitle}
        note={emptyNote}
        action={emptyAction}
      />
    );
  }

  return <>{children}</>;
}

export function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return 'Не удалось загрузить данные';
}
