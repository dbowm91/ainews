/* ainews service worker — offline support for the public site.
 *
 * Two rules matter here:
 *
 * 1. The cache name must change whenever the shipped CSS/JS changes.
 *    `self.__SW_VERSION` is injected by routes.public.feeds.service_worker
 *    from a fingerprint of the static tree, so a deploy that changes an
 *    asset produces a different worker script, a different cache name, and
 *    an activation that purges the stale cache.
 *
 * 2. Static assets are fetched network-first with the HTTP cache bypassed.
 *    A cache-first strategy pins every returning visitor to the assets they
 *    happened to load first, which is how a CSS change silently fails to
 *    reach the browser. The cache is still populated and still serves the
 *    site when the network is unavailable.
 */
var CACHE_NAME = 'ainews-' + (self.__SW_VERSION || 'dev');
var OFFLINE_URL = '/offline/';

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll([
        '/',
        OFFLINE_URL,
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

  /* An HTMX request for a URL returns a bare fragment, while the same URL
     returns a complete page for a normal navigation. Caching the fragment
     under the shared URL would hand the fragment to a later page load, so
     HTMX responses are never stored. */
  if (event.request.headers.get('HX-Request')) {
    return;
  }

  /* Network-first for static assets, with the cached copy as the offline
     fallback. `cache: 'reload'` bypasses the HTTP cache so a fresh copy of
     the asset is fetched (a 304 when it has not changed) instead of the
     browser's own long-lived copy. */
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      fetch(event.request, { cache: 'reload' }).then(function(response) {
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
          return new Response('', { status: 503, statusText: 'Service Unavailable' });
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
          return caches.match(OFFLINE_URL);
        }
        return new Response('', { status: 503, statusText: 'Service Unavailable' });
      });
    })
  );
});
