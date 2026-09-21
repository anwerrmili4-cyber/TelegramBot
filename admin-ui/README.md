# React admin dashboard

The React dashboard is the mobile-first administration interface. The Python
application serves its production build at `/admin` and exposes the secured
JSON and form-action endpoints used by every React page. The former
server-rendered interface is retained only as an emergency fallback at
`/admin-legacy`.

## Development

```powershell
npm install
npm run dev
```

Vite proxies `/admin/api` and POST `/admin` to `http://localhost:8080`.
Start the Python server on that port, open the Vite origin at `/admin`,
and authenticate there. GET `/admin` and section deep links serve React.

## Production build

```powershell
npm run build
```

The generated `dist` directory is committed because the Railway Python runtime
serves those static files directly and does not require Node.js at startup.

## Control Room

- `/admin/control-center`: priorities, local favorites and read-only connection diagnostics.
- `/admin/phone`: touch-oriented controls and iPhone home-screen guidance.
- `/admin/data-explorer`: server-filtered orders, customers, masked inventory,
  tickets and deposits; pagination; one locally saved resource/status view;
  CSV export of the displayed page only. Exports use explicit field allowlists
  and neutralize spreadsheet formulas. Record mutations remain in existing
  domain-specific pages, using existing secured handlers.
- The overview revenue chart uses the existing orders analytics endpoint,
  with UTC dates and revenue assigned to order creation dates.
- Mobile navigation, safe-area padding, 16px form inputs, cards for orders,
  native modal dialogs and reduced-motion support are included. No offline
  financial actions or administrative response caching are implemented.

## Validation

Run `npm test` for CSV/session behavior and the Vite proxy integration test.
From the repository root, run:

```powershell
python -m pytest tests/test_dashboard_api.py tests/test_webhook_http.py tests/test_railway_server.py -q
```

The isolated preview helper `outputs/admin-redesign/preview_connected.py`
serves this production build on loopback port 8770 with synthetic data.
It imports neither the bot nor the database and rejects every POST.
This preview is not the authenticated production server.

Responsive browser checks are not a substitute for physical-device Safari
acceptance testing. Check keyboard visibility, safe areas, CSV downloads,
session expiry and home-screen launching on the target iPhone before release.
