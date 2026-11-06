"""Fresh approval, spend block before the prompt, and /zaprite kill."""

from __future__ import annotations

import argparse
import json

import httpx

from hermes_plugins.zaprite import commands, policy, runtime, store
from hermes_plugins.zaprite.policy import (
    APPROVAL_TTL_SECONDS,
    RULE_PREFIX,
    post_approval_response,
    pre_tool_call,
)
from hermes_plugins.zaprite.tools import HANDLERS
from tests.approvals import allow
from tests.fakes import Router, order, use_router
from tests.test_policy import _Ctx


def _loads(raw: str) -> dict:
    return json.loads(raw)


def _order_args() -> dict:
    return {"amount": 100, "currency": "USD", "label": "retainer"}


def test_gated_write_without_a_human_yes_sends_nothing():
    router = Router()
    use_router(router)
    body = _loads(HANDLERS["zaprite_create_order"](_order_args()))
    assert body["ok"] is False
    assert body["error"]["code"] == "NO_APPROVAL"
    assert router.calls == []


def test_rule_key_is_one_time_and_session_does_not_carry():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (200, order()))
    use_router(router)
    first_args = _order_args()
    first = pre_tool_call("zaprite_create_order", first_args, "task-a")
    second = pre_tool_call("zaprite_create_order", first_args, "task-a")
    assert first["action"] == "approve"
    assert second["rule_key"].startswith(RULE_PREFIX)
    assert first["rule_key"] != second["rule_key"]
    post_approval_response(choice="session", pattern_key=f"plugin_rule:{first['rule_key']}", description=first["message"])
    body = _loads(HANDLERS["zaprite_create_order"](first_args, task_id="task-a"))
    assert body["ok"] is True
    assert len(router.calls) == 1
    again = _loads(HANDLERS["zaprite_create_order"](first_args, task_id="task-a"))
    assert again["error"]["code"] == "NO_APPROVAL"
    assert len(router.calls) == 1


def test_deny_smart_and_skipped_prompt_do_not_grant():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (_ for _ in ()).throw(AssertionError("must not post")))
    use_router(router)
    denied = pre_tool_call("zaprite_delete_contact", {"contact_id": "ct_1"})
    post_approval_response(choice="deny", pattern_key=denied["rule_key"], description=denied["message"])
    body = _loads(HANDLERS["zaprite_delete_contact"]({"contact_id": "ct_1"}))
    assert body["error"]["code"] == "NO_APPROVAL"

    smart = pre_tool_call("zaprite_delete_contact", {"contact_id": "ct_1"})
    post_approval_response(
        choice="once",
        pattern_key=smart["rule_key"],
        description=smart["message"],
        decided_by="aux_llm",
        surface="smart",
    )
    body = _loads(HANDLERS["zaprite_delete_contact"]({"contact_id": "ct_1"}))
    assert body["error"]["code"] == "NO_APPROVAL"

    pre_tool_call("zaprite_delete_contact", {"contact_id": "ct_1"})
    skipped = _loads(HANDLERS["zaprite_delete_contact"]({"contact_id": "ct_1"}))
    assert skipped["error"]["code"] == "NO_APPROVAL"
    assert router.calls == []


def test_over_cap_blocks_in_the_hook_before_an_approval_prompt():
    runtime.settings.spend_limit_cents = 1000
    directive = pre_tool_call("zaprite_create_order", {"amount": 1001, "currency": "BTC"})
    assert directive["action"] == "block"
    assert "sats" in directive["message"]
    assert "rule_key" not in directive
    assert policy.pending_count() == 0


def test_approval_expires():
    router = Router()
    use_router(router)
    clock = {"now": 0.0}
    policy.set_clock_for_tests(lambda: clock["now"])
    args = _order_args()
    directive = pre_tool_call("zaprite_create_order", args)
    post_approval_response(choice="once", pattern_key=directive["rule_key"], description=directive["message"])
    clock["now"] = APPROVAL_TTL_SECONDS + 5
    body = _loads(HANDLERS["zaprite_create_order"](args))
    assert body["error"]["code"] == "NO_APPROVAL"
    assert router.calls == []


def test_slash_kill_pause_and_resume_clear_pending_and_block_writes():
    router = Router()
    router.add("POST", "/v1/orders", lambda _r: (200, order()))
    use_router(router)
    args = _order_args()
    pending = pre_tool_call("zaprite_create_order", args)
    assert policy.pending_count() == 1
    paused = commands.handle_slash("kill")
    assert "paused" in paused.lower()
    assert "Cleared 1 pending approval" in paused
    assert policy.pending_count() == 0
    post_approval_response(choice="once", pattern_key=pending["rule_key"], description=pending["message"])
    blocked = pre_tool_call("zaprite_create_order", args)
    assert blocked["action"] == "block"
    body = _loads(HANDLERS["zaprite_create_order"](args))
    assert body["error"]["code"] == "PAUSED"
    assert router.calls == []
    status = commands.handle_slash("status")
    assert "Writes: paused" in status
    resumed = commands.handle_slash("resume")
    assert "open again" in resumed
    still = _loads(HANDLERS["zaprite_create_order"](args))
    assert still["error"]["code"] == "NO_APPROVAL"
    allow("zaprite_create_order", args)
    paid = _loads(HANDLERS["zaprite_create_order"](args))
    assert paid["ok"] is True
    assert commands.handle_slash("pause").startswith("Zaprite writes are paused")
    assert "open again" in commands.handle_slash("resume")
    assert "already open" in commands.handle_slash("resume")


def test_cron_block_does_not_leave_a_pending_approval():
    runtime.ctx = _Ctx(cron=object())
    blocked = pre_tool_call("zaprite_create_order", _order_args())
    assert blocked["action"] == "block"
    assert policy.pending_count() == 0


def test_slash_pause_alias_and_unknown_command():
    text = commands.handle_slash("stop")
    assert "paused" in text.lower()
    assert "Unknown" in commands.handle_slash("nope")
    assert "kill" in commands.handle_slash("help")


def test_cli_pause_and_resume():
    ctx = _Ctx()
    from hermes_plugins.zaprite import register

    register(ctx)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="top")
    zap = sub.add_parser("zaprite")
    ctx.cli_commands[0]["setup_fn"](zap)
    parser.parse_args(["zaprite", "kill"]).func(parser.parse_args(["zaprite", "kill"]))
    assert policy.writes_paused()
    parser.parse_args(["zaprite", "resume"]).func(parser.parse_args(["zaprite", "resume"]))
    assert policy.writes_paused() is False


def test_pause_stops_a_watch_before_and_during_polls():
    router = Router()
    router.add("GET", "/v1/orders/od_123", lambda _r: (200, order(status="PENDING")))
    use_router(router)
    policy.pause_writes()
    stopped = _loads(HANDLERS["zaprite_watch_order"]({"order_id": "od_123", "timeout_seconds": 30}))
    assert stopped["paused"] is True
    assert stopped["polls"] == 0
    assert router.calls == []

    policy.resume_writes()
    polls = {"n": 0}

    def clock() -> float:
        polls["n"] += 1
        return float(polls["n"])

    def sleeper(_seconds: float) -> None:
        policy.pause_writes()

    runtime.monotonic = clock
    runtime.sleep = sleeper
    mid = _loads(HANDLERS["zaprite_watch_order"]({"order_id": "od_123", "timeout_seconds": 30, "interval_seconds": 2}))
    assert mid["paused"] is True
    assert mid["polls"] == 1
    assert len(router.calls) == 1


def test_paused_contact_edit_sends_nothing_and_resume_does_not_restore_it():
    def explode(request):
        raise AssertionError(f"HTTP during pause: {request.method} {request.url}")

    use_router(Router())
    runtime.transport = httpx.MockTransport(explode)
    commands.handle_slash("kill")
    body = _loads(HANDLERS["zaprite_update_contact"]({"contact_id": "ct_1", "email": "a@b.c"}))
    assert body["error"]["code"] == "PAUSED"
    commands.handle_slash("resume")
    # Contact edits are writes, not gated money tools. Resume lets them through
    # without a fresh approval record. A router with no route proves we left pause.
    runtime.transport = None
    router = Router()
    router.add("GET", "/v1/contacts/ct_1", lambda _r: (200, {"id": "ct_1", "legalName": "N", "email": "old@b.c"}))
    router.add("PUT", "/v1/contacts/ct_1", lambda _r: (200, {"id": "ct_1", "legalName": "N", "email": "a@b.c"}))
    use_router(router)
    edited = _loads(HANDLERS["zaprite_update_contact"]({"contact_id": "ct_1", "email": "a@b.c"}))
    assert edited["ok"] is True


def test_docs_name_the_pause_command_and_the_gaps():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    setup = (root / "setup.md").read_text(encoding="utf-8")
    # The install line must name the repo the catalog entry names, so a rename
    # cannot leave the docs pointing at a repository that no longer exists.
    catalog = (root / "catalog" / "zaprite.yaml").read_text(encoding="utf-8")
    repo = next(line.split("https://github.com/", 1)[1].strip() for line in catalog.splitlines() if line.startswith("repo: https://github.com/"))
    assert f"hermes plugins install {repo} --ref " in readme
    assert "--yes-deps --enable" in readme
    assert "/zaprite kill" in readme
    assert "docs/api-gaps.md" in readme
    assert "sandbox" in readme.lower()
    assert "unsigned" in readme.lower()
    assert "branding_profile" in readme
    assert "Settings → Profile" in readme
    assert "/zaprite kill" in setup
    assert "docs/api-gaps.md" in setup
    manifest = (root / "plugin.yaml").read_text(encoding="utf-8")
    assert "post_approval_response" in manifest
    assert 'requires_hermes: ">=0.21.0"' in manifest
    catalog = (root / "catalog" / "zaprite.yaml").read_text(encoding="utf-8")
    assert "post_approval_response" in catalog
    assert "Sandbox org" in catalog
    import re

    pinned = re.search(r'(?m)^sha:\s*"([0-9a-f]{40})"', catalog)
    assert pinned, "catalog sha must be a 40-character release-tree commit"
    sha = pinned.group(1)
    assert f"--ref {sha} --yes-deps --enable" in readme
    assert f"--ref {sha} --yes-deps --enable" in setup
    assert sha in (root / "catalog" / "PIN.md").read_text(encoding="utf-8")
    assert "__RELEASE_TREE_SHA__" not in readme
    assert "__RELEASE_TREE_SHA__" not in setup
