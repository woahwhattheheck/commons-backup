"use strict";
var CACHE = "commons-agent-ops-20260827a";
var SHELL = ["./agent-ops.html", "./agent-ops.js", "./agent-ops.webmanifest"];
self.addEventListener("install", function (event) { event.waitUntil(caches.open(CACHE).then(function (cache) { return cache.addAll(SHELL); })); });
self.addEventListener("activate", function (event) { event.waitUntil(caches.keys().then(function (keys) { return Promise.all(keys.filter(function (key) { return key.indexOf("commons-agent-ops-") === 0 && key !== CACHE; }).map(function (key) { return caches.delete(key); })); })); });
self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (/\/(lastseen|claims|wakeups|recent|agent-ops-checkout)\.json$/.test(url.pathname)) { event.respondWith(fetch(event.request, { cache: "no-store" })); return; }
  event.respondWith(fetch(event.request).catch(function () { return caches.match(event.request); }));
});
