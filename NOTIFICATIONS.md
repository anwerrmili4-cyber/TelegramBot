# Admin notifications

The React dashboard refreshes the operational notification feed every five seconds while visible, on focus and after reconnection. Read state is shared in MongoDB for the single admin account. Device subscriptions and preferences also persist across application restarts.

The Railway entrypoint starts a background worker that checks a persistent MongoDB notification outbox every five seconds and delivers Web Push even when the dashboard is closed. Alert-producing writes snapshot the complete operational alert set into the outbox when an alert appears, so a state transition completed between worker runs remains eligible for delivery. The worker also reconciles the bounded dashboard feed for alerts that remain active. Browser/OS policies and network availability affect delivery.

## Deploy and activate

1. Install the updated `requirements.txt`, build `admin-ui` with `npm ci` and `npm run build`, and run `railway_server.py` (the existing Docker build performs these steps).
2. Serve the private admin origin over HTTPS. Preserve MongoDB: a VAPID key pair is generated once and stored in `admin_notification_config`. No private key is sent to the browser. Losing this record requires re-enrolling devices.
3. Optionally set `HP_WEB_PUSH_SUBJECT` to an operator contact such as `mailto:admin@example.com`. Otherwise the existing public base URL is used as the VAPID subject.
4. On **each** phone/PC, sign into the admin site, open the bell → “Notifications sur cet appareil” → “Activer sur cet appareil”, then accept the browser permission.
5. Press “Envoyer un test”. The UI reports acceptance by the push provider, not proof that the OS displayed the notification. Verify the actual notification on that device, including with the dashboard closed; clicking it should open the corresponding admin page, requiring login if the session expired.

On iPhone/iPad with iOS 16.4+, add the site to the Home Screen using Safari and activate notifications from that installed app. Android and desktop require a browser with Web Push support. Unsupported environments receive instructions rather than a false “enabled” status.

On iPhone, opening the dashboard in a normal Safari tab is not enough: Web Push runs only from the Home Screen web app. The activation screen now preloads the service worker and VAPID key so `pushManager.subscribe()` runs directly from the user tap, as required by WebKit. Push payloads use Declarative Web Push on iOS/iPadOS 18.4+ and retain the service-worker fallback for iOS 16.4–18.3 and other browsers. Reopen the Home Screen app after a deployment so it installs the newest service worker; if iOS still shows an old denied subscription, disable notifications in the dashboard, remove the Home Screen app, add it again, then activate and send a test.

## Behavior

- New enrollment seeds existing alerts without pushing the entire backlog.
- Category filters, critical-only mode, private lock-screen text and pauses of 1/8/24 hours apply per device. Paused/filtered events are skipped, not replayed when resumed.
- Successful deliveries and skipped alerts are recorded per device in MongoDB. A crash between provider acceptance and persistence may retry; stable notification tags replace duplicate OS entries.
- Temporary failures are retried from the outbox even after the alert leaves the live feed. HTTP 404/410 subscriptions are removed. A per-device lease prevents concurrent replicas from sending the same batch. At most five notifications per device are sent per worker run. Outbox entries and delivery records are retained for 30 days.
- Changing the dashboard password invalidates delivery to existing subscriptions until they are explicitly enabled again. Signing out alone leaves opted-in push active; use “Désactiver” before leaving a shared device. Private lock-screen text is the default.
- Read markers expire after 30 days. Push routes require admin authentication; mutations additionally require the dashboard write token. Push endpoints are restricted to supported browser providers, redirects are disabled, and no private dashboard data is cached by the service worker.

## Validation

Automated tests cover two-device fan-out, persistent deduplication, retry, alerts created and resolved between worker runs, pause/category/critical filters, expired subscriptions, key persistence, password rotation, shared read state, authentication and write protection. Physical phone/PC receipt requires the activation procedure above.

References: [MDN Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API), [Apple Web Push](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers).
