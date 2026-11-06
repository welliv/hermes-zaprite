"""Org-aware deep links and first-run copy."""

from __future__ import annotations

import json

from hermes_plugins.zaprite import store
from hermes_plugins.zaprite.constants import org_links, LINKS, SIGN_IN_URL
from hermes_plugins.zaprite.tools import HANDLERS
from tests.fakes import Router, use_router


def test_org_links_default_and_org_id():
    assert LINKS["api_keys"].endswith("/org/default/settings/api")
    assert org_links(None)["sign_in"] == SIGN_IN_URL
    assert org_links("cmw3")["connections"].endswith("/org/cmw3/connections")
    assert "/org/" not in org_links("cmw3")["connections_help"]
    assert org_links(None)["profile"] == "https://app.zaprite.com/org/default/settings/profile"
    assert org_links("cmw3")["profile"] == "https://app.zaprite.com/org/cmw3/settings/profile"
    assert org_links("org_9")["profile"] == "https://app.zaprite.com/org/org_9/settings/profile"
    assert (
        org_links("org_9")["branding_guide"]
        == "https://blog.zaprite.com/introducing-branded-invoices-and-checkouts/"
    )


def test_missing_key_guidance_is_context_first():
    use_router(Router(), api_key="")
    from hermes_plugins.zaprite import secrets

    secrets.set_api_key_for_tests(None)
    body = json.loads(HANDLERS["zaprite_doctor"]({}))
    assert body["key_mode"] == "missing"
    assert body["sign_in"] == SIGN_IN_URL
    assert body["deep_links"]["api_keys"].endswith("/org/default/settings/api")
    assert any("Sign in" in step or "sign up" in step.lower() for step in body["setup"])
