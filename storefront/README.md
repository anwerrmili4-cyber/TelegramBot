# BlackMarket Tunisie — storefront

Public customer site for the Tunisian market: a Vite + React single-page app
that sells from the same live MongoDB catalog as the Telegram bot, in dinars,
with a multi-item cart, customer accounts and a dinar wallet. Customers pay from
their wallet or by D17/Flouci/IZI/Wafa Cash transfer with a receipt screenshot.

## Commands

```sh
npm install
npm run dev        # dev server on :5173, proxying /api/storefront to the backend
npm run build      # typecheck, then emit dist/
npm run preview    # serve the production build
npm run typecheck
```

## Talking to the backend

The app calls these endpoints on the Python server (`api/webhook.py`). Those
marked 🔒 need the `Authorization: Bearer <session>` header returned at login.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/storefront/catalog` | Services, offers, categories, payment methods and where to send money |
| `POST /api/storefront/auth/register`, `login`, `verify-email`, … | Account and session |
| 🔒 `POST /api/storefront/orders` | Create a cart paid by `wallet`, or by transfer with `transaction_reference` and `receipt` (image `data:` URL) |
| 🔒 `GET /api/storefront/auth/orders` | Purchase history, with the delivered access details |
| 🔒 `GET /api/storefront/auth/wallet` | Balance, ledger and deposit requests |
| 🔒 `POST /api/storefront/auth/deposits` | Wallet top-up: `method`, `amount`, `transaction_reference`, `receipt` |
| 🔒 `POST /api/storefront/auth/profile`, `password` | Account settings |
| `GET /api/storefront/cart?ref=&token=` | Cart status, authenticated by the tracking token |

`VITE_STOREFRONT_API_URL` selects the backend for a production build (see
`.env.example`). Leave it empty to call the same origin. In development the
value is ignored: requests stay same-origin and Vite proxies them to
`STOREFRONT_DEV_API_TARGET`, which defaults to `http://127.0.0.1:8080`.

## How the cart works

Only offer ids and quantities are persisted in `localStorage`. Names, prices and
stock are always re-read from the live catalog, so a cart reopened the next day
cannot check out at yesterday's price, and offers that went away or sold out
drop out of it on their own.

The backend stores the cart as **one order document per line**, grouped by a
shared `cart_reference` such as `TN-K4P7QX`. That keeps each line looking like a
bot sale to the admin dashboard, delivery and inventory, while the customer
deals with a single reference and a single payment.

A wallet payment is debited at once. A transfer payment waits in
`manual_review` until an administrator checks the receipt. Wallet deposits work
the same way: nothing is credited until the admin approves the request.

Once paid, each line is delivered from the bot's encrypted inventory when it has
stock. Lines without inventory wait for the admin to type the access details.
Either way the customer gets them by email and in their account.

## Layout

```
src/
  App.tsx              page composition and overlay state
  types.ts             API response shapes
  lib/api.ts           fetch wrappers and error normalisation
  lib/format.ts        dinar/millime money, phone rules, quantity clamping
  lib/motion.ts        View Transition and stagger helpers
  hooks/useCatalog.ts  catalog fetch, retry, ordering
  hooks/useCart.ts     persisted cart reconciled against the live catalog
  components/          header, hero, catalog, product detail, cart drawer, checkout, footer
  pages/               login, register, account (orders, wallet, profile)
  styles/              tokens, base, layout, catalog, overlay, motion
```

`styles/motion.css` holds every animation, so motion can be reviewed or removed
in one place. It uses scroll-driven reveals (`animation-timeline: view()`),
View Transitions for filtering, `@starting-style` for the mobile cart bar, and
an animated `@property` gradient in the hero — each behind a feature query or a
capability check, and all of it disabled under `prefers-reduced-motion`.
