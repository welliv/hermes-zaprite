"""Approvals, cron fail-closed, read-only keys, manifest parity."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from hermes_plugins.zaprite import commands, runtime, schemas, secrets, store
from hermes_plugins.zaprite import register
from hermes_plugins.zaprite.constants import GATED_TOOLS, TOOL_NAMES, WRITE_TOOLS
from hermes_plugins.zaprite.policy import pre_tool_call
from hermes_plugins.zaprite.tools import HANDLERS
from tests.fakes import Router, use_router

ROOT = Path(__file__).resolve().parents[1]


class _Ctx:
    def __init__(self, cron=None):
        self.cron = cron
        self.tools = []
        self.hooks = []
        self.commands = []
        self.skills = []
        self.cli = []
        self.cli_commands = []
        self.blueprints = []
        self.config = {
            "base_url": "https://api.zaprite.com",
            "spend_limit_cents": 2500,
            "notify": "session",
        }

    def current_cron_execution(self):
        return self.cron

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def register_tool(self, **kwargs):
        self.tools.append(kwargs["name"])

    def register_hook(self, name, callback):
        self.hooks.append(name)
        self.hook = callback

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands.append(name)
        self.slash = handler

    def register_skill(self, name, path):
        self.skills.append((name, path))

    def register_cli_command(self, **kwargs):
        self.cli.append(kwargs["name"])
        self.cli_commands.append(kwargs)

    def register_automation_blueprint(self, key, **kwargs):
        self.blueprints.append(key)

    def ask_choice(self, question, choices):
        return "ready"


def _yaml_list(field: str) -> list[str]:
    text = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    lines = text.splitlines()
    collecting = False
    values = []
    for line in lines:
        if line.startswith(f"{field}:"):
            collecting = True
            continue
        if collecting:
            if line.startswith("  - "):
                values.append(line[4:].strip())
                continue
            if line.strip() and not line.startswith(" "):
                break
    return values


def test_register_matches_manifest_exactly():
    ctx = _Ctx()
    register(ctx)
    assert ctx.tools == TOOL_NAMES
    assert ctx.tools == _yaml_list("provides_tools")
    catalog = (ROOT / "catalog" / "zaprite.yaml").read_text(encoding="utf-8")
    catalog_tools = [
        line.strip()[2:].strip()
        for line in catalog.splitlines()
        if line.strip().startswith("- zaprite_")
    ]
    assert catalog_tools == TOOL_NAMES
    assert ctx.hooks == ["pre_tool_call", "post_approval_response"]
    assert ctx.hooks == _yaml_list("provides_hooks")
    assert "ZAPRITE_API_KEY" in (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert ctx.commands == ["zaprite"]
    assert "zaprite" in ctx.skills[0][0]
    assert ctx.blueprints == ["zaprite-paid-digest"]
    schemas.all_schemas()
    assert runtime.settings.spend_limit_cents == 2500


def test_money_tools_ask_for_human_approval_and_cron_blocks():
    runtime.ctx = _Ctx(cron=None)
    for name in sorted(GATED_TOOLS):
        directive = pre_tool_call(name, {"amount": 100, "currency": "USD"}, "task")
        assert directive["action"] == "approve", name
        assert "Approve" in directive["message"]
    assert pre_tool_call("zaprite_get_order", {"order_id": "od_1"}, "task") is None
    assert pre_tool_call("zaprite_doctor", {}, "task") is None

    runtime.ctx = _Ctx(cron=object())
    blocked = pre_tool_call("zaprite_create_invoice", {"currency": "USD"}, "task")
    assert blocked["action"] == "block"
    assert "unattended" in blocked["message"]


@pytest.mark.parametrize("name", sorted(WRITE_TOOLS))
def test_every_write_refuses_before_http_when_unattended(name):
    def explode(request):
        raise AssertionError(f"HTTP before the unattended check: {request.method} {request.url}")

    use_router(Router())
    runtime.transport = httpx.MockTransport(explode)
    runtime.ctx = _Ctx(cron=object())
    body = json.loads(HANDLERS[name]({}))
    assert body["ok"] is False
    assert body["error"]["code"] == "UNATTENDED"
    assert "zk_test_key" not in json.dumps(body)


def test_handler_fail_closed_under_cron_makes_no_http_call():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (_ for _ in ()).throw(AssertionError("must not post")))
    use_router(router)
    runtime.ctx = _Ctx(cron=object())
    body = json.loads(
        HANDLERS["zaprite_create_order"]({"amount": 100, "currency": "USD"})
    )
    assert body["ok"] is False
    assert body["error"]["code"] == "UNATTENDED"
    assert router.calls == []


def test_read_only_key_refuses_writes_and_maps_403():
    store.set_meta("key_mode", "read_only")
    router = Router()
    use_router(router)
    body = json.loads(HANDLERS["zaprite_create_order"]({"amount": 100, "currency": "USD"}))
    assert body["error"]["code"] == "READ_ONLY_KEY"
    assert router.calls == []

    store.reset_for_tests()
    store.set_meta("rails_state", "skipped")
    router.add(
        "POST",
        "/v1/orders",
        lambda _r: (403, {"code": "FORBIDDEN", "message": "read-only key"}),
    )
    from tests.approvals import allow

    order_args = {"amount": 100, "currency": "USD"}
    allow("zaprite_create_order", order_args)
    body = json.loads(HANDLERS["zaprite_create_order"](order_args))
    assert body["error"]["code"] == "READ_ONLY_KEY"
    assert store.get_meta("key_mode") == "read_only"


def test_spend_limit_on_create():
    use_router(Router())
    runtime.settings.spend_limit_cents = 1000
    body = json.loads(HANDLERS["zaprite_create_order"]({"amount": 1001, "currency": "USD"}))
    assert body["error"]["code"] == "SPEND_LIMIT"
    assert "cents" in body["error"]["message"]
    assert "sats" in body["error"]["message"]
    btc = json.loads(HANDLERS["zaprite_create_order"]({"amount": 1001, "currency": "BTC"}))
    assert btc["error"]["code"] == "SPEND_LIMIT"
    assert "sats" in btc["error"]["message"]


def test_api_key_follows_get_secret_env_fallthrough(monkeypatch):
    """Plugin reads ZAPRITE_API_KEY only through agent.secret_scope.get_secret.

    Hermes falls through to os.environ when no multiplex secret scope is
    installed (single-profile systemd / ``op run`` / shell). A scope hit wins.
    Multiplex with no scope raises, and this plugin must not catch that and
    substitute the process env. With Hermes absent, the env var is ignored.
    """
    import os
    import sys
    import types

    monkeypatch.setenv("ZAPRITE_API_KEY", "from-the-shell")
    secrets.clear_test_override()

    agent = types.ModuleType("agent")
    blocked = types.ModuleType("agent.secret_scope")
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", blocked)
    agent.secret_scope = blocked
    assert secrets.load_api_key() is None

    scope = types.ModuleType("agent.secret_scope")
    state: dict = {"mapping": None, "multiplex": False, "routed": False}

    def get_secret(name, default=None):
        assert name == "ZAPRITE_API_KEY"
        mapping = state["mapping"]
        if mapping is not None:
            val = mapping.get(name)
            if val is not None:
                return val
            # Scope miss on a routed profile must not borrow os.environ.
            # A non-routed miss still falls through, matching Hermes.
            if state["routed"]:
                return default
            return os.environ.get(name, default)
        if state["multiplex"]:
            raise RuntimeError("no profile secret scope while multiplexing is on")
        return os.environ.get(name, default)

    scope.get_secret = get_secret
    monkeypatch.setitem(sys.modules, "agent.secret_scope", scope)
    agent.secret_scope = scope

    assert secrets.load_api_key() == "from-the-shell"

    state["mapping"] = {"ZAPRITE_API_KEY": "from-hermes"}
    assert secrets.load_api_key() == "from-hermes"

    state["mapping"] = {}
    state["routed"] = False
    assert secrets.load_api_key() == "from-the-shell"

    state["routed"] = True
    assert secrets.load_api_key() is None

    state["mapping"] = None
    state["multiplex"] = True
    with pytest.raises(RuntimeError, match="no profile secret scope"):
        secrets.load_api_key()

    secrets.set_api_key_for_tests("zk_override")
    assert secrets.load_api_key() == "zk_override"


def test_source_does_not_read_env_or_ship_exec():
    import ast

    paths = [ROOT / "__init__.py", *sorted((ROOT / "zaprite_core").glob("*.py"))]
    assert len(paths) >= 10
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "environ":
                raise AssertionError(f"{path.relative_to(ROOT)} reads environ")
            if isinstance(node, ast.Name) and node.id == "getenv":
                raise AssertionError(f"{path.relative_to(ROOT)} names getenv")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "getenv"}:
                raise AssertionError(f"{path.relative_to(ROOT)} calls {node.func.id}")
            if isinstance(node, ast.Attribute) and node.attr == "getenv":
                raise AssertionError(f"{path.relative_to(ROOT)} calls getenv")
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                assert module not in {"subprocess", "dotenv"}
                assert "dotenv" not in module


def test_slash_status_hides_the_key():
    secrets.set_api_key_for_tests("zk_do_not_print")
    text = commands.handle_slash("status")
    assert "zk_do_not_print" not in text
    assert "Key: set" in text
    setup = commands.handle_slash("setup", ctx=_Ctx())
    assert "ready" in setup.lower() or "doctor" in setup.lower()


def test_write_and_gated_sets_are_subsets():
    assert GATED_TOOLS <= WRITE_TOOLS
    assert WRITE_TOOLS <= set(TOOL_NAMES)
    assert "zaprite_watch_order" not in WRITE_TOOLS
    assert "zaprite_doctor" not in WRITE_TOOLS
