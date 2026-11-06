"""Zaprite for Hermes. register(ctx) wires the Paid loop."""

from __future__ import annotations

import logging
from pathlib import Path

from . import commands, runtime, schemas
from .constants import PLUGIN_NAME, TOOL_NAMES
from .policy import post_approval_response, pre_tool_call
from .tools import HANDLERS

logger = logging.getLogger("zaprite")


def register(ctx) -> None:
    """Called once when Hermes loads the plugin."""
    runtime.bind(ctx)
    for name in TOOL_NAMES:
        ctx.register_tool(
            name=name,
            toolset=PLUGIN_NAME,
            schema=schemas.SCHEMAS[name],
            handler=HANDLERS[name],
        )
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_approval_response", post_approval_response)

    def _slash(raw_args: str = "", **kwargs):
        kwargs = dict(kwargs)
        kwargs.setdefault("ctx", ctx)
        return commands.handle_slash(raw_args, **kwargs)

    ctx.register_command(
        "zaprite",
        handler=_slash,
        description="Zaprite status, setup, doctor, and pause",
        args_hint="[status|setup|doctor|kill|pause|resume|help]",
    )
    _register_skills(ctx)
    _register_blueprint(ctx)
    try:
        commands.register_cli(ctx)
    except Exception:
        logger.warning("zaprite CLI command was not registered", exc_info=True)


def _register_skills(ctx) -> None:
    # Skills live at the plugin root (sibling of zaprite_core), not inside the package.
    here = Path(__file__).resolve().parent
    candidates = (here / "skills", here.parent / "skills")
    skills_dir = next((d for d in candidates if d.is_dir()), None)
    if skills_dir is None or not hasattr(ctx, "register_skill"):
        return
    for child in sorted(skills_dir.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.is_file():
            ctx.register_skill(child.name, skill_md)


def _register_blueprint(ctx) -> None:
    register_blueprint = getattr(ctx, "register_automation_blueprint", None)
    if not callable(register_blueprint):
        return
    try:
        register_blueprint(
            "zaprite-paid-digest",
            title="Zaprite paid digest",
            description="Read-only check for paid Zaprite orders and overdue invoices.",
            schedule_template="{minute} {hour} * * *",
            prompt_template=(
                "Read-only Zaprite check. Call zaprite_report and zaprite_list_overdue. "
                "Tell this chat which orders are paid and which invoices are OVERDUE. "
                "Do not create orders, invoices, quotes, charges, contacts, or tickets. "
                "Do not mark orders complete. Do not email customers."
            ),
            category="finance",
            # {minute} and {hour} are derived from a slot named "time"; without it the host
            # rejects the blueprint at load and the automation never reaches the gallery.
            slots=(
                {
                    "name": "time",
                    "type": "time",
                    "label": "What time?",
                    "default": "08:00",
                    "help": "24h local time, e.g. 08:00",
                },
            ),
            deliver_default="origin",
            skills=("zaprite",),
            tags=("payments", "zaprite"),
        )
    except Exception:
        logger.warning("zaprite automation blueprint was not registered", exc_info=True)
