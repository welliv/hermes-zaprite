# Paid loop — one continuous scene

Copy this path when teaching an agent or filming `DEMO.md`. Every rail that is already connected on the org shows on one `checkoutUrl`. Telegram is not required. The webhook body is never the receipt.

## Setup (human, once)

Org + rails + `ZAPRITE_API_KEY` in Hermes. Then:

```text
/zaprite doctor
```

Expect `key_mode: full`. `connections_api` is always false.

## Merchant intent

```text
Invoice Northwind 1280 USD for the March retainer. Card, bank, Lightning, or on-chain bitcoin.
```

## Tools the agent runs

1. `zaprite_create_contact` — `legal_name`, `email` (cron-blocked; no money gate).
2. `zaprite_create_invoice` — line items + `contact_id` + `external_uniq_id`. Hermes shows Approve. Cron refuses.
3. Say `session_notice` in this chat. Hand the payer `checkoutUrl`.
4. `zaprite_watch_order` — re-fetches until `PAID` / `OVERPAID` / `COMPLETE`, or timeout. Call again to keep waiting. Trust this JSON, not a webhook.
5. Deliver. `zaprite_update_order` with `status` `COMPLETE` after a second Approve.

Optional in-chat bitcoin: `zaprite_create_quote` with `LIGHTNING` or `BITCOIN` → show `paymentUrl`. Do not pay it yourself.

## Shape of a create response

```json
{
  "ok": true,
  "id": "od_…",
  "status": "PENDING",
  "checkoutUrl": "https://pay.zaprite.com/order/od_…",
  "rails": "The checkout shows only rails already connected…",
  "webhook": "Zaprite webhooks are id-only and unsigned…",
  "session_notice": "Checkout is ready for 1280.00 USD. Send https://pay.zaprite.com/order/od_… to the payer. …",
  "telegram_required": false,
  "next": "Send checkoutUrl to the payer. Call zaprite_watch_order to wait for Paid."
}
```

Amounts are integers in the smallest unit: `128000` USD is $1,280.00. Bitcoin is sats. `send_receipt` defaults to false in this plugin.

## Ten-second closer (after Paid)

```text
If another agent wants to pay us in bitcoin?
```

Answer from `zaprite_sovereign_rails`: Lightning Address or xpub already connected → `zaprite_create_quote` → they pay `paymentUrl` only if a person asked them to. Stop. Do not open Connections. Do not lead with tickets.

## Fail closed

| Signal | Meaning |
| --- | --- |
| Hermes Approve prompt | `{"action":"approve"}` escalated. A person still decides. |
| `UNATTENDED` | Cron or nobody to approve. Stop. Digest may only report/overdue. |
| `READ_ONLY_KEY` | Reports work. Creates do not. |
| `SPEND_LIMIT` | Cap hit before HTTP. Do not split to hide the total. |

## Do not invent

Connections list, branding read/write (logo and accent color are Settings → Profile, gap `branding_profile`), checkout write, payment-link create, recurring create, event create, refund, webhook signature. See `docs/api-gaps.md`.
