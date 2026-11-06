"""Amounts as people write them, and the one-call pay verb."""

from __future__ import annotations

import json

import pytest

from hermes_plugins.zaprite import store
from hermes_plugins.zaprite.zaprite_core.amounts import AmountError, parse_amount
from hermes_plugins.zaprite.tools import HANDLERS
from tests.approvals import allow
from tests.fakes import Router, order, use_router


@pytest.mark.parametrize(
    "value,currency,expected",
    [
        ("$1,280", "USD", 128000),
        ("1280 usd", "USD", 128000),
        ("1280", "USD", 128000),
        ("1,280.50", "USD", 128050),
        ("$12.80", "USD", 1280),
        (128000, "USD", 128000),
        ("0.05 BTC", "BTC", 5000000),
        ("50000 sats", "BTC", 50000),
        (250000, "BTC", 250000),
    ],
)
def test_amounts_are_read_as_written(value, currency, expected):
    minor, phrase = parse_amount(value, currency)
    assert minor == expected
    assert phrase


@pytest.mark.parametrize("value", [0, -5, "", "abc", "$1,2x0", True])
def test_unreadable_amounts_are_refused(value):
    with pytest.raises(AmountError):
        parse_amount(value, "USD")


def test_pay_bills_a_customer_in_one_approval():
    router = Router()
    router.add("POST", "/v1/contacts", lambda _r: (201, {"id": "c_1", "legalName": "Dana", "email": "dana@example.com"}))
    router.add(
        "POST",
        "/v1/orders",
        lambda _r: (201, order(id="od_pay", status="PENDING", totalAmount=128000, checkoutUrl="https://pay.zaprite.com/order/od_pay")),
    )
    use_router(router)
    store.set_meta("rails_state", "skipped")

    args = {
        "description": "November retainer",
        "amount": "$1,280",
        "customer": {"name": "Dana", "email": "dana@example.com"},
    }
    allow("zaprite_pay", args)
    body = json.loads(HANDLERS["zaprite_pay"](args))

    assert body["ok"] is True
    assert body["amount"]["minor"] == 128000
    assert body["checkoutUrl"].endswith("od_pay")
    assert "1,280.00" in body["summary"]
    assert any(r.url.path == "/v1/contacts" for r in router.calls)
    created = router.json_bodies("POST", "/v1/orders")[0]
    assert created["invoice"]["lineItems"][0]["unitPrice"] == 128000


def test_pay_without_a_wire_is_refused_before_any_call():
    router = Router()
    use_router(router)
    store.set_meta("rails_state", "unset")
    args = {"description": "Retainer", "amount": "1280", "customer": {"name": "Dana", "email": "dana@example.com"}}
    allow("zaprite_pay", args)
    body = json.loads(HANDLERS["zaprite_pay"](args))
    assert body["error"]["code"] == "NO_RAILS"
    assert router.calls == []


def test_pay_as_an_open_link_needs_no_customer():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (201, order(id="od_open", status="PENDING", totalAmount=7500, checkoutUrl="https://pay.zaprite.com/order/od_open")))
    use_router(router)
    store.set_meta("rails_state", "skipped")
    args = {"description": "Workshop seat", "amount": "75", "as": "order"}
    allow("zaprite_pay", args)
    body = json.loads(HANDLERS["zaprite_pay"](args))
    assert body["ok"] is True
    assert body["amount"]["minor"] == 7500
    assert not any(r.url.path == "/v1/contacts" for r in router.calls)


def test_the_approval_says_what_it_creates_and_what_it_does_not():
    from hermes_plugins.zaprite.policy import pre_tool_call

    args = {"description": "Retainer", "amount": "$1,280", "customer": {"name": "Dana"}}
    directive = pre_tool_call("zaprite_pay", args)
    assert directive["action"] == "approve"
    message = directive["message"]
    assert "1,280.00" in message
    assert "does not charge" in message
    assert "will pay" not in message


def test_amount_and_approval_copy_meet_the_standard():
    import re

    from hermes_plugins.zaprite.policy import pre_tool_call

    banned = ["rails", "org", "orgid", "endpoint", "webhook", "minor unit",
              "idempot", "checkout", "payload", "nullable"]
    messages = []
    for bad in (1280, 0, "abc"):
        try:
            parse_amount(bad, "USD")
        except AmountError as exc:
            messages.append(str(exc))
    messages.append(pre_tool_call("zaprite_pay", {"description": "x", "amount": "$1,280"})["message"])
    for message in messages:
        prose = re.sub(r"https?://\S+", "", message).lower()
        assert not [w for w in banned if w in prose], f"{message}: jargon"
        assert len(message) <= 320


def test_pay_reads_a_bare_integer_as_the_amount_said():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (201, order(id="od_int", status="PENDING", checkoutUrl="https://pay.zaprite.com/order/od_int")))
    use_router(router)
    store.set_meta("rails_state", "skipped")
    args = {"description": "Retainer", "amount": 1280, "as": "order"}
    allow("zaprite_pay", args)
    body = json.loads(HANDLERS["zaprite_pay"](args))
    assert body["amount"]["minor"] == 128000


def test_pay_fails_closed_when_nobody_can_approve():
    from hermes_plugins.zaprite import policy, runtime

    class CronCtx:
        def current_cron_execution(self):
            return object()

    runtime.ctx = CronCtx()
    try:
        directive = policy.pre_tool_call("zaprite_pay", {"description": "x", "amount": "10"})
        assert directive["action"] == "block"
        assert policy.pending_count() == 0
    finally:
        runtime.ctx = None


def test_the_invoice_line_says_quantity_one():
    router = Router()
    router.add("POST", "/v1/contacts", lambda _r: (201, {"id": "c_1", "legalName": "Dana", "email": "d@x.com"}))
    router.add("POST", "/v1/orders", lambda _r: (201, order(id="od_q", totalAmount=125, checkoutUrl="https://pay.zaprite.com/order/od_q")))
    use_router(router)
    store.set_meta("rails_state", "skipped")
    args = {"description": "Seat", "amount": "$1.25", "customer": {"name": "Dana", "email": "d@x.com"}}
    allow("zaprite_pay", args)
    assert json.loads(HANDLERS["zaprite_pay"](args))["ok"] is True
    body = router.json_bodies("POST", "/v1/orders")[0]
    assert body["invoice"]["lineItems"][0]["quantity"] == 1


def test_a_wrong_total_returns_no_link():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (201, order(id="od_bad", totalAmount=100, checkoutUrl="https://pay.zaprite.com/order/od_bad")))
    use_router(router)
    store.set_meta("rails_state", "skipped")
    args = {"description": "Seat", "amount": "$1.25", "as": "order"}
    allow("zaprite_pay", args)
    body = json.loads(HANDLERS["zaprite_pay"](args))
    assert body["ok"] is False
    assert body["error"]["code"] == "AMOUNT_MISMATCH"
    assert "checkoutUrl" not in body
    assert "1.00" in body["error"]["message"] and "1.25" in body["error"]["message"]
