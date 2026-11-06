# Checkout wizard (site → Zaprite)

Continuous scene the agent should follow when a merchant wants Zaprite on a website.

## 1. Context

```text
User: I have a small storefront. I want Zaprite checkout — card, bank, Lightning, bitcoin.
Agent: runs zaprite_doctor → key full, org_id_seen set, deep_links.connections ready
Agent: asks sandbox vs live; user picks sandbox
Agent: asks hook-up existing site vs build; user: hook up existing
```

## 2. Rails

If a needed rail is off, give `deep_links.connections` and wait. Optional: `zaprite_bridge_handoff` with `gap=checkout_methods`. Do not invent a connections API. Do not toggle connectors yourself unless asked.

## 3. Implement

Site creates an order (plugin tool or same HTTP):

- `zaprite_create_order` with amount + currency + `external_uniq_id`, or
- `zaprite_create_invoice` with contact + line items (text only; no image field)

Redirect the payer to `checkoutUrl`.

## 4. Test

Open the sandbox `checkoutUrl`. Confirm rails that are connected appear. Do not complete a live payment on a live org unless the merchant explicitly asks. Re-fetch with `zaprite_get_order` / `zaprite_watch_order`. Webhooks are id-only and unsigned.

## 5. Hand back

Once checkout works, the soft-keyboard Paid loop in `examples/paid-loop.md` is the day-to-day path.
