---
name: zaprite-checkout-wizard
description: >
  Use when a merchant describes a website (existing or to build) and wants
  Zaprite checkout on it. Guided path: check connections, human setup links
  for missing rails, hook-up vs build, sandbox vs live, then implement
  checkoutUrl from POST /v1/orders and test without completing a live payment
  unless they explicitly ask.
---

# Zaprite checkout wizard

Guided site integration. The Paid loop in the `zaprite` skill is still the hero once checkout exists. This skill is how you get a site there without guessing.

## Before you write any site code

Fail closed on missing context.

1. **Key and mode.** Call `zaprite_doctor`. Missing key → sign in/up at `https://app.zaprite.com`, create a key, paste into Hermes. Ask whether this run is **sandbox (test)** or **live**. Mode is which org the key belongs to; you cannot flip it without a different key.
2. **Connections.** There is no connections API. Tell the merchant checkout will only offer rails already connected (card, bank, Lightning, on-chain bitcoin, stablecoins). If they need a rail that is not connected, give `deep_links.connections` from doctor and wait for them to finish the human setup. Use `zaprite_bridge_handoff` with gap `checkout_methods` when they also need a checkout toggled in the dashboard.
3. **Hook-up vs build.** Ask: integrate Zaprite into an existing site, or build a small cart/storefront that creates orders?
4. **Products and amounts.** Collect product names, quantities, amounts (smallest unit), currency, and any color/variant text that should appear as line-item description. The order API has no image URL field — keep photos on the merchant site; put text detail in the line item. The checkout logo, accent color, and display name are Settings → Profile, which API checkouts inherit. This plugin cannot set them. "Add my logo" is `zaprite_bridge_handoff` with gap `branding_profile`. After they save Profile, open a `checkoutUrl` to preview.
5. **Do not invent APIs.** Create checkout with `zaprite_create_order` or `zaprite_create_invoice` (POST /v1/orders). There is no payment-link create, no connection create, no checkout write beyond that.

## Implement

1. On the site (or the one you build), collect cart details, then call Zaprite through this plugin (or the same HTTP shape) to create an order.
2. Redirect or deep-link the payer to the returned `checkoutUrl` on `pay.zaprite.com`.
3. Prefer `external_uniq_id` so retries do not open a second checkout.
4. After payment, re-fetch with `zaprite_get_order` / `zaprite_watch_order`. Webhooks are id-only and unsigned — never trust them alone.
5. Leave `send_receipt` false unless they asked to email a receipt.

## Test

1. **Sandbox first** when they chose test: create a small order, open `checkoutUrl`, confirm the connected rails appear, do **not** complete a live payment on a live org unless they explicitly ask.
2. Say which mode you used (sandbox key vs live key) in the session.
3. If a rail is missing on the hosted page, send them back to Connections / checkout settings via the human link — do not toggle Alby, Glow, or any connector yourself unless they asked.

## After checkout works

Hand back to the main `zaprite` skill: share links, watch until Paid, next merchant act in the same chat. Sovereign agent-to-agent is a ten-second closer only (`zaprite-sovereign`).
