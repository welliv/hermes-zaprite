"""The P0 fixes, pinned.

Each of these was a real defect found by auditing the walkthrough against the code:
a secret invited into chat, an unpayable checkout, a JSON error where a sentence
belongs, and an overpayment reported as a clean payment.
"""

from __future__ import annotations

import json

from hermes_plugins.zaprite import store
from hermes_plugins.zaprite.tools import HANDLERS
from hermes_plugins.zaprite.zaprite_core import onboarding
from tests.approvals import allow
from tests.fakes import Router, order, use_router


def test_setup_never_asks_for_a_secret_in_chat():
    data: dict[str, str] = {}
    onboarding.store = type("S", (), {"get_meta": staticmethod(lambda k: data.get(k)),
                                      "set_meta": staticmethod(lambda k, v: data.__setitem__(k, v))})
    message = onboarding.state(False, None, None)["message"]
    assert "paste it here" not in message.lower()
    assert "Tools" in message
    onboarding.store = store


def test_no_checkout_until_a_way_to_pay_is_connected():
    use_router(Router())  # any HTTP call would be recorded
    store.set_meta("rails_state", "unset")
    allow("zaprite_create_order", {"amount": 5000, "currency": "USD"})
    body = json.loads(HANDLERS["zaprite_create_order"]({"amount": 5000, "currency": "USD"}))
    assert body["error"]["code"] == "NO_RAILS"
    assert "connections" in body["error"]["message"].lower()
    assert "unpayable" in body["error"]["message"]
    # /org/default/ is not this merchant's org.
    assert "/org/default/" not in body["error"]["message"]


def test_skipping_rails_is_respected():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (201, order(status="PENDING")))
    use_router(router)
    store.set_meta("rails_state", "skipped")
    allow("zaprite_create_order", {"amount": 5000, "currency": "USD"})
    body = json.loads(HANDLERS["zaprite_create_order"]({"amount": 5000, "currency": "USD"}))
    assert body["ok"] is True


def test_a_rejected_key_is_a_sentence_not_json():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (401, {"code": "UNAUTHORIZED", "message": "bad key"}))
    use_router(router)
    allow("zaprite_create_order", {"amount": 5000, "currency": "USD"})
    body = json.loads(HANDLERS["zaprite_create_order"]({"amount": 5000, "currency": "USD"}))
    assert body["error"]["code"] == "INVALID_KEY"
    message = body["error"]["message"]
    assert "rejected" in message.lower()
    assert "revoked" in message.lower()
    assert "UNAUTHORIZED" not in message


def test_overpayment_says_so_instead_of_counting_it_as_paid():
    router = Router()
    router.add("GET", "/v1/orders/od_over", lambda _r: (200, order(id="od_over", status="OVERPAID", paidAt="2026-11-06T00:00:00Z")))
    use_router(router)
    body = json.loads(HANDLERS["zaprite_get_order"]({"order_id": "od_over"}))
    assert body["paid"] is True
    assert "refund" in body["warning"].lower()


def test_confirmed_rails_still_create_normally():
    # The gate must not block a merchant who did connect a rail.
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (201, order(status="PENDING")))
    use_router(router)
    store.set_meta("rails_state", "confirmed")
    store.set_meta("rails", "card")
    allow("zaprite_create_order", {"amount": 5000, "currency": "USD"})
    body = json.loads(HANDLERS["zaprite_create_order"]({"amount": 5000, "currency": "USD"}))
    assert body["ok"] is True
    assert len(router.calls) == 1


def test_invoices_are_gated_too():
    router = Router()
    use_router(router)
    store.set_meta("rails_state", "unset")
    allow("zaprite_create_invoice", {"contact_id": "c1", "currency": "USD", "line_items": [{"name": "x", "unit_price": 100}]})
    body = json.loads(
        HANDLERS["zaprite_create_invoice"](
            {"contact_id": "c1", "currency": "USD", "line_items": [{"name": "x", "unit_price": 100}]}
        )
    )
    assert body["error"]["code"] == "NO_RAILS"
    assert router.calls == []


def test_an_agent_cannot_declare_money_paid():
    # Payment status is a fact from Zaprite, not an assertion an agent can make.
    store.set_meta("rails_state", "skipped")
    use_router(Router())
    allow("zaprite_update_order", {"order_id": "od_1", "status": "PAID"})
    body = json.loads(HANDLERS["zaprite_update_order"]({"order_id": "od_1", "status": "PAID"}))
    assert body["ok"] is False
    assert "dashboard" in body["error"]["message"].lower()


def test_complete_is_still_allowed():
    router = Router()
    router.add("PATCH", "/v1/orders/od_1", lambda _r: (200, order(id="od_1", status="COMPLETE")))
    store.set_meta("rails_state", "skipped")
    use_router(router)
    allow("zaprite_update_order", {"order_id": "od_1", "status": "COMPLETE"})
    body = json.loads(HANDLERS["zaprite_update_order"]({"order_id": "od_1", "status": "COMPLETE"}))
    assert body["ok"] is True
