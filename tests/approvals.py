"""Record a fresh human yes for one gated tool call."""

from __future__ import annotations

from hermes_plugins.zaprite.policy import post_approval_response, pre_tool_call


def allow(tool_name: str, args: dict | None = None, **kwargs) -> dict:
    payload = args if isinstance(args, dict) else {}
    directive = pre_tool_call(tool_name, payload, **kwargs)
    if not isinstance(directive, dict) or directive.get("action") != "approve":
        raise AssertionError(f"expected an approval prompt for {tool_name}, got {directive!r}")
    post_approval_response(
        choice="once",
        pattern_key=directive["rule_key"],
        description=directive.get("message") or "",
        **kwargs,
    )
    return directive
