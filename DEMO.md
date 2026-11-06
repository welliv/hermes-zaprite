# Demo — 90 seconds

One shot. Merchant at a keyboard. Tool path: `examples/paid-loop.md`. Hermes in the chat. Payer on a phone. Sandbox org, so the payment is a test. Say card, bank, Lightning, on-chain bitcoin. Do not open the Zaprite admin.

## 0:00–0:08

Merchant:

> Invoice Northwind 1,280 dollars for the March retainer. Card, bank, Lightning, or on-chain bitcoin.

Hermes asks to approve the invoice. Merchant taps Approve. Cut.

## 0:08–0:22

Hermes:

> Checkout is ready for 1280.00 USD. Send them https://pay.zaprite.com/order/od_…

Merchant forwards that one URL.

Caption: **One link. Every rail this org connected.**

## 0:22–0:45

Phone. Zaprite checkout. The connected methods are on screen. Payer pays with Lightning, or the sandbox test payment if Lightning is not connected.

The host in the address bar is `pay.zaprite.com`.

## 0:45–1:05

Merchant's chat. Hermes, same session:

> Paid. 1280.00 USD on od_… is PAID.

Merchant:

> Mark it complete. I'll send the files.

Hermes asks to approve Mark complete. Merchant approves.

> Order od_… is now COMPLETE.

## 1:05–1:15

Merchant:

> If another agent wants to pay us in bitcoin?

Hermes:

> You already connected a Lightning Address. I can put a bolt11 in this chat. They pay from their wallet. Zaprite doesn't hold it. Card and bank stay on that same checkout.

Stop. Do not open Connections. Do not show a second product.

## Must be true in the shot

- The plugin produced `checkoutUrl`.
- A payer paid on Zaprite checkout.
- Paid was a re-fetch, not a webhook body.
- Mark complete happened in the same chat, after a second approval.

## Leave out

- Creating the org or the key.
- A browser agent in the dashboard.
- Tickets.
- Any line that treats `{orderId}` as proof of payment.
