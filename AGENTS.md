# Agents integrating Zaprite

Use this when you are writing an app that charges through Zaprite, or when you are Hermes using the plugin in this repo.

## Receive money

1. A person already created the org, connected rails, and issued `ZAPRITE_API_KEY`.
2. `POST https://api.zaprite.com/v1/orders` with `Authorization: Bearer <key>`.
3. Required: `currency`. Amount is an integer in the smallest unit (`128000` USD = 1280.00). Or send `invoice.lineItems` plus `contactId` and let Zaprite sum the invoice.
4. Redirect the payer to `checkoutUrl`. Do not rebuild checkout.
5. Persist `id` and your `externalUniqId`. That field is the only idempotency key on order create.

Official reference: https://api.zaprite.com/llms.txt and https://api.zaprite.com/openapi.json. SDK: `@zaprite/api`.

## Webhooks

Subscribe with `POST /v1/webhooks` (`url`, `label` only) if you have your own HTTPS endpoint. The body is ids, for example `{eventType, orderId, orgId}`. There is no signing secret.

On every delivery:

1. Read `orderId`.
2. `GET /v1/orders/{orderId}` with the API key.
3. Fulfill only when that order's `status` is `PAID`, `OVERPAID`, or `COMPLETE` (or the invoice status is `PAID` or `OVERPAID`).
4. Return 200 quickly. Zaprite retries non-200 and may disable the endpoint.
5. Make the handler idempotent. The same id will arrive more than once.

Do not treat the webhook JSON as the payment.

## Rails

Only rails connected on the org appear. You cannot list connections. A contact's `paymentProfiles[].connection.pluginSlug` is the only hint, and only after a customer has saved a method.

`POST /v1/orders/create-quote` returns Lightning or on-chain (`paymentUrl`). Card, bank, and stablecoins stay on `checkoutUrl`.

Pass `customCheckoutId` only if a person already created that checkout. You cannot create one, and you cannot set a Lightning discount from the API.

## Do not call

These routes are not in the public API. Do not guess them.

- Connections list, create, or test
- Branding read or write (logo, accent color, display name). Settings → Profile. Invoices inherit it.
- Checkout create or update
- Payment link create (GET list/get exist), product, event, or POS create
- Recurring invoice create
- Invoice send or void
- Refunds
- Webhook signatures

`docs/api-gaps.md` is the same list with the reason.

## Hermes plugin

If this process is a Hermes session, do not hand-roll `httpx`. Call the `zaprite_*` tools. They enforce approval, the spend cap, read-only keys, and the re-fetch watcher. Skills: `skill_view("zaprite:zaprite")` (context-first Paid loop), `zaprite-checkout-wizard` (site), `zaprite-sovereign` (closer).

## Money safety

- Default receipts off unless a person asked for email.
- Do not charge a saved profile unless they named that customer and that charge.
- Do not mark an order `PAID` to skip a real payment. `COMPLETE` is for after you deliver.
- Sandbox orgs exist so the first run does not move money.
