"""Paid loop: create, re-fetch, local ledger, quote, charge cap."""

from __future__ import annotations

import json

from hermes_plugins.zaprite import runtime, store
from hermes_plugins.zaprite.constants import WEBHOOK_DISCLOSURE
from hermes_plugins.zaprite.tools import HANDLERS
from tests.approvals import allow
from tests.fakes import Router, order, use_router


def _loads(raw: str) -> dict:
    assert isinstance(raw, str)
    return json.loads(raw)


def test_create_order_returns_checkout_and_tracks_it():
    router = Router()
    router.add(
        "POST",
        "/v1/orders",
        lambda _r: (
            200,
            order(externalUniqId="retainer-march", status="PENDING"),
        ),
    )
    use_router(router)
    args = {
        "amount": 128000,
        "currency": "usd",
        "label": "March retainer",
        "external_uniq_id": "retainer-march",
        "send_receipt": False,
    }
    allow("zaprite_create_order", args, session_id="sess_1")
    raw = HANDLERS["zaprite_create_order"](args, session_id="sess_1")
    body = _loads(raw)
    assert body["ok"] is True
    assert body["checkoutUrl"] == "https://pay.zaprite.com/order/od_123"
    assert body["id"] == "od_123"
    assert body["status"] == "PENDING"
    assert body["session_notice"]
    assert body["telegram_required"] is False
    assert body["delivery"] == "active_session"
    assert "unsigned" in body["webhook"]
    assert "connected" in body["rails"].lower()
    assert "no connections api" in body["rails"].lower()
    assert store.count_orders() == 1
    sent = router.json_bodies("POST", "/v1/orders")[0]
    assert sent["amount"] == 128000
    assert sent["currency"] == "USD"
    assert sent["sendReceiptToCustomer"] is False
    assert sent["externalUniqId"] == "retainer-march"


def test_external_id_replay_does_not_create_a_second_order():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (200, order(externalUniqId="retainer-march")))
    router.add("GET", "/v1/orders/od_123", lambda _r: (200, order(status="PENDING", externalUniqId="retainer-march")))
    use_router(router)
    first = {"amount": 128000, "currency": "USD", "external_uniq_id": "retainer-march"}
    allow("zaprite_create_order", first)
    HANDLERS["zaprite_create_order"](first)
    second = {"amount": 128000, "currency": "USD", "external_uniq_id": "retainer-march"}
    allow("zaprite_create_order", second)
    raw = HANDLERS["zaprite_create_order"](second)
    body = _loads(raw)
    assert body["idempotent_replay"] is True
    assert len(router.json_bodies("POST", "/v1/orders")) == 1
    assert any(call.method == "GET" for call in router.calls)


def test_invoice_sends_line_items_and_contact():
    router = Router()

    def created(request):
        payload = json.loads(request.content.decode())
        assert payload["contactId"] == "ct_1"
        assert payload["invoice"]["lineItems"][0]["unitPrice"] == 128000
        assert payload["invoice"]["daysToPay"] == 14
        return 200, order(
            orderType="apiInvoice",
            invoice={"id": "in_1", "number": "1042", "status": "SENT"},
        )

    router.add("POST", "/v1/orders", created)
    use_router(router)
    invoice_args = {
        "contact_id": "ct_1",
        "currency": "USD",
        "days_to_pay": 14,
        "line_items": [{"name": "March retainer", "unit_price": 128000, "quantity": 1}],
    }
    allow("zaprite_create_invoice", invoice_args)
    body = _loads(HANDLERS["zaprite_create_invoice"](invoice_args))
    assert body["checkoutUrl"].startswith("https://pay.zaprite.com/order/")
    assert body["invoice_status"] == "SENT"
    assert store.count_orders() == 1


def test_watch_refetches_until_paid_and_discloses_unsigned_webhooks():
    class Clock:
        def __init__(self) -> None:
            self.t = 0.0

        def monotonic(self) -> float:
            return self.t

        def sleep(self, seconds: float) -> None:
            self.t += seconds

    clock = Clock()
    runtime.monotonic = clock.monotonic
    runtime.sleep = clock.sleep
    states = iter(["PENDING", "PROCESSING", "PAID"])
    router = Router()

    def fetched(_request):
        status = next(states)
        # Zaprite stamps paidAt only when money arrived; a PENDING order with a
        # payment timestamp is not a thing, and this fixture used to assert one.
        return 200, order(status=status, paidAt="2026-11-05T12:00:00Z" if status == "PAID" else None)

    router.add("GET", "/v1/orders/od_123", fetched)
    use_router(router)
    body = _loads(
        HANDLERS["zaprite_watch_order"](
            {"order_id": "od_123", "timeout_seconds": 30, "interval_seconds": 2},
            session_id="sess_live",
        )
    )
    assert body["paid"] is True
    assert body["polls"] == 3
    assert body["status"] == "PAID"
    assert body["webhook"] == WEBHOOK_DISCLOSURE
    assert body["session_notice"].startswith("Paid.")
    assert body["session_id"] == "sess_live"
    assert "Telegram" not in body["session_notice"]
    assert len([call for call in router.calls if call.method == "GET"]) == 3
    assert store.list_local(1)[0]["status"] == "PAID"


def test_watch_times_out_without_treating_silence_as_paid():
    runtime.monotonic = lambda: 0.0
    runtime.sleep = lambda _seconds: None
    router = Router()
    router.add("GET", "/v1/orders/od_123", lambda _r: (200, order(status="PENDING")))
    use_router(router)
    body = _loads(HANDLERS["zaprite_watch_order"]({"order_id": "od_123", "timeout_seconds": 0}))
    assert body["paid"] is False
    assert body["timed_out"] is True
    assert body["polls"] == 1
    assert "unsigned" in body["webhook"]


def test_quote_is_lightning_or_on_chain_and_respects_spend_limit():
    router = Router()
    router.add("GET", "/v1/orders/od_123", lambda _r: (200, order(totalAmount=128000)))
    router.add(
        "POST",
        "/v1/orders/create-quote",
        lambda _r: (
            200,
            {
                "method": "LIGHTNING",
                "paymentUrl": "lightning:lnbc1quote",
                "btcAmount": 1400,
                "orderAmount": 128000,
                "orderCurrency": "USD",
                "btcRate": 0.07,
            },
        ),
    )
    use_router(router)
    quote_args = {"order_id": "od_123", "transaction_method": "LIGHTNING"}
    allow("zaprite_create_quote", quote_args)
    body = _loads(HANDLERS["zaprite_create_quote"](quote_args))
    assert body["quote"]["paymentUrl"].startswith("lightning:")
    sent = router.json_bodies("POST", "/v1/orders/create-quote")[0]
    assert sent == {"orderId": "od_123", "transactionMethod": "LIGHTNING"}

    runtime.settings.spend_limit_cents = 100
    capped = {"order_id": "od_123"}
    allow("zaprite_create_quote", capped)
    refused = _loads(HANDLERS["zaprite_create_quote"](capped))
    assert refused["ok"] is False
    assert refused["error"]["code"] == "SPEND_LIMIT"
    assert len(router.json_bodies("POST", "/v1/orders/create-quote")) == 1


def test_charge_stops_before_the_network_when_over_the_cap():
    router = Router()
    router.add("GET", "/v1/orders/od_123", lambda _r: (200, order(totalAmount=900000)))
    router.add("POST", "/v1/orders/charge", lambda _r: (200, order(status="PAID")))
    use_router(router)
    runtime.settings.spend_limit_cents = 50000
    charge_args = {
        "order_id": "od_123",
        "payment_profile_id": "pp_1",
        "send_receipt": False,
    }
    allow("zaprite_charge_profile", charge_args)
    body = _loads(HANDLERS["zaprite_charge_profile"](charge_args))
    assert body["error"]["code"] == "SPEND_LIMIT"
    assert router.json_bodies("POST", "/v1/orders/charge") == []


def test_handlers_return_json_instead_of_raising():
    use_router(Router())
    allow("zaprite_create_order", {})
    raw = HANDLERS["zaprite_create_order"](None)
    body = _loads(raw)
    assert body["ok"] is False
    assert body["error"]["code"] == "BAD_REQUEST"
    raw = HANDLERS["zaprite_get_order"]({})
    assert _loads(raw)["ok"] is False
