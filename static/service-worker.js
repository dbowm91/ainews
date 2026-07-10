/* Service worker for ainews PWA — cache-first strategy with offline fallback. */
var CACHE_NAME = 'ainews-' + (self.__SW_VERSION || 'dev');
var OFFLINE_URL = '/offline/';

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll([
        '/',
        '/offline/',
      ]);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.filter(function(name) {
          return name !== CACHE_NAME;
        }).map(function(name) {
          return caches.delete(name);
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(event) {
  if (event.request.method !== 'GET') return;

  var url = new URL(event.request.url);

  /* Bypass for API endpoints, HTMX requests, and dynamic paths */
  if (url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/admin/') ||
      url.pathname.startsWith('/hx-') ||
      url.pathname.includes('.json') ||
      url.searchParams.has('hx-current-url')) {
    return;
  }

  /* Cache-first for static assets */
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(function(cached) {
        if (cached) return cached;
        return fetch(event.request).then(function(response) {
          if (response && response.status === 200) {
            var clone = response.clone();
            caches.open(CACHE_NAME).then(function(cache) {
              cache.put(event.request, clone);
            });
          }
          return response;
        }).catch(function() {
          return caches.match('/offline/');
        });
      })
    );
    return;
  }

  /* Network-first for page navigations, with offline fallback */
  event.respondWith(
    fetch(event.request).then(function(response) {
      if (response && response.status === 200) {
        var clone = response.clone();
        caches.open(CACHE_NAME).then(function(cache) {
          cache.put(event.request, clone);
        });
      }
      return response;
    }).catch(function() {
      return caches.match(event.request).then(function(cached) {
        if (cached) return cached;
        /* Return offline page for navigation requests */
        if (event.request.mode === 'navigate') {
          return caches.match('/offline/');
        }
        return new Response('', { status: 503, statusText: 'Service Unavailable' });
      });
    })
  );
});