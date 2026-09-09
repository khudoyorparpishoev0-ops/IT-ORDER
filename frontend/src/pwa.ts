/**
 * Установка панели на телефон (PWA).
 *
 * Здесь два дела, и оба должны случиться до монтирования React:
 *  1. регистрация service worker (только в сборке: dev-сервер Vite отдаёт
 *     модули иначе, и воркер там только мешал бы);
 *  2. перехват события `beforeinstallprompt` — Chrome на Android шлёт его
 *     один раз, сразу после загрузки, и если не поймать, кнопка
 *     «Установить на экран» в «Параметрах» останется без дела.
 *
 * Состояние отдаётся наружу маленьким хранилищем с подпиской — без
 * контекста и провайдера: единственный потребитель — карточка в
 * «Параметрах».
 */

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

export type InstallState = {
  /** Панель открыта как установленное приложение. */
  standalone: boolean;
  /** Браузер готов показать свой диалог установки (Chrome, Edge, Samsung). */
  canPrompt: boolean;
  /** iPhone или iPad: установка только через меню «Поделиться». */
  ios: boolean;
};

let prompt: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((fn) => fn());
}

function isStandalone(): boolean {
  try {
    return (
      window.matchMedia('(display-mode: standalone)').matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true
    );
  } catch {
    return false;
  }
}

function isIos(): boolean {
  const ua = navigator.userAgent;
  // iPadOS представляется как Mac, но у него есть тач-экран.
  return /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
}

// Снимок состояния кэшируется: useSyncExternalStore сравнивает результат
// по ссылке, и новый объект на каждый вызов означал бы бесконечный
// перерендер.
let snapshot: InstallState = { standalone: false, canPrompt: false, ios: false };

export function getInstallState(): InstallState {
  const next = { standalone: isStandalone(), canPrompt: prompt !== null, ios: isIos() };
  if (
    next.standalone !== snapshot.standalone ||
    next.canPrompt !== snapshot.canPrompt ||
    next.ios !== snapshot.ios
  ) {
    snapshot = next;
  }
  return snapshot;
}

export function subscribeInstall(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Показать диалог установки браузера. Возвращает, согласился ли человек. */
export async function promptInstall(): Promise<boolean> {
  if (!prompt) return false;
  const current = prompt;
  prompt = null;
  notify();
  await current.prompt();
  const choice = await current.userChoice;
  return choice.outcome === 'accepted';
}

export function setupPwa(): void {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    prompt = e as InstallPromptEvent;
    notify();
  });
  window.addEventListener('appinstalled', () => {
    prompt = null;
    notify();
  });
  try {
    window.matchMedia('(display-mode: standalone)').addEventListener('change', notify);
  } catch {
    /* старый браузер без addEventListener у MediaQueryList */
  }

  if (import.meta.env.PROD && 'serviceWorker' in navigator) {
    // После загрузки, а не сразу: регистрация не должна конкурировать с
    // первым запросом к API за скорость.
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js').catch((err) => {
        console.warn('Service worker не зарегистрирован', err);
      });
    });
  }
}
