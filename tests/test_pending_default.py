"""Pending is what "outstanding" means. The default must include it."""

from __future__ import annotations

import json

from hermes_plugins.zaprite.tools import HANDLERS
from tests.fakes import Router, order, use_router


def _router():
    router = Router()
    router.add("GET", "/v1/orders", lambda _r: (200, {"items": [order(status="PENDING")], "meta": {"itemsCount": 1}}))
    use_router(router)
    return router


def test_report_includes_pending_by_default():
    router = _router()
    body = json.loads(HANDLERS["zaprite_report"]({}))
    assert "includePending=true" in str(router.calls[0].url)
    assert body["by_status"].get("PENDING") == 1


def test_list_orders_includes_pending_by_default():
    router = _router()
    body = json.loads(HANDLERS["zaprite_list_orders"]({}))
    assert "includePending=true" in str(router.calls[0].url)
    assert len(body["orders"]) == 1


def test_pending_can_still_be_excluded_on_request():
    router = _router()
    HANDLERS["zaprite_report"]({"include_pending": False})
    assert "includePending=true" not in str(router.calls[0].url)
