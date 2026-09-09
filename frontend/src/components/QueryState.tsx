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
      <div className="empty" role="status" aria-live="polite">
        <div className="label">Загрузка</div>
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        kicker="Ошибка"
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
        kicker="Нет данных"
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
