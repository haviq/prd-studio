// Minimal service worker: network-first, cache fallback for shell assets.
var CACHE = 'prdstudio-v1';
var SHELL = ['/', '/studio', '/styles.css', '/logo.svg'];

self.addEventListener('install', function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(SHELL).catch(function(){}); }));
  self.skipWaiting();
});

self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.filter(function(k){ return k !== CACHE; }).map(function(k){ return caches.delete(k); }));
  }));
  self.clients.claim();
});

self.addEventListener('fetch', function(e){
  var req = e.request;
  if(req.method !== 'GET') return;
  var url = new URL(req.url);
  if(url.pathname.indexOf('/api/') === 0) return; // never cache API
  e.respondWith(
    fetch(req).then(function(res){
      var copy = res.clone();
      caches.open(CACHE).then(function(c){ c.put(req, copy).catch(function(){}); });
      return res;
    }).catch(function(){ return caches.match(req); })
  );
});
