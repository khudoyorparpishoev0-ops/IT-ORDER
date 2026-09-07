import { useState } from 'react';
import { downloadFile } from '@/api/download';
import { useShell } from '@/shell/ShellContext';

/**
 * Скачивание с блокировкой кнопки и тостом об ошибке.
 * Без этого повторные нажатия запускают выгрузку по нескольку раз,
 * а отказ по правам проходит незамеченным.
 */
export function useDownload() {
  const { flash } = useShell();
  const [busy, setBusy] = useState<string | null>(null);

  const download = async (
    key: string,
    path: string,
    params?: Record<string, string | number | boolean | undefined | null>,
    fallbackName?: string,
  ) => {
    if (busy) return;
    setBusy(key);
    try {
      await downloadFile(path, params, fallbackName);
    } catch (error) {
      flash(
        error instanceof Error ? error.message : 'Не удалось выгрузить файл',
        'var(--dot-err)',
      );
    } finally {
      setBusy(null);
    }
  };

  return { download, busy };
}
