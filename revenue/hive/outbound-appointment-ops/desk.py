#!/usr/bin/env python3
"""Provider-independent outbound appointment operations desk.

The desk deliberately does not send messages or mutate calendar/CRM providers.
It stores customer-provided lawful-source pointers, creates UNSENT drafts,
records inbound reply outcomes, enforces durable suppression, and exports local
CRM/calendar handoffs that an authorized operator can review and transport.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "commons-hive-outbound-appointment-ops/v1"
UTC = dt.timezone.utc
REPLY_KINDS = frozenset({"interested", "question", "not_now", "opt_out"})
PROSPECT_STATUSES = frozenset({"NEW", "DRAFT_READY", "REPLIED", "BOOKED", "SUPPRESSED"})


class DeskError(ValueError):
    """A desk operation failed closed."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeskError(f"{label} must be a nonempty string")
    return value.strip()


def _parse_time(value: str) -> dt.datetime:
    text = _nonempty(value, "timestamp")
    text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise DeskError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DeskError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _iso_z(value: dt.datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_route(value: str) -> str:
    route = _nonempty(value, "route_ref")
    if any(ch.isspace() for ch in route):
        raise DeskError("route_ref must be an opaque non-whitespace identifier")
    return route


def _ical_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ical_stamp(value: str) -> str:
    return _parse_time(value).strftime("%Y%m%dT%H%M%SZ")


class OutboundDesk:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self._schema()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "OutboundDesk":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                offer TEXT NOT NULL,
                source_policy TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS prospects (
                prospect_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
                organization TEXT NOT NULL,
                contact_name TEXT NOT NULL,
                route_ref TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                lawful_source_note TEXT NOT NULL,
                relevance_note TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS prospect_route_once ON prospects(route_ref);
            CREATE TABLE IF NOT EXISTS suppressions (
                route_ref TEXT PRIMARY KEY,
                reason TEXT NOT NULL,
                source_reply_id TEXT,
                suppressed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drafts (
                draft_id TEXT PRIMARY KEY,
                prospect_id TEXT NOT NULL REFERENCES prospects(prospect_id),
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state='UNSENT'),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS replies (
                reply_id TEXT PRIMARY KEY,
                prospect_id TEXT NOT NULL REFERENCES prospects(prospect_id),
                kind TEXT NOT NULL,
                note TEXT NOT NULL,
                received_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS slots (
                slot_id TEXT PRIMARY KEY,
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                state TEXT NOT NULL,
                booked_prospect_id TEXT REFERENCES prospects(prospect_id),
                UNIQUE(starts_at, ends_at)
            );
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id TEXT PRIMARY KEY,
                prospect_id TEXT NOT NULL UNIQUE REFERENCES prospects(prospect_id),
                slot_id TEXT NOT NULL UNIQUE REFERENCES slots(slot_id),
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    def _operate(self, operation_id: str, kind: str, request: dict[str, Any], fn: Any) -> dict[str, Any]:
        op = _nonempty(operation_id, "operation_id")
        payload = canonical_json({"kind": kind, "request": request})
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        prior = self.db.execute(
            "SELECT kind, request_hash, result_json FROM operations WHERE operation_id=?", (op,)
        ).fetchone()
        if prior:
            if prior["kind"] != kind or prior["request_hash"] != digest:
                raise DeskError(f"operation_id {op} already used for different input")
            return json.loads(prior["result_json"])
        try:
            self.db.execute("BEGIN IMMEDIATE")
            result = fn()
            stamp = _iso_z(dt.datetime.now(UTC))
            self.db.execute(
                "INSERT INTO operations(operation_id,kind,request_hash,result_json,created_at) VALUES(?,?,?,?,?)",
                (op, kind, digest, canonical_json(result), stamp),
            )
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def create_campaign(
        self,
        *,
        campaign_id: str,
        customer_name: str,
        offer: str,
        source_policy: str,
        operation_id: str,
    ) -> dict[str, Any]:
        values = {
            "campaign_id": _nonempty(campaign_id, "campaign_id"),
            "customer_name": _nonempty(customer_name, "customer_name"),
            "offer": _nonempty(offer, "offer"),
            "source_policy": _nonempty(source_policy, "source_policy"),
        }

        def apply() -> dict[str, Any]:
            created = _iso_z(dt.datetime.now(UTC))
            self.db.execute(
                "INSERT INTO campaigns(campaign_id,customer_name,offer,source_policy,created_at) VALUES(?,?,?,?,?)",
                (*values.values(), created),
            )
            return {"schema": SCHEMA, "kind": "CAMPAIGN", **values, "created_at": created, "transport": "NONE"}

        return self._operate(operation_id, "create_campaign", values, apply)

    def add_prospect(
        self,
        *,
        campaign_id: str,
        prospect_id: str,
        organization: str,
        contact_name: str,
        route_ref: str,
        source_ref: str,
        lawful_source_note: str,
        relevance_note: str,
        operation_id: str,
    ) -> dict[str, Any]:
        values = {
            "campaign_id": _nonempty(campaign_id, "campaign_id"),
            "prospect_id": _nonempty(prospect_id, "prospect_id"),
            "organization": _nonempty(organization, "organization"),
            "contact_name": _nonempty(contact_name, "contact_name"),
            "route_ref": _normalize_route(route_ref),
            "source_ref": _nonempty(source_ref, "source_ref"),
            "lawful_source_note": _nonempty(lawful_source_note, "lawful_source_note"),
            "relevance_note": _nonempty(relevance_note, "relevance_note"),
        }

        def apply() -> dict[str, Any]:
            if not self.db.execute("SELECT 1 FROM campaigns WHERE campaign_id=?", (values["campaign_id"],)).fetchone():
                raise DeskError(f"unknown campaign {values['campaign_id']}")
            if self.is_suppressed(values["route_ref"]):
                raise DeskError("route is suppressed")
            created = _iso_z(dt.datetime.now(UTC))
            self.db.execute(
                "INSERT INTO prospects(prospect_id,campaign_id,organization,contact_name,route_ref,source_ref,lawful_source_note,relevance_note,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    values["prospect_id"], values["campaign_id"], values["organization"], values["contact_name"],
                    values["route_ref"], values["source_ref"], values["lawful_source_note"], values["relevance_note"],
                    "NEW", created,
                ),
            )
            return {"schema": SCHEMA, "kind": "PROSPECT", **values, "status": "NEW", "created_at": created}

        return self._operate(operation_id, "add_prospect", values, apply)

    def is_suppressed(self, route_ref: str) -> bool:
        return bool(self.db.execute("SELECT 1 FROM suppressions WHERE route_ref=?", (_normalize_route(route_ref),)).fetchone())

    def _prospect(self, prospect_id: str) -> sqlite3.Row:
        pid = _nonempty(prospect_id, "prospect_id")
        row = self.db.execute(
            "SELECT p.*, c.customer_name, c.offer FROM prospects p JOIN campaigns c USING(campaign_id) WHERE p.prospect_id=?",
            (pid,),
        ).fetchone()
        if not row:
            raise DeskError(f"unknown prospect {pid}")
        return row

    def create_draft(self, *, prospect_id: str, operation_id: str) -> dict[str, Any]:
        request = {"prospect_id": _nonempty(prospect_id, "prospect_id")}

        def apply() -> dict[str, Any]:
            row = self._prospect(request["prospect_id"])
            if self.is_suppressed(row["route_ref"]) or row["status"] == "SUPPRESSED":
                raise DeskError("prospect is suppressed")
            if row["status"] == "BOOKED":
                raise DeskError("prospect is already booked")
            draft_id = f"draft-{hashlib.sha256((row['campaign_id'] + ':' + row['prospect_id']).encode()).hexdigest()[:16]}"
            subject = f"Idea for {row['organization']}"
            body = (
                f"Hi {row['contact_name']},\n\n"
                f"I noticed {row['relevance_note']}. {row['customer_name']} offers {row['offer']}. "
                "If that is relevant, I can share a short outline and a few available times.\n\n"
                "If you would rather not hear from us, reply opt out and this route will be suppressed."
            )
            created = _iso_z(dt.datetime.now(UTC))
            self.db.execute(
                "INSERT OR IGNORE INTO drafts(draft_id,prospect_id,subject,body,state,created_at) VALUES(?,?,?,?,?,?)",
                (draft_id, row["prospect_id"], subject, body, "UNSENT", created),
            )
            self.db.execute(
                "UPDATE prospects SET status='DRAFT_READY' WHERE prospect_id=? AND status='NEW'", (row["prospect_id"],)
            )
            return {
                "schema": SCHEMA,
                "kind": "DRAFT",
                "draft_id": draft_id,
                "prospect_id": row["prospect_id"],
                "route_ref": row["route_ref"],
                "subject": subject,
                "body": body,
                "state": "UNSENT",
                "transport": "NONE",
            }

        return self._operate(operation_id, "create_draft", request, apply)

    def record_reply(
        self,
        *,
        prospect_id: str,
        reply_id: str,
        kind: str,
        note: str,
        received_at: str,
        operation_id: str,
    ) -> dict[str, Any]:
        reply_kind = _nonempty(kind, "kind")
        if reply_kind not in REPLY_KINDS:
            raise DeskError(f"kind must be one of {sorted(REPLY_KINDS)}")
        values = {
            "prospect_id": _nonempty(prospect_id, "prospect_id"),
            "reply_id": _nonempty(reply_id, "reply_id"),
            "kind": reply_kind,
            "note": _nonempty(note, "note"),
            "received_at": _iso_z(_parse_time(received_at)),
        }

        def apply() -> dict[str, Any]:
            row = self._prospect(values["prospect_id"])
            self.db.execute(
                "INSERT INTO replies(reply_id,prospect_id,kind,note,received_at) VALUES(?,?,?,?,?)",
                (values["reply_id"], values["prospect_id"], values["kind"], values["note"], values["received_at"]),
            )
            if values["kind"] == "opt_out":
                self.db.execute(
                    "INSERT OR IGNORE INTO suppressions(route_ref,reason,source_reply_id,suppressed_at) VALUES(?,?,?,?)",
                    (row["route_ref"], "opt_out", values["reply_id"], values["received_at"]),
                )
                self.db.execute("UPDATE prospects SET status='SUPPRESSED' WHERE route_ref=?", (row["route_ref"],))
                status = "SUPPRESSED"
            else:
                self.db.execute(
                    "UPDATE prospects SET status='REPLIED' WHERE prospect_id=? AND status!='BOOKED'", (values["prospect_id"],)
                )
                status = "REPLIED"
            return {"schema": SCHEMA, "kind": "REPLY", **values, "status": status, "transport": "INBOUND_RECORDED"}

        return self._operate(operation_id, "record_reply", values, apply)

    def add_slot(self, *, slot_id: str, starts_at: str, ends_at: str, operation_id: str) -> dict[str, Any]:
        start = _parse_time(starts_at)
        end = _parse_time(ends_at)
        if end <= start:
            raise DeskError("slot end must be after start")
        values = {"slot_id": _nonempty(slot_id, "slot_id"), "starts_at": _iso_z(start), "ends_at": _iso_z(end)}

        def apply() -> dict[str, Any]:
            self.db.execute(
                "INSERT INTO slots(slot_id,starts_at,ends_at,state,booked_prospect_id) VALUES(?,?,?,?,NULL)",
                (values["slot_id"], values["starts_at"], values["ends_at"], "AVAILABLE"),
            )
            return {"schema": SCHEMA, "kind": "SLOT", **values, "state": "AVAILABLE", "provider_mutation": False}

        return self._operate(operation_id, "add_slot", values, apply)

    def _latest_reply_kind(self, prospect_id: str) -> str | None:
        row = self.db.execute(
            "SELECT kind FROM replies WHERE prospect_id=? ORDER BY received_at DESC, rowid DESC LIMIT 1", (prospect_id,)
        ).fetchone()
        return str(row["kind"]) if row else None

    def book_slot(self, *, prospect_id: str, slot_id: str, operation_id: str) -> dict[str, Any]:
        request = {"prospect_id": _nonempty(prospect_id, "prospect_id"), "slot_id": _nonempty(slot_id, "slot_id")}

        def apply() -> dict[str, Any]:
            prospect = self._prospect(request["prospect_id"])
            if self.is_suppressed(prospect["route_ref"]) or prospect["status"] == "SUPPRESSED":
                raise DeskError("prospect is suppressed")
            if self._latest_reply_kind(prospect["prospect_id"]) != "interested":
                raise DeskError("booking requires the latest recorded reply to be interested")
            slot = self.db.execute("SELECT * FROM slots WHERE slot_id=?", (request["slot_id"],)).fetchone()
            if not slot:
                raise DeskError(f"unknown slot {request['slot_id']}")
            if slot["state"] != "AVAILABLE" or slot["booked_prospect_id"] is not None:
                raise DeskError("slot is unavailable")
            booking_id = f"booking-{hashlib.sha256((prospect['prospect_id'] + ':' + slot['slot_id']).encode()).hexdigest()[:16]}"
            title = f"{prospect['customer_name']} / {prospect['organization']} intro"
            created = _iso_z(dt.datetime.now(UTC))
            self.db.execute(
                "INSERT INTO bookings(booking_id,prospect_id,slot_id,title,created_at) VALUES(?,?,?,?,?)",
                (booking_id, prospect["prospect_id"], slot["slot_id"], title, created),
            )
            self.db.execute(
                "UPDATE slots SET state='BOOKED', booked_prospect_id=? WHERE slot_id=?",
                (prospect["prospect_id"], slot["slot_id"]),
            )
            self.db.execute("UPDATE prospects SET status='BOOKED' WHERE prospect_id=?", (prospect["prospect_id"],))
            return {
                "schema": SCHEMA,
                "kind": "BOOKING_HANDOFF",
                "booking_id": booking_id,
                "prospect_id": prospect["prospect_id"],
                "slot_id": slot["slot_id"],
                "starts_at": slot["starts_at"],
                "ends_at": slot["ends_at"],
                "title": title,
                "calendar_provider_mutation": False,
                "transport": "LOCAL_HANDOFF_ONLY",
            }

        return self._operate(operation_id, "book_slot", request, apply)

    def booking_ics(self, booking_id: str) -> str:
        bid = _nonempty(booking_id, "booking_id")
        row = self.db.execute(
            """SELECT b.*, s.starts_at, s.ends_at, p.organization, p.contact_name
               FROM bookings b JOIN slots s USING(slot_id) JOIN prospects p USING(prospect_id)
               WHERE booking_id=?""",
            (bid,),
        ).fetchone()
        if not row:
            raise DeskError(f"unknown booking {bid}")
        uid = f"{bid}@commons-outbound-appointment-ops"
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Commons//Outbound Appointment Ops//EN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:{_ical_escape(uid)}",
            f"DTSTART:{_ical_stamp(row['starts_at'])}",
            f"DTEND:{_ical_stamp(row['ends_at'])}",
            f"SUMMARY:{_ical_escape(row['title'])}",
            f"DESCRIPTION:{_ical_escape('Local handoff only; review before provider import. Prospect: ' + row['contact_name'])}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
        return "\r\n".join(lines)

    def crm_rows(self, campaign_id: str) -> list[dict[str, Any]]:
        cid = _nonempty(campaign_id, "campaign_id")
        rows = self.db.execute(
            """SELECT p.prospect_id,p.organization,p.contact_name,p.route_ref,p.source_ref,p.lawful_source_note,
                      p.relevance_note,p.status,
                      (SELECT kind FROM replies r WHERE r.prospect_id=p.prospect_id ORDER BY received_at DESC,rowid DESC LIMIT 1) latest_reply,
                      b.booking_id,s.starts_at,s.ends_at
               FROM prospects p
               LEFT JOIN bookings b ON b.prospect_id=p.prospect_id
               LEFT JOIN slots s ON s.slot_id=b.slot_id
               WHERE p.campaign_id=? ORDER BY p.prospect_id""",
            (cid,),
        ).fetchall()
        return [dict(row) for row in rows]

    def export_campaign(self, campaign_id: str, folder: str | Path) -> dict[str, Any]:
        cid = _nonempty(campaign_id, "campaign_id")
        campaign = self.db.execute("SELECT * FROM campaigns WHERE campaign_id=?", (cid,)).fetchone()
        if not campaign:
            raise DeskError(f"unknown campaign {cid}")
        target = Path(folder)
        target.mkdir(parents=True, exist_ok=True)
        rows = self.crm_rows(cid)
        manifest = {
            "schema": SCHEMA,
            "kind": "CUSTOMER_HANDOFF",
            "campaign": dict(campaign),
            "prospects": rows,
            "transport": "NONE",
            "calendar_provider_mutation": False,
        }
        (target / "handoff.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        fieldnames = [
            "prospect_id", "organization", "contact_name", "route_ref", "source_ref", "lawful_source_note",
            "relevance_note", "status", "latest_reply", "booking_id", "starts_at", "ends_at",
        ]
        with (target / "crm.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        bookings = self.db.execute(
            "SELECT booking_id FROM bookings b JOIN prospects p USING(prospect_id) WHERE p.campaign_id=? ORDER BY booking_id",
            (cid,),
        ).fetchall()
        for booking in bookings:
            bid = str(booking["booking_id"])
            (target / f"{bid}.ics").write_text(self.booking_ics(bid), encoding="utf-8", newline="")
        files = sorted(path.name for path in target.iterdir() if path.is_file())
        return {"schema": SCHEMA, "kind": "EXPORT", "campaign_id": cid, "folder": str(target), "files": files}

    def status(self) -> dict[str, Any]:
        counts = {}
        for table in ("campaigns", "prospects", "drafts", "replies", "suppressions", "slots", "bookings", "operations"):
            counts[table] = int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return {"schema": SCHEMA, "kind": "STATUS", "counts": counts, "transport_actions": 0}


def demo(path: str | Path, export_folder: str | Path) -> dict[str, Any]:
    db_path = Path(path)
    if db_path.exists():
        db_path.unlink()
    with OutboundDesk(db_path) as desk:
        desk.create_campaign(
            campaign_id="demo-campaign", customer_name="Northstar Systems",
            offer="a fixed-scope workflow cleanup for small service teams",
            source_policy="synthetic fixture: customer-provided lawful business directory only",
            operation_id="demo-op-campaign",
        )
        for index in range(1, 4):
            desk.add_prospect(
                campaign_id="demo-campaign", prospect_id=f"prospect-{index}", organization=f"Example Co {index}",
                contact_name=f"Sample Person {index}", route_ref=f"synthetic-route-{index}",
                source_ref=f"example://directory/record-{index}",
                lawful_source_note="synthetic public-business-directory fixture; not a real person",
                relevance_note="the example company operates a manual appointment workflow",
                operation_id=f"demo-op-prospect-{index}",
            )
            desk.create_draft(prospect_id=f"prospect-{index}", operation_id=f"demo-op-draft-{index}")
        desk.record_reply(
            prospect_id="prospect-1", reply_id="reply-interested-1", kind="interested",
            note="Synthetic reply asks for a time.", received_at="2026-09-08T13:00:00Z",
            operation_id="demo-op-reply-1",
        )
        desk.record_reply(
            prospect_id="prospect-2", reply_id="reply-opt-out-2", kind="opt_out",
            note="Synthetic opt-out fixture.", received_at="2026-09-08T13:01:00Z",
            operation_id="demo-op-reply-2",
        )
        desk.add_slot(
            slot_id="slot-1", starts_at="2026-09-09T15:00:00Z", ends_at="2026-09-09T15:30:00Z",
            operation_id="demo-op-slot-1",
        )
        booking = desk.book_slot(prospect_id="prospect-1", slot_id="slot-1", operation_id="demo-op-book-1")
        exported = desk.export_campaign("demo-campaign", export_folder)
        return {"schema": SCHEMA, "booking": booking, "export": exported, "status": desk.status()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="outbound-appointment-ops.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    demo_cmd = sub.add_parser("demo")
    demo_cmd.add_argument("--export", default="outbound-appointment-demo-export")
    status_cmd = sub.add_parser("status")
    export_cmd = sub.add_parser("export")
    export_cmd.add_argument("campaign_id")
    export_cmd.add_argument("folder")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "demo":
            print(json.dumps(demo(args.db, args.export), indent=2, sort_keys=True))
            return 0
        with OutboundDesk(args.db) as desk:
            if args.command == "status":
                print(json.dumps(desk.status(), indent=2, sort_keys=True))
                return 0
            if args.command == "export":
                print(json.dumps(desk.export_campaign(args.campaign_id, args.folder), indent=2, sort_keys=True))
                return 0
        raise DeskError(f"unknown command {args.command}")
    except (DeskError, sqlite3.Error, OSError) as exc:
        print(f"outbound-appointment-ops: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
