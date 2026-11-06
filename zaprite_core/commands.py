"""Slash command /zaprite and the terminal helper hermes zaprite."""

from __future__ import annotations

import json
from typing import Any

from . import policy, service
from .constants import LINKS, SIGN_IN_URL, org_links
from . import store


def _cmd_links():
    return org_links(store.get_meta("org_id") or None)


def _status_text() -> str:
    status = service.local_status()
    lines = [
        "Zaprite",
        f"Key: {'set' if status['key_present'] else 'missing'} ({status['key_mode']})",
        f"API: {status['base_url']}",
        f"Spend limit (smallest unit, 0 = no cap): {status['spend_limit_cents']}",
        f"Paid notices: {status['notify']} (this chat, not a required Telegram bot)",
        f"Orders this plugin created: {status['local_orders_tracked']}",
        (
            f"Writes: {'paused' if status.get('writes_paused') else 'open'} "
            f"(pending approvals {status.get('pending_approvals', 0)})"
        ),
    ]
    for order in status["local_orders"]:
        lines.append(
            f"- {order['id']} {order['status']} {order.get('amount')} {order.get('currency')} {order.get('checkout_url') or ''}"
        )
    if not status["local_orders"]:
        lines.append("No local orders yet. Ask for an invoice when the key is set.")
    lines.append("Commands: /zaprite setup | doctor | status | kill | pause | resume | help")
    return "\n".join(lines)


def _pause_text() -> str:
    cleared = policy.pause_writes()
    noun = "approval" if cleared == 1 else "approvals"
    return (
        f"Zaprite writes are paused. Cleared {cleared} pending {noun}. "
        "No new order, invoice, quote, charge, ticket change, webhook change, "
        "contact edit, or dashboard handoff will be sent. An in-flight watch stops "
        "on its next poll. Lookups still work. This did not cancel an order already "
        "created at Zaprite and it did not refund. /zaprite resume to allow writes again."
    )


def _resume_text() -> str:
    if not policy.writes_paused():
        return "Zaprite writes are already open. Each money or destructive write still needs a fresh approval."
    policy.resume_writes()
    return (
        "Zaprite writes are open again. Pending approvals were not restored. "
        "The next order, invoice, quote, charge, or other gated write asks for a fresh approval."
    )


def _setup_text(ctx: Any) -> str:
    steps = "\n".join(f"{i}. {step}" for i, step in enumerate(service._setup_steps(), start=1))
    choice = None
    if ctx is not None and hasattr(ctx, "ask_choice"):
        try:
            choice = ctx.ask_choice(
                "Where are you with Zaprite?",
                [
                    {"value": "ready", "label": "Org and key are ready", "description": "Run doctor next"},
                    {"value": "rails", "label": "I still need rails", "description": "Open Connections"},
                    {"value": "sandbox", "label": "I want a sandbox", "description": "Test payment, no real money"},
                ],
            )
        except Exception:
            choice = None
    extra = ""
    if choice == "rails":
        extra = f"\nOpen {_cmd_links()['connections']} and connect card, bank, Lightning, on-chain, or stablecoins. Then come back."
    elif choice == "sandbox":
        extra = f"\nSandbox guide: {_cmd_links()['sandbox']}\nTest payments: {_cmd_links()['test_payments']}"
    elif choice == "ready":
        extra = "\nNext: /zaprite doctor"
    elif choice is None:
        extra = "\nReply setup, doctor, or status if the picker is not available."
    return steps + extra


def handle_slash(raw_args: str = "", **kwargs: Any) -> str:
    cmd = (raw_args or "").strip().lower()
    ctx = kwargs.get("ctx")
    if cmd in {"", "status"}:
        return _status_text()
    if cmd == "help":
        return (
            "Zaprite gets you paid from this chat.\n"
            "/zaprite status — key and orders this plugin tracked\n"
            "/zaprite setup — the one human setup\n"
            "/zaprite doctor — live read-only check\n"
            "/zaprite kill — pause writes, clear pending approvals, stop an in-flight watch\n"
            "/zaprite pause — same as kill\n"
            "/zaprite resume — allow writes again; the next write asks again\n"
            "Then ask: invoice Northwind 1280 USD for the March retainer."
        )
    if cmd == "setup":
        return _setup_text(ctx)
    if cmd in {"kill", "pause", "stop"}:
        return _pause_text()
    if cmd == "resume":
        return _resume_text()
    if cmd == "doctor":
        try:
            payload = json.loads(tools_doctor())
        except Exception as exc:
            return f"Doctor failed before it could report: {exc.__class__.__name__}"
        mode = payload.get("key_mode")
        ok = payload.get("ok")
        lines = [
            f"Doctor: {'ok' if ok else 'needs a look'} — key {mode}.",
            "Writes are paused. /zaprite resume to allow them." if policy.writes_paused() else "",
            payload.get("connections_note") or "",
            payload.get("webhook") or "",
        ]
        if payload.get("branding"):
            lines.append(payload["branding"])
        profile = (payload.get("deep_links") or {}).get("profile") or _cmd_links()["profile"]
        lines.append(f"Profile (logo, accent color, display name): {profile}")
        guide = (payload.get("deep_links") or {}).get("branding_guide")
        if guide:
            lines.append(f"Branding guide: {guide}")
        if payload.get("error"):
            err = payload["error"]
            lines.append(f"{err.get('code')}: {err.get('message')}")
        lines.append(f"API keys: {_cmd_links()['api_keys']}")
        return "\n".join(line for line in lines if line)
    return "Unknown /zaprite command. Use status, setup, doctor, kill, pause, resume, or help."


def tools_doctor() -> str:
    from .tools import zaprite_doctor

    return zaprite_doctor({})


def register_cli(ctx: Any) -> None:
    if not hasattr(ctx, "register_cli_command"):
        return

    def _setup(subparser: Any) -> None:
        subs = subparser.add_subparsers(dest="zaprite_cmd")
        subs.add_parser("status", help="Local Zaprite plugin status")
        subs.add_parser("doctor", help="Read-only live check against api.zaprite.com")
        subs.add_parser("kill", help="Pause writes and clear pending approvals")
        subs.add_parser("pause", help="Pause writes and clear pending approvals")
        subs.add_parser("resume", help="Allow Zaprite writes again")
        subparser.set_defaults(func=_run)

    def _run(args: Any) -> None:
        command = getattr(args, "zaprite_cmd", None) or "status"
        if command == "doctor":
            print(tools_doctor())
            return
        if command in {"kill", "pause", "stop"}:
            print(_pause_text())
            return
        if command == "resume":
            print(_resume_text())
            return
        print(_status_text())

    ctx.register_cli_command(
        name="zaprite",
        help="Zaprite merchant status, doctor, and pause",
        setup_fn=_setup,
        handler_fn=_run,
    )
