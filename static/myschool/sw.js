// Safer minimal SW: production only (we register it only in PROD). Network-first with offline fallback.
const CACHE = 'myschool-v1';
const CORE = ['.', 'index.html'];


self.addEventListener('install', (event) => {
event.waitUntil((async () => {
const cache = await caches.open(CACHE);
await cache.addAll(CORE);
self.skipWaiting();
})());
});


self.addEventListener('activate', (event) => {
event.waitUntil((async () => {
const keys = await caches.keys();
await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
self.clients.claim();
})());
});


self.addEventListener('fetch', (event) => {
// Ignore dev server and Vite client URLs just in case this is ever active in dev
const url = new URL(event.request.url);
if (url.pathname.startsWith('/@vite') || url.searchParams.has('vite')) return;


event.respondWith((async () => {
try {
const res = await fetch(event.request);
const cache = await caches.open(CACHE);
cache.put(event.request, res.clone());
return res;
} catch (err) {
const cached = await caches.match(event.request);
if (cached) return cached;
if (event.request.mode === 'navigate') {
return caches.match('index.html');
}
throw err;
}
})());
});
