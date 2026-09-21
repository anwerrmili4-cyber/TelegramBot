/* Push-only worker v3: never caches private administration pages or API responses. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("push", (event) => {
  let payload = {};
  try { payload = event.data?.json() || {}; } catch { /* Still display every push. */ }
  const proposed = payload.notification || payload;
  const options = { ...proposed };
  delete options.title;
  delete options.navigate;
  delete options.mutable;
  delete options.app_badge;
  options.body ||= "Une nouvelle notification est disponible.";
  options.tag ||= "blackmarket-update";
  options.icon ||= "/admin-v2/notification-icon-192.png";
  options.data = { ...(proposed.data || {}), url: proposed.data?.url || proposed.navigate || "/admin" };
  const tasks = [self.registration.showNotification(proposed.title || "Black Market", options)];
  if ("setAppBadge" in navigator) tasks.push(navigator.setAppBadge(1));
  event.waitUntil(Promise.all(tasks));
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
