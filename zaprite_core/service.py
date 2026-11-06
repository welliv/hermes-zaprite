"""Zaprite operations. Return dicts. Tools JSON-encode them and never raise."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from . import runtime, secrets, store
from .amounts import parse_amount
from .client import MissingKey, ZapriteClient, ZapriteError
from .constants import (
    BRANDING_NOTE,
    CONTEXT_FIRST,
    ENVIRONMENT_NOTE,
    INVOICE_EMAIL_NOTE,
    LINKS,
    ORG_SLUG_NOTE,
    ORDER_DONE,
    OVERDUE_MAX_PAGES,
    RAILS_NOTE,
    SIGN_IN_URL,
    WATCH_DEFAULT_INTERVAL,
    WATCH_DEFAULT_TIMEOUT,
    WATCH_MAX_POLLS,
    WATCH_MAX_TIMEOUT,
    WATCH_MIN_INTERVAL,
    WEBHOOK_DISCLOSURE,
    WEBHOOK_EVENTS,
    org_links,
)
from .policy import over_limit, pending_count, read_only_from_error, refuse_write, writes_paused
from .summarize import checkout_notice, contact_view, format_amount, is_paid, order_view, paid_notice


def dumps_ready(payload: dict) -> dict:
    return payload


def _client() -> ZapriteClient:
    key = secrets.load_api_key()
    if not key:
        raise MissingKey()
    return ZapriteClient(
        key,
        runtime.settings.base_url,
        transport=runtime.transport,
    )


def _active_org_id() -> str | None:
    return store.get_meta("org_id") or None


def _active_links() -> dict[str, str]:
    """App deep links using a seen orgId when doctor or an order stored one."""
    return org_links(_active_org_id())


def _remember_org_id(org_id: str | None) -> None:
    if org_id and isinstance(org_id, str) and org_id.strip():
        store.set_meta("org_id", org_id.strip())


def _missing() -> dict:
    links = _active_links()
    return {
        "ok": False,
        "error": {
            "code": "MISSING_API_KEY",
            "message": (
                "ZAPRITE_API_KEY is not set. Sign in or sign up at Zaprite, open "
                "the org (sandbox for test, live for real money), connect the rails "
                "you want, create an API key, and paste it into Hermes — not into chat."
            ),
            "url": links["api_keys"],
            "sign_in": SIGN_IN_URL,
            "sandbox": links["sandbox"],
            "test_payments": links["test_payments"],
            "connections": links["connections"],
            "environment": ENVIRONMENT_NOTE,
            "context_first": CONTEXT_FIRST,
            "issues": [],
        },
        "setup": _setup_steps(),
    }


def _from_error(exc: ZapriteError) -> dict:
    mapped = read_only_from_error(exc.code, exc.status)
    if mapped and exc.status == 403:
        return mapped
    return {"ok": False, "error": exc.to_dict()}


def _session(kwargs: dict) -> dict[str, Any]:
    return {
        "session_id": kwargs.get("session_id") or kwargs.get("task_id"),
        "delivery": "active_session",
        "telegram_required": False,
    }


def _notice(text: str) -> str | None:
    if runtime.settings.notify == "silent":
        return None
    return text


def _truthy(args: dict, *names: str) -> bool:
    value = _pick(args, *names)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _pick(args: dict, *names: str) -> Any:
    for name in names:
        if name in args and args[name] is not None:
            return args[name]
    return None


def _params(pairs: list[tuple[str, Any]]) -> list[tuple[str, str]]:
    encoded: list[tuple[str, str]] = []
    for key, value in pairs:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                if item is not None:
                    encoded.append((key, str(item)))
        elif isinstance(value, bool):
            encoded.append((key, "true" if value else "false"))
        else:
            encoded.append((key, str(value)))
    return encoded


def _metadata(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("metadata must be an object of string keys and string values, at most 50.")
    if len(value) > 50:
        raise ValueError("metadata accepts at most 50 keys.")
    out = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ValueError("metadata keys and values must be strings.")
        out[key] = item
    return out


def _tags(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 10:
        raise ValueError("tags must be a list of at most 10 strings.")
    tags = []
    for item in value:
        text = str(item)
        if len(text) > 32:
            raise ValueError("each tag must be 32 characters or fewer.")
        tags.append(text)
    return tags


def _remember(order: dict, kind: str, note: str) -> dict:
    view = order_view(order)
    store.upsert_order(view, order, kind=kind)
    if view.get("id"):
        store.add_event(str(view["id"]), view.get("status"), note)
    return view


def _replay(external: str | None) -> dict | None:
    if not external:
        return None
    row = store.get_by_external(external)
    if not row or not row.get("id"):
        return None
    try:
        live = _client().get_order(str(row["id"]))
    except ZapriteError as exc:
        if exc.status == 404 or exc.code == "NOT_FOUND":
            return None
        raise
    view = _remember(live, row.get("kind") or "order", "idempotent replay")
    return {
        "ok": True,
        "idempotent_replay": True,
        "order": view,
        "checkoutUrl": view.get("checkoutUrl"),
        "id": view.get("id"),
        "status": view.get("status"),
        "rails": RAILS_NOTE,
        "next": "This external_uniq_id already has an order. Share checkoutUrl or watch it. No second order was created.",
    }


def _rails_gate() -> dict | None:
    """No checkout before a way to get paid is connected, or explicitly skipped."""
    from . import onboarding

    if onboarding.rails_confirmed() or onboarding.rails_skipped():
        return None
    # A key that cannot write is the real blocker; do not lecture about rails first.
    if store.get_meta("key_mode") in {"read_only", "invalid"}:
        return None
    org_id = store.get_meta("org_id")
    # /org/default/ is the documented slug, not this merchant's org.
    where = (
        org_links(org_id)["connections"]
        if org_id
        else "Settings → Connections at https://app.zaprite.com"
    )
    return {
        "ok": False,
        "error": {
            "code": "NO_RAILS",
            "message": (
                "Nothing is connected to take payments yet, so this checkout would be unpayable.\n"
                f"Connect one here: {where}\n"
                "Then tell me which: card, bank, lightning or onchain — or say skip."
            ),
            "issues": [],
        },
    }


def create_order(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_create_order", args, kwargs)
    if refused:
        return refused
    blocked = _rails_gate()
    if blocked:
        return blocked
    currency = _pick(args, "currency")
    amount = _pick(args, "amount")
    if not currency:
        raise ValueError("currency is required. Example: USD.")
    if amount is None:
        raise ValueError(
            "amount is required, as an integer in the smallest unit. 50000 USD is 500.00, not 500."
        )
    amount = _require_int(amount, "amount")
    if amount < 0:
        raise ValueError("amount must be zero or greater. Use an invoice line with a negative unit_price for a credit.")
    external = _pick(args, "external_uniq_id", "externalUniqId")
    replay = _replay(external)
    if replay:
        replay.update(_session(kwargs))
        return replay
    body: dict[str, Any] = {
        "currency": str(currency).upper(),
        "amount": amount,
        "sendReceiptToCustomer": bool(_pick(args, "send_receipt", "sendReceiptToCustomer") or False),
    }
    _copy_order_options(args, body)
    if external:
        body["externalUniqId"] = str(external)
    order = _client().create_order(body)
    view = _remember(order, "order", "created")
    payload = {
        "ok": True,
        "id": view.get("id"),
        "status": view.get("status"),
        "checkoutUrl": view.get("checkoutUrl"),
        "order": view,
        "rails": RAILS_NOTE,
        "dashboard_note": "API orders show in the Zaprite dashboard after they receive a payment.",
        "next": "Send checkoutUrl to the payer. Call zaprite_watch_order to wait for Paid.",
        "session_notice": _notice(checkout_notice(view)),
        "webhook": WEBHOOK_DISCLOSURE,
    }
    payload.update(_session(kwargs))
    return payload


def pay(args: dict, **kwargs: Any) -> dict:
    """One sentence in, one link out: contact, invoice or order, in one approval."""
    refused = refuse_write("zaprite_pay", args, kwargs)
    if refused:
        return refused
    blocked = _rails_gate()
    if blocked:
        return blocked

    description = _pick(args, "description", "title", "label")
    if not description:
        raise ValueError("What is this for? Give me a short description, like 'November retainer'.")
    currency = str(_pick(args, "currency") or "USD").upper()
    raw_amount = _pick(args, "amount", "total")
    # In the human verb an integer means what the person said: 1280 is $1,280.
    # The API's minor-unit shape stays available on create_order/create_invoice.
    if isinstance(raw_amount, int) and not isinstance(raw_amount, bool):
        raw_amount = str(raw_amount)
    amount, phrase = parse_amount(raw_amount, currency)

    customer = _pick(args, "customer") or {}
    if not isinstance(customer, dict):
        customer = {}
    name = _pick(customer, "name", "legal_name", "legalName") or _pick(args, "customer_name")
    email = _pick(customer, "email") or _pick(args, "customer_email")

    contact_id = _pick(args, "contact_id", "contactId")
    if not contact_id and name and email:
        created = create_contact({"legal_name": name, "email": email}, **kwargs)
        if not created.get("ok"):
            return created
        contact_id = (created.get("contact") or {}).get("id")

    kind = str(_pick(args, "as") or "invoice").lower()
    external = _pick(args, "external_uniq_id", "externalUniqId")
    due = _pick(args, "due_days", "days_to_pay", "daysToPay")

    if kind == "order":
        made = create_order(
            {
                "amount": amount,
                "currency": currency,
                "description": str(description),
                "external_uniq_id": external,
            },
            **kwargs,
        )
    else:
        if not contact_id:
            raise ValueError(
                "An invoice needs a customer. Give me a name and email, or use as='order' "
                "for a link anyone can pay."
            )
        item = {"name": str(description), "unit_price": amount}
        invoice_args: dict[str, Any] = {
            "contact_id": contact_id,
            "currency": currency,
            "line_items": [item],
            "title": str(description),
            "external_uniq_id": external,
        }
        if due is not None:
            invoice_args["days_to_pay"] = due
        made = create_invoice(invoice_args, **kwargs)

    if not made.get("ok"):
        return made

    url = made.get("checkoutUrl")
    view = made.get("order") or {}
    who = name or email or ""
    noun = "Order" if kind == "order" else "Invoice"
    summary = f"{noun} for {phrase}" + (f" to {who}" if who else "") + f" — {url}"
    return {
        "ok": True,
        "id": made.get("id"),
        "checkoutUrl": url,
        "summary": summary,
        "amount": {"minor": amount, "phrase": phrase},
        "customer": {"name": name, "email": email, "contact_id": contact_id},
        "order": view,
        "next": "Send that link. Then ask me whether it is paid; I re-fetch the order rather than trust a webhook.",
    }


def create_invoice(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_create_invoice", args, kwargs)
    if refused:
        return refused
    blocked = _rails_gate()
    if blocked:
        return blocked
    contact_id = _pick(args, "contact_id", "contactId")
    currency = _pick(args, "currency")
    items = _pick(args, "line_items", "lineItems")
    if not contact_id:
        raise ValueError("contact_id is required. Create the contact first. Every Zaprite invoice needs one.")
    if not currency:
        raise ValueError("currency is required.")
    if not isinstance(items, list) or not items:
        raise ValueError("line_items needs at least one item with name and unit_price.")
    external = _pick(args, "external_uniq_id", "externalUniqId")
    replay = _replay(external)
    if replay:
        replay.update(_session(kwargs))
        return replay
    line_items = [_line_item(item) for item in items]
    invoice: dict[str, Any] = {"lineItems": line_items}
    for src, dest in (
        ("title", "title"),
        ("number", "number"),
        ("date", "date"),
        ("days_to_pay", "daysToPay"),
        ("purchase_order_number", "purchaseOrderNumber"),
        ("footer_note", "footerNote"),
    ):
        value = _pick(args, src, dest)
        if value is not None:
            invoice[dest] = value
    body: dict[str, Any] = {
        "currency": str(currency).upper(),
        "contactId": str(contact_id),
        "invoice": invoice,
        "sendReceiptToCustomer": bool(_pick(args, "send_receipt", "sendReceiptToCustomer") or False),
    }
    _copy_order_options(args, body)
    if external:
        body["externalUniqId"] = str(external)
    order = _client().create_order(body)
    view = _remember(order, "invoice", "invoice created")
    payload = {
        "ok": True,
        "id": view.get("id"),
        "status": view.get("status"),
        "invoice_status": view.get("invoice_status"),
        "checkoutUrl": view.get("checkoutUrl"),
        "order": view,
        "rails": RAILS_NOTE,
        "dashboard_note": (
            "API invoices show in the dashboard after a payment. "
            + INVOICE_EMAIL_NOTE
        ),
        "invoice_email": INVOICE_EMAIL_NOTE,
        "next": "Send checkoutUrl. Call zaprite_watch_order until Paid, then deliver and mark complete.",
        "session_notice": _notice(checkout_notice(view)),
        "webhook": WEBHOOK_DISCLOSURE,
    }
    payload.update(_session(kwargs))
    return payload


def _copy_order_options(args: dict, body: dict) -> None:
    mapping = {
        "label": "label",
        "redirect_url": "redirectUrl",
        "redirectUrl": "redirectUrl",
        "custom_checkout_id": "customCheckoutId",
        "customCheckoutId": "customCheckoutId",
        "expires_at": "expiresAt",
        "expiresAt": "expiresAt",
        "contact_id": "contactId",
        "contactId": "contactId",
    }
    for src, dest in mapping.items():
        if src in args and args[src] is not None and dest not in body:
            body[dest] = args[src]
    if _pick(args, "redirect_if_pending", "redirectIfPending") is not None:
        body["redirectIfPending"] = bool(_pick(args, "redirect_if_pending", "redirectIfPending"))
    if _pick(args, "countdown_to_expiry", "countdownToExpiry") is not None:
        body["countdownToExpiry"] = bool(_pick(args, "countdown_to_expiry", "countdownToExpiry"))
    if _pick(args, "allow_save_payment_profile", "allowSavePaymentProfile") is not None:
        body["allowSavePaymentProfile"] = bool(
            _pick(args, "allow_save_payment_profile", "allowSavePaymentProfile")
        )
    customer = {}
    email = _pick(args, "customer_email", "email")
    name = _pick(args, "customer_name")
    if email:
        customer["email"] = email
    if name:
        customer["name"] = name
    if customer:
        body["customerData"] = customer
    meta = _metadata(_pick(args, "metadata"))
    if meta:
        body["metadata"] = meta
    tags = _tags(_pick(args, "tags"))
    if tags:
        body["tags"] = tags
    fields = _pick(args, "customer_fields", "customerFields")
    if isinstance(fields, dict):
        body["customerFields"] = fields


def _require_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer.")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise ValueError(f"{field} must be an integer in the smallest currency unit.")


def _line_item(item: Any) -> dict:
    if not isinstance(item, dict):
        raise ValueError("each line item must be an object.")
    name = item.get("name")
    price = item.get("unit_price", item.get("unitPrice"))
    if not name or price is None:
        raise ValueError("each line item needs name and unit_price (smallest currency unit).")
    price = _require_int(price, "unit_price")
    built: dict[str, Any] = {"name": str(name), "unitPrice": price}
    if item.get("description"):
        built["description"] = str(item["description"])
    if item.get("quantity") is not None:
        built["quantity"] = item["quantity"]
    for src, dest in (
        ("tax_rate_bips", "taxRateBips"),
        ("discount_rate_bips", "discountRateBips"),
        ("discount_amount", "discountAmount"),
    ):
        if item.get(src) is not None:
            built[dest] = item[src]
        elif item.get(dest) is not None:
            built[dest] = item[dest]
    return built


def get_order(args: dict, **kwargs: Any) -> dict:
    order_id = _pick(args, "order_id", "orderId", "id")
    if not order_id:
        raise ValueError("order_id is required. A Zaprite id or externalUniqId both work.")
    order = _client().get_order(str(order_id))
    view = _remember(order, "order", "fetched")
    payload = {
        "ok": True,
        "order": view,
        "paid": is_paid(order),
        "webhook": WEBHOOK_DISCLOSURE,
        "rails": RAILS_NOTE,
    }
    if str(order.get("status") or "").upper() == "OVERPAID":
        payload["warning"] = (
            "Paid more than the total. Zaprite has no refund API — refund the difference yourself."
        )
    if not is_paid(order) and str(order.get("status") or "").upper() in ORDER_DONE:
        payload["warning"] = (
            "COMPLETE means the work is done, not that money arrived. "
            "Payment truth is a PAID or OVERPAID status."
        )
    if is_paid(order):
        payload["session_notice"] = _notice(paid_notice(view))
        payload["next"] = "Deliver the work, then zaprite_update_order with status COMPLETE."
    payload.update(_session(kwargs))
    return payload


def _include_pending(args: dict) -> bool:
    """Pending is what a merchant means by "outstanding", so it is on unless refused."""
    raw = _pick(args, "include_pending", "includePending")
    return True if raw is None else bool(raw)


def list_orders(args: dict, **kwargs: Any) -> dict:
    status = _pick(args, "status")
    if isinstance(status, str):
        status = [status]
    currency = _pick(args, "currency")
    if isinstance(currency, str):
        currency = [currency]
    params = _params(
        [
            ("page", _pick(args, "page") or 1),
            ("search", _pick(args, "search")),
            ("contactId", _pick(args, "contact_id", "contactId")),
            ("status", status),
            ("type", _pick(args, "type")),
            ("currency", currency),
            ("createdAtMin", _pick(args, "created_at_min", "createdAtMin")),
            ("createdAtMax", _pick(args, "created_at_max", "createdAtMax")),
            ("paidAtMin", _pick(args, "paid_at_min", "paidAtMin")),
            ("paidAtMax", _pick(args, "paid_at_max", "paidAtMax")),
            ("tags", _pick(args, "tags")),
            ("includePending", "true" if _include_pending(args) else None),
            ("sortBy", _pick(args, "sort_by", "sortBy")),
            ("sortOrder", _pick(args, "sort_order", "sortOrder")),
        ]
    )
    data = _client().list_orders(params)
    items = data.get("items") if isinstance(data, dict) else []
    views = []
    for order in items or []:
        if isinstance(order, dict):
            views.append(order_view(order))
    return {
        "ok": True,
        "orders": views,
        "meta": data.get("meta") if isinstance(data, dict) else None,
        "note": "PENDING orders are hidden unless include_pending is true or status is set. API orders appear in the dashboard only after a payment.",
    }


def create_quote(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_create_quote", args, kwargs)
    if refused:
        return refused
    order_id = _pick(args, "order_id", "orderId")
    if not order_id:
        raise ValueError("order_id is required.")
    existing = _client().get_order(str(order_id))
    if isinstance(existing, dict):
        limited = over_limit(existing.get("totalAmount"), existing.get("currency"))
        if limited:
            return limited
    method = _pick(args, "transaction_method", "transactionMethod")
    body: dict[str, Any] = {"orderId": str(order_id)}
    if method:
        method = str(method).upper()
        if method not in {"LIGHTNING", "BITCOIN"}:
            raise ValueError("transaction_method must be LIGHTNING or BITCOIN. Omit it to try Lightning first.")
        body["transactionMethod"] = method
    quote = _client().create_quote(body)
    amount = format_amount(
        quote.get("orderAmount") if isinstance(quote, dict) else None,
        quote.get("orderCurrency") if isinstance(quote, dict) else None,
    )
    method_used = quote.get("method") if isinstance(quote, dict) else None
    payment_url = quote.get("paymentUrl") if isinstance(quote, dict) else None
    notice = (
        f"Quote ready. {amount} via {method_used}. "
        f"Payment URL {payment_url}. Show it to the payer. Do not pay it unless a person asked you to pay."
    )
    payload = {
        "ok": True,
        "quote": quote,
        "rails": "create-quote returns Lightning or on-chain bitcoin only. Card, bank, and stablecoins stay on checkoutUrl.",
        "session_notice": _notice(notice),
        "next": "Watch the same order with zaprite_watch_order. The quote is not a webhook and it is not signed.",
    }
    payload.update(_session(kwargs))
    return payload


def watch_order(args: dict, **kwargs: Any) -> dict:
    order_id = _pick(args, "order_id", "orderId", "id")
    if not order_id:
        raise ValueError("order_id is required.")
    timeout = _pick(args, "timeout_seconds")
    interval = _pick(args, "interval_seconds")
    try:
        timeout_s = float(WATCH_DEFAULT_TIMEOUT if timeout is None else timeout)
        interval_s = float(WATCH_DEFAULT_INTERVAL if interval is None else interval)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds and interval_seconds must be numbers.") from exc
    timeout_s = max(0.0, min(timeout_s, float(WATCH_MAX_TIMEOUT)))
    interval_s = max(float(WATCH_MIN_INTERVAL), interval_s)
    clock = runtime.monotonic or time.monotonic
    sleeper = runtime.sleep or time.sleep
    deadline = clock() + timeout_s
    polls = 0
    last: dict | None = None
    if writes_paused():
        return _paused_watch(str(order_id), polls)
    client = _client()
    while polls < WATCH_MAX_POLLS:
        if writes_paused():
            return _paused_watch(str(order_id), polls)
        polls += 1
        last = client.get_order(str(order_id))
        if not isinstance(last, dict):
            raise ZapriteError(0, "BAD_RESPONSE", "Order re-fetch was not an object.")
        view = _remember(last, "order", "watch")
        if is_paid(last):
            payload = {
                "ok": True,
                "paid": True,
                "polls": polls,
                "order": view,
                "id": view.get("id"),
                "status": view.get("status"),
                "checkoutUrl": view.get("checkoutUrl"),
                "webhook": WEBHOOK_DISCLOSURE,
                "session_notice": _notice(paid_notice(view)),
                "next": "Deliver the work. Then zaprite_update_order status COMPLETE. That step needs approval.",
            }
            payload.update(_session(kwargs))
            return payload
        now = clock()
        if now >= deadline:
            break
        sleeper(min(interval_s, max(0.0, deadline - now)))
    view = order_view(last or {})
    waiting = (
        f"Still {view.get('status') or 'unpaid'} on {view.get('id')}. "
        f"Checkout {view.get('checkoutUrl')}. Call zaprite_watch_order again to keep waiting."
    )
    payload = {
        "ok": True,
        "paid": False,
        "timed_out": True,
        "polls": polls,
        "order": view,
        "id": view.get("id"),
        "status": view.get("status"),
        "checkoutUrl": view.get("checkoutUrl"),
        "webhook": WEBHOOK_DISCLOSURE,
        "session_notice": _notice(waiting),
        "next": "Share checkoutUrl if the payer does not have it. Re-fetch later. Do not treat a webhook id as payment.",
    }
    payload.update(_session(kwargs))
    return payload


def _paused_watch(order_id: str, polls: int) -> dict:
    return {
        "ok": True,
        "paid": False,
        "paused": True,
        "polls": polls,
        "id": order_id,
        "webhook": WEBHOOK_DISCLOSURE,
        "session_notice": _notice(
            "Zaprite writes are paused, so this watch stopped. Lookups still work. /zaprite resume to continue."
        ),
        "next": "Nothing was cancelled or refunded. /zaprite resume, then zaprite_watch_order again.",
    }


def update_order(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_update_order", args, kwargs)
    if refused:
        return refused
    order_id = _pick(args, "order_id", "orderId", "id")
    status = _pick(args, "status")
    expires = _pick(args, "expires_at", "expiresAt")
    if not order_id:
        raise ValueError("order_id is required.")
    body: dict[str, Any] = {}
    if status:
        status = str(status).upper()
        if status == "PAID":
            # Money moving is a fact, not an assertion. An agent must never be able to
            # make an unpaid order look paid; the dashboard is where a person records cash.
            raise ValueError(
                "This cannot mark an order PAID. Payment status comes from Zaprite when money "
                "arrives. If you took cash or a cheque, mark it paid in the Zaprite dashboard."
            )
        if status != "COMPLETE":
            raise ValueError("status must be COMPLETE. Use the Zaprite dashboard for anything else.")
        body["status"] = status
    if "expires_at" in args or "expiresAt" in args:
        body["expiresAt"] = expires
    if not body:
        raise ValueError("Pass status COMPLETE or PAID, or expires_at. There is no general order edit.")
    order = _client().update_order(str(order_id), body)
    view = _remember(order, "order", f"updated {body}")
    notice = f"Order {view.get('id')} is now {view.get('status')}."
    payload = {
        "ok": True,
        "order": view,
        "session_notice": _notice(notice),
        "note": "PATCH only sets COMPLETE or expiresAt. It cannot set PAID. It does not refund, void an invoice, or edit line items.",
    }
    payload.update(_session(kwargs))
    return payload


def charge_profile(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_charge_profile", args, kwargs)
    if refused:
        return refused
    order_id = _pick(args, "order_id", "orderId")
    profile_id = _pick(args, "payment_profile_id", "paymentProfileId")
    if not order_id or not profile_id:
        raise ValueError("order_id and payment_profile_id are required. Profiles come from zaprite_get_contact.")
    if "send_receipt" not in args and "sendReceiptToCustomer" not in args:
        raise ValueError("send_receipt must be true or false. Zaprite requires the field. It emails the customer when true.")
    existing = _client().get_order(str(order_id))
    if isinstance(existing, dict):
        limited = over_limit(existing.get("totalAmount"), existing.get("currency"))
        if limited:
            return limited
    send = bool(_pick(args, "send_receipt", "sendReceiptToCustomer"))
    order = _client().charge(
        {
            "orderId": str(order_id),
            "paymentProfileId": str(profile_id),
            "sendReceiptToCustomer": send,
        }
    )
    view = _remember(order, "charge", "charged profile")
    payload = {
        "ok": True,
        "order": view,
        "paid": is_paid(order),
        "session_notice": _notice(
            paid_notice(view) if is_paid(order) else f"Charge submitted. {view.get('id')} is {view.get('status')}."
        ),
        "rails": "A saved profile only works when that connection is enabled on the order checkout.",
    }
    payload.update(_session(kwargs))
    return payload


def create_contact(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_create_contact", args, kwargs)
    if refused:
        return refused
    legal = _pick(args, "legal_name", "legalName")
    email = _pick(args, "email")
    if not legal or not email:
        raise ValueError("legal_name and email are required.")
    body: dict[str, Any] = {"legalName": str(legal), "email": str(email)}
    for src, dest in (
        ("contact_name", "contactName"),
        ("display_name", "displayName"),
        ("internal_note", "internalNote"),
        ("tax_id", "taxId"),
        ("default_currency", "defaultCurrency"),
    ):
        value = _pick(args, src, dest)
        if value is not None:
            body[dest] = value
    address = _pick(args, "billing_address", "billingAddress")
    if isinstance(address, dict):
        body["billingAddress"] = address
    contact = _client().create_contact(body)
    return {"ok": True, "contact": contact_view(contact) if isinstance(contact, dict) else contact}


def get_contact(args: dict, **kwargs: Any) -> dict:
    contact_id = _pick(args, "contact_id", "contactId", "id")
    if not contact_id:
        raise ValueError("contact_id is required.")
    contact = _client().get_contact(str(contact_id))
    view = contact_view(contact) if isinstance(contact, dict) else contact
    return {
        "ok": True,
        "contact": view,
        "note": "paymentProfiles[].id is what zaprite_charge_profile needs. pluginSlug is the only connection hint the API returns.",
    }


def list_contacts(args: dict, **kwargs: Any) -> dict:
    params = _params(
        [
            ("page", _pick(args, "page") or 1),
            ("query", _pick(args, "query", "search")),
            ("email", _pick(args, "email")),
        ]
    )
    data = _client().list_contacts(params)
    items = data.get("items") if isinstance(data, dict) else []
    views = [contact_view(item) for item in items or [] if isinstance(item, dict)]
    return {"ok": True, "contacts": views, "meta": data.get("meta") if isinstance(data, dict) else None}


_CONTACT_PUT_FIELDS = (
    "contactName",
    "displayName",
    "legalName",
    "email",
    "internalNote",
    "taxId",
    "defaultCurrency",
    "billingAddress",
)


def update_contact(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_update_contact", args, kwargs)
    if refused:
        return refused
    contact_id = _pick(args, "contact_id", "contactId", "id")
    if not contact_id:
        raise ValueError("contact_id is required.")
    overlay: dict[str, Any] = {}
    for src, dest in (
        ("legal_name", "legalName"),
        ("email", "email"),
        ("contact_name", "contactName"),
        ("display_name", "displayName"),
        ("internal_note", "internalNote"),
        ("tax_id", "taxId"),
        ("default_currency", "defaultCurrency"),
    ):
        value = _pick(args, src, dest)
        if value is not None:
            overlay[dest] = value
    address = _pick(args, "billing_address", "billingAddress")
    if isinstance(address, dict):
        overlay["billingAddress"] = address
    if not overlay:
        raise ValueError("Provide at least one field to change. Contacts update with PUT; this plugin fetches first and merges.")
    existing = _client().get_contact(str(contact_id))
    if not isinstance(existing, dict):
        raise ValueError("Could not fetch the contact before PUT.")
    body: dict[str, Any] = {}
    for dest in _CONTACT_PUT_FIELDS:
        if dest in existing:
            body[dest] = existing[dest]
    body.update(overlay)
    if not str(body.get("legalName") or "").strip():
        raise ValueError("legal_name is required on PUT. Pass legal_name; the fetched contact did not have one.")
    contact = _client().update_contact(str(contact_id), body)
    return {
        "ok": True,
        "contact": contact_view(contact) if isinstance(contact, dict) else contact,
        "merged": True,
        "note": "Contacts update with PUT. This plugin fetched the contact first and merged your fields so other values are not wiped.",
    }


def delete_contact(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_delete_contact", args, kwargs)
    if refused:
        return refused
    contact_id = _pick(args, "contact_id", "contactId", "id")
    if not contact_id:
        raise ValueError("contact_id is required.")
    _client().delete_contact(str(contact_id))
    return {"ok": True, "deleted": str(contact_id)}


def report(args: dict, **kwargs: Any) -> dict:
    include_pending = _include_pending(args)
    params = _params(
        [
            ("page", 1),
            ("includePending", "true" if include_pending else None),
            ("sortBy", "createdAt"),
            ("sortOrder", "desc"),
        ]
    )
    data = _client().list_orders(params)
    items = data.get("items") if isinstance(data, dict) else []
    counts: dict[str, int] = {}
    by_type: dict[str, int] = {}
    owed: dict[str, int] = {}
    open_links: dict[str, int] = {}
    recent = []
    for order in items or []:
        if not isinstance(order, dict):
            continue
        status = str(order.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
        kind = str(order.get("orderType") or "unknown")
        by_type[kind] = by_type.get(kind, 0) + 1
        if status.upper() in {"PENDING", "OVERDUE"}:
            currency = str(order.get("currency") or "")
            amount = int(order.get("totalAmount") or 0)
            bucket = owed if kind in {"invoice", "apiInvoice"} else open_links
            bucket[currency] = bucket.get(currency, 0) + amount
        if len(recent) < 8:
            recent.append(order_view(order))
    paid = sum(counts.get(name, 0) for name in ("PAID", "OVERPAID"))
    completed = sum(counts.get(name, 0) for name in ("COMPLETE",))
    return {
        "ok": True,
        "by_status": counts,
        "by_type": by_type,
        "owed": owed,
        "open_links": open_links,
        "paid_on_this_page": paid,
        "completed_on_this_page": completed,
        "recent": recent,
        "meta": data.get("meta") if isinstance(data, dict) else None,
        "local_orders_tracked": store.count_orders(),
        "note": "First page of orders, not an accounting export. Zaprite has no reports API. Pending is included unless you set include_pending to false. Paid counts PAID and OVERPAID only; COMPLETE means work done, not money.",
    }


def list_overdue(args: dict, **kwargs: Any) -> dict:
    found = []
    pages = 0
    truncated = False
    for order_type in ("invoice", "apiInvoice"):
        for page in range(1, OVERDUE_MAX_PAGES + 1):
            pages += 1
            data = _client().list_orders(
                _params([("page", page), ("type", order_type), ("includePending", "true")])
            )
            items = data.get("items") if isinstance(data, dict) else []
            meta = data.get("meta") if isinstance(data, dict) else {}
            for order in items or []:
                if not isinstance(order, dict):
                    continue
                invoice = order.get("invoice") if isinstance(order.get("invoice"), dict) else None
                if invoice and invoice.get("status") == "OVERDUE":
                    found.append(order_view(order))
            page_count = int((meta or {}).get("pagesCount") or 1)
            if page >= page_count:
                break
            if page == OVERDUE_MAX_PAGES:
                truncated = True
    return {
        "ok": True,
        "overdue": found,
        "count": len(found),
        "pages_scanned": pages,
        "truncated": truncated,
        "note": "OVERDUE is the invoice status on the order. There is no invoice-status filter, so this scans invoice and apiInvoice pages. There is no send-reminder API; share checkoutUrl.",
    }


def list_webhooks(args: dict, **kwargs: Any) -> dict:
    page = int(_pick(args, "page") or 1)
    data = _client().list_webhooks(page)
    return {
        "ok": True,
        "webhooks": data,
        "events": list(WEBHOOK_EVENTS),
        "webhook": WEBHOOK_DISCLOSURE,
        "note": "This plugin does not run a receiver. Register your own HTTPS URL with zaprite_create_webhook, then re-fetch the order. Payloads stay id-only and unsigned.",
    }


def create_webhook(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_create_webhook", args, kwargs)
    if refused:
        return refused
    url = _pick(args, "url")
    if not url:
        raise ValueError("url is required. This plugin does not run a webhook server; point Zaprite at yours.")
    parsed = urlparse(str(url).strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https":
        pass
    elif parsed.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}:
        pass
    else:
        raise ValueError("webhook url must be https (http is accepted only for localhost tests).")
    if not parsed.netloc:
        raise ValueError("webhook url must include a host.")
    body: dict[str, Any] = {"url": str(url).strip()}
    label = _pick(args, "label")
    if label is not None:
        body["label"] = str(label)
    created = _client().create_webhook(body)
    endpoint_id = created.get("id") if isinstance(created, dict) else None
    return {
        "ok": True,
        "id": endpoint_id,
        "webhook_endpoint": created,
        "webhook": WEBHOOK_DISCLOSURE,
        "note": "Registered your URL. This plugin does not receive those posts. Re-fetch the order and treat GET as the source of truth. The 'webhook' field is the disclosure text, not the endpoint object — use webhook_endpoint or id.",
    }


def delete_webhook(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_delete_webhook", args, kwargs)
    if refused:
        return refused
    webhook_id = _pick(args, "webhook_id", "webhookId", "id")
    if not webhook_id:
        raise ValueError("webhook_id is required.")
    _client().delete_webhook(str(webhook_id))
    return {
        "ok": True,
        "deleted": str(webhook_id),
        "webhook": WEBHOOK_DISCLOSURE,
    }


def list_payment_links(args: dict, **kwargs: Any) -> dict:
    params = _params(
        [
            ("page", _pick(args, "page") or 1),
            ("search", _pick(args, "search")),
            ("type", _pick(args, "type")),
            ("published", _pick(args, "published")),
        ]
    )
    data = _client().list_payment_links(params)
    return {
        "ok": True,
        "payment_links": data,
        "note": "Read-only. This API cannot create a payment link, product, event, POS terminal, or ticket type.",
    }


def get_payment_link(args: dict, **kwargs: Any) -> dict:
    payment_link_id = _pick(args, "payment_link_id", "paymentLinkId", "id")
    if not payment_link_id:
        raise ValueError("payment_link_id is required.")
    link = _client().get_payment_link(str(payment_link_id))
    return {
        "ok": True,
        "payment_link": link,
        "note": "Read-only. Ticket types live on payment_link items. Event create is not in the API.",
    }


def list_tickets(args: dict, **kwargs: Any) -> dict:
    status = _pick(args, "status")
    if isinstance(status, str):
        status = [status]
    params = _params(
        [
            ("page", _pick(args, "page") or 1),
            ("paymentLinkId", _pick(args, "payment_link_id", "paymentLinkId")),
            ("paymentLinkItemId", _pick(args, "payment_link_item_id", "paymentLinkItemId")),
            ("status", status),
        ]
    )
    data = _client().list_tickets(params)
    return {
        "ok": True,
        "tickets": data,
        "note": "Ticket URLs are secrets. Anyone with the URL can view the ticket. Event creation is not in the API.",
    }


def get_ticket(args: dict, **kwargs: Any) -> dict:
    ticket_id = _pick(args, "ticket_id", "ticketId", "id")
    if not ticket_id:
        raise ValueError("ticket_id is required.")
    ticket = _client().get_ticket(str(ticket_id))
    return {"ok": True, "ticket": ticket}


def issue_tickets(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_issue_tickets", args, kwargs)
    if refused:
        return refused
    item_id = _pick(args, "payment_link_item_id", "paymentLinkItemId")
    tickets = _pick(args, "tickets")
    if not item_id or not isinstance(tickets, list) or not tickets:
        raise ValueError("payment_link_item_id and tickets are required. Find the ticket type with zaprite_list_payment_links.")
    if "decrement_stock" not in args and "decrementStock" not in args:
        raise ValueError("decrement_stock must be true or false.")
    body: dict[str, Any] = {
        "paymentLinkItemId": str(item_id),
        "tickets": tickets,
        "decrementStock": bool(_pick(args, "decrement_stock", "decrementStock")),
        "sendTicketsToCustomer": bool(_pick(args, "send_tickets", "sendTicketsToCustomer") or False),
    }
    owner = _pick(args, "persistent_owner_email", "persistentOwnerEmail")
    if owner:
        body["persistentOwnerEmail"] = owner
    key = _pick(args, "idempotency_key", "idempotencyKey")
    if key:
        body["idempotencyKey"] = str(key)
    issued = _client().issue_tickets(body)
    return {
        "ok": True,
        "tickets": issued,
        "fee_note": (
            "Standard ticket fees apply to issued tickets (1% + $3 per ticket on the ticket product). "
            "send_tickets defaults to false here so this call does not email attendees unless you set it true."
        ),
    }


def ticket_activity(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_ticket_activity", args, kwargs)
    if refused:
        return refused
    ticket_id = _pick(args, "ticket_id", "ticketId", "id")
    action = _pick(args, "action")
    if not ticket_id or not action:
        raise ValueError("ticket_id and action are required. action is CHECK_IN, SCAN, CANCEL, or REACTIVATE.")
    action = str(action).upper()
    if action not in {"CHECK_IN", "SCAN", "CANCEL", "REACTIVATE"}:
        raise ValueError("action must be CHECK_IN, SCAN, CANCEL, or REACTIVATE.")
    body: dict[str, Any] = {"action": action}
    event_id = _pick(args, "payment_link_id", "paymentLinkId")
    if event_id:
        body["paymentLinkId"] = str(event_id)
    if _pick(args, "force") is not None:
        body["force"] = bool(_pick(args, "force"))
    if _pick(args, "update_stock", "updateStock") is not None:
        body["updateStock"] = bool(_pick(args, "update_stock", "updateStock"))
    ticket = _client().ticket_activity(str(ticket_id), body)
    return {"ok": True, "ticket": ticket, "action": action}


JOBS_NOTE = (
    "Here: bills and invoices, links a customer can pay, contacts, ticket check-in, payment alerts.\n"
    "Not here, because Zaprite has no API for them: payment links, recurring invoices, "
    "payment requests, POS, transactions, payment settings, connected accounts, branding.\n"
    "Those happen in the dashboard."
)


def doctor(args: dict, **kwargs: Any) -> dict:
    """Read-only honesty check. The empty POST cannot create an order."""
    present = secrets.key_is_configured()
    known_org = _active_org_id()
    links = org_links(known_org)
    base = {
        "key_present": present,
        "base_url": runtime.settings.base_url,
        "spend_limit_cents": runtime.settings.spend_limit_cents,
        "notify": runtime.settings.notify,
        "local_orders_tracked": store.count_orders(),
        "connections_api": False,
        "connections_note": RAILS_NOTE,
        "branding_api": False,
        "branding": BRANDING_NOTE,
        "org_slug_discovered": False,
        "documented_org_slug": "default",
        "org_id_seen": known_org,
        "org_links_use_org_id": bool(known_org),
        "org_slug_note": ORG_SLUG_NOTE,
        "deep_links": links,
        "sign_in": SIGN_IN_URL,
        "environment": ENVIRONMENT_NOTE,
        "context_first": CONTEXT_FIRST,
        "invoice_email": INVOICE_EMAIL_NOTE,
        "webhook": WEBHOOK_DISCLOSURE,
        "webhook_events": list(WEBHOOK_EVENTS),
        "link_note": ORG_SLUG_NOTE,
        "jobs": JOBS_NOTE,
        "not_here": [
            "payment links", "recurring invoices", "payment requests", "pos",
            "transactions", "checkout settings", "connections", "branding",
        ],
    }
    if not present:
        base.update(
            {
                "ok": False,
                "key_mode": "missing",
                "setup": _setup_steps(),
            }
        )
        return base
    client = _client()
    try:
        hooks = client.list_webhooks(1)
        orders = client.list_orders(_params([("page", 1), ("includePending", "true")]))
    except ZapriteError as exc:
        mode = "invalid" if exc.status == 401 or exc.code == "UNAUTHORIZED" else "unreachable"
        store.set_meta("key_mode", mode)
        base.update({"ok": False, "key_mode": mode, "error": exc.to_dict(), "setup": _setup_steps()})
        return base
    mode = _probe_key_mode(client)
    store.set_meta("key_mode", mode)
    items = orders.get("items") if isinstance(orders, dict) else []
    org_id = known_org
    if items and isinstance(items[0], dict):
        org_id = items[0].get("orgId") or org_id
    if not org_id:
        hook_items_probe = hooks.get("items") if isinstance(hooks, dict) else []
        if hook_items_probe and isinstance(hook_items_probe[0], dict):
            org_id = hook_items_probe[0].get("orgId") or org_id
    _remember_org_id(org_id)
    links = org_links(org_id)
    hook_items = hooks.get("items") if isinstance(hooks, dict) else []
    base.update(
        {
            "ok": mode in {"full", "read_only"},
            "key_mode": mode,
            "org_id_seen": org_id,
            "org_links_use_org_id": bool(org_id),
            "deep_links": links,
            "orders_meta": orders.get("meta") if isinstance(orders, dict) else None,
            "webhook_count": len(hook_items or []),
            "key_probe": (
                "POST /v1/orders with an empty body. Currency is required, so a full key returns "
                "400 BAD_REQUEST and creates nothing. A read-only key returns 403 FORBIDDEN."
            ),
            "writes": (
                "Reports and lookups work."
                if mode == "read_only"
                else "This key can create orders. Money tools still wait for a human approval and fail closed in cron."
            ),
            "setup": _setup_steps(),
            "next": [
                "Confirm whether this key's org is sandbox (test) or live.",
                "If a needed payment rail is missing, open deep_links.connections (human setup).",
                "Logo, accent color, and display name: a person saves Settings → Profile (deep_links.profile). This plugin cannot set them. After Profile is saved, open a checkoutUrl to preview.",
                "Ask for any missing recipient name, email, service, and amount before creating.",
                "Create the order or invoice, share checkoutUrl, then zaprite_watch_order until Paid.",
            ],
        }
    )
    return base


def _probe_key_mode(client: ZapriteClient) -> str:
    try:
        created = client.create_order({})
    except ZapriteError as exc:
        if exc.status == 400 or exc.code == "BAD_REQUEST":
            return "full"
        if exc.status == 403 or exc.code == "FORBIDDEN":
            return "read_only"
        if exc.status == 401 or exc.code == "UNAUTHORIZED":
            return "invalid"
        return "unknown"
    if isinstance(created, dict) and created.get("id"):
        _remember(created, "order", "unexpected empty-body create during doctor")
    return "unexpected_write"


# Exact gap name agents must pass for a logo, accent color, or display name.
# Aliases and a logo/color note on gap "other" resolve here so that ask is not
# sent to Checkouts or Connections.
_BRANDING_GAP = "branding_profile"
_EXPLICIT_NON_BRANDING_GAPS = frozenset({"lightning_discount", "checkout_methods"})
_BRANDING_GAP_ALIASES = frozenset(
    {
        "branding_profile",
        "branding",
        "logo",
        "logos",
        "profile",
        "accent",
        "accent_color",
        "accent_colour",
        "display_name",
        "add_my_logo",
        "my_logo",
        "brand_color",
        "brand_colour",
        "logo_color",
        "logo_colour",
        "color",
        "colour",
    }
)
_BRANDING_INTENT = re.compile(
    r"\b(logos?|branding|branded|accent(?:\s+colou?rs?)?|display\s+name|brand\s+colou?rs?)\b",
    re.IGNORECASE,
)


def _gap_token(value: str | None) -> str:
    raw = (value or "").strip().lower()
    return re.sub(r"[\s\-]+", "_", raw)


def _resolve_bridge_gap(gap: str | None, note: str) -> str:
    """Pick a typed gap. Logo/color asks become branding_profile, including gap other."""
    token = _gap_token(gap)
    if token in _EXPLICIT_NON_BRANDING_GAPS:
        return token
    if token in _BRANDING_GAP_ALIASES or _BRANDING_INTENT.search(token.replace("_", " ")):
        return _BRANDING_GAP
    if _BRANDING_INTENT.search(note or ""):
        return _BRANDING_GAP
    if not token:
        return "lightning_discount"
    return "other"


def bridge_handoff(args: dict, **kwargs: Any) -> dict:
    refused = refuse_write("zaprite_bridge_handoff", args, kwargs)
    if refused:
        return refused
    outcome = _pick(args, "outcome")
    handoff_id = _pick(args, "handoff_id", "handoffId")
    if outcome and handoff_id:
        found = store.set_handoff_outcome(str(handoff_id), str(outcome)[:1000])
        return {
            "ok": found,
            "handoff_id": handoff_id,
            "recorded_outcome": bool(found),
            "browser": "not_used",
            "note": "Recorded what a person said they changed. The plugin did not open the dashboard.",
        }
    note_in = str(_pick(args, "note") or "")
    gap = _resolve_bridge_gap(None if _pick(args, "gap") is None else str(_pick(args, "gap")), note_in)
    links = _active_links()
    known = {
        "lightning_discount": (
            "Bitcoin or Lightning discount on a checkout is dashboard-only. "
            "Open Checkouts, edit the checkout, set the discount at the top level, "
            "and copy customCheckoutId back. The next zaprite_create_order can pass custom_checkout_id."
        ),
        "checkout_methods": (
            "Which rails a checkout offers is dashboard-only. Connect the rail first, "
            "then enable it on the checkout. The API cannot write either step."
        ),
        "branding_profile": (
            "Logo, accent color, and display name are Settings → Profile. "
            "API-created invoices and checkouts inherit them. "
            "This plugin cannot set a logo or a color. "
            f"Guide: {links['branding_guide']}"
        ),
        "other": "Describe the dashboard change in note. A person has to make it.",
    }
    if gap == "branding_profile":
        url = links["profile"]
        help_url = links["branding_guide"]
    elif gap == "checkout_methods":
        url = links["connections"]
        help_url = links["connections_help"]
    else:
        url = links["checkouts"]
        help_url = links["connections_help"]
    new_id = "zh_" + uuid.uuid4().hex[:12]
    note = note_in or known[gap]
    store.add_handoff(new_id, gap, url, note)
    steps = [
        "A person opens the URL while logged into the Zaprite org.",
        known[gap],
    ]
    if gap == "branding_profile":
        steps.append(
            "They save the logo, accent color, and display name. "
            "API-created invoices and checkouts inherit that Profile."
        )
        steps.append("After they save, open a checkoutUrl from the next invoice or order to preview.")
    else:
        steps.append("They tell you the result, including customCheckoutId if they created a checkout.")
    steps.append("Call zaprite_bridge_handoff again with handoff_id and outcome to record it.")
    steps.append("Leave the dashboard to the person. This plugin does not drive the browser.")
    payload = {
        "ok": True,
        "handoff_id": new_id,
        "gap": gap,
        "browser": "not_used",
        "approval": "required",
        "unsupervised_browser": False,
        "url": url,
        "help": help_url,
        "steps": steps,
        "session_notice": _notice(
            f"Dashboard step needed for {gap}. Open {url}. I will not click through it."
        ),
    }
    if gap == "branding_profile":
        payload["guide"] = links["branding_guide"]
    return payload


def sovereign_rails(args: dict, **kwargs: Any) -> dict:
    """Guidance only. Does not connect a wallet and does not call a write API."""
    return {
        "ok": True,
        "custody": "Zaprite is non-custodial. Funds land in the wallets the merchant already connected.",
        "human_first": (
            "A person creates the organization and the API key. After that, open rails "
            "are a dashboard paste: a Lightning Address, or an xpub the merchant verifies "
            "at index 0. This plugin cannot submit either value."
        ),
        "then": [
            "Connect Lightning Address or an xpub (Coldcard, Sparrow, Ledger, Trezor, and the branded xpub plugins) under Connections.",
            "Confirm the rail is enabled on the checkout you pass as custom_checkout_id.",
            "Create an order with zaprite_create_order and, if a payer wants bitcoin in chat, zaprite_create_quote.",
            "Hand paymentUrl (bolt11 or bitcoin:) to the paying agent. They pay only if a person asked them to pay, from a wallet they control.",
            "zaprite_watch_order re-fetches until PAID. That is the receipt. There is no signature on the webhook.",
        ],
        "deep_links": {
            "connections": _active_links()["connections"],
            "connections_help": _active_links()["connections_help"],
            "lightning_address_notes": _active_links()["lightning_address_notes"],
            "btcpay": _active_links()["btcpay"],
            "checkouts": _active_links()["checkouts"],
            "sign_in": SIGN_IN_URL,
        },
        "closer": (
            "One merchant, every rail they connected, and a checkout URL any payer can open. "
            "When the payer is another agent, Lightning and on-chain are the open rail: "
            "quote, pay, re-fetch, done. Card and bank stay on that same checkout for people."
        ),
        "not_this_plugin": [
            "No connections list or connect call.",
            "No checkout write, so no silent Lightning discount.",
            "No remote MCP spend. This plugin receives. It does not pay on the merchant's behalf.",
        ],
    }


def _setup_steps() -> list[str]:
    links = _active_links()
    return [
        f"Sign in or sign up at {SIGN_IN_URL}.",
        "Open the organization you mean: sandbox for test payments with no real money, or live for real checkouts.",
        f"Connect the rails you want (card, bank, Lightning, on-chain bitcoin, stablecoins): {links['connections']}. Only connected rails appear on checkout. There is no connections API.",
        (
            f"Logo, accent color, and display name are Settings → Profile: {links['profile']}. "
            "API-created invoices and checkouts inherit them. This plugin cannot set a logo or a color. "
            f"Guide: {links['branding_guide']}. After Profile is saved, open a checkoutUrl to preview."
        ),
        f"Create an API key: {links['api_keys']}. Full access to get paid; read-only for reports only.",
        "Paste it into Hermes → Tools → Zaprite. Never into this chat.",
        "Run zaprite_doctor. Confirm test vs live from which org the key belongs to, then ask for any missing name, email, service, and amount before acting.",
    ]


def local_status() -> dict:
    return {
        "plugin": "zaprite",
        "key_present": secrets.key_is_configured(),
        "key_mode": store.get_meta("key_mode") or "unchecked",
        "base_url": runtime.settings.base_url,
        "spend_limit_cents": runtime.settings.spend_limit_cents,
        "notify": runtime.settings.notify,
        "writes_paused": writes_paused(),
        "pending_approvals": pending_count(),
        "local_orders": store.list_local(5),
        "local_orders_tracked": store.count_orders(),
        "recent_handoffs": store.recent_handoffs(3),
        "setup": _setup_steps(),
        "rails": RAILS_NOTE,
    }


def setup(args: dict, **kwargs: Any) -> dict:
    """First run. Account, key, rails, identity — local state, no HTTP without a key."""
    from . import onboarding

    if _truthy(args, "skip_brand", "skip_branding"):
        return onboarding.skip_brand()
    if _truthy(args, "skip", "skip_rails"):
        return onboarding.skip()

    brand_name = _pick(args, "business_name", "businessName")
    brand_color = _pick(args, "brand_color", "brandColor")
    logo = _pick(args, "logo", "logo_path", "logoPath")
    assets = _pick(args, "assets")
    if brand_name or brand_color or logo or assets:
        if isinstance(assets, str):
            assets = [part.strip() for part in assets.split(",") if part.strip()]
        return onboarding.set_brand(
            business_name=str(brand_name) if brand_name else None,
            brand_color=str(brand_color) if brand_color else None,
            logo=str(logo) if logo else None,
            assets=list(assets) if assets else None,
        )

    rails = _pick(args, "rails", "confirm_rails")
    if rails:
        if isinstance(rails, str):
            rails = [part for part in re.split(r"[,\s]+", rails) if part]
        return onboarding.confirm(list(rails))
    return onboarding.state(secrets.key_is_configured(), store.get_meta("key_mode"), _active_org_id())
