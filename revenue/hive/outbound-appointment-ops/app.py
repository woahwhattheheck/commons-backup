#!/usr/bin/env python3
"""Browser/operator adapter for the landed Hive028 OutboundDesk.

This module intentionally wraps the existing desk.py runtime instead of
reimplementing campaign, suppression, reply, booking, or retry semantics.
All actions are local SQLite operations; there is no email, calendar, CRM,
or provider transport.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import desk

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.html"


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise desk.DeskError(f"{key} must be a nonempty string")
    return value.strip()


class OperatorApp:
    """Thin application layer over :class:`desk.OutboundDesk`."""

    def __init__(self, db_path: str | Path):
        self.desk = desk.OutboundDesk(db_path)
        path = self.desk.path
        self.desk.db.close()
        self.desk.db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.desk.db.row_factory = sqlite3.Row
        self.desk.db.execute("PRAGMA foreign_keys=ON")
        self.desk.db.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self.desk.close()

    def __enter__(self) -> "OperatorApp":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def state(self) -> dict[str, Any]:
        with self._lock:
            return self._state_locked()

    def _state_locked(self) -> dict[str, Any]:
        db = self.desk.db
        campaigns = [
            dict(row)
            for row in db.execute(
                "SELECT campaign_id,customer_name,offer,source_policy,created_at "
                "FROM campaigns ORDER BY created_at,campaign_id"
            )
        ]
        prospects = [
            dict(row)
            for row in db.execute(
                """
                SELECT p.prospect_id,p.campaign_id,p.organization,p.contact_name,
                       p.route_ref,p.source_ref,p.lawful_source_note,p.relevance_note,
                       p.status,p.created_at,
                       EXISTS(SELECT 1 FROM suppressions s WHERE s.route_ref=p.route_ref) AS suppressed,
                       (SELECT kind FROM replies r WHERE r.prospect_id=p.prospect_id
                        ORDER BY r.received_at DESC,r.rowid DESC LIMIT 1) AS latest_reply,
                       (SELECT subject FROM drafts d WHERE d.prospect_id=p.prospect_id
                        ORDER BY d.rowid DESC LIMIT 1) AS draft_subject,
                       (SELECT state FROM drafts d WHERE d.prospect_id=p.prospect_id
                        ORDER BY d.rowid DESC LIMIT 1) AS draft_state
                FROM prospects p ORDER BY p.created_at,p.prospect_id
                """
            )
        ]
        slots = [
            dict(row)
            for row in db.execute(
                "SELECT slot_id,starts_at,ends_at,state,booked_prospect_id "
                "FROM slots ORDER BY starts_at,slot_id"
            )
        ]
        bookings = [
            dict(row)
            for row in db.execute(
                """
                SELECT b.booking_id,b.prospect_id,b.slot_id,b.title,b.created_at,
                       p.route_ref,p.organization,s.starts_at,s.ends_at,s.state AS slot_state
                FROM bookings b
                JOIN prospects p USING(prospect_id)
                JOIN slots s USING(slot_id)
                ORDER BY b.created_at,b.booking_id
                """
            )
        ]
        suppressions = [
            dict(row)
            for row in db.execute(
                "SELECT route_ref,reason,source_reply_id,suppressed_at "
                "FROM suppressions ORDER BY suppressed_at,route_ref"
            )
        ]
        return {
            "schema": "commons-hive-outbound-appointment-ops/operator-v1",
            "transport": "NONE",
            "provider_mutation": False,
            "status": self.desk.status(),
            "campaigns": campaigns,
            "prospects": prospects,
            "slots": slots,
            "bookings": bookings,
            "suppressions": suppressions,
        }

    def action(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise desk.DeskError("request body must be a JSON object")
        action = _required(payload, "action")
        operation_id = _required(payload, "operation_id")

        with self._lock:
            if action == "campaign":
                return self.desk.create_campaign(
                    campaign_id=_required(payload, "campaign_id"),
                    customer_name=_required(payload, "customer_name"),
                    offer=_required(payload, "offer"),
                    source_policy=_required(payload, "source_policy"),
                    operation_id=operation_id,
                )
            if action == "prospect":
                return self.desk.add_prospect(
                    campaign_id=_required(payload, "campaign_id"),
                    prospect_id=_required(payload, "prospect_id"),
                    organization=_required(payload, "organization"),
                    contact_name=_required(payload, "contact_name"),
                    route_ref=_required(payload, "route_ref"),
                    source_ref=_required(payload, "source_ref"),
                    lawful_source_note=_required(payload, "lawful_source_note"),
                    relevance_note=_required(payload, "relevance_note"),
                    operation_id=operation_id,
                )
            if action == "draft":
                return self.desk.create_draft(
                    prospect_id=_required(payload, "prospect_id"),
                    operation_id=operation_id,
                )
            if action == "reply":
                return self.desk.record_reply(
                    prospect_id=_required(payload, "prospect_id"),
                    reply_id=_required(payload, "reply_id"),
                    kind=_required(payload, "kind"),
                    note=_required(payload, "note"),
                    received_at=_required(payload, "received_at"),
                    operation_id=operation_id,
                )
            if action == "slot":
                return self.desk.add_slot(
                    slot_id=_required(payload, "slot_id"),
                    starts_at=_required(payload, "starts_at"),
                    ends_at=_required(payload, "ends_at"),
                    operation_id=operation_id,
                )
            if action == "book":
                return self.desk.book_slot(
                    prospect_id=_required(payload, "prospect_id"),
                    slot_id=_required(payload, "slot_id"),
                    operation_id=operation_id,
                )
            # Names without a bound OutboundDesk method still reach dispatch.
            # Nothing is sent and no provider is mutated.
            return {
                "schema": "commons-hive-outbound-appointment-ops/operator-v1",
                "kind": "OPERATOR_INPUT",
                "action": action,
                "operation_id": operation_id,
                "transport": "NONE",
                "provider_mutation": False,
                "applied": False,
            }

    def crm_csv(self, campaign_id: str) -> str:
        with self._lock:
            rows = self.desk.crm_rows(campaign_id)
        if not rows:
            return ""
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()

    def booking_ics(self, booking_id: str) -> str:
        with self._lock:
            return self.desk.booking_ics(booking_id)


class Handler(BaseHTTPRequestHandler):
    server_version = "Hive028Operator/1.0"

    @property
    def app(self) -> OperatorApp:
        return self.server.app  # type: ignore[attr-defined]

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        self._bytes(
            status,
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path in {"/", "/index.html"}:
                self._bytes(HTTPStatus.OK, INDEX.read_bytes(), "text/html; charset=utf-8")
                return
            if parsed.path == "/state":
                self._json(HTTPStatus.OK, self.app.state())
                return
            if parsed.path == "/crm.csv":
                campaign = parse_qs(parsed.query).get("campaign_id", [""])[0]
                body = self.app.crm_csv(campaign).encode("utf-8")
                self._bytes(HTTPStatus.OK, body, "text/csv; charset=utf-8")
                return
            if parsed.path == "/calendar.ics":
                booking = parse_qs(parsed.query).get("booking_id", [""])[0]
                body = self.app.booking_ics(booking).encode("utf-8")
                self._bytes(HTTPStatus.OK, body, "text/calendar; charset=utf-8")
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except desk.DeskError as exc:
            self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except Exception as exc:  # fail closed at the HTTP boundary
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise desk.DeskError("request body size is invalid")
            payload = json.loads(self.rfile.read(length))
            result = self.app.action(payload)
            self._json(HTTPStatus.OK, result)
        except desk.DeskError as exc:
            self._json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})

    def log_message(self, *_: Any) -> None:
        return


class Server(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], app: OperatorApp):
        super().__init__(address, Handler)
        self.app = app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local browser/operator consumer for Hive028")
    parser.add_argument("--db", default="outbound-appointment-ops.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args(argv)
    app = OperatorApp(args.db)
    server = Server((args.host, args.port), app)
    try:
        print(
            json.dumps(
                {
                    "url": f"http://{args.host}:{server.server_address[1]}/",
                    "transport": "NONE",
                    "provider_mutation": False,
                }
            ),
            flush=True,
        )
        server.serve_forever()
    finally:
        server.server_close()
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
