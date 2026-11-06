"""Profile branding is a dashboard handoff. There is no branding HTTP API."""

from __future__ import annotations

import json
import re
from pathlib import Path

from hermes_plugins.zaprite import commands, secrets, store
from hermes_plugins.zaprite.client import ZapriteClient
from hermes_plugins.zaprite.constants import BRANDING_GUIDE_URL, org_links
from hermes_plugins.zaprite.tools import HANDLERS
from tests.approvals import allow
from tests.fakes import Router, order, use_router

ROOT = Path(__file__).resolve().parents[1]
GUIDE = "https://blog.zaprite.com/introducing-branded-invoices-and-checkouts/"


def _loads(raw: str) -> dict:
    return json.loads(raw)


def _handoff(args: dict) -> dict:
    router = Router()
    use_router(router)
    allow("zaprite_bridge_handoff", args)
    body = _loads(HANDLERS["zaprite_bridge_handoff"](args))
    body["_calls"] = list(router.calls)
    return body


def test_profile_url_is_org_aware_with_default_fallback():
    assert org_links(None)["profile"] == "https://app.zaprite.com/org/default/settings/profile"
    assert org_links("")["profile"] == "https://app.zaprite.com/org/default/settings/profile"
    assert org_links("org_9")["profile"] == "https://app.zaprite.com/org/org_9/settings/profile"
    assert org_links("org_9")["branding_guide"] == GUIDE
    assert BRANDING_GUIDE_URL == GUIDE


def test_branding_profile_handoff_uses_profile_not_checkout_or_connections():
    store.set_meta("org_id", "org_9")
    body = _handoff({"gap": "branding_profile", "note": "Add my logo"})
    assert body["ok"] is True
    assert body["gap"] == "branding_profile"
    assert body["browser"] == "not_used"
    assert body["url"] == "https://app.zaprite.com/org/org_9/settings/profile"
    assert body["help"] == GUIDE
    assert body["guide"] == GUIDE
    assert "/checkouts" not in body["url"]
    assert "/connections" not in body["url"]
    steps = "\n".join(body["steps"])
    assert "customCheckoutId" not in steps
    assert "/checkouts" not in steps
    assert "/connections" not in steps
    assert "inherit" in steps.lower()
    assert "checkoutUrl" in steps
    assert "Settings → Profile" in steps
    assert body["_calls"] == []

    store.reset_for_tests()
    bare = _handoff({"gap": "branding_profile"})
    assert bare["url"] == "https://app.zaprite.com/org/default/settings/profile"
    assert bare["_calls"] == []


def test_other_logo_or_color_ask_is_not_sent_to_checkouts():
    logo = _handoff({"gap": "other", "note": "Add my logo"})
    assert logo["gap"] == "branding_profile"
    assert logo["url"].endswith("/org/default/settings/profile")
    assert "/checkouts" not in logo["url"]
    assert "/connections" not in logo["url"]
    assert "customCheckoutId" not in "\n".join(logo["steps"])

    color = _handoff({"gap": "other", "note": "Please set the accent color"})
    assert color["gap"] == "branding_profile"
    assert color["url"].endswith("/settings/profile")

    named = _handoff({"gap": "add my logo"})
    assert named["gap"] == "branding_profile"
    assert named["url"].endswith("/settings/profile")

    implied = _handoff({"note": "Add my logo and display name"})
    assert implied["gap"] == "branding_profile"

    untouched = _handoff({"gap": "other", "note": "Need a refund on last week's order"})
    assert untouched["gap"] == "other"
    assert untouched["url"].endswith("/org/default/checkouts")
    assert "customCheckoutId" in "\n".join(untouched["steps"])

    discount = _handoff({"gap": "lightning_discount", "note": "10% and mention the logo"})
    assert discount["gap"] == "lightning_discount"
    assert discount["url"].endswith("/checkouts")


def test_doctor_discloses_profile_inheritance():
    router = Router()
    router.add("GET", "/v1/webhooks", lambda _r: (200, {"items": [], "meta": {}}))
    router.add(
        "GET",
        "/v1/orders",
        lambda _r: (
            200,
            {
                "items": [order(status="PAID", orgId="org_9")],
                "meta": {"itemsCount": 1, "pagesCount": 1, "page": 1, "perPage": 100},
            },
        ),
    )
    router.add("POST", "/v1/orders", lambda _r: (400, {"code": "BAD_REQUEST", "message": "Invalid input data"}))
    use_router(router)
    body = _loads(HANDLERS["zaprite_doctor"]({}))
    assert body["branding_api"] is False
    assert body["deep_links"]["profile"] == "https://app.zaprite.com/org/org_9/settings/profile"
    assert body["deep_links"]["branding_guide"] == GUIDE
    branding = body["branding"].lower()
    assert "profile" in branding
    assert "inherit" in branding
    assert "cannot" in branding
    assert any("checkoutUrl" in step for step in body["next"])
    assert any("Profile" in step for step in body["setup"])
    paths = [call.url.path for call in router.calls]
    assert paths
    assert all(not re.search(r"brand|logo|profile", path, re.I) for path in paths)


def test_missing_key_doctor_and_setup_name_the_default_profile_url():
    use_router(Router(), api_key="")
    secrets.set_api_key_for_tests(None)
    body = _loads(HANDLERS["zaprite_doctor"]({}))
    assert body["key_mode"] == "missing"
    assert body["branding_api"] is False
    assert body["deep_links"]["profile"] == "https://app.zaprite.com/org/default/settings/profile"
    assert "inherit" in body["branding"].lower()
    setup = commands.handle_slash("setup")
    assert "https://app.zaprite.com/org/default/settings/profile" in setup
    assert "inherit" in setup.lower()
    assert "cannot" in setup.lower()
    doctor = commands.handle_slash("doctor")
    assert "https://app.zaprite.com/org/default/settings/profile" in doctor
    assert GUIDE in doctor
    assert "inherit" in doctor.lower()


def test_client_has_no_branding_http_route():
    names = [name for name in dir(ZapriteClient) if not name.startswith("_")]
    assert not any(re.search(r"brand|logo", name, re.I) for name in names)
    blob = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "zaprite_core").glob("*.py"))
    assert not re.search(r"""["']/v1/[^"']*(brand|logo|settings/profile)""", blob, re.I)
    client = (ROOT / "zaprite_core" / "client.py").read_text(encoding="utf-8").lower()
    for token in ("branding", "logo", "/settings/profile", "/v1/org"):
        assert token not in client
