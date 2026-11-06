"""Orders the agent created, plus handoffs. Uses Hermes plugin_db when present.

Unit tests pin a private in-memory database first so they cannot write plugin-data.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
# Pytest pins this before any connection. Production leaves it off and uses
# Hermes plugin_db. reset_for_tests() must not clear it: a test that resets
# mid-case still has to stay off the live plugin-data file.
_memory_for_tests = False


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _memory_connection() -> sqlite3.Connection:
    return sqlite3.connect(":memory:", check_same_thread=False)


def _drop_conn_locked() -> None:
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except sqlite3.Error:
            pass
        _conn = None


def force_memory_for_tests(enabled: bool = True) -> None:
    """Pin the ledger to a private in-memory database.

    Unit tests enable this so an importable Hermes ``plugin_db`` cannot write
    ``~/.hermes/plugin-data/zaprite/data.db``. Production ``register()`` never
    calls this. The pin survives ``reset_for_tests()``.
    """
    global _memory_for_tests
    with _lock:
        _memory_for_tests = bool(enabled)
        _drop_conn_locked()


def connection() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        conn = _open()
        conn.row_factory = sqlite3.Row
        _migrate(conn)
        _conn = conn
        return conn


def _open() -> sqlite3.Connection:
    if _memory_for_tests:
        return _memory_connection()
    try:
        from plugins.plugin_storage import plugin_db

        return plugin_db("zaprite")
    except Exception:
        # A checkout that is not inside Hermes. The memory database holds no API key.
        return _memory_connection()


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            external_uniq_id TEXT,
            kind TEXT NOT NULL,
            checkout_url TEXT,
            status TEXT,
            invoice_status TEXT,
            currency TEXT,
            amount INTEGER,
            label TEXT,
            contact_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_orders_external ON orders(external_uniq_id);
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            status TEXT,
            note TEXT,
            at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS handoffs (
            id TEXT PRIMARY KEY,
            gap TEXT NOT NULL,
            url TEXT,
            note TEXT,
            outcome TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()


def reset_for_tests() -> None:
    """Close the cached connection. Does not clear the in-memory test pin."""
    with _lock:
        _drop_conn_locked()


def upsert_order(view: dict[str, Any], raw: dict | None, *, kind: str) -> None:
    conn = connection()
    now = _now()
    order_id = str(view.get("id") or "")
    if not order_id:
        return
    with _lock:
        existing = conn.execute("SELECT created_at FROM orders WHERE id = ?", (order_id,)).fetchone()
        created = existing["created_at"] if existing else now
        conn.execute(
            """
            INSERT INTO orders (
                id, external_uniq_id, kind, checkout_url, status, invoice_status,
                currency, amount, label, contact_id, created_at, updated_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                external_uniq_id = excluded.external_uniq_id,
                kind = excluded.kind,
                checkout_url = excluded.checkout_url,
                status = excluded.status,
                invoice_status = excluded.invoice_status,
                currency = excluded.currency,
                amount = excluded.amount,
                label = excluded.label,
                contact_id = excluded.contact_id,
                updated_at = excluded.updated_at,
                raw_json = excluded.raw_json
            """,
            (
                order_id,
                view.get("externalUniqId"),
                kind,
                view.get("checkoutUrl"),
                view.get("status"),
                view.get("invoice_status"),
                view.get("currency"),
                view.get("totalAmount"),
                view.get("label"),
                view.get("contactId"),
                created,
                now,
                json.dumps(raw, default=str) if raw is not None else None,
            ),
        )
        conn.commit()


def add_event(order_id: str, status: str | None, note: str) -> None:
    conn = connection()
    with _lock:
        conn.execute(
            "INSERT INTO events (order_id, status, note, at) VALUES (?, ?, ?, ?)",
            (order_id, status, note, _now()),
        )
        conn.commit()


def get_by_external(external_uniq_id: str) -> dict | None:
    conn = connection()
    row = conn.execute(
        "SELECT * FROM orders WHERE external_uniq_id = ? ORDER BY updated_at DESC LIMIT 1",
        (external_uniq_id,),
    ).fetchone()
    return dict(row) if row else None


def list_local(limit: int = 20) -> list[dict]:
    conn = connection()
    rows = conn.execute(
        "SELECT id, kind, checkout_url, status, invoice_status, currency, amount, label, updated_at "
        "FROM orders ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def count_orders() -> int:
    conn = connection()
    row = conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()
    return int(row["n"]) if row else 0


def set_meta(key: str, value: str) -> None:
    conn = connection()
    with _lock:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_meta(key: str) -> str | None:
    conn = connection()
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else None


def delete_meta(key: str) -> None:
    conn = connection()
    with _lock:
        conn.execute("DELETE FROM meta WHERE key = ?", (key,))
        conn.commit()


def add_handoff(handoff_id: str, gap: str, url: str, note: str) -> None:
    conn = connection()
    with _lock:
        conn.execute(
            "INSERT INTO handoffs (id, gap, url, note, outcome, created_at) VALUES (?, ?, ?, ?, NULL, ?)",
            (handoff_id, gap, url, note, _now()),
        )
        conn.commit()


def set_handoff_outcome(handoff_id: str, outcome: str) -> bool:
    conn = connection()
    with _lock:
        cur = conn.execute(
            "UPDATE handoffs SET outcome = ? WHERE id = ?",
            (outcome, handoff_id),
        )
        conn.commit()
        return cur.rowcount > 0


def recent_handoffs(limit: int = 5) -> list[dict]:
    conn = connection()
    rows = conn.execute(
        "SELECT id, gap, url, note, outcome, created_at FROM handoffs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
