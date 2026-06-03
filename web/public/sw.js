// WI13 — offline service worker (PRD AC-P3). Cache-first for *same-origin* GET requests, so
// after the first visit every static asset (HTML, JS, CSS, the Pyodide runtime + the engine
// zip) is served from the cache and the app works with no network. The worker makes no
// network requests of its own — it only intercepts and caches what the page already fetches
// (AC-P1/AC-P3: nothing off-origin, no telemetry).
/* eslint-disable no-undef */
const CACHE = "pds-cache-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  if (new URL(req.url).origin !== self.location.origin) return; // never touch off-origin
  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      const hit = await cache.match(req);
      if (hit) return hit;
      const resp = await fetch(req);
      if (resp.ok && resp.type === "basic") cache.put(req, resp.clone());
      return resp;
    })(),
  );
});
