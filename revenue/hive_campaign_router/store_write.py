# SPDX-License-Identifier: Apache-2.0
"""RouteFoundry write operations and idempotent event recording."""
from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from route_validation import (
    EVENT_TYPES, ROUTE_MODES, UTM_KEYS, EventResult, ValidationError, event_id,
    referrer_host, require_text, utc_now, validate_destination, validate_slug,
)


class StoreWriteMixin:
    def create_product(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        name = require_text(payload.get("name"), "name", maximum=120)
        brand = require_text(payload.get("brand", name), "brand", maximum=80)
        with self.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO products(name, brand, created_at) VALUES (?, ?, ?)",
                (name, brand, utc_now()),
            )
            row = conn.execute("SELECT * FROM products WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def create_offer(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        product_id = self._int_id(payload.get("product_id"), "product_id")
        name = require_text(payload.get("name"), "name", maximum=120)
        headline = require_text(payload.get("headline"), "headline", maximum=180)
        body = require_text(payload.get("body"), "body", maximum=2000)
        cta = require_text(payload.get("cta_label", "Continue"), "cta_label", maximum=80)
        with self.transaction() as conn:
            if conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone() is None:
                raise ValidationError("product_id does not exist")
            cursor = conn.execute(
                "INSERT INTO offers(product_id, name, headline, body, cta_label, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (product_id, name, headline, body, cta, utc_now()),
            )
            row = conn.execute("SELECT * FROM offers WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def create_preset(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        values = {
            "name": require_text(payload.get("name"), "name", maximum=80),
            "utm_source": require_text(payload.get("utm_source"), "utm_source", maximum=120),
            "utm_medium": require_text(payload.get("utm_medium"), "utm_medium", maximum=120),
            "utm_campaign": require_text(payload.get("utm_campaign"), "utm_campaign", maximum=160),
            "utm_content": require_text(payload.get("utm_content", ""), "utm_content", maximum=160, allow_empty=True),
            "utm_term": require_text(payload.get("utm_term", ""), "utm_term", maximum=160, allow_empty=True),
        }
        with self.transaction() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO presets(name, utm_source, utm_medium, utm_campaign, utm_content, utm_term, created_at) "
                    "VALUES (:name, :utm_source, :utm_medium, :utm_campaign, :utm_content, :utm_term, :created_at)",
                    {**values, "created_at": utc_now()},
                )
            except sqlite3.IntegrityError as exc:
                raise ValidationError("preset name already exists") from exc
            row = conn.execute("SELECT * FROM presets WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def _validate_link_refs(
        self, conn: sqlite3.Connection, product_id: int, offer_id: int | None, preset_id: int | None, route_mode: str
    ) -> None:
        if conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone() is None:
            raise ValidationError("product_id does not exist")
        if offer_id is not None:
            offer = conn.execute("SELECT product_id FROM offers WHERE id = ?", (offer_id,)).fetchone()
            if offer is None:
                raise ValidationError("offer_id does not exist")
            if offer["product_id"] != product_id:
                raise ValidationError("offer_id belongs to another product")
        if route_mode == "offer" and offer_id is None:
            raise ValidationError("offer routes require an offer_id")
        if preset_id is not None and conn.execute("SELECT 1 FROM presets WHERE id = ?", (preset_id,)).fetchone() is None:
            raise ValidationError("preset_id does not exist")

    def create_link(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        slug = validate_slug(payload.get("slug"))
        product_id = self._int_id(payload.get("product_id"), "product_id")
        offer_id = self._int_id(payload.get("offer_id"), "offer_id", optional=True)
        preset_id = self._int_id(payload.get("preset_id"), "preset_id", optional=True)
        destination = validate_destination(payload.get("destination"))
        route_mode = require_text(payload.get("route_mode", "offer"), "route_mode", maximum=16)
        if route_mode not in ROUTE_MODES:
            raise ValidationError("route_mode must be redirect or offer")
        active = payload.get("active", True)
        if not isinstance(active, bool):
            raise ValidationError("active must be true or false")
        now = utc_now()
        with self.transaction() as conn:
            self._validate_link_refs(conn, product_id, offer_id, preset_id, route_mode)
            try:
                cursor = conn.execute(
                    "INSERT INTO links(slug, product_id, offer_id, preset_id, destination, route_mode, active, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (slug, product_id, offer_id, preset_id, destination, route_mode, int(active), now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ValidationError("slug already exists") from exc
            row = conn.execute("SELECT * FROM links WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)

    def update_link(self, slug: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        slug = validate_slug(slug)
        allowed = {"destination", "offer_id", "preset_id", "route_mode", "active"}
        if not payload or any(key not in allowed for key in payload):
            raise ValidationError("update contains no supported fields")
        with self.transaction() as conn:
            current = conn.execute("SELECT * FROM links WHERE slug = ?", (slug,)).fetchone()
            if current is None:
                raise KeyError(slug)
            values = dict(current)
            if "destination" in payload:
                values["destination"] = validate_destination(payload["destination"])
            if "offer_id" in payload:
                values["offer_id"] = self._int_id(payload["offer_id"], "offer_id", optional=True)
            if "preset_id" in payload:
                values["preset_id"] = self._int_id(payload["preset_id"], "preset_id", optional=True)
            if "route_mode" in payload:
                values["route_mode"] = require_text(payload["route_mode"], "route_mode", maximum=16)
                if values["route_mode"] not in ROUTE_MODES:
                    raise ValidationError("route_mode must be redirect or offer")
            if "active" in payload:
                if not isinstance(payload["active"], bool):
                    raise ValidationError("active must be true or false")
                values["active"] = int(payload["active"])
            self._validate_link_refs(
                conn, values["product_id"], values["offer_id"], values["preset_id"], values["route_mode"]
            )
            conn.execute(
                "UPDATE links SET destination=?, offer_id=?, preset_id=?, route_mode=?, active=?, updated_at=? WHERE slug=?",
                (values["destination"], values["offer_id"], values["preset_id"], values["route_mode"],
                 values["active"], utc_now(), slug),
            )
            row = conn.execute("SELECT * FROM links WHERE slug = ?", (slug,)).fetchone()
        return dict(row)

    def record_event(
        self,
        slug: str,
        kind: str,
        *,
        requested_event_id: str | None = None,
        parent_event_id: str | None = None,
        referrer: str | None = None,
    ) -> EventResult:
        slug = validate_slug(slug)
        if kind not in EVENT_TYPES:
            raise ValidationError("event_type must be click or conversion")
        identifier = event_id(requested_event_id)
        if parent_event_id is not None:
            parent_event_id = event_id(parent_event_id)
        link = self.get_link(slug, active_only=True)
        if link is None:
            raise KeyError(slug)
        values = tuple(link.get(key) or "" for key in UTM_KEYS)
        with self.transaction() as conn:
            if parent_event_id is not None:
                parent = conn.execute(
                    "SELECT link_id, event_type FROM events WHERE event_id = ?", (parent_event_id,)
                ).fetchone()
                if parent is None or parent["link_id"] != link["id"] or parent["event_type"] != "click":
                    raise ValidationError("parent_event_id must identify a click for the same link")
            existing = conn.execute(
                "SELECT link_id, event_type, parent_event_id FROM events WHERE event_id = ?", (identifier,)
            ).fetchone()
            if existing is not None:
                if (existing["link_id"], existing["event_type"], existing["parent_event_id"]) != (
                    link["id"], kind, parent_event_id
                ):
                    raise ValidationError("event_id already belongs to a different event")
                return EventResult(identifier, False)
            conn.execute(
                "INSERT INTO events(event_id, link_id, event_type, parent_event_id, occurred_at, referrer_host, "
                "utm_source, utm_medium, utm_campaign, utm_content, utm_term) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (identifier, link["id"], kind, parent_event_id, utc_now(), referrer_host(referrer), *values),
            )
        return EventResult(identifier, True)
