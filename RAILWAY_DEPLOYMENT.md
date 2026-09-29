# Railway deployment

The production service runs three isolated HTTP surfaces in one Railway service,
each reachable on its own domain:

| Surface | Port | Serves |
| --- | --- | --- |
| Public bot | Railway's injected `PORT` (locally 8080) | Telegram landing page, webhook, operational endpoints |
| Admin | `ADMIN_PORT` (8081) | Dashboard and operational API |
| Tunisian storefront | `STOREFRONT_PORT` (8082) | The customer site plus `/api/storefront/*` only |

Telegram webhook, buyer API, restock checks, and supplier price checks remain in
the same process.

The storefront surface deliberately exposes nothing else: the webhook, buyer
API, cron endpoints and dashboard all return 404 there. Because it answers
`/api/storefront/*` on its own domain, the site is same-origin with its API and
needs no CORS and no API base URL.

## 1. Generate the public domain

In the Railway service, open **Settings > Networking > Public Networking** and
select **Generate Domain**. The application automatically reads Railway's
`RAILWAY_PUBLIC_DOMAIN`; `HP_PUBLIC_BASE_URL` can remain unset.

Configure three target ports under **Settings > Networking > Public Networking**:

1. Public bot domain → target port shown by `PORT`.
2. Admin domain → target port `8081` (or the value of `ADMIN_PORT`).
3. Storefront domain → target port `8082` (or the value of `STOREFRONT_PORT`).

### Pointing a custom domain at the storefront

Add the domain under **Custom Domain** and set its target port to
`STOREFRONT_PORT`. Railway then shows a CNAME target such as
`abc123.up.railway.app`; create that record at your DNS provider:

- A subdomain (`shop.example.com`) is a plain `CNAME` record.
- An apex domain (`example.com`) cannot use a plain CNAME. The DNS provider must
  support `ALIAS`/`ANAME` records or CNAME flattening — Cloudflare's free tier
  does this. Otherwise point `www` at Railway and redirect the apex to it.

Railway issues the TLS certificate automatically once the record resolves. If
the provider proxies traffic (Cloudflare orange cloud), keep SSL mode on
**Full** so it does not conflict with Railway's certificate.

Set `HP_ADMIN_BASE_URL=https://YOUR-ADMIN-DOMAIN` so an accidental `/admin`
visit on the public domain redirects to the isolated dashboard. Set
`HP_PUBLIC_BASE_URL` to the public domain that should receive Telegram's
`/api/webhook`; both HTTP surfaces support that endpoint.

## 2. Configure variables

Copy the real values from the previous production environment. Never use the
literal value `[SENSITIVE]`.

Required variables:

- `HP_BOT_TOKEN`
- `HP_ADMIN_ID`
- `HP_MONGODB_URI`
- `HP_MONGODB_DB=heavenprem`
- `HP_WEBHOOK_SECRET` (letters, numbers, `_` and `-` only)
- `CRON_SECRET` (a different random value, at least 24 characters)
- `HP_DASHBOARD_PASSWORD`
- `ADMIN_PORT=8081`
- `STOREFRONT_PORT=8082`
- `HP_ADMIN_BASE_URL=https://YOUR-ADMIN-DOMAIN`
- `HP_INVENTORY_KEY` when encrypted inventory is enabled
- Provider API keys used by the active catalog
- `HP_REQUIRED_CHANNEL=@blackmarketBotChannel`
- `HP_BOT_USERNAME=blackmarketa_bot`

Generate independent webhook and cron secrets locally with PowerShell:

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLower()
```

Run the command twice and store the two different results in Railway. Do not
commit either result.

## 3. Deploy

`railway.json` builds the root `Dockerfile`, starts `python railway_server.py`,
checks `/health`, binds to Railway's injected `PORT`, and keeps one European
replica. The `.dockerignore` file keeps local caches, secrets, Git history, and
development-only files out of the image build context. On startup, the
service registers `${RAILWAY_PUBLIC_DOMAIN}/api/webhook` with Telegram.

`Dockerfile` builds both front-ends before the Python image: `admin-ui/dist` for
the dashboard and `storefront/dist` for the customer site.

After deployment, confirm:

- `https://YOUR-PUBLIC-DOMAIN/health` returns `{"ok": true, ...}`.
- `https://YOUR-PUBLIC-DOMAIN/` opens the public bot landing page.
- `https://YOUR-PUBLIC-DOMAIN/admin` redirects to the admin domain.
- `https://YOUR-ADMIN-DOMAIN/` redirects to `/admin`.
- `https://YOUR-ADMIN-DOMAIN/admin` requests the dashboard password.
- `https://YOUR-STOREFRONT-DOMAIN/` opens the Tunisian customer site.
- `https://YOUR-STOREFRONT-DOMAIN/api/storefront/catalog` returns the catalog.
- `https://YOUR-STOREFRONT-DOMAIN/admin` returns 404.
- Railway logs contain `Telegram webhook registered`.

The process runs its own restock and supplier-price scheduler, replacing the
two Vercel cron entries. Keep exactly one Railway replica to prevent duplicate
scheduled announcements.
