"""Tool handlers. Each one returns a JSON string and does not raise."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from . import service
from .client import MissingKey, ZapriteError, redact
from .constants import TOOL_NAMES, WRITE_TOOLS
from .policy import invalid_key_from_error, read_only_from_error, refuse_write, release_approval_hold
from .secrets import load_api_key

logger = logging.getLogger("zaprite")

_OPS: dict[str, Callable] = {
    "zaprite_pay": service.pay,
    "zaprite_create_order": service.create_order,
    "zaprite_create_invoice": service.create_invoice,
    "zaprite_get_order": service.get_order,
    "zaprite_list_orders": service.list_orders,
    "zaprite_create_quote": service.create_quote,
    "zaprite_watch_order": service.watch_order,
    "zaprite_update_order": service.update_order,
    "zaprite_charge_profile": service.charge_profile,
    "zaprite_create_contact": service.create_contact,
    "zaprite_get_contact": service.get_contact,
    "zaprite_list_contacts": service.list_contacts,
    "zaprite_update_contact": service.update_contact,
    "zaprite_delete_contact": service.delete_contact,
    "zaprite_report": service.report,
    "zaprite_list_overdue": service.list_overdue,
    "zaprite_doctor": service.doctor,
    "zaprite_setup": service.setup,
    "zaprite_list_webhooks": service.list_webhooks,
    "zaprite_create_webhook": service.create_webhook,
    "zaprite_delete_webhook": service.delete_webhook,
    "zaprite_bridge_handoff": service.bridge_handoff,
    "zaprite_sovereign_rails": service.sovereign_rails,
    "zaprite_list_payment_links": service.list_payment_links,
    "zaprite_get_payment_link": service.get_payment_link,
    "zaprite_list_tickets": service.list_tickets,
    "zaprite_get_ticket": service.get_ticket,
    "zaprite_issue_tickets": service.issue_tickets,
    "zaprite_ticket_activity": service.ticket_activity,
}


def _dumps(payload: dict) -> str:
    try:
        secret = load_api_key()
    except Exception:
        secret = None
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return redact(text, secret)


def _safe_message(exc: BaseException) -> str:
    try:
        secret = load_api_key()
    except Exception:
        secret = None
    text = redact(str(exc), secret)
    return text or exc.__class__.__name__


def _handler(name: str, fn: Callable) -> Callable:
    def handler(args: dict | None = None, **kwargs: Any) -> str:
        if not isinstance(args, dict):
            args = {}
        # Stop every write before the service function builds an HTTP client.
        # Hermes runs pre_tool_call first. {"action": "approve"} only escalates
        # to the human gate. post_approval_response must record a fresh human
        # yes before a gated write is sent. This check is the backstop when
        # the prompt was skipped.
        try:
            if name in WRITE_TOOLS:
                refused = refuse_write(name, args, kwargs)
                if refused:
                    return _dumps(refused)
            try:
                result = fn(args, **kwargs)
                if not isinstance(result, dict):
                    result = {"ok": True, "result": result}
                return _dumps(result)
            except MissingKey:
                return _dumps(service._missing())
            except ZapriteError as exc:
                logger.info("zaprite %s failed code=%s status=%s", name, exc.code, exc.status)
                if name in WRITE_TOOLS:
                    mapped = read_only_from_error(exc.code, exc.status)
                    if mapped:
                        return _dumps(mapped)
                invalid = invalid_key_from_error(exc.code, exc.status)
                if invalid:
                    return _dumps(invalid)
                return _dumps({"ok": False, "error": exc.to_dict()})
            except ValueError as exc:
                return _dumps(
                    {
                        "ok": False,
                        "error": {"code": "BAD_REQUEST", "message": _safe_message(exc), "issues": []},
                    }
                )
            except Exception as exc:
                logger.info("zaprite %s plugin error %s", name, exc.__class__.__name__)
                return _dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": "PLUGIN_ERROR",
                            "message": _safe_message(exc),
                            "issues": [],
                        },
                    }
                )
        finally:
            release_approval_hold()

    handler.__name__ = name
    return handler


HANDLERS = {name: _handler(name, _OPS[name]) for name in TOOL_NAMES}


def zaprite_create_order(args: dict, **kwargs: Any) -> str:
    return HANDLERS["zaprite_create_order"](args, **kwargs)


def zaprite_get_order(args: dict, **kwargs: Any) -> str:
    return HANDLERS["zaprite_get_order"](args, **kwargs)


def zaprite_watch_order(args: dict, **kwargs: Any) -> str:
    return HANDLERS["zaprite_watch_order"](args, **kwargs)


def zaprite_doctor(args: dict | None = None, **kwargs: Any) -> str:
    return HANDLERS["zaprite_doctor"](args or {}, **kwargs)


def zaprite_list_overdue(args: dict | None = None, **kwargs: Any) -> str:
    return HANDLERS["zaprite_list_overdue"](args or {}, **kwargs)
