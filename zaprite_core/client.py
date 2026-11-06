"""Typed httpx client for https://api.zaprite.com/v1.

Handlers catch ZapriteError and return JSON. This module may raise.
Redirects are not followed: the bearer token stays on the configured origin.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from .constants import DEFAULT_BASE_URL, USER_AGENT


class ZapriteError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        issues: list | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.issues = issues or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "issues": self.issues,
        }


class MissingKey(Exception):
    def __init__(self) -> None:
        super().__init__("ZAPRITE_API_KEY is not set")


def normalize_base_url(url: str) -> str:
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raw = DEFAULT_BASE_URL
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ZapriteError(
            0,
            "BAD_BASE_URL",
            "base_url must be an origin with no user, query, or fragment.",
        )
    if not host:
        raise ZapriteError(0, "BAD_BASE_URL", "base_url is missing a host.")
    if parsed.scheme == "https":
        return raw
    if parsed.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}:
        return raw
    raise ZapriteError(
        0,
        "BAD_BASE_URL",
        "base_url must be https (http is accepted only for localhost tests).",
    )


_BEARER = re.compile(r"(?i)\bBearer\s+\S+")
_AUTH_HEADER = re.compile(r"(?i)\bauthorization\s*[:=]\s*\S+")


def redact(text: str, secret: str | None, *, limit: int | None = None) -> str:
    """Strip API keys and Authorization values. Never truncates unless limit is set."""
    if not text:
        return ""
    cleaned = _BEARER.sub("Bearer [redacted]", text)
    cleaned = _AUTH_HEADER.sub("authorization: [redacted]", cleaned)
    if secret and len(secret) >= 8 and secret in cleaned:
        cleaned = cleaned.replace(secret, "[redacted]")
    if limit is not None and len(cleaned) > limit:
        cleaned = cleaned[:limit] + "…"
    return cleaned


def _issues(raw: Any, secret: str | None) -> list:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:20]:
        if isinstance(item, dict):
            message = redact(str(item.get("message") or ""), secret, limit=500)
            path = item.get("path")
            entry: dict[str, Any] = {"message": message}
            if isinstance(path, str):
                entry["path"] = redact(path, secret, limit=200)
            elif path is not None:
                entry["path"] = path
            out.append(entry)
        else:
            out.append({"message": redact(str(item), secret)})
    return out


class ZapriteClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not api_key or not str(api_key).strip():
            raise MissingKey()
        self.api_key = str(api_key).strip()
        self.base_url = normalize_base_url(base_url)
        self._timeout = timeout
        self._transport = transport

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: list[tuple[str, str]] | None = None,
    ) -> Any:
        url = self.base_url + path
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
            ) as http:
                response = http.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    params=params,
                )
        except httpx.TimeoutException as exc:
            raise ZapriteError(
                0,
                "TIMEOUT",
                "Zaprite did not respond before the timeout.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ZapriteError(
                0,
                "NETWORK",
                "Could not reach Zaprite.",
            ) from exc

        if response.status_code in {301, 302, 303, 307, 308}:
            raise ZapriteError(
                response.status_code,
                "REDIRECT",
                "Zaprite returned a redirect. Refusing to follow it with the API key.",
            )
        if response.status_code >= 400:
            self._raise_for_status(response)
        if response.status_code == 204 or not response.content or not response.content.strip():
            return {}
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise ZapriteError(
                response.status_code,
                "BAD_RESPONSE",
                "Zaprite returned a non-JSON body.",
            ) from exc

    def _raise_for_status(self, response: httpx.Response) -> None:
        code = f"HTTP_{response.status_code}"
        message = response.reason_phrase or "Request failed"
        issues: list = []
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = None
        if isinstance(body, dict):
            if body.get("code"):
                code = str(body["code"])
            if body.get("message"):
                message = str(body["message"])
            issues = _issues(body.get("issues"), self.api_key)
        message = redact(message, self.api_key, limit=500)
        raise ZapriteError(response.status_code, code, message, issues)

    def create_order(self, body: dict) -> Any:
        return self.request("POST", "/v1/orders", json_body=body)

    def get_order(self, order_id: str) -> Any:
        return self.request("GET", f"/v1/orders/{_seg(order_id)}")

    def list_orders(self, params: list[tuple[str, str]]) -> Any:
        return self.request("GET", "/v1/orders", params=params)

    def update_order(self, order_id: str, body: dict) -> Any:
        return self.request("PATCH", f"/v1/orders/{_seg(order_id)}", json_body=body)

    def charge(self, body: dict) -> Any:
        return self.request("POST", "/v1/orders/charge", json_body=body)

    def create_quote(self, body: dict) -> Any:
        return self.request("POST", "/v1/orders/create-quote", json_body=body)

    def create_contact(self, body: dict) -> Any:
        return self.request("POST", "/v1/contacts", json_body=body)

    def get_contact(self, contact_id: str) -> Any:
        return self.request("GET", f"/v1/contacts/{_seg(contact_id)}")

    def list_contacts(self, params: list[tuple[str, str]]) -> Any:
        return self.request("GET", "/v1/contacts", params=params)

    def update_contact(self, contact_id: str, body: dict) -> Any:
        return self.request("PUT", f"/v1/contacts/{_seg(contact_id)}", json_body=body)

    def delete_contact(self, contact_id: str) -> Any:
        return self.request("DELETE", f"/v1/contacts/{_seg(contact_id)}")

    def list_webhooks(self, page: int = 1) -> Any:
        return self.request("GET", "/v1/webhooks", params=[("page", str(page))])

    def create_webhook(self, body: dict) -> Any:
        return self.request("POST", "/v1/webhooks", json_body=body)

    def delete_webhook(self, webhook_id: str) -> Any:
        return self.request("DELETE", f"/v1/webhooks/{_seg(webhook_id)}")

    def list_payment_links(self, params: list[tuple[str, str]]) -> Any:
        return self.request("GET", "/v1/payment-links", params=params)

    def get_payment_link(self, payment_link_id: str) -> Any:
        return self.request("GET", f"/v1/payment-links/{_seg(payment_link_id)}")

    def list_tickets(self, params: list[tuple[str, str]]) -> Any:
        return self.request("GET", "/v1/tickets", params=params)

    def get_ticket(self, ticket_id: str) -> Any:
        return self.request("GET", f"/v1/tickets/{_seg(ticket_id)}")

    def issue_tickets(self, body: dict) -> Any:
        return self.request("POST", "/v1/tickets/issue", json_body=body)

    def ticket_activity(self, ticket_id: str, body: dict) -> Any:
        return self.request(
            "POST",
            f"/v1/tickets/{_seg(ticket_id)}/activity",
            json_body=body,
        )


def _seg(value: str) -> str:
    return quote(str(value).strip(), safe="")
