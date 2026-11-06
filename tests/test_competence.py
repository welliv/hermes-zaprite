"""Doctor, overdue scan, bridge handoff, sovereign closer."""

from __future__ import annotations

import json

from hermes_plugins.zaprite import store
from hermes_plugins.zaprite.tools import HANDLERS
from tests.approvals import allow
from tests.fakes import Router, order, use_router


def _loads(raw: str) -> dict:
    return json.loads(raw)


def test_doctor_missing_key_does_not_call_the_network():
    router = Router()
    router.add("GET", "/v1/webhooks", lambda _r: (_ for _ in ()).throw(AssertionError("network")))
    use_router(router, api_key="")
    from hermes_plugins.zaprite import secrets

    secrets.set_api_key_for_tests(None)
    body = _loads(HANDLERS["zaprite_doctor"]({}))
    assert body["key_present"] is False
    assert body["key_mode"] == "missing"
    assert body["connections_api"] is False
    assert "unsigned" in body["webhook"]
    assert router.calls == []


def test_doctor_detects_read_only_and_full_without_creating_an_order():
    def live(mode_status, mode_body):
        router = Router()
        router.add(
            "GET",
            "/v1/webhooks",
            lambda _r: (200, {"items": [{"id": "wh_1", "url": "https://example.com/hook"}], "meta": {}}),
        )
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
        router.add("POST", "/v1/orders", lambda _r: (mode_status, mode_body))
        use_router(router)
        body = _loads(HANDLERS["zaprite_doctor"]({}))
        posted = router.json_bodies("POST", "/v1/orders")
        assert posted == [{}]
        return body

    read_only = live(403, {"code": "FORBIDDEN", "message": "read-only"})
    assert read_only["key_mode"] == "read_only"
    assert read_only["connections_api"] is False
    assert read_only["org_slug_discovered"] is False
    assert read_only["documented_org_slug"] == "default"
    assert "/org/" not in read_only["deep_links"]["connections_help"]
    # Once orgId is seen, app deep links prefer /org/{orgId}/ over the docs slug.
    assert read_only["org_id_seen"] == "org_9"
    assert read_only["org_links_use_org_id"] is True
    assert read_only["deep_links"]["api_keys"].endswith("/org/org_9/settings/api")
    assert read_only["deep_links"]["connections"].endswith("/org/org_9/connections")
    assert read_only["deep_links"]["sign_in"] == "https://app.zaprite.com"
    assert "sandbox" in read_only["environment"].lower()
    assert "checkoutUrl" in read_only["invoice_email"] or "checkout" in read_only["invoice_email"].lower()
    assert "zaprite_doctor" in read_only["context_first"].lower()
    assert "fail closed" in read_only["context_first"].lower()
    note = read_only["connections_note"].lower()
    assert "connection" in note
    assert store.get_meta("key_mode") == "read_only"

    store.reset_for_tests()
    full = live(400, {"code": "BAD_REQUEST", "message": "Invalid input data", "issues": []})
    assert full["key_mode"] == "full"
    assert full["ok"] is True
    assert full["webhook_count"] == 1


def test_overdue_filters_invoice_status():
    router = Router()

    def listed(request):
        order_type = request.url.params.get("type")
        if order_type == "invoice":
            item = order(
                id="od_due",
                status="PENDING",
                invoice={"id": "in_9", "number": "99", "status": "OVERDUE"},
                checkoutUrl="https://pay.zaprite.com/order/od_due",
            )
        else:
            item = order(id="od_ok", status="PAID", invoice={"status": "PAID"})
        return 200, {"items": [item], "meta": {"pagesCount": 1, "page": 1}}

    router.add("GET", "/v1/orders", listed)
    use_router(router)
    body = _loads(HANDLERS["zaprite_list_overdue"]({}))
    assert body["count"] == 1
    assert body["overdue"][0]["id"] == "od_due"
    assert body["overdue"][0]["invoice_status"] == "OVERDUE"


def test_bridge_handoff_does_not_browse():
    router = Router()
    use_router(router)
    handoff_args = {"gap": "lightning_discount", "note": "10% on Lightning"}
    allow("zaprite_bridge_handoff", handoff_args)
    body = _loads(HANDLERS["zaprite_bridge_handoff"](handoff_args))
    assert body["browser"] == "not_used"
    assert body["unsupervised_browser"] is False
    assert body["url"].startswith("https://app.zaprite.com/")
    assert router.calls == []
    follow_args = {"handoff_id": body["handoff_id"], "outcome": "Set 10% and copied ck_1"}
    allow("zaprite_bridge_handoff", follow_args)
    follow = _loads(HANDLERS["zaprite_bridge_handoff"](follow_args))
    assert follow["recorded_outcome"] is True
    assert router.calls == []


def test_sovereign_rails_is_guidance_only():
    router = Router()
    use_router(router)
    body = _loads(HANDLERS["zaprite_sovereign_rails"]({}))
    assert body["ok"] is True
    assert "xpub" in body["human_first"]
    assert "Lightning Address" in body["human_first"]
    blob = json.dumps(body)
    assert "non-custodial" in blob.lower()
    assert "zaprite_create_quote" in blob or "create_quote" in blob
    assert router.calls == []


def test_report_counts_statuses():
    router = Router()
    router.add(
        "GET",
        "/v1/orders",
        lambda _r: (
            200,
            {
                "items": [order(status="PAID"), order(id="od_2", status="COMPLETE")],
                "meta": {"itemsCount": 2, "pagesCount": 1, "page": 1, "perPage": 100},
            },
        ),
    )
    use_router(router)
    body = _loads(HANDLERS["zaprite_report"]({}))
    assert body["by_status"]["PAID"] == 1
    assert body["by_status"]["COMPLETE"] == 1
    # COMPLETE is work done, not money. It used to count as paid; that was the bug.
    assert body["paid_on_this_page"] == 1
    assert body["completed_on_this_page"] == 1



def test_doctor_records_unexpected_empty_create():
    router = Router()
    router.add("GET", "/v1/webhooks", lambda _r: (200, {"items": [], "meta": {}}))
    router.add("GET", "/v1/orders", lambda _r: (200, {"items": [], "meta": {}}))
    router.add("POST", "/v1/orders", lambda _r: (200, order(status="PENDING")))
    use_router(router)
    body = _loads(HANDLERS["zaprite_doctor"]({}))
    assert body["key_mode"] == "unexpected_write"
    assert store.count_orders() == 1


def test_update_contact_fetches_then_merges():
    router = Router()
    router.add(
        "GET",
        "/v1/contacts/ct_1",
        lambda _r: (
            200,
            {
                "id": "ct_1",
                "legalName": "Northwind",
                "email": "old@example.com",
                "internalNote": "keep me",
                "orgId": "org_1",
            },
        ),
    )

    def put(request):
        payload = __import__("json").loads(request.content.decode())
        assert payload["legalName"] == "Northwind"
        assert payload["email"] == "new@example.com"
        assert payload["internalNote"] == "keep me"
        assert "orgId" not in payload
        payload["id"] = "ct_1"
        return 200, payload

    router.add("PUT", "/v1/contacts/ct_1", put)
    use_router(router)
    raw = HANDLERS["zaprite_update_contact"]({"contact_id": "ct_1", "email": "new@example.com"})
    body = _loads(raw)
    assert body["ok"] is True
    assert body["merged"] is True
    assert body["contact"]["email"] == "new@example.com"


def test_create_and_delete_webhook_and_reject_cleartext():
    router = Router()
    router.add(
        "POST",
        "/v1/webhooks",
        lambda _r: (200, {"id": "wh_1", "url": "https://merchant.example/hook", "label": "ops"}),
    )
    router.add("DELETE", "/v1/webhooks/wh_1", lambda _r: (204, {}))
    router.add(
        "GET",
        "/v1/payment-links/pl_1",
        lambda _r: (200, {"id": "pl_1", "type": "EVENT", "items": [{"id": "pli_1"}]}),
    )
    use_router(router)
    webhook_args = {"url": "https://merchant.example/hook", "label": "ops"}
    allow("zaprite_create_webhook", webhook_args)
    created = _loads(HANDLERS["zaprite_create_webhook"](webhook_args))
    assert created["ok"] is True
    assert created["webhook_endpoint"]["id"] == "wh_1"
    assert "unsigned" in created["webhook"]
    sent = router.json_bodies("POST", "/v1/webhooks")[0]
    assert sent == {"url": "https://merchant.example/hook", "label": "ops"}
    cleartext = {"url": "http://evil.example/hook"}
    allow("zaprite_create_webhook", cleartext)
    refused = _loads(HANDLERS["zaprite_create_webhook"](cleartext))
    assert refused["ok"] is False
    delete_args = {"webhook_id": "wh_1"}
    allow("zaprite_delete_webhook", delete_args)
    deleted = _loads(HANDLERS["zaprite_delete_webhook"](delete_args))
    assert deleted["ok"] is True
    assert deleted["deleted"] == "wh_1"
    link = _loads(HANDLERS["zaprite_get_payment_link"]({"payment_link_id": "pl_1"}))
    assert link["ok"] is True
    assert link["payment_link"]["id"] == "pl_1"
