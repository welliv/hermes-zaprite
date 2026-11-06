# Reaching Zaprite

Two things worth sending: a working integration they do not have, and the API gaps found while
building it. Send the second one as feedback, not as a complaint — it is the part they can act on
this week.

## Who to contact

| Channel | Use it for |
|---|---|
| https://zaprite.com/contact | Primary. Choose **API** as the product, tick the video consultation box |
| `dropfiat@zaprite.com` | Fallback when the form errors, and for a plain email thread |
| `@ZapriteApp` on X | Short public note once the catalog PR is open — they reply there |
| github.com/zapriteapp | Their public repos; `app-to-app-authorization` is the closest to this work |

## The message

Subject: **Hermes agent plugin for the Zaprite API — and three gaps found building it**

> Hi,
>
> I built an open-source Hermes Agent plugin for the Zaprite API (MIT, catalog PR open at
> NousResearch/hermes-agent#149875). A user types "invoice Northwind 1,280 dollars" and gets one
> checkoutUrl back; the plugin watches the order until it is paid. 27 tools across orders, invoices,
> contacts, tickets, webhooks and reporting, with an approval gate so a model cannot move money on
> its own.
>
> Three things I could not do through the API, in case they are on your roadmap:
>
> 1. **Connections.** There is no way to list, add or test a rail. Every merchant has to be sent to
>    the dashboard, and the plugin can only say "check what is connected" — the checkout silently
>    shows a subset.
> 2. **Webhooks are id-only and unsigned.** A delivery is `{eventType, orderId, orgId}`. I re-fetch
>    the order on every event, which is correct but means the webhook is only a hint. A signature
>    header would make it a fact.
> 3. **Invoice email.** `POST /v1/orders` with an invoice marks it SENT but does not reliably email
>    the customer, and there is no send-invoice call. I hand people the checkoutUrl instead.
>
> Two smaller ones: no payment-link creation, and no refunds.
>
> I would like to work on this surface properly — agent-driven checkout is a distribution channel
> Zaprite does not have yet, and the plugin is a working reference for it. Happy to walk through the
> code on a call.
>
> [name] · [repo link] · [demo video link]

## What not to do

- Do not lead with "hire me". Lead with the artefact and the gaps; the job conversation follows or
  it does not.
- Do not claim their endorsement. The plugin is third-party and stays that way until they say
  otherwise.
- Do not paste an API key, an org id, or a customer's email into the message.
- Do not send it before the catalog PR is public — "it exists" is much weaker than "here is the
  link".

## After sending

Expect a support-shaped reply first ("thanks, we'll pass it on"). The useful follow-up is the
video call: bring the demo, one live invoice, and the three gaps written as a short list they can
forward internally.
