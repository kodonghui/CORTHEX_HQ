// CORTHEX HQ — Service Worker (PWA 오프라인 셸)
const CACHE_NAME = 'corthex-hq-v1';
const SHELL_ASSETS = [
  '/',
  '/static/css/corthex-styles.css',
  '/static/js/corthex-app.js',
  '/static/images/corthex-logo-512.png',
  '/static/images/corthex-logo-256.png'
];

// Install — 기본 셸 캐시
self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activate — 오래된 캐시 제거
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch — 네트워크 우선, 실패 시 캐시
self.addEventListener('fetch', (e) => {
  // API 요청은 항상 네트워크 (캐시 안 함)
  if (e.request.url.includes('/api/') || e.request.url.includes('/ws')) return;

  e.respondWith(
    fetch(e.request)
      .then(res => {
        // 정적 리소스만 캐시 업데이트
        if (res.ok && e.request.url.includes('/static/')) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
