# Manual D17 and Flouci payments

The Tunisian storefront accepts **D17** and **Flouci** as manual payment
methods. There is no payment-provider API integration and no automatic payment
confirmation in this flow.

## Customer flow

1. The backend creates the order in `pending_payment`.
2. The storefront calls `manual_payment_service.request_manual_review()` with
   `d17` or `flouci`.
3. The order moves to `manual_review` and the customer receives a prefilled
   WhatsApp link for **+216 21 994 132**.
4. The customer sends the payment receipt in WhatsApp.
5. An administrator checks the receipt and uses **Confirmer paiement** in the
   dashboard.
6. Only that administrator action marks the order as `payment_confirmed`.

Opening WhatsApp or returning to the website never marks an order as paid.

## Database

MongoDB is the only runtime database for this flow and remains shared with the
Telegram bot. Manual payment data is stored on the existing `orders` document:

- `payment_method`: `d17` or `flouci`
- `status`: `manual_review` until an administrator approves the receipt
- `verification_channel`: `whatsapp`
- `verification_recipient`: the configured digits-only WhatsApp number

The flow uses the project's existing PyMongo connection, audit log collection,
order status index, and atomic conditional updates. PostgreSQL and Prisma are
not used.

## Configuration

```env
HP_TN_WHATSAPP_NUMBER=21621994132
```

Use digits only, including Tunisia's country code. The default is already set
to `21621994132`, but production deployments should set the variable explicitly.

## Integration result

`request_manual_review(order_id, method)` returns the normalized payment method,
the `manual_review` status, the WhatsApp number, and the encoded `wa.me` URL.
Amounts are read from `total_millimes` (or the legacy
`tn_total_millimes`) and shown as DT with three decimal places.
