"""Small, stable views of Zaprite orders for the model and the local ledger."""

from __future__ import annotations

from typing import Any

from .constants import INVOICE_PAID, ORDER_PAID

ZERO_DECIMAL = frozenset({"JPY", "KRW", "VND", "CLP", "ISK", "UGX"})


def format_amount(amount: Any, currency: Any) -> str:
    if amount is None or currency is None:
        return "an amount"
    code = str(currency).upper()
    try:
        number = int(amount)
    except (TypeError, ValueError):
        return f"{amount} {code}"
    if code in {"BTC", "LBTC"}:
        return f"{number} sats"
    if code in ZERO_DECIMAL:
        return f"{number} {code}"
    sign = "-" if number < 0 else ""
    cents = abs(number)
    return f"{sign}{cents // 100}.{cents % 100:02d} {code}"


def order_view(order: dict) -> dict[str, Any]:
    invoice = order.get("invoice") if isinstance(order.get("invoice"), dict) else None
    contact = order.get("contact") if isinstance(order.get("contact"), dict) else None
    transactions = []
    for tx in order.get("transactions") or []:
        if not isinstance(tx, dict):
            continue
        transactions.append(
            {
                "method": tx.get("method"),
                "status": tx.get("status"),
                "amount": tx.get("amount"),
                "currency": tx.get("currency"),
            }
        )
    return {
        "id": order.get("id"),
        "status": order.get("status"),
        "invoice_status": invoice.get("status") if invoice else None,
        "invoice_number": invoice.get("number") if invoice else None,
        "checkoutUrl": order.get("checkoutUrl"),
        "totalAmount": order.get("totalAmount"),
        "currency": order.get("currency"),
        "label": order.get("label"),
        "orderType": order.get("orderType"),
        "externalUniqId": order.get("externalUniqId"),
        "paidAt": order.get("paidAt"),
        "expiresAt": order.get("expiresAt"),
        "contactId": contact.get("id") if contact else None,
        "receiptPdfUrl": order.get("receiptPdfUrl"),
        "transactions": transactions,
    }


def is_paid(order: dict) -> bool:
    view = order if "invoice_status" in order else order_view(order)
    if view.get("status") in ORDER_PAID:
        return True
    if view.get("invoice_status") in INVOICE_PAID:
        return True
    return False


def paid_notice(view: dict) -> str:
    amount = format_amount(view.get("totalAmount"), view.get("currency"))
    status = view.get("status") or "PAID"
    return (
        f"Paid. {amount} on {view.get('id')} is {status}. "
        f"Checkout {view.get('checkoutUrl')}. "
        "Next: deliver the work, then mark the order complete."
    )


def checkout_notice(view: dict) -> str:
    amount = format_amount(view.get("totalAmount"), view.get("currency"))
    return (
        f"Checkout is ready for {amount}. Send {view.get('checkoutUrl')} to the payer. "
        "Card, bank, Lightning, on-chain bitcoin, and stablecoins appear only when "
        "this org has already connected them."
    )


def contact_view(contact: dict) -> dict[str, Any]:
    profiles = []
    for profile in contact.get("paymentProfiles") or []:
        if not isinstance(profile, dict):
            continue
        connection = profile.get("connection") if isinstance(profile.get("connection"), dict) else {}
        profiles.append(
            {
                "id": profile.get("id"),
                "method": profile.get("method"),
                "label": profile.get("label"),
                "pluginSlug": connection.get("pluginSlug"),
                "expiresAt": profile.get("expiresAt"),
            }
        )
    return {
        "id": contact.get("id"),
        "legalName": contact.get("legalName"),
        "email": contact.get("email"),
        "displayName": contact.get("displayName"),
        "defaultCurrency": contact.get("defaultCurrency"),
        "paymentProfiles": profiles,
    }
