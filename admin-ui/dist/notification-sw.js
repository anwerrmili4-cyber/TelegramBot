/* Push-only worker: never caches private administration pages or API responses. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("push", (event) => {
  let payload = {};
  try { payload = event.data?.json() || {}; } catch { /* Still display every push. */ }
  event.waitUntil(self.registration.showNotification(payload.title || "Black Market", {
    body: payload.body || "Une nouvelle notification est disponible.",
    tag: payload.id || "blackmarket-update",
    icon: "/admin-v2/notification-icon-192.png",
    data: { url: payload.url || "/admin" },
  }));
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/admin", self.location.origin);
  if (url.origin !== self.location.origin || !/^\/admin(?:\/|$)/.test(url.pathname)) return;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const existing = windows.find((client) => new URL(client.url).origin === url.origin && /^\/admin(?:\/|$)/.test(new URL(client.url).pathname));
    if (existing) {
      await existing.navigate(url.href);
      await existing.focus();
    } else await self.clients.openWindow(url.href);
  })());
});
