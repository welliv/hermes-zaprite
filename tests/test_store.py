"""Ledger isolation: unit tests must not touch Hermes plugin-data."""

from __future__ import annotations

import json
import sqlite3
import sys
import types

from hermes_plugins.zaprite import secrets, store
from hermes_plugins.zaprite.tools import HANDLERS
from tests.fakes import Router, use_router


def _install_plugin_db(monkeypatch, plugin_db):
    mod = types.ModuleType("plugins.plugin_storage")
    mod.plugin_db = plugin_db
    pkg = types.ModuleType("plugins")
    pkg.__path__ = []  # type: ignore[attr-defined]
    pkg.plugin_storage = mod
    monkeypatch.setitem(sys.modules, "plugins", pkg)
    monkeypatch.setitem(sys.modules, "plugins.plugin_storage", mod)


def test_unit_tests_do_not_write_org_meta_to_plugin_db(monkeypatch):
    calls: list[str] = []

    def plugin_db(name, filename="data.db"):
        calls.append(name)
        # Stand-in only. The real helper would create plugin-data/<name>/data.db.
        assert filename == "data.db"
        return sqlite3.connect(":memory:", check_same_thread=False)

    _install_plugin_db(monkeypatch, plugin_db)
    store.force_memory_for_tests(True)
    store.reset_for_tests()

    store.set_meta("org_id", "org_9")
    assert calls == []
    opened = store.connection().execute("PRAGMA database_list").fetchone()
    assert opened["file"] == ""

    # Closing the handle must drop the row. A live data.db would still return org_9,
    # which is how missing-key deep links picked up a unit-test org id.
    store.reset_for_tests()
    assert store.get_meta("org_id") is None
    assert calls == []

    use_router(Router(), api_key="")
    secrets.set_api_key_for_tests(None)
    body = json.loads(HANDLERS["zaprite_doctor"]({}))
    assert body["key_mode"] == "missing"
    assert body["org_id_seen"] is None
    assert body["deep_links"]["api_keys"].endswith("/org/default/settings/api")
    assert "/org/org_9/" not in json.dumps(body["deep_links"])
    assert calls == []

    store.force_memory_for_tests(False)
    try:
        store.set_meta("org_id", "org_probe")
        assert calls == ["zaprite"]
        assert store.get_meta("org_id") == "org_probe"
        probed = store.connection().execute("PRAGMA database_list").fetchone()
        assert probed["file"] == ""
    finally:
        store.force_memory_for_tests(True)
        store.reset_for_tests()
