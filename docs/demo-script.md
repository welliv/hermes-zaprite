# 90-second demo

Record in a chat surface, not a terminal — this plugin is about what a merchant types. Dark theme,
default font size, nothing else on screen.

| t | On screen | Say |
|---|---|---|
| 0–8s | `hermes plugins list` shows `zaprite · enabled` | "Zaprite for Hermes. One sentence in, one checkout link out." |
| 8–18s | `/zaprite doctor` | "First it proves the key, which org it belongs to, and whether it can write. Full access, live org." |
| 18–34s | type **invoice Northwind 1,280 dollars for the November retainer** | "It reads the amount the way a person says it — one thousand two hundred eighty, not twelve eighty — creates the customer, the invoice, and hands back one link." |
| 34–44s | open `pay.zaprite.com/order/od_…` | "Card, bank, Lightning, on-chain — whatever this org connected. Zaprite hosts the checkout; the plugin never renders a payment form." |
| 44–56s | ask for a second invoice | **Approval prompt appears.** "This is what a skill can't do. Every write needs a fresh human yes for that exact call. A previous 'always' doesn't carry." Decline it. |
| 56–68s | mark the first order complete, then ask **is it paid?** | "Delivered is not paid. Marking it complete says the work is done; it never says money arrived. Only a re-fetched PAID or OVERPAID counts, and the plugin cannot declare it." |
| 68–78s | `/zaprite kill`, then ask for another invoice | "Kill switch. Writes stop, lookups keep working. It's honest about what it can't undo — nothing already at Zaprite was cancelled." |
| 78–88s | `zaprite watch_order` on the first order | "Then it re-fetches until money lands. Webhooks are unsigned, so a delivery is a hint — the order is the proof." |

Do not narrate the tool list. The three moments that land are the **amount read as said**, the
**fresh approval**, and **delivered ≠ paid**. Everything else is setup.

## Copy for the post

> Zaprite payments for Hermes — one sentence in, one checkout link out.
>
> "Invoice Northwind 1,280 dollars" → one link: card, bank, Lightning, on-chain. Amounts are read
> the way people write them ($1,280, 0.05 BTC).
>
> Every write needs a fresh human yes for that exact call; cron is refused; `/zaprite kill` stops
> writes while lookups keep working. And it can never mark money paid that didn't arrive — COMPLETE
> means delivered, PAID means paid.
>
> 29 tools, 138 tests, MIT, no telemetry.
>
> @NousResearch #HermesAgent

## If something goes wrong on camera

- **Tools missing** → the gateway loaded an older plugin build; restart it and start a new session.
- **"needs a fresh human approval"** appears unprompted → that is the feature, not a bug; approve it
  and continue.
- **No approval prompt** → the run is non-interactive (cron or `-z`); use a real chat surface.
