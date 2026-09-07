/**
 * Скачивание файлов выгрузки.
 *
 * Через fetch, а не обычной ссылкой: ссылка не покажет ошибку прав или
 * истёкшей сессии — браузер просто откроет вкладку с JSON. Здесь ошибка
 * доходит до интерфейса, а имя файла берётся из заголовка сервера.
 */
import { ApiError, query } from './client';

/** Имя файла из Content-Disposition. Кириллица приходит в filename* (RFC 5987). */
function filenameFrom(header: string | null, fallback: string): string {
  if (!header) return fallback;

  const encoded = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      /* испорченное кодирование — берём запасное имя */
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1] : fallback;
}

export async function downloadFile(
  path: string,
  params: Record<string, string | number | boolean | undefined | null> = {},
  fallbackName = 'export',
): Promise<void> {
  const response = await fetch(path + query(params));
  if (!response.ok) {
    let detail = `Ошибка ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(response.status, detail);
  }

  const blob = await response.blob();
  const name = filenameFrom(response.headers.get('content-disposition'), fallbackName);

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();

  // Освободить блоб сразу нельзя: браузер ещё не начал его читать, и
  // скачивание срывается или теряет имя файла. Без revoke блоб держится
  // в памяти до перезагрузки страницы, поэтому чистим на следующем тике.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
