"""Load the plugin as hermes_plugins.zaprite so tests match Hermes import shape."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Build hermes_plugins.zaprite as a real package pointing at the plugin root,
# matching how Hermes loads an installed plugin.
parent = sys.modules.get("hermes_plugins")
if parent is None:
    parent = types.ModuleType("hermes_plugins")
    parent.__path__ = []  # type: ignore[attr-defined]
    sys.modules["hermes_plugins"] = parent

# Import the plugin package under a temporary name first if needed, then alias.
# The directory name has a hyphen, so load via spec from ROOT.
import importlib.util

spec = importlib.util.spec_from_file_location(
    "hermes_plugins.zaprite",
    ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
assert spec and spec.loader
pkg = importlib.util.module_from_spec(spec)
pkg.__path__ = [str(ROOT)]  # type: ignore[attr-defined]
sys.modules["hermes_plugins.zaprite"] = pkg
parent.zaprite = pkg  # type: ignore[attr-defined]
spec.loader.exec_module(pkg)

# Eager-load implementation modules so handlers and tests share one object graph.
for name in (
    "zaprite_core",
    "zaprite_core.client",
    "zaprite_core.commands",
    "zaprite_core.constants",
    "zaprite_core.policy",
    "zaprite_core.runtime",
    "zaprite_core.schemas",
    "zaprite_core.secrets",
    "zaprite_core.service",
    "zaprite_core.store",
    "zaprite_core.summarize",
    "zaprite_core.tools",
    "zaprite_core.registration",
):
    importlib.import_module(f"hermes_plugins.zaprite.{name}")

# Convenience aliases used by older tests: hermes_plugins.zaprite.secrets → core
core = sys.modules["hermes_plugins.zaprite.zaprite_core"]
for attr in (
    "client",
    "commands",
    "constants",
    "policy",
    "runtime",
    "schemas",
    "secrets",
    "service",
    "store",
    "summarize",
    "tools",
    "registration",
):
    mod = sys.modules[f"hermes_plugins.zaprite.zaprite_core.{attr}"]
    setattr(pkg, attr, mod)
    sys.modules[f"hermes_plugins.zaprite.{attr}"] = mod

PLUGIN = pkg


def _refuse_live_zaprite_db() -> None:
    """If this pytest process can see Hermes, never create plugin-data/zaprite."""
    try:
        import plugins.plugin_storage as storage
    except Exception:
        return
    real = getattr(storage, "plugin_db", None)
    if real is None or getattr(real, "_zaprite_tests_guard", False):
        return

    def plugin_db(name, *args, **kwargs):
        if name == "zaprite":
            raise RuntimeError("unit tests cannot open the live zaprite plugin database")
        return real(name, *args, **kwargs)

    plugin_db._zaprite_tests_guard = True  # type: ignore[attr-defined]
    storage.plugin_db = plugin_db


# Pin before collection imports a test that touches the ledger. reset_for_tests()
# only closes the handle; on a live Hermes install the next open would otherwise
# be plugin_db("zaprite") and commit rows into plugin-data/zaprite/data.db.
sys.modules["hermes_plugins.zaprite.zaprite_core.store"].force_memory_for_tests(True)
_refuse_live_zaprite_db()


@pytest.fixture(autouse=True)
def _fresh_plugin_state():
    from hermes_plugins.zaprite import policy, runtime, secrets, store

    store.force_memory_for_tests(True)
    store.reset_for_tests()
    # Most tests are about orders, not onboarding; a test that wants the gate sets it itself.
    store.set_meta("rails_state", "skipped")
    secrets.clear_test_override()
    runtime.reset_for_tests()
    policy.reset_for_tests()
    yield
    store.force_memory_for_tests(True)
    store.reset_for_tests()
    secrets.clear_test_override()
    runtime.reset_for_tests()
    policy.reset_for_tests()
