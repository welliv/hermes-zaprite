# Zaprite for Hermes — every rail, one agent

You say the merchant job. Hermes becomes the soft keyboard: tools for *this* payment, not another dashboard screen.

> Invoice Northwind 1,280 dollars — card, bank, Lightning, or on-chain bitcoin.

One `checkoutUrl`. The payer chooses among rails this org already connected — including stablecoins when those are connected. Hermes re-fetches until **Paid** in this chat. Zaprite hosts checkout and does not hold the funds.

**Hermes is the device. Zaprite is where the rails live.**

Agent-to-agent settlement is a ~10s closer. The merchant Paid loop above is the product.

Below: sandbox first, unsigned webhooks, API ceilings, dual-hook approval, `/zaprite kill`.

## Why this

Zaprite already put every rail in one account. This plugin puts every merchant act in one conversation.

The keyboard we remove is the fixed dashboard click-path — and single-rail tooling that only speaks one payment grammar. The soft keyboard is tools that appear for *this* job: invoice, checkout, watch until **Paid**, overdue — without Zaprite having drawn that screen.

Intent is the finger. Computer-use poking a dashboard is the stylus: it works, but it's transitional. API-native tools plus human approval are the multi-touch layer.

Checkout only offers rails this org already connected — card, bank, Lightning, on-chain bitcoin, and stablecoins when those are connected. A person still does identity, Connections, and Profile once. The agent does the repeatable loop.

Say **every rail, not one**. Agent-to-agent settlement stays a ~10s closer; the merchant Paid loop is the product.

## Quickstart

Chat runs the Paid loop. A person still uses the dashboard once for Connections, Settings → Profile (logo/color), and anything with no API (recurring create, payment-link create, POS, events, refunds).

Say one of these:

- **Invoice a contact.** `Invoice Northwind 1280 USD for the March retainer.`
- **Create a checkout link.** `Create a checkout link for 500 USD.`
- **Watch until Paid.** `Watch that order until Paid.`
- **Overdue report.** `What's overdue?`
- **Doctor.** `/zaprite doctor`
- **Add my logo.** `Add my logo.` Hermes calls `zaprite_bridge_handoff` with gap `branding_profile` and opens Settings → Profile. It cannot set the logo or the accent color. Invoices and checkouts inherit Profile after you save it. Then open a `checkoutUrl` to preview. Guide: https://blog.zaprite.com/introducing-branded-invoices-and-checkouts/

The Paid loop below is the path. Tickets and the open-rail closer stay later in this file.

For a live walkthrough, the demo storefront is our own PlugnStay org. No keys or org data live in this repo.

## Install

Hermes `>=0.21.0`. Preferred, from the release-tree commit (the 40-character sha in `catalog/zaprite.yaml`, not a later commit that only edits the pin):

```bash
hermes plugins install welliv/hermes-zaprite --ref 524ce9fd3df4f9f015b6b940407e6460b4770297 --yes-deps --enable
```

Add `--force` when replacing a copy that is already installed:

```bash
hermes plugins install welliv/hermes-zaprite --ref 524ce9fd3df4f9f015b6b940407e6460b4770297 --yes-deps --enable --force
```

From a local checkout while developing:

```bash
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
hermes plugins install "$PWD" --yes-deps
hermes plugins enable zaprite
```

Restart the session. Hermes asks for the key: sign in or sign up at https://app.zaprite.com, create one, then paste it into **Hermes → Tools → Zaprite**. Never into chat. Then `/zaprite doctor` before any money or site work: it confirms the key, test vs live (which org the key belongs to), and human setup links for Connections. The plugin reads the key only with `agent.secret_scope.get_secret`.

## The Paid loop

1. `zaprite_doctor` if you have not checked the key.
2. `zaprite_pay` — one call. Give it a description, the amount, and a name and email. It
   finds or creates the customer, creates the invoice, and returns one link. Use `as="order"`
   for a link anyone can pay.
3. Need line items or a custom invoice? `zaprite_create_contact` (`legal_name`, `email`)
   then `zaprite_create_invoice`.
4. Send `checkoutUrl` to the payer. Say the `session_notice` in this chat. Telegram is not required.
5. `zaprite_watch_order` re-fetches until `PAID` or `OVERPAID`, or until the timeout (default 25s, max 90s). Call it again to keep waiting.
6. Deliver the work. `zaprite_update_order` with status `COMPLETE` marks merchant work done. It does **not** mean money arrived. Payment truth is only a re-fetched order status (`PAID` / `OVERPAID`). The agent cannot declare payment.

In `zaprite_pay`, write the amount the way a person says it: `$1,280`, `1280 usd`, `0.05 BTC`.
It echoes back what it understood. On `zaprite_create_order` and `zaprite_create_invoice`,
amounts stay integers in the smallest unit — `128000` USD is $1,280.00, and Bitcoin is sats.

`external_uniq_id` is the idempotency key Zaprite gives order creation. Reusing it returns the stored order instead of a second checkout.

`send_receipt` defaults to false in this plugin. The API default is true. Set it true only when a person asked to email the customer.

API orders show in the Zaprite dashboard after the first payment, not when you create them.

`zaprite_create_quote` is the in-chat Lightning or on-chain quote (`paymentUrl`). Card, bank, and stablecoins stay on `checkoutUrl`.

## One human setup

Do this once per organization. The agent cannot do it. Context first every session.

1. Sign in or sign up at https://app.zaprite.com. Open a sandbox org for test payments (no real money) or a live org for real checkouts: https://help.zaprite.com/en/articles/9987875-what-is-a-sandbox-environment · https://help.zaprite.com/en/articles/9875022-how-to-test-payments-for-an-api-integration
2. Connect the rails you want. Only those rails appear on checkout. There is no API to list or add them. Help (no org slug): https://help.zaprite.com/en/collections/9686374-connections. After doctor has seen an `orgId`, use its `deep_links.connections` (`/org/{orgId}/…`). Until then do not guess a slug if `/org/default/` 404s — use the org switcher in the app.
3. Create an API key from doctor’s `deep_links.api_keys` (Settings → API).
4. Give the key to Hermes through **Tools → Zaprite**. Never paste it into the chat.
5. Set the logo, accent color, and display name in Settings → Profile (doctor’s `deep_links.profile`). API-created invoices and checkouts inherit them. This plugin cannot set a logo or a color. After you save Profile, open a `checkoutUrl` to preview. Guide: https://blog.zaprite.com/introducing-branded-invoices-and-checkouts/
6. Say: "Invoice Northwind 1280 USD for the March retainer." Share the `checkoutUrl` with the customer — the API may mark an invoice SENT but does not reliably email it.

`/zaprite` in the Hermes session:

| Command | What it does |
| --- | --- |
| `/zaprite` | Key present or not, spend cap, orders this plugin created |
| `/zaprite setup` | The human setup, including Profile branding, with a picker when the surface has one |
| `/zaprite doctor` | Live read-only check |
| `/zaprite kill` | Pause writes, clear pending approvals, stop an in-flight watch on its next poll. Does not cancel an order already at Zaprite and does not refund |
| `/zaprite pause` | Same as kill |
| `/zaprite resume` | Allow writes again. The next gated write asks for a fresh approval |
| `/zaprite help` | The same commands |

`hermes zaprite status`, `hermes zaprite doctor`, `hermes zaprite kill`, `hermes zaprite pause`, and `hermes zaprite resume` do the same from a terminal.

## Disclosures

What you are installing:

- **Network.** Calls `https://api.zaprite.com` with the org API key. User-Agent `zaprite-hermes/0.1.0`. No other host. No telemetry.
- **Money movement.** A full-access key can open real checkouts. Customers can pay them. `zaprite_charge_profile` charges a payment profile the customer already saved.
- **Email.** Receipts and ticket emails stay off unless you set the flag. The Zaprite API defaults receipts to on. This plugin sends `false` unless you ask.
- **Tickets.** Issuing tickets can incur Zaprite's standard ticket fee (1% + $3 per ticket on that product).
- **Mark complete.** `zaprite_update_order` can set `COMPLETE` or an expiry. It cannot set `PAID`: payment status comes from Zaprite, and cash is recorded in the dashboard. It cannot refund.
- **Webhooks.** Payloads are id-only and unsigned (`{eventType, orderId, orgId}`). There is no signature. Every watch and get re-fetches the order and says so. This plugin does not run a webhook server. `zaprite_create_webhook` can register your own HTTPS URL; payloads stay unsigned.
- **Local ledger.** Orders this plugin creates sit in Hermes `plugin_db("zaprite")`. The API key is not stored there.
- **Dashboard handoff.** One URL and a note for a gap the API cannot write (a Lightning discount, or Settings → Profile for a logo and accent color). No browser, no clicking.
- **Branding.** Logo, accent color, and display name are dashboard Profile inheritance only. API-created invoices and checkouts inherit them. This plugin cannot read or write branding.
- **Approvals.** `pre_tool_call` may return `{"action": "approve"}` with a one-time `rule_key`. That **escalates to the Hermes human gate**. It does not approve the call, does not set YOLO, and does not skip the prompt. `post_approval_response` records a fresh human yes (`once`, `session`, or `always` on that prompt). The handler sends the request only after it consumes that record. A session or always answer does not cover the next write. Smart (model) approval, YOLO, approvals off, cron, and a skipped prompt do not count. `{"action": "block"}` refuses unattended cron, a spend cap exceeded before the prompt, and `/zaprite kill`. A denial, a cron run, or a missing yes sends nothing.
- **Fees.** Orders this plugin creates are API orders. On those, Zaprite's fee applies to bitcoin (on-chain, Lightning, Liquid) and Tether: 1%, cap $15 per transaction. Card and bank use the merchant's own processor; Zaprite adds no fee on fiat. Dashboard-created invoices, payment links, POS, and payment requests have no Zaprite transaction fee. Event ticket issue carries the ticket product fee (1% + $3 per ticket). Plans are $25/month or $240/year, credited against fees.
- **Rails.** Only rails a person already connected appear. There is no connections API. Doctor says that every time.

## Before any real payment

- **Sandbox first.** A sandbox organization takes test payments and moves no real money. A live organization opens real checkouts. The plugin cannot switch orgs for you: paste the key for the org you mean. https://help.zaprite.com/en/articles/9987875-what-is-a-sandbox-environment · https://help.zaprite.com/en/articles/9875022-how-to-test-payments-for-an-api-integration
- **Unsigned webhooks.** A delivery is ids only, `{eventType, orderId, orgId}`, and it has no signature. Re-fetch the order. A webhook is not a payment.
- **API ceilings.** There is no API to create a recurring invoice, a payment link, a POS terminal, an event, or a refund. Logo, accent color, and display name are not an API write. A person sets them in Settings → Profile. `zaprite_bridge_handoff` with gap `branding_profile` opens that page. It does not send a logo or a color to Connections or Checkouts. The full list is [`docs/api-gaps.md`](docs/api-gaps.md).

## When to use it

- Invoice a customer and hand them a checkout link.
- Watch that order until Paid without opening the dashboard.
- Quote Lightning or on-chain bitcoin for the same order, in chat.
- Charge a payment profile the customer already saved.
- See overdue invoices and a short status report.
- Check in a ticket for an event that already exists.

## When not to use it

- The agent is the one paying. This plugin is receive-side. A paying agent may settle a `lightning:` or `bitcoin:` URL only when a person asked it to pay.
- You need a new organization, a new API key, a new rail, a checkout discount, a logo or accent color, to **create** a payment link, a recurring invoice, an event, or a refund. Those writes are not in the API. Listing an existing payment link is fine. A person does the one dashboard step. `zaprite_bridge_handoff` records it and does not drive a browser. A logo or color uses gap `branding_profile` (Settings → Profile).
- The org has not connected a rail. Checkout only offers what is already connected.

`requires_hermes` is `>=0.21.0` for manifest v2, `register_skill`, `plugin_db`, and the human-approval directive. `ask_choice` and `current_cron_execution` are used when that Hermes has them. Python: `httpx>=0.27,<0.29`. Tests: `pip install "httpx>=0.27,<0.29" "pytest>=8.2,<10" && pytest`.

## Settings

Under the plugin's settings (`plugins.entries.zaprite.settings`):

| Key | Default | Meaning |
| --- | --- | --- |
| `base_url` | `https://api.zaprite.com` | HTTPS origin only. Localhost HTTP is for tests. Redirects are not followed, so the key stays on that origin. |
| `spend_limit_cents` | `0` | One integer in the **order's** smallest unit. USD: cents (`50000` = $500.00). BTC: sats (`50000` = 50,000 sats, not $500). `0` turns the cap off. The name says cents because USD is the common case. It is not a dollar cap on bitcoin. Approval still applies. |
| `notify` | `session` | `session` fills `session_notice` for this chat. `silent` returns the data without that line. |

Bundled skills: `zaprite` (context-first Paid loop), `zaprite-checkout-wizard` (site hook-up or build), `zaprite-sovereign` (ten-second closer). Examples: `examples/paid-loop.md`, `examples/checkout-wizard.md`, `examples/invoice-share.md`.

The bundled digest blueprint is read-only: report and overdue only. It must not create, charge, or email.

`{"action": "approve"}` is not an auto-approve. Hermes shows the human gate. `post_approval_response` is the record that a person answered. This repo never sets YOLO and never spawns a child to skip it. `/zaprite kill` (or `pause`) is the stop button: it drops pending approvals and refuses further writes until `/zaprite resume`.

## Read-only keys

Doctor probes with `POST /v1/orders` and an empty body. Currency is required, so a full key returns `400` and creates nothing. A read-only key returns `403`. Reports, get, list, watch, and doctor keep working. Writes return `READ_ONLY_KEY` with the key-settings URL.

## Validate

```bash
pytest
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
```

`pytest` mocks `httpx`. It does not need a Zaprite key and it does not call the network. Doctor and validate need the Hermes CLI on a version that satisfies `>=0.21.0`.

## Catalog

`catalog/zaprite.yaml` is the entry for `NousResearch/hermes-agent` `plugin-catalog/zaprite.yaml`. `repo`, `docs_url`, and the manifest homepage are `https://github.com/welliv/hermes-zaprite`. `sha` is `524ce9fd3df4f9f015b6b940407e6460b4770297`, the commit that landed this tree on `main`. `requires_hermes` is `>=0.21.0`. Instructions are in `catalog/PIN.md`.

## Known gaps

Honest list. Do not code around these.

- No connections list, connect, or test API. Checkout only shows rails a person already connected.
- No checkout create or edit. `customCheckoutId` must already exist. A Lightning discount is a dashboard handoff.
- No branding API. Settings → Profile sets the logo, accent color, and display name. API-created invoices and checkouts inherit them. `zaprite_bridge_handoff` gap `branding_profile` opens that page (`/org/{orgId}/settings/profile`, or `/org/default/settings/profile` before an orgId is stored). Guide: https://blog.zaprite.com/introducing-branded-invoices-and-checkouts/
- No payment-link, product, POS, or event create. Payment links and tickets are read, plus issue and check-in for a ticket type that already exists.
- No recurring-invoice create, no invoice send, no invoice void. Sharing `checkoutUrl` is the send. `OVERDUE` is a status you can list, not an email you can trigger.
- No refunds. No promo-code write.
- No webhook signing, no per-event subscription, no test ping. Re-fetch is the model.
- No idempotency key on order create except `externalUniqId`. Ticket issue has `idempotencyKey`.
- Order create does not appear in the dashboard until a payment lands.
- Doctor and `zaprite_bridge_handoff` build dashboard links with `org_links(orgId)`. Once an orgId is stored those links use `/org/{orgId}/`. A first run or a missing key still uses `/org/default/` until an orgId is stored. Doctor reports `org_slug_discovered: false` because `default` is the documented fallback, not a discovered org. Help-center links have no org segment. A link is not proof a rail is connected.
- `spend_limit_cents` is one integer compared with the order total. A cap meant as USD cents also caps a bitcoin order at that many sats.
- Portable `plugin.json` / `mcp.json` under `portable/` are stubs. They are not a second install path and they do not start a server.

Proposed API surface, without pretending it exists: `docs/api-gaps.md`.

## Layout

```
plugin.yaml                 manifest v2 (provides_tools must match register)
__init__.py                 dual-import register(ctx)
zaprite_core/               implementation package
  registration.py           tools, hooks, slash, skills, digest blueprint
  schemas.py                tool schemas the model reads
  tools.py                  JSON handlers that never raise
  client.py                 httpx client for /v1 (no redirects with the key)
  service.py                Paid loop and the rest of the OpenAPI surface
  policy.py                 approve escalates; fresh yes required; cron, cap, and kill fail closed
  store.py                  plugin_db ledger (orders this plugin created)
  secrets.py                agent.secret_scope.get_secret only
  commands.py               /zaprite and hermes zaprite
skills/zaprite/             when to get paid, fail closed, re-fetch
skills/zaprite-sovereign/   ten-second open-rail closer
examples/paid-loop.md       one continuous merchant scene for agents and film
tests/                      mocked httpx; loads as hermes_plugins.zaprite
catalog/zaprite.yaml        catalog entry pinned to the tree commit on main
docs/api-gaps.md            writes that do not exist — do not invent them
```

## License

MIT. Homepage: https://github.com/welliv/hermes-zaprite. Maintainer: welliv.
