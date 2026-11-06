# 90-second demo

Record in a chat surface, not a terminal — this plugin is about what a merchant types. Dark theme,
default font size, nothing else on screen.

| t | On screen | Say |
|---|---|---|
| 0–8s | `hermes plugins list` shows `zaprite · enabled` | "Zaprite for Hermes. Twenty-seven tools, and a gate that stops a model moving money on its own." |
| 8–18s | `/zaprite doctor` | "One command proves the key, which org it belongs to, and whether it can write. Full access, live org." |
| 18–34s | type **invoice Northwind 1,280 dollars for the November retainer, due in 14 days** | "One sentence. It asks for the missing email instead of guessing, then creates the contact, the invoice, and returns a checkout link." |
| 34–44s | open `pay.zaprite.com/order/od_…` | "Card, bank, Lightning, on-chain — whatever the org connected. Zaprite hosts the checkout; the plugin never renders a payment form." |
| 44–58s | ask for a second invoice | **Approval prompt appears.** "This is the part a skill can't do. Every write needs a fresh human yes for that exact call. A previous 'always' doesn't carry." Decline it. |
| 58–72s | `/zaprite kill`, then ask for another invoice | "Kill switch. Writes stop, lookups keep working. It's honest about what it can't undo — it did not cancel anything already at Zaprite." |
| 72–88s | `zaprite watch_order` on the first order | "Then it re-fetches until the order is paid. Webhooks are unsigned, so a delivery is a hint — the order is the proof." |

Do not narrate the tool list. The two moments that land are the **fresh approval** and the
**kill switch**; everything else is setup.

## Copy for the post

> Zaprite payments for Hermes — and a gate a prompt can't give you.
>
> Say "invoice Northwind 1,280 dollars" and get one checkoutUrl back: card, bank, Lightning or
> on-chain. 27 tools. Every write needs a fresh human yes for that exact call; cron is refused
> outright; `/zaprite kill` stops writes while lookups keep working.
>
> 68 tests. Catalog PR open.
>
> @NousResearch #HermesAgent

## If something goes wrong on camera

- **Tools missing** → the gateway loaded an older plugin build; restart it and start a new session.
- **"needs a fresh human approval"** appears unprompted → that is the feature, not a bug; approve it
  and continue.
- **No approval prompt** → the run is non-interactive (cron or `-z`); use a real chat surface.
