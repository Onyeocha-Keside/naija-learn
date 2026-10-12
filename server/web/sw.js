var CACHE = 'naija-learn-shell-v2';
var SHELL = ['/', '/static/style.css', '/static/app.js', '/static/manifest.json', '/static/icon.svg', '/static/icon-192.png', '/static/icon-512.png', '/lessons', '/lessons/fractions', '/lessons/plants', '/lessons/verbs'];
self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(CACHE).then(function (cache) { return cache.addAll(SHELL); }));
});
self.addEventListener('activate', function (event) {
  event.waitUntil(caches.keys().then(function (keys) { return Promise.all(keys.filter(function (key) { return key.indexOf('naija-learn-shell-') === 0 && key !== CACHE; }).map(function (key) { return caches.delete(key); })); }).then(function () { return self.clients.claim(); }));
});
self.addEventListener('fetch', function (event) {
  var url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || SHELL.indexOf(url.pathname) === -1) { return; }
  event.respondWith(fetch(event.request).then(function (response) {
    if (response.ok) { var copy = response.clone(); event.waitUntil(caches.open(CACHE).then(function (cache) { return cache.put(event.request, copy); })); }
    return response;
  }).catch(function () { return caches.match(event.request); }));
});
