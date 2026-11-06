"""Process settings and test seams. No secrets live here."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import DEFAULT_BASE_URL


@dataclass
class Settings:
    base_url: str = DEFAULT_BASE_URL
    spend_limit_cents: int = 0
    notify: str = "session"


ctx = None
settings = Settings()
transport = None
sleep = None  # tests inject; None means time.sleep
monotonic = None  # tests inject; None means time.monotonic


def bind(plugin_ctx) -> None:
    """Read this plugin's config_schema values. Secrets stay in secret_scope."""
    global ctx, settings
    ctx = plugin_ctx
    settings = _settings_from(plugin_ctx)


def _settings_from(plugin_ctx) -> Settings:
    base = DEFAULT_BASE_URL
    limit = 0
    notify = "session"
    if plugin_ctx is not None and hasattr(plugin_ctx, "get_config"):
        raw_base = plugin_ctx.get_config("base_url", DEFAULT_BASE_URL)
        if isinstance(raw_base, str) and raw_base.strip():
            base = raw_base.strip()
        raw_limit = plugin_ctx.get_config("spend_limit_cents", 0)
        try:
            limit = int(raw_limit or 0)
        except (TypeError, ValueError):
            limit = 0
        if limit < 0:
            limit = 0
        raw_notify = plugin_ctx.get_config("notify", "session")
        if raw_notify in ("session", "silent"):
            notify = raw_notify
    return Settings(base_url=base, spend_limit_cents=limit, notify=notify)


def reset_for_tests() -> None:
    global ctx, settings, transport, sleep, monotonic
    ctx = None
    settings = Settings()
    transport = None
    sleep = None
    monotonic = None
