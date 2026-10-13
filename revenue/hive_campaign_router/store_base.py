# SPDX-License-Identifier: Apache-2.0
"""SQLite schema, connection lifetime, and shared Store helpers."""
from __future__ import annotations

from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from route_validation import ValidationError


class StoreBase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with closing(self.connect()) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    brand TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS offers (
                    id INTEGER PRIMARY KEY,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    headline TEXT NOT NULL,
                    body TEXT NOT NULL,
                    cta_label TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS presets (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    utm_source TEXT NOT NULL,
                    utm_medium TEXT NOT NULL,
                    utm_campaign TEXT NOT NULL,
                    utm_content TEXT NOT NULL DEFAULT '',
                    utm_term TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS links (
                    id INTEGER PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                    offer_id INTEGER REFERENCES offers(id) ON DELETE RESTRICT,
                    preset_id INTEGER REFERENCES presets(id) ON DELETE SET NULL,
                    destination TEXT NOT NULL,
                    route_mode TEXT NOT NULL CHECK(route_mode IN ('redirect', 'offer')),
                    active INTEGER NOT NULL CHECK(active IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK(route_mode = 'redirect' OR offer_id IS NOT NULL)
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    link_id INTEGER NOT NULL REFERENCES links(id) ON DELETE RESTRICT,
                    event_type TEXT NOT NULL CHECK(event_type IN ('click', 'conversion')),
                    parent_event_id TEXT,
                    occurred_at TEXT NOT NULL,
                    referrer_host TEXT,
                    utm_source TEXT NOT NULL,
                    utm_medium TEXT NOT NULL,
                    utm_campaign TEXT NOT NULL,
                    utm_content TEXT NOT NULL,
                    utm_term TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_link_type_idx
                    ON events(link_id, event_type, occurred_at);
                CREATE INDEX IF NOT EXISTS events_campaign_idx
                    ON events(utm_campaign, event_type, occurred_at);
                """
            )

    @staticmethod
    def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    @staticmethod
    def _int_id(value: Any, field: str, *, optional: bool = False) -> int | None:
        if optional and value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValidationError(f"{field} must be an integer")
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{field} must be an integer") from exc
        if result < 1 or str(result) != str(value).strip():
            raise ValidationError(f"{field} must be a positive integer")
        return result
