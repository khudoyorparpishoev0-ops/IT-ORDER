import { useSyncExternalStore } from 'react';

/**
 * Признак «сессия истекла».
 *
 * Раньше 401 в середине работы просто подменял экран на форму входа:
 * заполненная карточка исчезала, и выглядело это как «окно само
 * закрылось, ничего не сохранилось». Теперь панель говорит, что
 * произошло, и человек знает, что данные придётся ввести заново.
 */
let expired = false;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function markSessionExpired(): void {
  if (expired) return;
  expired = true;
  emit();
}

export function clearSessionExpired(): void {
  if (!expired) return;
  expired = false;
  emit();
}

export function useSessionExpired(): boolean {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => expired,
    () => false,
  );
}
