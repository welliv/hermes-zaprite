"""The paid-digest blueprint must survive the host's own validation.

Hermes derives {minute}/{hour} from a slot named "time" (cron/blueprint_plugins.py,
_DERIVED_SCHEDULE_FIELDS). Registering the blueprint without that slot raises ValueError,
the host logs a warning and drops the automation — silently, from the user's point of view.
The fake ctx used elsewhere does not validate, so this test re-implements the rule.
"""

from __future__ import annotations

import string
from datetime import datetime

from hermes_plugins.zaprite import register
from tests.test_policy import _Ctx

DERIVED = {"minute": "time", "hour": "time", "dow": None}


class _RecordingCtx(_Ctx):
    def __init__(self):
        super().__init__()
        self.blueprint_calls = []

    def register_automation_blueprint(self, key, **kwargs):
        self.blueprint_calls.append((key, kwargs))
        self.blueprints.append(key)


def _placeholders(template: str) -> list[str]:
    return [name for _lit, name, _spec, _conv in string.Formatter().parse(template) if name]


def test_paid_digest_blueprint_satisfies_host_schedule_rules():
    ctx = _RecordingCtx()
    register(ctx)

    assert len(ctx.blueprint_calls) == 1, "the blueprint must register exactly once"
    key, kwargs = ctx.blueprint_calls[0]
    assert key == "zaprite-paid-digest"

    slots = {slot["name"]: slot for slot in kwargs["slots"]}
    for name in _placeholders(kwargs["schedule_template"]):
        needed = DERIVED.get(name, name)
        if needed is None:
            continue
        assert needed in slots, f"schedule uses {{{name}}} but no slot {needed!r} exists"

    time_slot = slots["time"]
    assert time_slot["type"] == "time"
    datetime.strptime(str(time_slot["default"]), "%H:%M")  # a real 24h time
    for name in _placeholders(kwargs["prompt_template"]):
        assert name in slots, f"prompt uses {{{name}}} but there is no such slot"
