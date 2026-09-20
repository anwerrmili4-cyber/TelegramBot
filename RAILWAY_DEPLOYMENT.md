# Railway deployment

The production service runs two isolated HTTP surfaces in one Railway service:

- Public landing page, Telegram webhook, and operational endpoints on Railway's injected `PORT` (default locally: 8080)
- Admin dashboard and operational endpoints on `ADMIN_PORT` (default: 8081)

Telegram webhook, buyer API, restock checks, and supplier price checks remain in
the same process.

## 1. Generate the public domain

In the Railway service, open **Settings > Networking > Public Networking** and
select **Generate Domain**. The application automatically reads Railway's
`RAILWAY_PUBLIC_DOMAIN`; `HP_PUBLIC_BASE_URL` can remain unset.

Configure two target ports under **Settings > Networking > Public Networking**:

1. Public bot domain → target port shown by `PORT`.
2. Admin domain → target port `8081` (or the value of `ADMIN_PORT`).

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

After deployment, confirm:

- `https://YOUR-PUBLIC-DOMAIN/health` returns `{"ok": true, ...}`.
- `https://YOUR-PUBLIC-DOMAIN/` opens the public bot landing page.
- `https://YOUR-PUBLIC-DOMAIN/admin` redirects to the admin domain.
- `https://YOUR-ADMIN-DOMAIN/` redirects to `/admin`.
- `https://YOUR-ADMIN-DOMAIN/admin` requests the dashboard password.
- Railway logs contain `Telegram webhook registered`.

The process runs its own restock and supplier-price scheduler, replacing the
two Vercel cron entries. Keep exactly one Railway replica to prevent duplicate
scheduled announcements.
