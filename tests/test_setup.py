"""First run: account → key → rails → identity.

The order is the product. Nothing is chargeable before the key works and the
merchant has said how they get paid; branding comes last because it changes what
the payer sees, not whether they can pay. The plugin never claims a rail works,
and never pretends it can read branding back.
"""

from __future__ import annotations

import json

import pytest

from hermes_plugins.zaprite.zaprite_core import onboarding, policy
from hermes_plugins.zaprite.tools import HANDLERS


@pytest.fixture
def meta(monkeypatch):
    data: dict[str, str] = {}
    monkeypatch.setattr(onboarding.store, "get_meta", lambda k: data.get(k))
    monkeypatch.setattr(onboarding.store, "set_meta", lambda k, v: data.__setitem__(k, v))
    return data


# --- step 1: account and key -------------------------------------------------


def test_no_key_starts_with_account_then_api_key(meta):
    out = onboarding.state(False, None, None)
    assert out["step"] == "key"
    assert out["ready"] is False
    assert out["links"]["sign_up"] == "https://app.zaprite.com"
    assert "make an API key" in out["message"]
    assert "Full access" in out["message"]
    # Without an org there is no honest settings URL, so no link is given.
    assert "org/default/settings/api" not in out["message"]


def test_read_only_key_is_named_and_refused(meta):
    out = onboarding.state(True, "read_only", "org_1")
    assert out["step"] == "key_read_only"
    assert out["ready"] is False
    assert "Full access" in out["message"]


# --- step 2: rails, before anything can be charged ---------------------------


def test_rails_come_before_anything_else(meta):
    out = onboarding.state(True, "full", "org_1")
    assert out["step"] == "rails"
    assert out["ready"] is False
    assert "connections" in out["links"]["connections"]
    assert set(out["choices"]) == {"card", "bank", "lightning", "onchain"}
    assert "Connect one" in out["message"]


def test_unknown_rail_is_rejected_not_stored(meta):
    out = onboarding.confirm(["card", "carrier-pigeon"])
    assert out["ok"] is False
    assert out["error"]["code"] == "BAD_REQUEST"
    assert "carrier-pigeon" in out["error"]["message"]
    assert meta.get("rails_state") is None


# --- step 3: identity, which the API cannot set ------------------------------


def test_confirmed_rails_move_to_branding_not_ready(meta):
    out = onboarding.confirm(["card", "lightning"])
    assert out["step"] == "brand"
    assert out["ready"] is False
    assert out["rails"] == ["card", "lightning"]
    assert "logo" in out["message"].lower()


def test_brand_is_normalised_and_returned_as_a_screen_task(meta):
    meta["org_id"] = "org_1"
    onboarding.confirm(["card"])
    out = onboarding.set_brand(business_name="Acme", brand_color="#1f7a4d", logo="/tmp/logo.png")
    assert out["brand"]["brand_color"] == "#1F7A4D"
    task = out["screen_task"]
    assert task is not None
    assert task["where"].endswith("/settings/profile")
    assert any("Acme" in step for step in task["steps"])
    assert any("/tmp/logo.png" in step for step in task["steps"])
    assert task["verify"].startswith("none")


def test_short_hex_is_expanded(meta):
    out = onboarding.set_brand(brand_color="#abc")
    assert out["brand"]["brand_color"] == "#AABBCC"


def test_bad_colour_is_rejected_and_nothing_is_stored(meta):
    out = onboarding.set_brand(brand_color="mint green")
    assert out["ok"] is False
    assert out["error"]["code"] == "BAD_REQUEST"
    assert meta.get("brand_color") is None


def test_skipping_brand_reaches_ready_without_a_screen_task(meta):
    onboarding.confirm(["card"])
    out = onboarding.skip_brand()
    assert out["step"] == "ready"
    assert out["ready"] is True
    assert out["screen_task"] is None
    assert "card" in out["message"]


def test_skipping_rails_is_remembered_and_says_what_it_costs(meta):
    onboarding.skip()
    out = onboarding.skip_brand()
    assert out["ready"] is True
    assert out["rails"] == []
    assert "can't pay" in out["message"]


# --- the tool ----------------------------------------------------------------


def test_setup_tool_is_not_gated(meta):
    assert policy.pre_tool_call("zaprite_setup", {}) is None
    out = json.loads(HANDLERS["zaprite_setup"]({}))
    assert out["ok"] is True
    assert "step" in out


def test_setup_tool_accepts_csv_rails(meta):
    out = json.loads(HANDLERS["zaprite_setup"]({"rails": "card, bank"}))
    assert out["rails"] == ["card", "bank"]


def test_setup_tool_accepts_brand_assets_as_csv(meta):
    onboarding.confirm(["card"])
    out = json.loads(
        HANDLERS["zaprite_setup"]({"business_name": "Acme", "assets": "tagline, invoice footer"})
    )
    assert out["brand"]["assets"] == ["tagline", "invoice footer"]


def test_screen_task_without_an_org_points_at_the_app_and_names_the_path(meta):
    onboarding.confirm(["card"])
    out = onboarding.set_brand(logo="/tmp/logo.png")
    assert out["screen_task"]["where"] == "https://app.zaprite.com"
    assert out["screen_task"]["where_path"] == "Settings → Profile"


def test_no_action_links_a_default_slug_org(meta):
    # Without a seen orgId, /org/default/ is not this merchant's org.
    out = onboarding.state(False, None, None)
    assert "/org/default/" not in out["next_action"]["url"]
    onboarding.confirm(["card"])
    out = onboarding.state(True, "full", None)
    assert "/org/default/" not in (out["next_action"] or {}).get("url", "")
