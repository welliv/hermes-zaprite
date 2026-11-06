"""The report answers by kind, and the doctor says what is out of reach."""

from __future__ import annotations

import json

from hermes_plugins.zaprite.tools import HANDLERS
from tests.fakes import Router, order, use_router


def test_report_separates_owed_from_open_links():
    router = Router()
    router.add(
        "GET",
        "/v1/orders",
        lambda _r: (
            200,
            {
                "items": [
                    order(id="od_inv", orderType="apiInvoice", status="PENDING", totalAmount=120000),
                    order(id="od_ord", orderType="apiOrder", status="PENDING", totalAmount=9000),
                    order(id="od_paid", orderType="apiInvoice", status="PAID", totalAmount=5000, paidAt="2026-11-01T00:00:00Z"),
                ]
            },
        ),
    )
    use_router(router)
    body = json.loads(HANDLERS["zaprite_report"]({}))
    assert body["by_type"] == {"apiInvoice": 2, "apiOrder": 1}
    assert body["owed"] == {"USD": 120000}
    assert body["open_links"] == {"USD": 9000}


def test_doctor_names_the_screens_it_cannot_reach():
    body = json.loads(HANDLERS["zaprite_doctor"]({}))
    assert len(body["not_here"]) == 8
    assert "recurring invoices" in body["not_here"]
    assert "dashboard" in body["jobs"].lower()


def test_the_doctor_copy_meets_the_copy_standard():
    import re
    body = json.loads(HANDLERS["zaprite_doctor"]({}))
    jobs = body["jobs"]
    banned = ["rails", "org", "orgid", "endpoint", "webhook", "minor unit",
              "idempot", "checkout", "payload", "nullable"]
    prose = re.sub(r"https?://\S+", "", jobs).lower()
    assert not [w for w in banned if w in prose], f"jargon: {[w for w in banned if w in prose]}"
    assert len(jobs) <= 320
    assert len(jobs.splitlines()) <= 3
