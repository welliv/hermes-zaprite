"""An agent may mark delivery, never payment."""

from __future__ import annotations

import json

from hermes_plugins.zaprite import store
from hermes_plugins.zaprite.tools import HANDLERS
from tests.approvals import allow
from tests.fakes import Router, order, use_router


def test_paid_is_refused_and_points_at_the_dashboard():
    use_router(Router())
    allow("zaprite_update_order", {"order_id": "od_1", "status": "PAID"})
    body = json.loads(HANDLERS["zaprite_update_order"]({"order_id": "od_1", "status": "PAID"}))
    assert body["ok"] is False
    assert "dashboard" in body["error"]["message"].lower()


def test_complete_is_allowed():
    router = Router()
    router.add("PATCH", "/v1/orders/od_1", lambda _r: (200, order(id="od_1", status="COMPLETE")))
    use_router(router)
    allow("zaprite_update_order", {"order_id": "od_1", "status": "COMPLETE"})
    assert json.loads(HANDLERS["zaprite_update_order"]({"order_id": "od_1", "status": "COMPLETE"}))["ok"] is True
