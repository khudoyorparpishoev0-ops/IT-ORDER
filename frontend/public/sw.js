/* Service worker панели HONA ORDER.
 *
 * Задача одна: панель, поставленная на экран телефона, должна открываться
 * и при обрыве связи показывать понятную заглушку, а не серую ошибку
 * браузера. Данные не кэшируются никогда: заявки и решения по ним живут
 * только на сервере, устаревшая копия здесь хуже отсутствующей.
 *
 * Стратегии:
 *  - переходы (навигация) — сеть, при отказе offline.html;
 *  - /assets/ — кэш, при промахе сеть (имена файлов хэшированы, содержимое
 *    неизменяемо);
 *  - /api/, /health — только сеть, воркер их не трогает.
 *
 * Версия кэша меняется с каждой сборкой: старый кэш удаляется при
 * активации, чтобы после обновления сервера не смешивались ассеты двух
 * версий.
 */
const VERSION = '__BUILD_VERSION__';
const STATIC = 'hona-static-' + VERSION;
const OFFLINE_URL = '/offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(STATIC)
      .then((cache) => cache.addAll([OFFLINE_URL, '/manifest.webmanifest', '/icons/order-192.png']))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== STATIC).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname === '/health') return;

  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/')) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(STATIC).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
  }
});

/* Push-уведомления. Сервер шлёт JSON: { title, body, url }. */
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'HONA ORDER';
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || '',
      icon: '/icons/order-192.png',
      badge: '/icons/order-192.png',
      tag: data.tag || undefined,
      data: { url: data.url || '/' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || '/', self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if ('focus' in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
