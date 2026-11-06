"""httpx.MockTransport helpers."""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx


class Router:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self._routes: list[tuple[str, str, Callable]] = []

    def add(self, method: str, path: str, responder: Callable) -> None:
        self._routes.append((method.upper(), path, responder))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        for method, path, responder in self._routes:
            if request.method == method and request.url.path == path:
                result = responder(request)
                if isinstance(result, httpx.Response):
                    return result
                status, body = result
                return httpx.Response(status, json=body)
        return httpx.Response(
            404,
            json={"code": "NOT_FOUND", "message": f"{request.method} {request.url.path}"},
        )

    def json_bodies(self, method: str, path: str) -> list[Any]:
        out = []
        for request in self.calls:
            if request.method == method and request.url.path == path and request.content:
                out.append(json.loads(request.content.decode()))
        return out


def order(**overrides: Any) -> dict:
    base = {
        "id": "od_123",
        "orgId": "org_1",
        "status": "PENDING",
        "totalAmount": 128000,
        "currency": "USD",
        "checkoutUrl": "https://pay.zaprite.com/order/od_123",
        "label": "March retainer",
        "orderType": "apiOrder",
        "externalUniqId": None,
        "transactions": [],
        "invoice": None,
        "contact": None,
        "paidAt": None,
    }
    base.update(overrides)
    return base


def use_router(router: Router, api_key: str = "zk_test_key") -> None:
    from hermes_plugins.zaprite import runtime, secrets

    secrets.set_api_key_for_tests(api_key)
    runtime.transport = httpx.MockTransport(router)
