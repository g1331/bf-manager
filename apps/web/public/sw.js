/**
 * BF-Manager service worker：只做一件事——断网时打开页面，给出离线提示页，而不是浏览器报错页。
 *
 * 不缓存页面 HTML 和 /api/*：发版后不会看到旧页面，数据也永远是实时的。
 * 带哈希的静态资源已经由 Cloudflare 下发一年的浏览器缓存，这里不重复处理。
 * 以后做推送时，push / notificationclick 处理也加在这个文件里。
 */

// 改了 offline.html 就把版本号加一：sw.js 有变化浏览器才会重新安装、缓存新的离线页
const CACHE = "bfm-offline-v2";
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.add(OFFLINE_URL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // 导航预加载：service worker 启动的同时就发出页面请求，抵消拦截带来的延迟
      if (self.registration.navigationPreload) {
        await self.registration.navigationPreload.enable();
      }
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)));
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(
    (async () => {
      try {
        const preloaded = await event.preloadResponse;
        if (preloaded) return preloaded;
        return await fetch(event.request);
      } catch {
        const cached = await caches.match(OFFLINE_URL);
        return cached ?? Response.error();
      }
    })(),
  );
});
