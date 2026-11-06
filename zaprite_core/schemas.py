"""Tool schemas. The description is how Hermes decides to call the tool."""

from __future__ import annotations

from .constants import RAILS_NOTE, TOOL_NAMES


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


_AMOUNT = {
    "type": "integer",
    "description": (
        "Integer in the currency's smallest unit. 50000 USD is 500.00 dollars, "
        "not 500. Bitcoin amounts are satoshis. Do not send a decimal string."
    ),
}
_CURRENCY = {
    "type": "string",
    "description": "Order currency. USD, BTC, USDT, USDC, LBTC, or another code Zaprite lists.",
}
_ORDER_ID = {
    "type": "string",
    "description": "Zaprite order id (od_…) or the external_uniq_id you set at create time.",
}
_BOOL = {"type": "boolean"}

SCHEMAS = {
    "zaprite_pay": _tool(
        "zaprite_pay",
        (
            "Get paid in one call: finds or creates the customer, creates the invoice (or an order), "
            "and returns one link. amount takes what a person says: '$1,280', '1280 usd', '0.05 BTC'. "
            "Refuses when nothing is connected to take payment. Needs approval. Fails closed in cron."
        ),
        {
            "description": {
                "type": "string",
                "description": "What the payment is for, in the customer's words. 'November retainer'.",
            },
            "amount": {
                "type": "string",
                "description": "As a person writes it: '$1,280', '1280', '0.05 BTC'. Not cents.",
            },
            "currency": _CURRENCY,
            "customer": {
                "type": "object",
                "description": "Who pays. name and email. Omit for an open link (as='order').",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                },
            },
            "contact_id": {"type": "string", "description": "Use an existing contact instead of a name."},
            "as": {
                "type": "string",
                "enum": ["invoice", "order"],
                "description": "invoice bills a named customer. order is an open link anyone can pay.",
            },
            "due_days": {"type": "integer", "description": "Days until due. Invoices only."},
            "external_uniq_id": {
                "type": "string",
                "description": "Your own id. Sending the same one twice cannot bill twice.",
            },
        },
        ["description", "amount"],
    ),
    "zaprite_setup": _tool(
        "zaprite_setup",
        (
            "First run and setup. Returns the one next step: create an account and API key, or "
            "connect how you want to get paid, or ready. Call it with no arguments to see the "
            "state. After the person connects rails in the Zaprite dashboard, call it with "
            "rails=['card','lightning'] (or skip=true). Never guesses whether a rail works."
        ),
        {
            "rails": {
                "type": "array",
                "items": {"type": "string", "enum": ["card", "bank", "lightning", "onchain"]},
                "description": "Rails the person says they connected in the Zaprite dashboard.",
            },
            "skip": _BOOL,
            "skip_brand": _BOOL,
            "business_name": {"type": "string", "description": "What customers should see."},
            "brand_color": {"type": "string", "description": "Hex colour, e.g. #1F7A4D."},
            "logo": {"type": "string", "description": "Path or URL to the logo file the person shared."},
            "assets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Other brand assets: tagline, font, invoice footer.",
            },
        },
        [],
    ),
    "zaprite_create_order": _tool(
        "zaprite_create_order",
        (
            "Create a Zaprite order and return checkoutUrl. The payer opens that URL and pays "
            "on the rails this organization already connected (card, bank, Lightning, on-chain "
            "bitcoin, stablecoins). Use this for a one-amount checkout. Use zaprite_create_invoice "
            "when you have line items and a contact. Needs human approval. Fails closed in cron. "
            "Receipt email stays off unless send_receipt is true. Pass external_uniq_id so a retry "
            "returns the same order. " + RAILS_NOTE
        ),
        {
            "amount": _AMOUNT,
            "currency": _CURRENCY,
            "label": {"type": "string", "description": "Shown on the checkout and in on-chain labels."},
            "external_uniq_id": {
                "type": "string",
                "description": "Your idempotency key. Reusing it returns the existing order.",
            },
            "redirect_url": {"type": "string", "description": "Where to send the payer after they pay."},
            "customer_email": {"type": "string"},
            "customer_name": {"type": "string"},
            "contact_id": {"type": "string"},
            "custom_checkout_id": {
                "type": "string",
                "description": "Optional checkout id already created in the dashboard. The API cannot create one.",
            },
            "expires_at": {"type": "string", "description": "ISO 8601 UTC expiry. A past time blocks a still-unpaid order."},
            "send_receipt": {
                "type": "boolean",
                "description": "Email a receipt after payment. Default false. The Zaprite API default is true; this plugin overrides that.",
            },
            "metadata": {"type": "object", "description": "Up to 50 string keys and string values."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Up to 10 tags, 32 characters each."},
        },
        ["amount", "currency"],
    ),
    "zaprite_create_invoice": _tool(
        "zaprite_create_invoice",
        (
            "Create a Zaprite invoice order (POST /v1/orders with invoice and contactId) and return "
            "checkoutUrl. There is no separate invoice-send API: sharing checkoutUrl is how the "
            "payer gets it. Amount is computed from line items. unit_price is an integer in the "
            "smallest currency unit and may be negative for a credit. Needs a contact. Needs human "
            "approval. Fails closed in cron. " + RAILS_NOTE
        ),
        {
            "contact_id": {"type": "string", "description": "Required. Create the contact first."},
            "currency": _CURRENCY,
            "line_items": {
                "type": "array",
                "description": "At least one item. name and unit_price required.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "quantity": {"type": "number"},
                        "unit_price": _AMOUNT,
                        "tax_rate_bips": {"type": "integer", "description": "1000 = 10%."},
                        "discount_rate_bips": {"type": "integer"},
                        "discount_amount": {"type": "integer"},
                    },
                },
            },
            "title": {"type": "string"},
            "number": {"type": "string", "description": "Invoice number. Zaprite generates one if omitted."},
            "date": {"type": "string", "description": "YYYY-MM-DD. Defaults to today."},
            "days_to_pay": {"type": "integer", "description": "Days until due. Omit for due on receipt."},
            "footer_note": {"type": "string"},
            "label": {"type": "string"},
            "external_uniq_id": {"type": "string"},
            "redirect_url": {"type": "string"},
            "custom_checkout_id": {"type": "string"},
            "send_receipt": _BOOL,
            "metadata": {"type": "object"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        ["contact_id", "currency", "line_items"],
    ),
    "zaprite_get_order": _tool(
        "zaprite_get_order",
        (
            "Re-fetch one order by id or external_uniq_id. This is how you verify payment. "
            "Webhook bodies are not proof. Read-only."
        ),
        {"order_id": _ORDER_ID},
        ["order_id"],
    ),
    "zaprite_list_orders": _tool(
        "zaprite_list_orders",
        (
            "List orders, pending included. Set include_pending to false to hide unpaid orders. "
            "Up to 100 per page. Read-only. Not an accounting export."
        ),
        {
            "page": {"type": "integer"},
            "search": {"type": "string"},
            "contact_id": {"type": "string"},
            "status": {
                "type": "string",
                "description": "PENDING, PROCESSING, PAID, OVERPAID, UNDERPAID, COMPLETE, or ABANDONED.",
            },
            "type": {
                "type": "string",
                "description": "invoice, apiInvoice, paymentLink, pos, event, wooCommerce, paymentRequest, apiOrder, or other.",
            },
            "currency": {"type": "string"},
            "include_pending": _BOOL,
            "created_at_min": {"type": "string"},
            "created_at_max": {"type": "string"},
            "paid_at_min": {"type": "string"},
            "paid_at_max": {"type": "string"},
            "sort_by": {"type": "string", "description": "createdAt or paidAt."},
            "sort_order": {"type": "string", "description": "asc or desc."},
        },
        [],
    ),
    "zaprite_create_quote": _tool(
        "zaprite_create_quote",
        (
            "Create a Lightning or on-chain bitcoin quote for an existing order (POST /v1/orders/create-quote). "
            "Returns paymentUrl (lightning: or bitcoin:) for an in-chat QR. Omit transaction_method to try "
            "Lightning first. Card, bank, and stablecoins are not quoted here; they stay on checkoutUrl. "
            "Show the URL to the payer. Do not pay it unless a person asked you to pay. Needs approval. "
            "Fails closed in cron."
        ),
        {
            "order_id": _ORDER_ID,
            "transaction_method": {
                "type": "string",
                "description": "LIGHTNING or BITCOIN. Omit to try Lightning, then on-chain.",
            },
        },
        ["order_id"],
    ),
    "zaprite_watch_order": _tool(
        "zaprite_watch_order",
        (
            "Re-fetch an order until money arrives (PAID or OVERPAID), or until timeout_seconds "
            "(default 25, max 90). This is a poll, not a webhook listener. Say session_notice to the "
            "user in this chat when it returns. Telegram is not required. Read-only. "
            "Call again to keep waiting. Unsigned webhook ids are never treated as payment."
        ),
        {
            "order_id": _ORDER_ID,
            "timeout_seconds": {"type": "number"},
            "interval_seconds": {"type": "number", "description": "Minimum 2 seconds between re-fetches."},
        },
        ["order_id"],
    ),
    "zaprite_update_order": _tool(
        "zaprite_update_order",
        (
            "Mark an order COMPLETE after you deliver, or set expires_at. It cannot set PAID: payment "
            "status comes from Zaprite when money arrives, and a person records cash in the dashboard. "
            "Does not refund or edit line items. Needs approval. Fails closed in cron."
        ),
        {
            "order_id": _ORDER_ID,
            "status": {"type": "string", "enum": ["COMPLETE"], "description": "COMPLETE only."},
            "expires_at": {"type": "string", "description": "ISO 8601, or null to clear expiry."},
        },
        ["order_id"],
    ),
    "zaprite_charge_profile": _tool(
        "zaprite_charge_profile",
        (
            "Charge a saved payment profile on an existing order (POST /v1/orders/charge). "
            "The profile id comes from zaprite_get_contact paymentProfiles. The checkout must "
            "have that connection enabled. send_receipt is required, true or false. "
            "Needs approval. Fails closed in cron. Refuses when the order total is over spend_limit_cents."
        ),
        {
            "order_id": _ORDER_ID,
            "payment_profile_id": {"type": "string"},
            "send_receipt": {"type": "boolean", "description": "Required. True emails the customer a receipt."},
        },
        ["order_id", "payment_profile_id", "send_receipt"],
    ),
    "zaprite_create_contact": _tool(
        "zaprite_create_contact",
        "Create a contact. legal_name and email are required before an invoice. Fails closed in cron.",
        {
            "legal_name": {"type": "string"},
            "email": {"type": "string"},
            "display_name": {"type": "string"},
            "contact_name": {"type": "string"},
            "default_currency": _CURRENCY,
            "tax_id": {"type": "string"},
            "internal_note": {"type": "string"},
            "billing_address": {"type": "object"},
        },
        ["legal_name", "email"],
    ),
    "zaprite_get_contact": _tool(
        "zaprite_get_contact",
        "Get a contact, including saved paymentProfiles (id, method, label, connection pluginSlug). Read-only.",
        {"contact_id": {"type": "string"}},
        ["contact_id"],
    ),
    "zaprite_list_contacts": _tool(
        "zaprite_list_contacts",
        "Search contacts by query or email. Read-only.",
        {
            "query": {"type": "string"},
            "email": {"type": "string"},
            "page": {"type": "integer"},
        },
        [],
    ),
    "zaprite_update_contact": _tool(
        "zaprite_update_contact",
        "Replace contact fields with PUT. Send every field that must remain. Fails closed in cron.",
        {
            "contact_id": {"type": "string"},
            "legal_name": {"type": "string"},
            "email": {"type": "string"},
            "display_name": {"type": "string"},
            "contact_name": {"type": "string"},
            "default_currency": {"type": "string"},
            "tax_id": {"type": "string"},
            "internal_note": {"type": "string"},
            "billing_address": {"type": "object"},
        },
        ["contact_id"],
    ),
    "zaprite_delete_contact": _tool(
        "zaprite_delete_contact",
        "Delete a contact. Needs approval. Fails closed in cron.",
        {"contact_id": {"type": "string"}},
        ["contact_id"],
    ),
    "zaprite_report": _tool(
        "zaprite_report",
        "Summarize the first page of recent orders by status, plus how many orders this plugin has tracked. Read-only. Zaprite has no reports or export API.",
        {"include_pending": _BOOL},
        [],
    ),
    "zaprite_list_overdue": _tool(
        "zaprite_list_overdue",
        "List invoices whose invoice status is OVERDUE. Scans invoice and apiInvoice orders. Read-only. There is no reminder-email API; share checkoutUrl.",
        {},
        [],
    ),
    "zaprite_doctor": _tool(
        "zaprite_doctor",
        (
            "Read-only setup check. Says whether the key is missing, invalid, read-only, or full; "
            "lists webhook endpoints; and states that connections cannot be listed. "
            "Also states that logo, accent color, and display name come from Settings → Profile "
            "and that API invoices inherit them. This plugin cannot set a logo or a color. "
            "The key probe is an empty POST /v1/orders, which cannot create an order. "
            "Run this before the first invoice and whenever a write is refused."
        ),
        {},
        [],
    ),
    "zaprite_list_webhooks": _tool(
        "zaprite_list_webhooks",
        "List webhook endpoints. Payloads are id-only and unsigned. Always re-fetch the order. Read-only.",
        {"page": {"type": "integer"}},
        [],
    ),
    "zaprite_create_webhook": _tool(
        "zaprite_create_webhook",
        (
            "Register your own HTTPS URL as a Zaprite webhook. This plugin does not run a receiver. "
            "Payloads are id-only and unsigned, so always re-fetch the order. Needs approval. Fails closed in cron."
        ),
        {
            "url": {"type": "string", "description": "Your HTTPS endpoint. Zaprite posts {eventType, orderId, orgId}."},
            "label": {"type": "string"},
        },
        ["url"],
    ),
    "zaprite_delete_webhook": _tool(
        "zaprite_delete_webhook",
        "Delete a Zaprite webhook endpoint you no longer want. Needs approval. Fails closed in cron.",
        {"webhook_id": {"type": "string"}},
        ["webhook_id"],
    ),
    "zaprite_bridge_handoff": _tool(
        "zaprite_bridge_handoff",
        (
            "Hand a person one dashboard step the API cannot do: a Lightning or bitcoin discount, "
            "which rails a checkout offers, or logo, accent color, and display name. "
            "Logo and color use gap branding_profile, which opens Settings → Profile. "
            "API-created invoices and checkouts inherit that Profile. "
            "Returns the URL and records the handoff. Does not open a browser and does not "
            "automate the dashboard. Needs approval. Call again with handoff_id and outcome after the person finishes."
        ),
        {
            "gap": {
                "type": "string",
                "description": (
                    "lightning_discount, checkout_methods, branding_profile, or other. "
                    "Logo, accent color, and display name must use branding_profile "
                    "(Settings → Profile). A logo or color note on gap other is treated as branding_profile."
                ),
            },
            "note": {"type": "string"},
            "handoff_id": {"type": "string"},
            "outcome": {"type": "string", "description": "What the person says they changed. Optional follow-up."},
        },
        [],
    ),
    "zaprite_sovereign_rails": _tool(
        "zaprite_sovereign_rails",
        (
            "Explain how a merchant receives from another agent after a person has created the org "
            "and connected an open rail (Lightning Address or xpub). Guidance only. No write, no browser, "
            "no custody. Use at the end of a get-paid conversation, not instead of checkoutUrl."
        ),
        {},
        [],
    ),
    "zaprite_list_payment_links": _tool(
        "zaprite_list_payment_links",
        "List payment links (GENERIC, POS, EVENT) and their items. Read-only. Cannot create a link, product, event, or ticket type.",
        {
            "page": {"type": "integer"},
            "search": {"type": "string"},
            "type": {"type": "string", "description": "GENERIC, POS, or EVENT."},
            "published": {"type": "string"},
        },
        [],
    ),
    "zaprite_get_payment_link": _tool(
        "zaprite_get_payment_link",
        "Get one payment link and its items (ticket types live here). Read-only. Cannot create a link or event.",
        {"payment_link_id": {"type": "string"}},
        ["payment_link_id"],
    ),
    "zaprite_list_tickets": _tool(
        "zaprite_list_tickets",
        "List event tickets. Read-only. Ticket URLs are bearer secrets. Event create is not in the API.",
        {
            "page": {"type": "integer"},
            "payment_link_id": {"type": "string"},
            "payment_link_item_id": {"type": "string"},
            "status": {"type": "string"},
        },
        [],
    ),
    "zaprite_get_ticket": _tool(
        "zaprite_get_ticket",
        "Get one ticket before check-in. Read-only. Do not paste the ticket URL into a public channel.",
        {"ticket_id": {"type": "string"}},
        ["ticket_id"],
    ),
    "zaprite_issue_tickets": _tool(
        "zaprite_issue_tickets",
        (
            "Issue no-charge tickets for an existing ticket type. Standard ticket fees apply. "
            "send_tickets defaults to false so attendees are not emailed unless you set it true. "
            "Needs approval. Fails closed in cron. Cannot create the event."
        ),
        {
            "payment_link_item_id": {"type": "string"},
            "tickets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"},
                        "name": {"type": "string"},
                        "company": {"type": "string"},
                        "quantity": {"type": "integer"},
                    },
                },
            },
            "decrement_stock": {"type": "boolean"},
            "send_tickets": {"type": "boolean"},
            "persistent_owner_email": {"type": "string"},
            "idempotency_key": {"type": "string"},
        },
        ["payment_link_item_id", "tickets", "decrement_stock"],
    ),
    "zaprite_ticket_activity": _tool(
        "zaprite_ticket_activity",
        "Record CHECK_IN, SCAN, CANCEL, or REACTIVATE on a ticket. CHECK_IN admits the attendee. Needs approval. Fails closed in cron.",
        {
            "ticket_id": {"type": "string"},
            "action": {"type": "string", "description": "CHECK_IN, SCAN, CANCEL, or REACTIVATE."},
            "payment_link_id": {"type": "string", "description": "Optional event id. Rejects a ticket from another event."},
            "force": {"type": "boolean", "description": "Allow CHECK_IN when already checked in."},
            "update_stock": {"type": "boolean"},
        },
        ["ticket_id", "action"],
    ),
}


def all_schemas() -> list[dict]:
    missing = [name for name in TOOL_NAMES if name not in SCHEMAS]
    if missing:
        raise RuntimeError(f"schemas missing: {missing}")
    extra = [name for name in SCHEMAS if name not in TOOL_NAMES]
    if extra:
        raise RuntimeError(f"schemas not in TOOL_NAMES: {extra}")
    return [SCHEMAS[name] for name in TOOL_NAMES]
