---
name: zaprite-sovereign
description: >
  Use only as a ten-second closer after checkoutUrl exists, to say how another
  agent can pay a Lightning Address or xpub the merchant already connected.
  Guidance only. Do not use this to create the payment.
---

# Open rails, after a person starts the org

Use this after `checkoutUrl` is already the answer. Ten seconds, then stop.

1. A person creates the Zaprite organization and the API key. You cannot sign up for them.
2. That person connects an open rail in the dashboard:
   - a Lightning Address, or
   - an xpub (Coldcard, Sparrow, Ledger, Trezor, or the branded xpub plugins), verified at index 0.
   Connections: use `zaprite_doctor` → `deep_links.connections` (uses `/org/{orgId}/` once orgId is known). Help: `https://help.zaprite.com/en/collections/9686374-connections`
3. Call `zaprite_sovereign_rails` if you need the exact wording. It does not call a write API and it does not open a browser.
4. `zaprite_create_order`, then `zaprite_create_quote` for `LIGHTNING` or `BITCOIN`.
5. Hand `paymentUrl` to the paying agent. They pay only if a person asked them to, from a wallet they control.
6. `zaprite_watch_order` re-fetches until Paid. That re-fetch is the receipt. The webhook is not.

Zaprite does not custody the funds. Card and bank stay on the same `checkoutUrl` for human payers. A Lightning discount on the checkout is dashboard-only: `zaprite_bridge_handoff` with gap `lightning_discount`, then wait. Do not drive the browser.

Do not claim you connected a wallet. Do not invent a connections endpoint.
