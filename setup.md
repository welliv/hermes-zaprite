# Set up Zaprite

Complete the plugin install yourself. The person only creates the org, connects rails, and mints the key. Gather every dependency before any money or site work.

## Human, once

1. Sign in or sign up at https://app.zaprite.com and open the organization they will get paid into.
   - **Sandbox (test):** no real money — https://help.zaprite.com/en/articles/9987875-what-is-a-sandbox-environment and https://help.zaprite.com/en/articles/9875022-how-to-test-payments-for-an-api-integration
   - **Live:** real checkouts on that org's connected rails.
2. Connect rails. Card, bank, Lightning, on-chain bitcoin, stablecoins. Checkout shows only what they connect. You cannot list or add them via API.
   - Help, no org slug: https://help.zaprite.com/en/collections/9686374-connections
   - App: after `/zaprite doctor`, use `deep_links.connections` (it prefers `/org/{orgId}/` once the API has returned an orgId). Until then Zaprite's docs use `/org/default/`, which may 404 for other orgs — use the org switcher rather than guessing a slug.
3. Logo, accent color, and display name are Settings → Profile. API-created invoices and checkouts inherit them. This plugin cannot set a logo or a color. After `/zaprite doctor`, use `deep_links.profile` (`/org/{orgId}/settings/profile` once an orgId is known, otherwise `https://app.zaprite.com/org/default/settings/profile`). Guide: https://blog.zaprite.com/introducing-branded-invoices-and-checkouts/. After they save Profile, open a `checkoutUrl` to preview. If they say "add my logo", call `zaprite_bridge_handoff` with gap `branding_profile`.
4. Create the key from doctor’s `deep_links.api_keys` (or Settings → API in the app). Full access to get paid. Read-only if Hermes should only report.
5. They paste the key into Hermes when it asks for `ZAPRITE_API_KEY`. Not into the model chat.

## Hermes

From a clone or the release-tree pin (`requires_hermes` `>=0.21.0`). The ref is the 40-character sha in `catalog/zaprite.yaml`, the commit that landed the plugin tree, not a later pin-edit commit. Add `--force` to replace an install that is already there.

```bash
hermes plugins install welliv/hermes-zaprite --ref adb4c95e41c2198d89ed62bca6f6ee5b9aaebf81 --yes-deps --enable
```

Or from this directory while developing:

```bash
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
hermes plugins install "$PWD" --yes-deps
hermes plugins enable zaprite
```

Restart the session if it was already open. Then:

```text
/zaprite doctor
```

Confirm key mode (full vs read-only), test vs live (which org the key belongs to), and the connection setup link. Then:

```text
Invoice Northwind 1280 USD for the March retainer. Card, bank, Lightning, or on-chain bitcoin.
```

Approve the create when Hermes asks. You get a `checkoutUrl` on `pay.zaprite.com`. Share that link — the API may mark an invoice SENT but does not reliably email it. After the payer pays, the same chat says Paid because the plugin re-fetched the order. A cron job will not create the invoice. The full tool path is in `examples/paid-loop.md`. Site checkout path: `skills/zaprite-checkout-wizard` and `examples/checkout-wizard.md`.

## Settings

- `spend_limit_cents`: one integer in the order's smallest unit. `50000` blocks a USD order above $500.00 and a BTC order above 50,000 sats. `0` disables the cap. It is not a dollar cap on bitcoin.
- `notify`: `session` (speak Paid here) or `silent`.

## If you want it to stop

`/zaprite kill` or `/zaprite pause` (and `hermes zaprite kill`) pauses every Zaprite write, clears pending approvals, and stops an in-flight `zaprite_watch_order` on its next poll. Lookups still work. An order already created at Zaprite stays there. This is not a refund. `/zaprite resume` allows writes again, and the next gated write asks for a fresh approval.

The ceilings that kill cannot fix — sandbox versus live, unsigned webhooks, no recurring-invoice create, no payment-link create, no POS, no event create, no refunds, branding only through Settings → Profile — are in [`docs/api-gaps.md`](docs/api-gaps.md). A logo or accent color uses `zaprite_bridge_handoff` gap `branding_profile`. That opens Profile, not Connections or Checkouts.

## If doctor says read-only

Reports work. Create, charge, and tickets do not. They make a full-access key and update the Hermes secret. Run `/zaprite doctor` again.

## If the write is refused as unattended

The run is cron, or nobody can approve. Open an interactive Hermes session and ask again.

```text
┌─ Zaprite setup ──────────────────────────────────┐
│  Human    sign in → org → rails → Profile → key  │
│  Hermes   hermes plugins enable zaprite           │
│  Check    /zaprite doctor (context first)         │
│  Paid     checkoutUrl, then re-fetch              │
└──────────────────────────────────────────────────┘
```
