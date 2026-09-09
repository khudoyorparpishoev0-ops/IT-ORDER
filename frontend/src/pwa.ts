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

/* --- Push-уведомления --------------------------------------------------- */

export type PushSupport = 'ok' | 'unsupported' | 'ios-needs-install';

/**
 * Может ли этот браузер подписаться. На iPhone push работает только у
 * панели, поставленной на экран (iOS 16.4+): в Safari во вкладке
 * PushManager есть, но подписка не сработает — объясняем заранее.
 */
export function pushSupport(): PushSupport {
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    return 'unsupported';
  }
  if (isIos() && !isStandalone()) return 'ios-needs-install';
  return 'ok';
}

export function pushPermission(): NotificationPermission | 'unsupported' {
  return 'Notification' in window ? Notification.permission : 'unsupported';
}

function toKey(base64url: string): Uint8Array {
  const padded = base64url + '='.repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

/** Текущая подписка этого браузера, если есть. */
export async function currentPushSubscription(): Promise<PushSubscription | null> {
  if (pushSupport() === 'unsupported') return null;
  const registration = await navigator.serviceWorker.ready;
  return registration.pushManager.getSubscription();
}

/**
 * Подписывает браузер. Спрашивает разрешение, если ещё не спрашивали;
 * возвращает null, если человек отказал.
 */
export async function subscribePush(publicKey: string): Promise<PushSubscription | null> {
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return null;
  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  if (existing) return existing;
  return registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: toKey(publicKey),
  });
}

export async function unsubscribePush(): Promise<string | null> {
  const existing = await currentPushSubscription();
  if (!existing) return null;
  const endpoint = existing.endpoint;
  await existing.unsubscribe();
  return endpoint;
}

/** Подписка в виде, который принимает сервер. */
export function subscriptionPayload(sub: PushSubscription): {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  user_agent: string;
} {
  const json = sub.toJSON();
  return {
    endpoint: sub.endpoint,
    keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
    user_agent: navigator.userAgent.slice(0, 200),
  };
}
