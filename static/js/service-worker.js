const CACHE_NAME = 'smartvision-v1.0.0';
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/manifest.json',
    '/static/img/icons/icon-192.png',
    '/static/img/icons/icon-512.png',
    '/static/img/icons/icon-maskable.png'
];

// Install: Cache core static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS).catch((err) => {
                console.warn('[SW] Cache addAll warning:', err);
            });
        })
    );
    self.skipWaiting();
});

// Activate: Clean up old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

// Fetch: Network First with cache fallback for HTML, Cache First for static assets
self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);

    // Bypass video stream and API POST requests from caching
    if (url.pathname.startsWith('/video_feed') || request.method !== 'GET') {
        return;
    }

    // Static Assets: Cache First
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request).then((cached) => {
                return cached || fetch(request).then((response) => {
                    if (response.status === 200) {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then((c) => c.put(request, copy));
                    }
                    return response;
                });
            })
        );
        return;
    }

    // HTML / Dynamic routes: Network First, fallback to cached
    event.respondWith(
        fetch(request)
            .then((response) => {
                if (response.status === 200) {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((c) => c.put(request, copy));
                }
                return response;
            })
            .catch(() => {
                return caches.match(request).then((cached) => {
                    if (cached) return cached;
                    // Generic offline fallback response
                    return new Response(
                        `<!DOCTYPE html>
                        <html lang="en">
                        <head>
                            <meta charset="utf-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1">
                            <title>Offline | SmartVision Idea Lab</title>
                            <link rel="stylesheet" href="/static/css/style.css">
                        </head>
                        <body style="background:#ffffff; color:#0f172a; text-align:center; padding:60px 20px; font-family:sans-serif;">
                            <div style="max-width:480px; margin:0 auto; padding:30px; border:1px solid #e2e8f0; border-radius:20px; box-shadow:0 4px 12px rgba(0,0,0,0.05);">
                                <div style="font-size:48px; color:#ff4d4f; margin-bottom:16px;">📶</div>
                                <h2 style="margin:0 0 8px 0; font-weight:700;">You are currently offline</h2>
                                <p style="color:#64748b; font-size:14px; margin-bottom:24px;">SmartVision DigiCampus requires an active network connection to sync live biometric attendance.</p>
                                <button onclick="location.reload()" style="background:#ff4d4f; color:#ffffff; border:none; padding:10px 24px; border-radius:12px; font-weight:600; cursor:pointer;">Retry Connection</button>
                            </div>
                        </body>
                        </html>`,
                        { headers: { 'Content-Type': 'text/html' } }
                    );
                });
            })
    );
});
