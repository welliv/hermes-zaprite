"""First run: account, key, rails, identity.

Order matters. Nothing can be charged until the key works and the merchant has
said how they get paid. Branding comes last because it changes what the payer
sees, not whether they can pay.

The API cannot set a logo or a brand colour — there is no branding endpoint.
So the plugin records what the person shares and returns a `screen_task`: one
instruction the Hermes agent performs on the Bot Screen, where the person is
already signed in. The plugin never drives the browser and never holds a cookie.
"""

from __future__ import annotations

import re

from . import store
from .constants import org_links

RAILS = {
    "card": "card — Stripe or your bank processor",
    "bank": "bank transfer — ACH / SEPA / wire",
    "lightning": "Lightning — Alby or another Lightning wallet",
    "onchain": "on-chain bitcoin — a wallet or xpub",
}

LABEL = {"lightning": "Lightning", "onchain": "bitcoin"}

HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

STATE_KEY = "key"
STATE_READ_ONLY = "key_read_only"
STATE_RAILS = "rails"
STATE_BRAND = "brand"
STATE_READY = "ready"


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _links(org_id: str | None) -> dict[str, str]:
    links = org_links(org_id)
    links["sign_up"] = "https://app.zaprite.com"
    return links


def stored_rails() -> list[str]:
    raw = store.get_meta("rails") or ""
    return [r for r in raw.split(",") if r]


def rails_confirmed() -> bool:
    return store.get_meta("rails_state") == "confirmed"


def rails_skipped() -> bool:
    return store.get_meta("rails_state") == "skipped"


def brand() -> dict:
    return {
        "business_name": store.get_meta("business_name") or "",
        "brand_color": store.get_meta("brand_color") or "",
        "logo": store.get_meta("logo") or "",
        "assets": [a for a in (store.get_meta("assets") or "").split(",") if a],
    }


def brand_state() -> str:
    return store.get_meta("brand_state") or "unset"


def _has_brand(details: dict) -> bool:
    return bool(details["business_name"] or details["brand_color"] or details["logo"])


def screen_task(org_id: str | None) -> dict | None:
    """The one thing the API cannot do, expressed as an instruction for the agent.

    Returned only when the person gave something to apply. The agent runs it on the
    screen where the person is already signed in; the plugin stays credential-free.
    """
    details = brand()
    if not _has_brand(details):
        return None
    steps = []
    if details["business_name"]:
        steps.append(f"set the display name to {details['business_name']!r}")
    if details["logo"]:
        steps.append(f"upload the logo at {details['logo']}")
    if details["brand_color"]:
        steps.append(f"set the accent colour to {details['brand_color']}")
    return {
        "what": "Apply the business identity",
        # /org/default/ is the documented slug, not every merchant's org. Without a
        # seen orgId, send them to the app and name the path instead of a wrong link.
        "where": _links(org_id)["profile"] if org_id else "https://app.zaprite.com",
        "where_path": "Settings → Profile",
        "steps": steps,
        "why_manual": (
            "Zaprite has no branding API. A logo and a colour exist only in the dashboard, so "
            "a person — or the agent on the Bot Screen — does this; the plugin cannot see it."
        ),
        "verify": "none — no API reads branding; confirm visually on the screen.",
    }


def state(key_present: bool, key_mode: str | None, org_id: str | None) -> dict:
    links = _links(org_id)
    rails = stored_rails()
    details = brand()

    if not key_present:
        # Without an org the settings link would point at the documented default slug,
        # which is not every merchant's org. Give the path, not a wrong URL.
        step, message = STATE_KEY, (
            "First: sign in or create a Zaprite account, then make an API key (Full access) "
            "and paste it into Hermes — Tools → Zaprite."
        )
    elif key_mode == "read_only":
        step, message = STATE_READ_ONLY, (
            "That key is read-only, so I can't take payments with it. Make one with Full access."
        )
    elif not (rails_confirmed() or rails_skipped()):
        step, message = STATE_RAILS, (
            "How do you want to get paid? Connect one, then tell me which."
        )
    elif brand_state() == "unset" and not _has_brand(details):
        step, message = STATE_BRAND, (
            "Last step: send a logo, a colour (#1F7A4D) or your business name — or say skip."
        )
    else:
        step = STATE_READY
        if rails:
            message = f"Ready — customers can pay by {_join([LABEL.get(r, r) for r in rails])}."
            if _has_brand(details):
                message += " Next: I'll set your logo and colour."
        else:
            message = (
                "Ready, but nothing is connected yet, so customers can't pay.\n"
                f"Add one here: {links['connections']}"
            )

    # A /org/default/ link may be another merchant's org. Without a seen orgId the
    # button opens the app and the step text names the path.
    actions = {
        STATE_KEY: {"label": "Open Zaprite", "url": links["sign_up"]},
        STATE_READ_ONLY: {
            "label": "Open API settings",
            "url": links["api_keys"] if org_id else links["sign_up"],
        },
        STATE_RAILS: {
            "label": "Open connections",
            "url": links["connections"] if org_id else links["sign_up"],
        },
        STATE_BRAND: {
            "label": "Open branding",
            "url": links["profile"] if org_id else links["sign_up"],
        },
    }
    if step == STATE_READY and not rails:
        actions[STATE_READY] = {"label": "Open connections", "url": links["connections"]}

    return {
        "ok": True,
        "step": step,
        "next_action": actions.get(step),
        "ready": step == STATE_READY,
        "key_present": key_present,
        "key_mode": key_mode or "unknown",
        "org_id": org_id,
        "rails": rails,
        "rails_confirmed": rails_confirmed(),
        "rails_skipped": rails_skipped(),
        "brand": details,
        "brand_state": brand_state(),
        "links": links,
        "choices": RAILS if step == STATE_RAILS else {},
        "screen_task": screen_task(org_id) if step == STATE_READY else None,
        "message": message,
    }


def confirm(rails: list[str] | None = None) -> dict:
    wanted = [r.strip().lower() for r in (rails or []) if r and r.strip()]
    unknown = [r for r in wanted if r not in RAILS]
    if unknown:
        return _bad(f"Unknown rail(s): {', '.join(unknown)}. Choose from: {', '.join(RAILS)}.")
    store.set_meta("rails", ",".join(wanted))
    store.set_meta("rails_state", "confirmed" if wanted else "skipped")
    return state(True, store.get_meta("key_mode"), store.get_meta("org_id"))


def skip() -> dict:
    store.set_meta("rails_state", "skipped")
    return state(True, store.get_meta("key_mode"), store.get_meta("org_id"))


def set_brand(
    business_name: str | None = None,
    brand_color: str | None = None,
    logo: str | None = None,
    assets: list[str] | None = None,
) -> dict:
    if brand_color:
        match = HEX.match(brand_color.strip())
        if not match:
            return _bad(f"{brand_color.strip()!r} is not a colour. Send hex, like #1F7A4D.")
        digits = match.group(1)
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        store.set_meta("brand_color", "#" + digits.upper())
    if business_name:
        store.set_meta("business_name", business_name.strip())
    if logo:
        store.set_meta("logo", logo.strip())
    if assets:
        store.set_meta("assets", ",".join(a.strip() for a in assets if a and a.strip()))
    store.set_meta("brand_state", "captured")
    return state(True, store.get_meta("key_mode"), store.get_meta("org_id"))


def skip_brand() -> dict:
    store.set_meta("brand_state", "skipped")
    return state(True, store.get_meta("key_mode"), store.get_meta("org_id"))


def _bad(message: str) -> dict:
    return {"ok": False, "error": {"code": "BAD_REQUEST", "message": message, "issues": []}}
