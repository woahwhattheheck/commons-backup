# SPDX-License-Identifier: Apache-2.0
"""RouteFoundry reads, attribution reports, and portable export."""
from __future__ import annotations

from contextlib import closing
import csv
from datetime import date
import io
import json
from typing import Any

from route_validation import ValidationError, short_url, utc_now, validate_public_base_url, validate_slug


def report_day(value: str | None, field: str) -> str | None:
    """Accept one canonical UTC calendar date; blank means unbounded."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a YYYY-MM-DD date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{field} must be a YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise ValidationError(f"{field} must be a YYYY-MM-DD date")
    return value


def csv_cell(value: Any) -> Any:
    """Keep operator text literal when a CSV is opened in a spreadsheet."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    if isinstance(value, str) and value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


class StoreReadMixin:
    def get_link(self, slug: str, *, active_only: bool = False) -> dict[str, Any] | None:
        slug = validate_slug(slug)
        where = "WHERE l.slug = ?" + (" AND l.active = 1" if active_only else "")
        with closing(self.connect()) as conn:
            row = conn.execute(
                "SELECT l.*, p.name AS product_name, p.brand, "
                "o.name AS offer_name, o.headline, o.body, o.cta_label, "
                "u.name AS preset_name, u.utm_source, u.utm_medium, u.utm_campaign, u.utm_content, u.utm_term "
                "FROM links l JOIN products p ON p.id=l.product_id "
                "LEFT JOIN offers o ON o.id=l.offer_id LEFT JOIN presets u ON u.id=l.preset_id " + where,
                (slug,),
            ).fetchone()
        return self._row_dict(row)

    def list_state(self, public_base_url: str) -> dict[str, Any]:
        base = validate_public_base_url(public_base_url)
        with closing(self.connect()) as conn:
            products = [dict(row) for row in conn.execute("SELECT * FROM products ORDER BY id")]
            offers = [dict(row) for row in conn.execute("SELECT * FROM offers ORDER BY id")]
            presets = [dict(row) for row in conn.execute("SELECT * FROM presets ORDER BY id")]
            links = [dict(row) for row in conn.execute(
                "SELECT l.*, p.name AS product_name, p.brand, o.name AS offer_name, u.name AS preset_name, "
                "SUM(CASE WHEN e.event_type='click' THEN 1 ELSE 0 END) AS clicks, "
                "SUM(CASE WHEN e.event_type='conversion' THEN 1 ELSE 0 END) AS conversions "
                "FROM links l JOIN products p ON p.id=l.product_id "
                "LEFT JOIN offers o ON o.id=l.offer_id LEFT JOIN presets u ON u.id=l.preset_id "
                "LEFT JOIN events e ON e.link_id=l.id GROUP BY l.id ORDER BY l.id"
            )]
            recent = [dict(row) for row in conn.execute(
                "SELECT e.event_id, e.event_type, e.occurred_at, e.referrer_host, e.utm_source, e.utm_medium, "
                "e.utm_campaign, e.utm_content, e.utm_term, l.slug, p.name AS product_name "
                "FROM events e JOIN links l ON l.id=e.link_id JOIN products p ON p.id=l.product_id "
                "ORDER BY e.occurred_at DESC, e.event_id DESC LIMIT 100"
            )]
        for link in links:
            link["active"] = bool(link["active"])
            link["short_url"] = short_url(base, link["slug"])
            link["qr_url"] = f"{base}/q/{link['slug']}.svg"
        return {"products": products, "offers": offers, "presets": presets, "links": links, "recent_events": recent}

    def report(self, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        start, end = report_day(start, "start"), report_day(end, "end")
        if start is not None and end is not None and start > end:
            raise ValidationError("start must be on or before end")
        clauses, parameters = [], []
        if start is not None:
            clauses.append("e.occurred_at >= ?")
            parameters.append(start + "T00:00:00.000Z")
        if end is not None:
            clauses.append("e.occurred_at <= ?")
            parameters.append(end + "T23:59:59.999Z")
        event_where = " WHERE " + " AND ".join(clauses) if clauses else ""
        event_join = " AND " + " AND ".join(clauses) if clauses else ""
        with closing(self.connect()) as conn:
            # Both report views describe one read snapshot, even during ingestion.
            conn.execute("BEGIN")
            campaign_rows = [dict(row) for row in conn.execute(
                "SELECT e.utm_campaign, e.utm_source, e.utm_medium, "
                "SUM(CASE WHEN e.event_type='click' THEN 1 ELSE 0 END) AS clicks, "
                "SUM(CASE WHEN e.event_type='conversion' THEN 1 ELSE 0 END) AS conversions, "
                "COUNT(DISTINCT l.slug) AS links "
                "FROM events e JOIN links l ON l.id=e.link_id" + event_where +
                " GROUP BY e.utm_campaign, e.utm_source, e.utm_medium "
                "ORDER BY conversions DESC, clicks DESC, e.utm_campaign, e.utm_source, e.utm_medium",
                parameters,
            )]
            link_rows = [dict(row) for row in conn.execute(
                "SELECT l.slug, p.name AS product, u.name AS preset, u.utm_campaign, "
                "SUM(CASE WHEN e.event_type='click' THEN 1 ELSE 0 END) AS clicks, "
                "SUM(CASE WHEN e.event_type='conversion' THEN 1 ELSE 0 END) AS conversions "
                "FROM links l JOIN products p ON p.id=l.product_id "
                "LEFT JOIN presets u ON u.id=l.preset_id LEFT JOIN events e ON e.link_id=l.id" + event_join +
                " GROUP BY l.id ORDER BY conversions DESC, clicks DESC, l.slug",
                parameters,
            )]
        return {
            "generated_at": utc_now(),
            "date_range": {"start": start, "end": end, "timezone": "UTC"},
            "campaigns": campaign_rows,
            "links": link_rows,
        }

    def report_csv(self, view: str, start: str | None = None, end: str | None = None) -> str:
        columns = {
            "campaigns": ("utm_campaign", "utm_source", "utm_medium", "links", "clicks", "conversions"),
            "links": ("slug", "product", "preset", "utm_campaign", "clicks", "conversions"),
        }
        if view not in columns:
            raise ValidationError("view must be campaigns or links")
        report = self.report(start, end)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(columns[view])
        for row in report[view]:
            writer.writerow(csv_cell(row[key]) for key in columns[view])
        return output.getvalue()

    def export_json(self) -> str:
        with closing(self.connect()) as conn:
            payload = {
                "schema": "routefoundry.export.v1",
                "exported_at": utc_now(),
                "products": [dict(row) for row in conn.execute("SELECT * FROM products ORDER BY id")],
                "offers": [dict(row) for row in conn.execute("SELECT * FROM offers ORDER BY id")],
                "presets": [dict(row) for row in conn.execute("SELECT * FROM presets ORDER BY id")],
                "links": [dict(row) for row in conn.execute("SELECT * FROM links ORDER BY id")],
                "events": [dict(row) for row in conn.execute("SELECT * FROM events ORDER BY occurred_at, event_id")],
            }
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
