Adds `zaprite` to the plugin catalog.

**What it does.** A merchant talks to Hermes; Hermes takes the payment. The plugin wraps all 20 published operations of the Zaprite v1 API (14 paths): create an order, invoice or Lightning/on-chain quote, hand back one `checkoutUrl` for card, ACH, bitcoin, Lightning, USDT and USDC, then re-fetch until the order is paid. It also covers contacts, payment links, event tickets, and the merchant's books — `zaprite_report`, `zaprite_list_overdue`, `zaprite_doctor`.

**What it refuses.** `zaprite_update_order` sets `COMPLETE` or `expires_at` and nothing else. Zaprite's PATCH endpoint also accepts `PAID`; this tool will not send it, because only money arriving may mark an order paid and only a person may record cash. `pre_tool_call` returns an approval request for every write, with a ten-minute TTL per exact call; the plugin cannot approve itself, and in cron it fails closed rather than hanging.

**Disclosure (rule 13).**
- **Network:** every call goes to `https://api.zaprite.com`. No other host, no telemetry.
- **Credentials:** reads `ZAPRITE_API_KEY` through the Hermes secret store on each call, never from a file and never logged. Setup guides the user to Hermes → Tools → Zaprite; it never asks for a key in chat.
- **Writes:** only after the user approves that exact call. `zaprite_create_webhook` registers a URL the user supplies; the plugin registers nothing by itself.
- **Background:** none by default. The optional `zaprite-paid-digest` blueprint is a read-only daily report that runs only if the user adds it.
- **Payment truth:** a Zaprite webhook is id-only and unsigned, so the plugin re-fetches the order and treats the re-fetch as the only source of truth. A webhook is not a payment.
- **No self-update:** no update check, no downloader; the catalog SHA is the release.

**Known gaps, stated on the entry.** The Zaprite API has no route for connections, payment-link creation, POS, events, recurring invoices, refunds or branding, so the plugin hands those to a person through `zaprite_bridge_handoff` with a dashboard link instead of pretending.

**Verification at the pinned commit**
- `hermes plugins validate .` → `Validation passed` (declared tools, hooks, middleware match registrations; security scan safe; no core override).
- `142 passed` in the plugin's test suite.
- Catalog entry: `scripts/validate_plugin_catalog.py` → `OK: 1 file(s) valid`.
- The plugin is installed and driving a real shop: orders created through it reconcile in the Zaprite dashboard, and a live checkout at `hackathon.plugnstay.supplies` takes real payments.

Install and try it without a Zaprite account: the plugin's `zaprite_setup` explains the sandbox org and where the key goes.
