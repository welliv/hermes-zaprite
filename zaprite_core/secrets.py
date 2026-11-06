"""The only credential read in this plugin.

Hermes stores ZAPRITE_API_KEY. Read it with agent.secret_scope.get_secret.
"""

from __future__ import annotations

from .constants import SECRET_NAME

_UNSET = object()
_test_override = _UNSET


def set_api_key_for_tests(value: str | None) -> None:
    """In-memory seam for unit tests. Production register() never calls this."""
    global _test_override
    _test_override = value


def clear_test_override() -> None:
    global _test_override
    _test_override = _UNSET


def load_api_key() -> str | None:
    if _test_override is not _UNSET:
        if _test_override is None:
            return None
        text = str(_test_override).strip()
        return text or None
    try:
        from agent.secret_scope import get_secret
    except ImportError:
        return None
    raw = get_secret(SECRET_NAME)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def key_is_configured() -> bool:
    return bool(load_api_key())
