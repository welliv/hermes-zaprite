"""Money is a fact from Zaprite. Work done is not money.

The bug this pins: ORDER_PAID included COMPLETE, so an agent could mark an
unpaid order COMPLETE and then see paid: true. Delivery is not payment.
"""

from __future__ import annotations

import json

from hermes_plugins.zaprite import runtime, store
from hermes_plugins.zaprite.summarize import is_paid
from hermes_plugins.zaprite.tools import HANDLERS
from tests.approvals import allow
from tests.fakes import Router, order, use_router


def test_complete_is_not_paid():
    assert is_paid({"status": "COMPLETE"}) is False
    assert is_paid({"status": "PAID"}) is True
    assert is_paid({"status": "OVERPAID"}) is True
    assert is_paid({"status": "COMPLETE", "invoice_status": "PAID"}) is True


def test_get_order_says_complete_is_not_money():
    router = Router()
    router.add("GET", "/v1/orders/od_c", lambda _r: (200, order(id="od_c", status="COMPLETE")))
    use_router(router)
    body = json.loads(HANDLERS["zaprite_get_order"]({"order_id": "od_c"}))
    assert body["paid"] is False
    assert "not that money arrived" in body["warning"]


def test_watch_does_not_stop_on_complete():
    router = Router()
    router.add("GET", "/v1/orders/od_c", lambda _r: (200, order(id="od_c", status="COMPLETE")))
    use_router(router)
    runtime.sleep = lambda _s: None
    runtime.monotonic = lambda: 1_000_000.0  # past the deadline after one poll
    body = json.loads(HANDLERS["zaprite_watch_order"]({"order_id": "od_c", "timeout_seconds": 1}))
    assert body["paid"] is False
    assert body["timed_out"] is True


def test_report_counts_complete_separately_from_paid():
    router = Router()
    router.add(
        "GET",
        "/v1/orders",
        lambda _r: (
            200,
            {
                "items": [
                    order(id="a", status="PAID"),
                    order(id="b", status="COMPLETE"),
                    order(id="c", status="PENDING"),
                ]
            },
        ),
    )
    use_router(router)
    body = json.loads(HANDLERS["zaprite_report"]({}))
    assert body["paid_on_this_page"] == 1
    assert body["completed_on_this_page"] == 1


def test_marking_complete_then_watching_still_reports_unpaid():
    store.set_meta("rails_state", "skipped")
    router = Router()
    router.add("PATCH", "/v1/orders/od_1", lambda _r: (200, order(id="od_1", status="COMPLETE")))
    router.add("GET", "/v1/orders/od_1", lambda _r: (200, order(id="od_1", status="COMPLETE")))
    use_router(router)
    allow("zaprite_update_order", {"order_id": "od_1", "status": "COMPLETE"})
    done = json.loads(HANDLERS["zaprite_update_order"]({"order_id": "od_1", "status": "COMPLETE"}))
    assert done["ok"] is True
    runtime.sleep = lambda _s: None
    runtime.monotonic = lambda: 2_000_000.0
    watched = json.loads(HANDLERS["zaprite_watch_order"]({"order_id": "od_1", "timeout_seconds": 1}))
    assert watched["paid"] is False


def test_report_rows_say_whether_money_arrived():
    router = Router()
    router.add("GET", "/v1/orders", lambda _r: (200, {"items": [
        order(id="done", status="COMPLETE"),
        order(id="paid", status="PAID"),
    ]}))
    use_router(router)
    body = json.loads(HANDLERS["zaprite_report"]({}))
    rows = {row["id"]: row for row in body["recent"]}
    assert rows["done"]["paid"] is False
    assert "not paid" in rows["done"]["money"]
    assert rows["paid"]["paid"] is True
    assert "money" not in rows["paid"]
