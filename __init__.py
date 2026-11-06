"""Zaprite for Hermes. register(ctx) wires the Paid loop."""

try:
    from .zaprite_core.registration import register
except ImportError:  # pytest may load this file without a package parent
    from zaprite_core.registration import register

__all__ = ["register"]
