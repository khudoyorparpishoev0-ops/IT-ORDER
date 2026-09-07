/**
 * HTTP-клиент. API отдаётся тем же origin через nginx, поэтому базовый
 * путь относительный и CORS не нужен.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') return body.detail;
    // Ошибки валидации FastAPI приходят списком — берём первое сообщение.
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      return String(body.detail[0].msg);
    }
  } catch {
    /* тело не JSON — покажем статус */
  }
  return `Ошибка ${response.status}`;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Собирает query-строку, пропуская пустые значения. */
export function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : '';
}
