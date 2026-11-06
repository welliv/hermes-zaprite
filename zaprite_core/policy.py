"""Approval, cron, spend limit, pause, and read-only key policy.

pre_tool_call {"action": "approve"} asks Hermes to put the call on the human
approval gate. It does not grant the call. The rule_key is one-time, so a
session or always answer cannot cover the next write.

post_approval_response records that a person answered this exact prompt.
The handler sends the request only after it consumes that record. YOLO,
approvals off, smart (model) approval, cron, and a skipped prompt never
produce it, so those paths fail closed before HTTP.

{"action": "block"} refuses the call. Unattended cron is blocked in the hook
and again in the handler. /zaprite kill pauses writes and drops pending
approvals.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from . import runtime, store
from .constants import GATED_TOOLS, WRITE_TOOLS


UNATTENDED_MESSAGE = (
    "Zaprite refused this write because the run is unattended (cron or no one "
    "to approve it). Creating orders, invoices, quotes, charges, tickets, "
    "contact edits, and dashboard handoffs fail closed. Run them from an "
    "interactive Hermes session."
)

INVALID_KEY_MESSAGE = (
    "Zaprite rejected this key. It may be revoked, or from a different account.\n"
    "Make a new one with Full access, then paste it into Hermes — Tools → Zaprite."
)

READ_ONLY_MESSAGE = (
    "That key is read-only, so I can't take payments with it. Reports and lookups "
    "still work. Make one with Full access to get paid: https://app.zaprite.com"
)

PAUSED_MESSAGE = (
    "Zaprite writes are paused. Nothing new will be created, charged or deleted.\n"
    "Lookups still work. This did not cancel or refund anything already at Zaprite.\n"
    "/zaprite resume to allow writes again — the next one asks again."
)

NO_APPROVAL_MESSAGE = (
    "Refused before any request was sent. This Zaprite write needs a fresh "
    "human approval for this exact call. A previous session or always answer "
    "does not cover the next one. YOLO, approvals off, smart (model) approval, "
    "cron, and a skipped prompt do not count. Nothing was created, charged, "
    "or deleted."
)

HUMAN_YES = frozenset({"once", "session", "always"})
RULE_PREFIX = "zaprite:gate:"
APPROVAL_TTL_SECONDS = 600

_lock = threading.Lock()
_pending: dict[str, "Pending"] = {}
_memory_paused = False
_tls = threading.local()
_now: Callable[[], float] = time.monotonic


@dataclass
class Pending:
    ref: str
    scope: str
    tool: str
    fingerprint: str
    created: float
    human_approved: bool = False
    choice: str = ""


def is_unattended(kwargs: dict | None = None) -> bool:
    kwargs = kwargs or {}
    if kwargs.get("unattended") is True:
        return True
    plugin_ctx = runtime.ctx
    if plugin_ctx is None:
        return False
    probe = getattr(plugin_ctx, "current_cron_execution", None)
    if not callable(probe):
        return False
    try:
        return probe() is not None
    except Exception:
        # If the host cannot tell us, fail closed for money tools.
        return True


def writes_paused() -> bool:
    if _memory_paused:
        return True
    try:
        return store.get_meta("writes_paused") == "1"
    except Exception:
        return True


def pending_count() -> int:
    with _lock:
        _expire_locked(_now())
        return len(_pending)


def pause_writes() -> int:
    """Pause every Zaprite write and drop pending approvals. Returns how many were dropped."""
    global _memory_paused
    with _lock:
        count = len(_pending)
        _pending.clear()
        _memory_paused = True
    try:
        store.set_meta("writes_paused", "1")
    except Exception:
        # The in-memory flag already fail-closes this process.
        pass
    return count


def resume_writes() -> None:
    """Lift the pause. Does not restore approvals that kill cleared."""
    global _memory_paused
    _memory_paused = False
    try:
        store.delete_meta("writes_paused")
    except Exception:
        _memory_paused = True
        raise
    if store.get_meta("writes_paused") == "1":
        _memory_paused = True
        raise RuntimeError("Zaprite could not clear the pause flag.")


def pre_tool_call(tool_name: str, args: dict | None = None, task_id: str | None = None, **kwargs: Any) -> dict | None:
    """Hook for every tool. Only Zaprite's own writes are touched.

    Hermes may call this positionally (tool_name, args, task_id) or by keyword.
    {"action": "approve"} escalates to the human approval gate. It does not
    grant the call. {"action": "block"} refuses it.
    """
    if tool_name not in WRITE_TOOLS:
        return None
    if writes_paused():
        return {"action": "block", "message": PAUSED_MESSAGE}
    if is_unattended(kwargs):
        return {"action": "block", "message": UNATTENDED_MESSAGE}
    if tool_name not in GATED_TOOLS:
        return None
    args = args if isinstance(args, dict) else {}
    amount = _amount_hint(tool_name, args)
    limited = over_limit(amount, args.get("currency"))
    if limited:
        return {"action": "block", "message": limited["error"]["message"]}
    ref = secrets.token_hex(6)
    scope = _scope(kwargs, task_id)
    with _lock:
        _expire_locked(_now())
        _pending[ref] = Pending(
            ref=ref,
            scope=scope,
            tool=tool_name,
            fingerprint=_fingerprint(tool_name, args),
            created=_now(),
        )
    detail = _approval_detail(tool_name, args)
    return {
        "action": "approve",
        "message": (
            f"{detail} This calls api.zaprite.com. "
            "Approve only if you want Zaprite to do it. "
            "A denial stops the call. "
            "Session and always do not cover the next write. "
            f"ref {ref}"
        ),
        "rule_key": f"{RULE_PREFIX}{ref}",
    }


def post_approval_response(
    choice: str = "",
    pattern_key: str = "",
    pattern_keys: Any = None,
    description: str = "",
    **kwargs: Any,
) -> None:
    """Record a human yes for the one-time rule, or drop the pending entry.

    Observer only. Hermes ignores the return value. Smart approvals
    (decided_by set, or surface smart) are not a human yes.
    """
    ref = _ref_from_approval(pattern_key, pattern_keys, description, kwargs.get("rule_key"))
    if not ref:
        return None
    human = (
        choice in HUMAN_YES
        and not kwargs.get("decided_by")
        and kwargs.get("surface") != "smart"
    )
    with _lock:
        pending = _pending.get(ref)
        if pending is None:
            return None
        if _now() - pending.created > APPROVAL_TTL_SECONDS:
            _pending.pop(ref, None)
            return None
        if human:
            pending.human_approved = True
            pending.choice = choice
        else:
            _pending.pop(ref, None)
    return None


def refuse_write(tool_name: str, args: dict, kwargs: dict | None = None) -> dict | None:
    if tool_name in WRITE_TOOLS and writes_paused():
        return _error("PAUSED", PAUSED_MESSAGE)
    if tool_name in WRITE_TOOLS and is_unattended(kwargs):
        return _error("UNATTENDED", UNATTENDED_MESSAGE)
    if tool_name in WRITE_TOOLS and store.get_meta("key_mode") == "read_only":
        return _error("READ_ONLY_KEY", READ_ONLY_MESSAGE)
    amount = _amount_hint(tool_name, args)
    limit = runtime.settings.spend_limit_cents
    if limit and amount is not None and amount > limit:
        return _error("SPEND_LIMIT", _limit_message(amount, limit, args.get("currency")))
    if tool_name in GATED_TOOLS:
        return _consume_or_refuse(tool_name, args, kwargs or {})
    return None


def release_approval_hold() -> None:
    """Allow the next gated write to require its own approval."""
    _tls.held = False


def over_limit(amount: int | None, currency: str | None = None) -> dict | None:
    limit = runtime.settings.spend_limit_cents
    if not limit or amount is None:
        return None
    if int(amount) > limit:
        return _error("SPEND_LIMIT", _limit_message(int(amount), limit, currency))
    return None


def _limit_message(amount: int, limit: int, currency: Any) -> str:
    code = str(currency or "").upper()
    if code in {"BTC", "LBTC"}:
        unit = f"{limit} sats ({code}). This is not a dollar cap."
    elif code == "USD":
        unit = f"{limit} cents, which is {limit / 100:.2f} USD. The same integer would mean {limit} sats on a BTC order."
    elif code:
        unit = (
            f"{limit} in the smallest unit of {code} "
            "(cents for 2-decimal fiat, sats for BTC). One integer, compared to the order total."
        )
    else:
        unit = (
            f"{limit} in the order's smallest unit: cents for USD, sats for BTC. "
            "One integer, compared to the order total. It is not a dollar cap on bitcoin."
        )
    return (
        f"Refused before any request was sent. Amount {amount} is above spend_limit_cents {limit} ({unit}) "
        "Set 0 to disable the plugin cap. Hermes approval still applies."
    )


def read_only_from_error(error_code: str, status: int) -> dict | None:
    if status == 403 or error_code == "FORBIDDEN":
        store.set_meta("key_mode", "read_only")
        return _error("READ_ONLY_KEY", READ_ONLY_MESSAGE)
    return None


def invalid_key_from_error(error_code: str, status: int) -> dict | None:
    if status == 401 or error_code == "UNAUTHORIZED":
        store.set_meta("key_mode", "invalid")
        return _error("INVALID_KEY", INVALID_KEY_MESSAGE)
    return None


def reset_for_tests() -> None:
    global _memory_paused, _now
    with _lock:
        _pending.clear()
        _memory_paused = False
    _tls.held = False
    _now = time.monotonic


def set_clock_for_tests(clock: Callable[[], float] | None) -> None:
    global _now
    _now = clock or time.monotonic


def _consume_or_refuse(tool_name: str, args: dict, kwargs: dict) -> dict | None:
    if getattr(_tls, "held", False):
        return None
    if not _consume(tool_name, args, kwargs):
        return _error("NO_APPROVAL", NO_APPROVAL_MESSAGE)
    _tls.held = True
    return None


def _consume(tool_name: str, args: dict, kwargs: dict) -> bool:
    fingerprint = _fingerprint(tool_name, args if isinstance(args, dict) else {})
    scope = _scope(kwargs, kwargs.get("task_id") if isinstance(kwargs, dict) else None)
    with _lock:
        _expire_locked(_now())
        match: Pending | None = None
        for pending in sorted(_pending.values(), key=lambda item: item.created):
            if pending.tool != tool_name or pending.fingerprint != fingerprint or not pending.human_approved:
                continue
            if pending.scope and scope and pending.scope != scope:
                continue
            match = pending
            break
        if match is None:
            return False
        _pending.pop(match.ref, None)
        return True


def _expire_locked(now: float) -> None:
    dead = [ref for ref, pending in _pending.items() if now - pending.created > APPROVAL_TTL_SECONDS]
    for ref in dead:
        _pending.pop(ref, None)


def _scope(kwargs: dict | None, task_id: str | None = None) -> str:
    kwargs = kwargs or {}
    return str(task_id or kwargs.get("task_id") or kwargs.get("session_id") or "")


def _fingerprint(tool_name: str, args: Any) -> str:
    try:
        blob = json.dumps(
            args if isinstance(args, dict) else {},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        blob = repr(args)
    return hashlib.sha256(f"{tool_name}\n{blob}".encode("utf-8")).hexdigest()


def _ref_from_approval(pattern_key: str, pattern_keys: Any, description: str, rule_key: Any) -> str | None:
    keys = [str(pattern_key or ""), str(rule_key or "")]
    if isinstance(pattern_keys, (list, tuple)):
        keys.extend(str(key) for key in pattern_keys)
    for key in keys:
        if RULE_PREFIX in key:
            return key.split(RULE_PREFIX, 1)[1].strip()[:12]
    text = str(description or "")
    if "ref " in text:
        return text.rsplit("ref ", 1)[1].strip()[:12]
    return None


def _error(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "issues": []}}


def _approval_detail(tool_name: str, args: dict) -> str:
    label = args.get("label") or args.get("title") or ""
    currency = args.get("currency") or ""
    amount = args.get("amount")
    if tool_name == "zaprite_pay":
        try:
            from .amounts import parse_amount

            _, phrase = parse_amount(args.get("amount"), str(args.get("currency") or "USD"))
        except Exception:
            phrase = f"{args.get('amount')} {args.get('currency') or ''}".strip()
        customer = args.get("customer") if isinstance(args.get("customer"), dict) else {}
        who = (customer.get("name") or args.get("customer_name") or "").strip()
        tail = f" to {who}" if who else " anyone can pay"
        return (
            f"Create a {phrase} payment link{tail}. Approving creates the link; "
            "it does not charge anyone."
        )
    if tool_name == "zaprite_charge_profile":
        return (
            f"Charge saved payment profile {args.get('payment_profile_id') or ''} "
            f"on order {args.get('order_id') or ''}."
        ).strip()
    if tool_name == "zaprite_issue_tickets":
        return (
            "Issue tickets. Zaprite standard ticket fees apply "
            "(1% + $3 per ticket on the Event Tickets product; confirm the fee)."
        )
    if tool_name == "zaprite_bridge_handoff":
        return (
            "Prepare a dashboard handoff. The plugin will not open a browser "
            "or change the checkout by itself."
        )
    if tool_name == "zaprite_delete_contact":
        return f"Delete Zaprite contact {args.get('contact_id') or ''}."
    if tool_name == "zaprite_create_webhook":
        return (
            f"Register webhook URL {args.get('url') or ''}. "
            "Zaprite will POST unsigned id-only payloads to it. This plugin will not receive them."
        )
    if tool_name == "zaprite_delete_webhook":
        return f"Delete Zaprite webhook {args.get('webhook_id') or ''}."
    if amount is not None and currency:
        tail = f" ({label})" if label else ""
        return f"Create or update a Zaprite payment for {amount} {currency}{tail}."
    pretty = tool_name.removeprefix("zaprite_").replace("_", " ")
    return f"Change Zaprite: {pretty}."


def _amount_hint(tool_name: str, args: dict) -> int | None:
    if tool_name == "zaprite_pay":
        try:
            from .amounts import parse_amount

            minor, _ = parse_amount(args.get("amount"), str(args.get("currency") or "USD"))
            return minor
        except Exception:
            return None
    if tool_name == "zaprite_create_order":
        return _as_int(args.get("amount"))
    if tool_name == "zaprite_create_invoice":
        return _invoice_total(args.get("line_items") or args.get("lineItems"))
    return None


def _invoice_total(items: Any) -> int | None:
    if not isinstance(items, list) or not items:
        return None
    total = 0.0
    for item in items:
        if not isinstance(item, dict):
            continue
        price = item.get("unit_price", item.get("unitPrice"))
        if price is None:
            continue
        qty = item.get("quantity", 1) or 1
        try:
            total += int(price) * float(qty)
        except (TypeError, ValueError):
            return None
    return int(round(total))


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
