# API gaps

Zaprite's public API is the contract. This plugin wraps it. The items below are not implemented on `api.zaprite.com` as of the OpenAPI this repo was written against (`https://api.zaprite.com/openapi.json`, API v1). Do not call guessed paths. Do not scrape the dashboard to fake them.

| Missing write | What to do instead |
| --- | --- |
| List, add, or test a connection (card processor, bank, Lightning, xpub, Lightning Address, BTCPay, and the rest) | A person uses Connections in the dashboard. Checkout then shows that rail. |
| Create or edit a checkout, including a bitcoin or Lightning discount | A person edits the checkout. Copy `customCheckoutId` into `zaprite_create_order`. Or `zaprite_bridge_handoff`. |
| Create a payment link, product, POS terminal, event, or ticket type | A person creates it. The plugin can list links and tickets, issue comps, and check in. |
| Send, void, or draft an invoice as its own object | `POST /v1/orders` with `invoice` and `contactId`. Share `checkoutUrl`. OVERDUE is a status on the order, not an email endpoint. |
| Create a recurring invoice or a payment request | Dashboard. |
| Refund | Not in the API. The merchant handles it with the processor or by sending bitcoin back themselves. |
| Webhook signing secret, per-event filter, or test ping | Re-fetch `GET /v1/orders/{id}`. Treat the webhook as a nudge that carries ids only. Creating or deleting a URL+label endpoint is in the API (`zaprite_create_webhook`, `zaprite_delete_webhook`); this plugin still does not receive those posts. |
| Org, team, branding (logo, accent color, display name), API-key create | A person, once, in the dashboard. Branding is Settings → Profile. API invoices and checkouts inherit it. `zaprite_bridge_handoff` gap `branding_profile`. There is no branding HTTP API. |
| Reports export | `zaprite_report` is the first page of orders plus a count. It is not accounting. |

If Zaprite adds any of these, this plugin should grow a typed tool and a disclosure line in the same change. Until then, doctor says "no connections API" out loud.
