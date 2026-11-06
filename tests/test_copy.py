"""Chat copy is part of the product: short, plain, skimmable.

Every message a merchant reads goes through this test. It is deliberately blunt:
if a sentence needs explaining, it fails here rather than in someone's chat.
"""

from __future__ import annotations

import re

import pytest

from hermes_plugins.zaprite.zaprite_core import onboarding

# Words that only make sense to whoever wrote the plugin.
BANNED = [
    "rails",
    "org",
    "orgid",
    "endpoint",
    "webhook",
    "minor unit",
    "idempot",
    "checkout",
    "payload",
    "screen_task",
    "api call",
    "nullable",
]

MAX_CHARS = 320
MAX_LINES = 6


@pytest.fixture
def meta(monkeypatch):
    data: dict[str, str] = {}
    monkeypatch.setattr(onboarding.store, "get_meta", lambda k: data.get(k))
    monkeypatch.setattr(onboarding.store, "set_meta", lambda k, v: data.__setitem__(k, v))
    return data


def _messages(meta) -> dict[str, str]:
    out = {}
    out["key"] = onboarding.state(False, None, None)["message"]
    out["key_with_org"] = onboarding.state(False, None, "org_1")["message"]
    out["read_only"] = onboarding.state(True, "read_only", "org_1")["message"]
    out["ways_to_pay"] = onboarding.state(True, "full", "org_1")["message"]
    onboarding.confirm(["card", "lightning"])
    out["brand"] = onboarding.state(True, "full", "org_1")["message"]
    out["ready"] = onboarding.set_brand(business_name="Acme")["message"]
    onboarding.skip_brand()
    out["ready_no_pay"] = onboarding.state(True, "full", "org_1")["message"]
    return out


def test_no_jargon_reaches_the_merchant(meta):
    for name, message in _messages(meta).items():
        # URLs carry org ids and slugs; they are not prose.
        prose = re.sub(r"https?://\S+", "", message).lower().replace("api key", "")
        lowered = prose
        for word in BANNED:
            assert word not in lowered, f"{name}: {word!r} leaks into chat copy"


def test_copy_stays_short_enough_to_skim(meta):
    for name, message in _messages(meta).items():
        assert len(message) <= MAX_CHARS, f"{name} is {len(message)} chars"
        assert len(message.splitlines()) <= MAX_LINES, f"{name} is {len(message.splitlines())} lines"


def test_no_repeated_lines_or_double_spaces(meta):
    for name, message in _messages(meta).items():
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        assert len(lines) == len(set(lines)), f"{name} repeats a line"
        assert "  " not in message, f"{name} has a double space"


def test_no_step_asks_more_than_one_thing(meta):
    for name, message in _messages(meta).items():
        assert message.count("?") <= 1, f"{name} asks more than one question"


def test_error_messages_meet_the_same_bar():
    from hermes_plugins.zaprite.zaprite_core import policy

    for name in ("INVALID_KEY_MESSAGE", "READ_ONLY_MESSAGE", "PAUSED_MESSAGE", "UNATTENDED_MESSAGE", "NO_APPROVAL_MESSAGE"):
        message = getattr(policy, name)
        prose = re.sub(r"https?://\S+", "", message).lower().replace("api key", "")
        assert not [w for w in BANNED if w in prose], f"error copy {name}: jargon leaks"
        assert len(message) <= MAX_CHARS, f"error copy {name}: {len(message)} chars"
        assert len(message.splitlines()) <= 3, f"error copy {name}: too many lines"
