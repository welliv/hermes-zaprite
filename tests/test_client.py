"""Client error envelope, redirects, and secret redaction."""

from __future__ import annotations

import json

import httpx
import pytest

from hermes_plugins.zaprite.client import ZapriteClient, ZapriteError
from tests.fakes import Router, use_router


def test_error_envelope_keeps_code_message_and_issues():
    router = Router()

    def bad(_request):
        return 400, {
            "code": "BAD_REQUEST",
            "message": "Invalid input data",
            "issues": [{"message": "Expected string, received number", "path": ["currency"]}],
        }

    router.add("POST", "/v1/orders", bad)
    use_router(router, "zk_test_key")
    client = ZapriteClient("zk_test_key", transport=router_transport(router))
    with pytest.raises(ZapriteError) as caught:
        client.create_order({"currency": "USD"})
    err = caught.value
    assert err.status == 400
    assert err.code == "BAD_REQUEST"
    assert err.message == "Invalid input data"
    assert err.issues[0]["message"].startswith("Expected string")
    assert "zk_test_key" not in json.dumps(err.to_dict())


def test_reflected_key_is_redacted():
    router = Router()

    def echo(request):
        leaked = request.headers["authorization"]
        return 401, {"code": "UNAUTHORIZED", "message": f"rejected {leaked}"}

    router.add("GET", "/v1/orders/od_1", echo)
    client = ZapriteClient("zk_live_supersecret", transport=httpx.MockTransport(router))
    with pytest.raises(ZapriteError) as caught:
        client.get_order("od_1")
    assert "zk_live_supersecret" not in caught.value.message
    assert "[redacted]" in caught.value.message


def test_redirect_is_not_followed():
    router = Router()

    def bounce(_request):
        return httpx.Response(302, headers={"location": "https://evil.example/collect"})

    router.add("GET", "/v1/orders/od_1", bounce)
    client = ZapriteClient("zk_test_key", transport=httpx.MockTransport(router))
    with pytest.raises(ZapriteError) as caught:
        client.get_order("od_1")
    assert caught.value.code == "REDIRECT"
    assert len(router.calls) == 1
    assert router.calls[0].url.host == "api.zaprite.com"


def test_network_and_timeout_are_envelopes():
    def explode(_request):
        raise httpx.ConnectError("connection refused")

    client = ZapriteClient("zk_test_key", transport=httpx.MockTransport(explode))
    with pytest.raises(ZapriteError) as caught:
        client.get_order("od_1")
    assert caught.value.code == "NETWORK"
    assert "connection refused" not in caught.value.message

    def slow(_request):
        raise httpx.ReadTimeout("slow")

    client = ZapriteClient("zk_test_key", transport=httpx.MockTransport(slow))
    with pytest.raises(ZapriteError) as caught:
        client.get_order("od_1")
    assert caught.value.code == "TIMEOUT"


def test_base_url_must_be_https_origin():
    with pytest.raises(ZapriteError) as caught:
        ZapriteClient("zk_test_key", "http://evil.example")
    assert caught.value.code == "BAD_BASE_URL"
    with pytest.raises(ZapriteError):
        ZapriteClient("zk_test_key", "https://user:pass@api.zaprite.com")


def test_issue_text_cannot_carry_a_bearer_token():
    router = Router()

    def echo(request):
        token = request.headers["authorization"].split(" ", 1)[1]
        return 400, {
            "code": "BAD_REQUEST",
            "message": "rejected",
            "issues": [{"message": f"saw Bearer {token} in the header", "path": token}],
        }

    router.add("POST", "/v1/orders", echo)
    from hermes_plugins.zaprite.tools import HANDLERS

    use_router(router, "zk_live_supersecret")
    from tests.approvals import allow

    order_args = {"amount": 100, "currency": "USD"}
    allow("zaprite_create_order", order_args)
    raw = HANDLERS["zaprite_create_order"](order_args)
    assert "zk_live_supersecret" not in raw
    assert "Bearer [redacted]" in raw or "[redacted]" in raw


def test_bearer_header_and_user_agent():
    router = Router()
    router.add("GET", "/v1/orders/od_1", lambda _r: (200, {"id": "od_1", "status": "PENDING"}))
    client = ZapriteClient("zk_test_key", transport=httpx.MockTransport(router))
    client.get_order("od_1")
    header = router.calls[0].headers["authorization"]
    assert header == "Bearer zk_test_key"
    assert router.calls[0].headers["user-agent"].startswith("zaprite-hermes/")


def router_transport(router: Router) -> httpx.MockTransport:
    return httpx.MockTransport(router)
