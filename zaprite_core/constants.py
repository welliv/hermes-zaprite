"""Shared names, limits, and the facts this plugin will not invent."""

from __future__ import annotations

VERSION = "0.1.0"
PLUGIN_NAME = "zaprite"
USER_AGENT = f"zaprite-hermes/{VERSION}"
SECRET_NAME = "ZAPRITE_API_KEY"
DEFAULT_BASE_URL = "https://api.zaprite.com"
# Zaprite's published API docs use /org/default/. That slug is not every
# merchant's org. Prefer org_links(org_id) once doctor has seen an orgId.
SIGN_IN_URL = "https://app.zaprite.com"
API_KEYS_URL = "https://app.zaprite.com/org/default/settings/api"

# Hermes manifest floor. Manifest v2, register_skill, plugin_db, and the
# pre_tool_call human-approval directive are all in the 0.21 plugin guide.
# ask_choice and current_cron_execution are used when the host provides them.
REQUIRES_HERMES = ">=0.21.0"

WATCH_DEFAULT_TIMEOUT = 25
WATCH_MAX_TIMEOUT = 90
WATCH_DEFAULT_INTERVAL = 3
WATCH_MIN_INTERVAL = 2
WATCH_MAX_POLLS = 40
OVERDUE_MAX_PAGES = 3

# Money arrived. COMPLETE is not here on purpose: it means work done, not cash.
ORDER_PAID = frozenset({"PAID", "OVERPAID"})
ORDER_DONE = frozenset({"COMPLETE"})
INVOICE_PAID = frozenset({"PAID", "OVERPAID"})
INVOICE_OPEN = frozenset({"DRAFT", "SENT", "OVERDUE", "UNDERPAID"})

WEBHOOK_EVENTS = (
    "order.change",
    "invoice.sent",
    "invoice.voided",
    "contact.updated",
    "ticket.change",
    "paymentProfile.created",
    "paymentProfile.updated",
    "paymentProfile.deleted",
)

WEBHOOK_DISCLOSURE = (
    "Zaprite webhooks are id-only and unsigned. A delivery such as "
    "{eventType, orderId, orgId} is not proof of payment and has no signature "
    "to check. Always re-fetch GET /v1/orders/{id} and trust that response. "
    "A non-200 from your endpoint is retried, then Zaprite may disable the webhook."
)

RAILS_NOTE = (
    "The checkout shows only rails already connected on this Zaprite organization: "
    "card, bank, Lightning, on-chain bitcoin, and stablecoins. This plugin cannot "
    "list, add, or test connections. There is no connections API."
)

# `default` is the slug Zaprite publishes in its API-key URL. Doctor rewrites
# app deep links to /org/{orgId}/ when an order or webhook returns orgId.
DOCUMENTED_ORG_SLUG = "default"
ORG_SLUG_NOTE = (
    "Before doctor has seen an orgId, app links use the documented slug "
    "default from Zaprite's API docs. After doctor (or any order) returns "
    "org_id_seen, this plugin builds /org/{orgId}/settings/api, "
    "/org/{orgId}/settings/profile, "
    "/org/{orgId}/connections, and /org/{orgId}/checkouts. Help-center "
    "links have no org segment. None of these links prove a rail is "
    "connected. There is no connections API."
)
# Settings → Profile is the only branding write. API invoices inherit it.
# There is no public branding read or write route. Do not invent one.
BRANDING_GUIDE_URL = "https://blog.zaprite.com/introducing-branded-invoices-and-checkouts/"
BRANDING_NOTE = (
    "Logo, accent color, and display name are set by a person in Zaprite "
    "Settings → Profile. API-created invoices and checkouts inherit them. "
    "There is no public branding read or write API, so this plugin cannot "
    "set a logo or a color. After Profile is saved, open a checkoutUrl to preview."
)
INVOICE_EMAIL_NOTE = (
    "Creating an invoice through the API can mark it SENT, but Zaprite does "
    "not reliably email the customer from that call. Always give the person "
    "the checkoutUrl so they can share it. They can also send from the "
    "Zaprite dashboard. There is no separate send-invoice email API."
)
ENVIRONMENT_NOTE = (
    "Test vs live is which Zaprite organization the API key belongs to. "
    "A sandbox org key takes test payments with no real money. A live org "
    "key opens real checkouts. The plugin cannot switch modes for you: "
    "paste the key for the org you mean, then run zaprite_doctor."
)
CONTEXT_FIRST = (
    "Before any money or site work: confirm the key (zaprite_doctor), "
    "confirm test vs live from which org that key belongs to, ask for any "
    "missing name/email/amount/service, and send the merchant to Connections "
    "when a needed rail is not yet connected. Fail closed if the key, mode, "
    "or a required human detail is missing."
)


def org_app_base(org_id: str | None) -> str:
    """App origin for an org. Prefer a seen orgId; else the documented default slug."""
    slug = (org_id or "").strip() or DOCUMENTED_ORG_SLUG
    return f"https://app.zaprite.com/org/{slug}"


def org_links(org_id: str | None = None) -> dict[str, str]:
    """Deep links. Help URLs stay slug-free. App URLs use orgId when known."""
    base = org_app_base(org_id)
    return {
        "sign_in": SIGN_IN_URL,
        "api_keys": f"{base}/settings/api",
        "profile": f"{base}/settings/profile",
        "branding_guide": BRANDING_GUIDE_URL,
        "connections": f"{base}/connections",
        "checkouts": f"{base}/checkouts",
        "connections_help": "https://help.zaprite.com/en/collections/9686374-connections",
        "sandbox": "https://help.zaprite.com/en/articles/9987875-what-is-a-sandbox-environment",
        "test_payments": "https://help.zaprite.com/en/articles/9875022-how-to-test-payments-for-an-api-integration",
        "status": "https://status.zaprite.com",
        "openapi": "https://api.zaprite.com/openapi.json",
        "llms": "https://api.zaprite.com/llms.txt",
        "lightning_address_notes": "https://help.zaprite.com/en/articles/15253069-zaprite-release-notes-2026-05-25",
        "btcpay": "https://blog.zaprite.com/how-to-connect-btcpay-server/",
    }


LINKS = org_links(None)

TOOL_NAMES = [
    "zaprite_pay",
    "zaprite_create_order",
    "zaprite_create_invoice",
    "zaprite_get_order",
    "zaprite_list_orders",
    "zaprite_create_quote",
    "zaprite_watch_order",
    "zaprite_update_order",
    "zaprite_charge_profile",
    "zaprite_create_contact",
    "zaprite_get_contact",
    "zaprite_list_contacts",
    "zaprite_update_contact",
    "zaprite_delete_contact",
    "zaprite_report",
    "zaprite_list_overdue",
    "zaprite_doctor",
    "zaprite_setup",
    "zaprite_list_webhooks",
    "zaprite_create_webhook",
    "zaprite_delete_webhook",
    "zaprite_bridge_handoff",
    "zaprite_sovereign_rails",
    "zaprite_list_payment_links",
    "zaprite_get_payment_link",
    "zaprite_list_tickets",
    "zaprite_get_ticket",
    "zaprite_issue_tickets",
    "zaprite_ticket_activity",
]

# Human approval gate, and a hard block during unattended cron.
GATED_TOOLS = frozenset(
    {
        "zaprite_pay",
        "zaprite_create_order",
        "zaprite_create_invoice",
        "zaprite_create_quote",
        "zaprite_update_order",
        "zaprite_charge_profile",
        "zaprite_delete_contact",
        "zaprite_issue_tickets",
        "zaprite_ticket_activity",
        "zaprite_create_webhook",
        "zaprite_delete_webhook",
        "zaprite_bridge_handoff",
    }
)

# Any mutating tool. Cron blocks these even when they are not money.
WRITE_TOOLS = GATED_TOOLS | frozenset(
    {
        "zaprite_create_contact",
        "zaprite_update_contact",
    }
)

READ_TOOLS = frozenset(TOOL_NAMES) - WRITE_TOOLS
