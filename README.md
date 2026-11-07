# Zaprite for Hermes

Take payments from a chat. One link for every rail the merchant's Zaprite account already connected — card, bank, bitcoin, Lightning, stablecoins — and the agent keeps checking until the money is actually there.

[![The 48-second demo: a live shop, a $1 payment, and the approval gate before any write](docs/demo-poster.png)](https://github.com/welliv/hermes-zaprite/releases/download/demo-v1/zaprite-demo.mp4)

▶ **[48-second demo](https://github.com/welliv/hermes-zaprite/releases/download/demo-v1/zaprite-demo.mp4)** — a real storefront, a real $1 checkout across six rails, then the agent refusing to send a duplicate invoice and stopping for a human yes before it writes.

## What it does

- **Get paid in one call.** `zaprite_pay` finds or creates the customer, raises the invoice, and returns a single `checkoutUrl`. Say the amount the way a person does: `Invoice Northwind 1,280 USD for the March retainer.`
- **Every rail, one link.** The payer picks card, bank transfer, bitcoin, Lightning, USDC or USDT on Zaprite's page. The plugin lists no rails and builds no payment form of its own.
- **Waits for real money.** `zaprite_watch_order` re-fetches until the order is `PAID` or `OVERPAID`. A partial payment is not paid, and no tool can declare one.
- **Keeps the books.** Recent orders, overdue invoices, a short report, and a live health check — without opening a dashboard.
- **The rest of the API.** Contacts, Lightning and on-chain quotes, payment links, event tickets (list, issue, check in), and webhooks you own.

## Why Hermes needs it

Hermes can browse, code, send messages, run commands. It could not get paid — the invoice, the link and the reconciliation all lived behind someone else's dashboard, so a person had to leave the conversation to finish the job.

This plugin closes that loop. The merchant's work happens where the work happens, and the money still lands in the merchant's own Zaprite account: nothing is re-hosted and no funds pass through Hermes.

## The one rule

**An agent may create a payment request. Only money may mark an order paid.**

- `zaprite_update_order` sets `COMPLETE` or an expiry. Zaprite's API also accepts `PAID`; this tool refuses it, because a merchant cannot declare payment. Cash is recorded in the dashboard by a person.
- Every write escalates through `pre_tool_call` to the human gate. The plugin cannot approve itself, a session or "always" answer covers only that call, and cron fails closed rather than hanging.
- A Zaprite webhook is ids only and unsigned, so every watch and read re-fetches the order. A webhook is not a payment.

## Install

Hermes `>=0.21.0`. Install at the release-tree commit (the 40-character sha in `catalog/zaprite.yaml`, not a later commit that only edits the pin):

```bash
hermes plugins install welliv/hermes-zaprite --ref e9bc25004bedfb22e68310cf17034b1ac9f53f01 --yes-deps --enable
```

Add `--force` to replace a copy that is already installed. From a local checkout:

```bash
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
hermes plugins install "$PWD" --yes-deps
hermes plugins enable zaprite
```

Restart the session. Hermes asks for the API key: create one at https://app.zaprite.com and put it in **Hermes → Tools → Zaprite** — never in chat. Then run `/zaprite doctor`, which confirms the key, whether it is a test or live org, and links the human setup steps. The plugin reads the key only through `agent.secret_scope.get_secret`.

## The Paid loop

1. `/zaprite doctor` — key, org, rails.
2. `zaprite_pay` — description, amount, name and email in one call. Use `as="order"` for a link anyone can pay.
3. Need line items? `zaprite_create_contact`, then `zaprite_create_invoice`.
4. Send the `checkoutUrl` to the payer. Telegram is not required.
5. `zaprite_watch_order` — re-fetch until paid (default 25s, max 90s per call; call again to keep waiting).
6. Deliver the work, then `zaprite_update_order` with `COMPLETE`. That means the merchant finished; it does not mean money arrived.

Amounts on `zaprite_create_order` and `zaprite_create_invoice` are integers in the smallest unit — `128000` USD is $1,280.00, and bitcoin is sats. `external_uniq_id` is the idempotency key: reuse it and Zaprite returns the stored order instead of a second checkout. `send_receipt` defaults to false here (the API default is true) — set it when a person asks for the email. API-created orders appear in the dashboard after the first payment, not at creation.

## One human setup, once per org

The agent cannot do these, and it will not pretend to.

1. **Pick the org.** Sandbox takes test payments and moves no real money; a live org opens real checkouts. The plugin cannot switch orgs — paste the key for the org you mean. https://help.zaprite.com/en/articles/9987875-what-is-a-sandbox-environment
2. **Connect rails.** Only what is connected appears at checkout. There is no connections API; use `deep_links.connections` from doctor.
3. **Create the key** (same doctor output, `deep_links.api_keys`).
4. **Give it to Hermes** through Tools → Zaprite. Never in chat.
5. **Brand it** in Settings → Profile — logo, accent colour, display name. API-created invoices and checkouts inherit them; this plugin cannot set them.

## Commands

| Command | What it does |
| --- | --- |
| `/zaprite` | Key present or not, spend cap, orders this plugin created |
| `/zaprite setup` | The human setup above, with a picker where the surface has one |
| `/zaprite doctor` | Live read-only check |
| `/zaprite kill` | Pause writes, drop pending approvals, stop an in-flight watch. Does not cancel or refund an order already at Zaprite |
| `/zaprite resume` | Allow writes again; the next write asks for a fresh approval |

`hermes zaprite status`, `doctor`, `kill` and `resume` do the same from a terminal.

## What it will not do

The honest list — the API has no route for these, so the plugin hands them to a person rather than inventing them. Full detail: [`docs/api-gaps.md`](docs/api-gaps.md).

- **Rails** — no list, connect or test. Checkout shows what a person connected.
- **Branding** — no logo, colour or display-name write. `zaprite_bridge_handoff` with gap `branding_profile` opens Settings → Profile; invoices inherit it after you save.
- **Create** — no payment link, product, POS, event, recurring invoice, promo code or refund. Payment links and tickets can be read; an existing ticket type can be issued and checked in.
- **Checkout** — no create or edit; `customCheckoutId` must already exist.
- **Signing** — no webhook signature, no test ping. Re-fetch is the model.
- **Idempotency** — only `externalUniqId` on order create (`idempotencyKey` on ticket issue).

## Disclosures

- **Network.** `https://api.zaprite.com` only, with the org key, User-Agent `zaprite-hermes/0.1.0`. No redirects with the key, no telemetry, no other host.
- **Money.** A full-access key opens real checkouts customers can pay, and `zaprite_charge_profile` charges a payment profile the customer already saved. Test on a sandbox org first.
- **Email.** Receipts and ticket emails stay off unless you ask.
- **Tickets.** Issuing carries Zaprite's ticket fee (1% + $3 per ticket on that product).
- **Fees.** API orders pay Zaprite's 1% (capped $15) on bitcoin and Tether; card and bank go through the merchant's own processor with no Zaprite fee. Dashboard-created invoices and payment links carry no transaction fee.
- **Ledger.** Orders this plugin creates are recorded in Hermes `plugin_db("zaprite")`. The API key is never stored there.
- **Handoff.** `zaprite_bridge_handoff` returns one dashboard URL and a note for a gap the API cannot write. No browser, no clicking.
- **Approvals.** `{"action": "approve"}` escalates to the Hermes human gate — it never auto-approves and never sets YOLO. `{"action": "block"}` refuses cron, a spend cap already exceeded, and `/zaprite kill`.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `base_url` | `https://api.zaprite.com` | HTTPS origin only; localhost HTTP for tests |
| `spend_limit_cents` | `0` | One integer in the **order's** smallest unit — USD cents, or sats on a bitcoin order. `0` turns the cap off. Approval still applies |
| `notify` | `session` | `session` fills `session_notice` for this chat; `silent` returns data only |

Bundled skills: `zaprite`, `zaprite-checkout-wizard`, `zaprite-sovereign`. Examples: `examples/paid-loop.md`, `examples/checkout-wizard.md`, `examples/invoice-share.md`. The digest blueprint is read-only: report and overdue, never create, charge or email.

## Validate

```bash
pytest
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
```

`pytest` mocks `httpx` — no key, no network. Validate and doctor need a Hermes CLI at `>=0.21.0`.

## Catalog

`catalog/zaprite.yaml` is the entry for `NousResearch/hermes-agent` → `plugin-catalog/zaprite.yaml`. `sha` is `e9bc25004bedfb22e68310cf17034b1ac9f53f01`, the commit that landed this tree on `main`; re-pin instructions are in `catalog/PIN.md`.

## Layout

```
plugin.yaml                 manifest v2 (provides_tools must match register)
zaprite_core/               implementation package
  registration.py           tools, hooks, slash commands, skills, digest blueprint
  schemas.py                tool schemas the model reads
  tools.py                  JSON handlers that never raise
  client.py                 httpx client for /v1 (no redirects with the key)
  service.py                the Paid loop and the rest of the OpenAPI surface
  policy.py                 approve escalates; fresh yes; cron, cap and kill fail closed
  store.py                  plugin_db ledger
  commands.py               /zaprite and hermes zaprite
skills/                     when to get paid, fail closed, re-fetch
examples/                   one continuous merchant scene for agents and film
catalog/zaprite.yaml        catalog entry pinned to the release tree
docs/api-gaps.md            writes that do not exist — do not invent them
```

## License

MIT. Maintainer: welliv.
