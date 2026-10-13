#!/usr/bin/env python3
"""Local-first podcast sponsorship flight operations desk.

This module manages owner-supplied operational records only. It does not publish
podcasts, insert ads, contact advertisers/publishers, mutate payment/accounting
systems, interpret contracts, or claim delivery beyond retained owner evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable


class DeskError(ValueError):
    """The requested mutation or retained evidence violates the desk contract."""


AUTHORITY_FLAGS = {
    "external_send_authorized": False,
    "publisher_mutation_authorized": False,
    "hosting_mutation_authorized": False,
    "payment_authorized": False,
    "accounting_mutation_authorized": False,
    "contract_signature_authorized": False,
    "revenue_recognized": False,
}

BOOKING_ACTIVE = {"BOOKED", "DELIVERED", "MISSED"}
BOOKING_TERMINAL = {"CANCELLED", "DELIVERED", "MISSED"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(value: Any, field: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeskError(f"{field} must be nonempty text")
    if len(value) > max_len:
        raise DeskError(f"{field} exceeds {max_len} characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise DeskError(f"{field} must be valid Unicode") from None
    if any(ord(c) < 32 for c in value):
        raise DeskError(f"{field} contains control characters")
    return value


def _ident(value: Any, field: str) -> str:
    value = _text(value, field, max_len=96)
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if any(c not in allowed for c in value):
        raise DeskError(f"{field} contains unsupported characters")
    return value


def _date(value: Any, field: str) -> str:
    import datetime as _dt
    if not isinstance(value, str) or len(value) != 10:
        raise DeskError(f"{field} must be YYYY-MM-DD")
    try:
        parsed = _dt.date.fromisoformat(value)
    except ValueError:
        raise DeskError(f"{field} must be a valid date") from None
    return parsed.isoformat()


def _utc(value: Any, field: str = "occurred_at") -> str:
    import datetime as _dt
    if not isinstance(value, str):
        raise DeskError(f"{field} must be an ISO-8601 UTC timestamp")
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise DeskError(f"{field} must be an ISO-8601 UTC timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DeskError(f"{field} must include a timezone")
    parsed = parsed.astimezone(_dt.timezone.utc).replace(microsecond=0)
    return parsed.isoformat().replace("+00:00", "Z")


def _int(value: Any, field: str, *, minimum: int = 0, maximum: int = 2_147_483_647) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DeskError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _money(value: Any, field: str) -> int:
    return _int(value, field, minimum=0, maximum=10_000_000_000)


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise DeskError(f"{field} must be a lowercase SHA-256 hex digest")
    if any(c not in "0123456789abcdef" for c in value):
        raise DeskError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DeskError(f"duplicate JSON field: {key}")
        out[key] = value
    return out


def load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=lambda token: (_ for _ in ()).throw(DeskError(f"non-finite JSON number: {token}")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeskError(f"cannot load JSON: {exc}") from None


class Desk:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self._schema()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Desk":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS operations(
                operation_key TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL,
                result_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shows(
                show_id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS slots(
                slot_id TEXT PRIMARY KEY,
                show_id TEXT NOT NULL REFERENCES shows(show_id),
                air_date TEXT NOT NULL,
                position TEXT NOT NULL,
                UNIQUE(show_id, air_date, position)
            );
            CREATE TABLE IF NOT EXISTS campaigns(
                campaign_id TEXT PRIMARY KEY,
                advertiser_ref TEXT NOT NULL,
                currency TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                contracted_insertions INTEGER NOT NULL,
                unit_rate_cents INTEGER NOT NULL,
                io_reference TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS creatives(
                creative_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
                source_sha256 TEXT NOT NULL,
                approval_ref TEXT,
                approved INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(creative_id, revision)
            );
            CREATE TABLE IF NOT EXISTS bookings(
                booking_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
                slot_id TEXT NOT NULL REFERENCES slots(slot_id),
                creative_id TEXT NOT NULL,
                creative_revision INTEGER NOT NULL,
                status TEXT NOT NULL,
                billable INTEGER NOT NULL,
                makegood_for TEXT UNIQUE REFERENCES bookings(booking_id),
                evidence_ref TEXT,
                FOREIGN KEY(creative_id, creative_revision)
                  REFERENCES creatives(creative_id, revision)
            );
            CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            """
        )
        self.db.commit()

    def _event(self, occurred_at: str, kind: str, entity_id: str, payload: dict[str, Any]) -> None:
        row = self.db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = row[0] if row else "0" * 64
        body = {
            "occurred_at": occurred_at,
            "kind": kind,
            "entity_id": entity_id,
            "payload": payload,
            "prev_hash": prev_hash,
        }
        event_hash = _hash(body)
        self.db.execute(
            "INSERT INTO events(occurred_at,kind,entity_id,payload_json,prev_hash,event_hash) VALUES(?,?,?,?,?,?)",
            (occurred_at, kind, entity_id, _canonical(payload).decode(), prev_hash, event_hash),
        )

    def _mutate(self, operation_key: Any, occurred_at: Any, action: str,
                payload: dict[str, Any], fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        key = _ident(operation_key, "operation_key")
        timestamp = _utc(occurred_at)
        request = {"action": action, "occurred_at": timestamp, "payload": payload}
        request_hash = _hash(request)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute(
                "SELECT request_hash,result_json FROM operations WHERE operation_key=?", (key,)
            ).fetchone()
            if prior:
                if prior["request_hash"] != request_hash:
                    raise DeskError("operation_key reuse with changed request")
                self.db.rollback()
                return json.loads(prior["result_json"])
            result = fn()
            result = {**result, "operation_key": key, "replayed": False}
            self.db.execute(
                "INSERT INTO operations(operation_key,request_hash,result_json) VALUES(?,?,?)",
                (key, request_hash, _canonical(result).decode()),
            )
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def add_show(self, operation_key: Any, occurred_at: Any, *, show_id: Any, name: Any) -> dict[str, Any]:
        sid, title = _ident(show_id, "show_id"), _text(name, "name")
        payload = {"show_id": sid, "name": title}
        def work() -> dict[str, Any]:
            try:
                self.db.execute("INSERT INTO shows(show_id,name) VALUES(?,?)", (sid, title))
            except sqlite3.IntegrityError:
                raise DeskError("show_id already exists") from None
            self._event(_utc(occurred_at), "SHOW_ADDED", sid, payload)
            return {"show_id": sid, "state": "SHOW_READY"}
        return self._mutate(operation_key, occurred_at, "add_show", payload, work)

    def add_slot(self, operation_key: Any, occurred_at: Any, *, slot_id: Any, show_id: Any,
                 air_date: Any, position: Any) -> dict[str, Any]:
        slot = _ident(slot_id, "slot_id")
        show = _ident(show_id, "show_id")
        day = _date(air_date, "air_date")
        pos = _text(position, "position", max_len=64)
        payload = {"slot_id": slot, "show_id": show, "air_date": day, "position": pos}
        def work() -> dict[str, Any]:
            if not self.db.execute("SELECT 1 FROM shows WHERE show_id=?", (show,)).fetchone():
                raise DeskError("unknown show_id")
            try:
                self.db.execute("INSERT INTO slots(slot_id,show_id,air_date,position) VALUES(?,?,?,?)",
                                (slot, show, day, pos))
            except sqlite3.IntegrityError:
                raise DeskError("slot_id or show/date/position already exists") from None
            self._event(_utc(occurred_at), "SLOT_ADDED", slot, payload)
            return {"slot_id": slot, "state": "OPEN"}
        return self._mutate(operation_key, occurred_at, "add_slot", payload, work)

    def add_campaign(self, operation_key: Any, occurred_at: Any, *, campaign_id: Any,
                     advertiser_ref: Any, currency: Any, start_date: Any, end_date: Any,
                     contracted_insertions: Any, unit_rate_cents: Any, io_reference: Any) -> dict[str, Any]:
        cid = _ident(campaign_id, "campaign_id")
        advertiser = _text(advertiser_ref, "advertiser_ref")
        cur = _text(currency, "currency", max_len=3).upper()
        if len(cur) != 3 or not cur.isalpha() or not cur.isascii():
            raise DeskError("currency must be a three-letter ASCII code")
        start, end = _date(start_date, "start_date"), _date(end_date, "end_date")
        if end < start:
            raise DeskError("end_date must not precede start_date")
        count = _int(contracted_insertions, "contracted_insertions", minimum=1, maximum=100_000)
        rate = _money(unit_rate_cents, "unit_rate_cents")
        io_ref = _text(io_reference, "io_reference")
        payload = {"campaign_id": cid, "advertiser_ref": advertiser, "currency": cur,
                   "start_date": start, "end_date": end, "contracted_insertions": count,
                   "unit_rate_cents": rate, "io_reference": io_ref}
        def work() -> dict[str, Any]:
            try:
                self.db.execute(
                    "INSERT INTO campaigns VALUES(?,?,?,?,?,?,?,?)",
                    (cid, advertiser, cur, start, end, count, rate, io_ref),
                )
            except sqlite3.IntegrityError:
                raise DeskError("campaign_id already exists") from None
            self._event(_utc(occurred_at), "CAMPAIGN_ADDED", cid, payload)
            return {"campaign_id": cid, "state": "PLANNING"}
        return self._mutate(operation_key, occurred_at, "add_campaign", payload, work)

    def add_creative(self, operation_key: Any, occurred_at: Any, *, creative_id: Any,
                     revision: Any, campaign_id: Any, source_sha256: Any) -> dict[str, Any]:
        creative = _ident(creative_id, "creative_id")
        rev = _int(revision, "revision", minimum=1, maximum=1_000_000)
        campaign = _ident(campaign_id, "campaign_id")
        digest = _sha256(source_sha256, "source_sha256")
        payload = {"creative_id": creative, "revision": rev, "campaign_id": campaign,
                   "source_sha256": digest}
        def work() -> dict[str, Any]:
            if not self.db.execute("SELECT 1 FROM campaigns WHERE campaign_id=?", (campaign,)).fetchone():
                raise DeskError("unknown campaign_id")
            current = self.db.execute(
                "SELECT MAX(revision) AS r FROM creatives WHERE creative_id=?", (creative,)
            ).fetchone()["r"]
            if current is not None and rev != current + 1:
                raise DeskError("creative revision must increase by exactly one")
            if current is None and rev != 1:
                raise DeskError("first creative revision must be 1")
            try:
                self.db.execute(
                    "INSERT INTO creatives(creative_id,revision,campaign_id,source_sha256) VALUES(?,?,?,?)",
                    (creative, rev, campaign, digest),
                )
            except sqlite3.IntegrityError:
                raise DeskError("creative revision already exists") from None
            self._event(_utc(occurred_at), "CREATIVE_ADDED", f"{creative}@{rev}", payload)
            return {"creative_id": creative, "revision": rev, "state": "APPROVAL_REQUIRED"}
        return self._mutate(operation_key, occurred_at, "add_creative", payload, work)

    def approve_creative(self, operation_key: Any, occurred_at: Any, *, creative_id: Any,
                         revision: Any, approval_ref: Any) -> dict[str, Any]:
        creative = _ident(creative_id, "creative_id")
        rev = _int(revision, "revision", minimum=1, maximum=1_000_000)
        ref = _text(approval_ref, "approval_ref")
        payload = {"creative_id": creative, "revision": rev, "approval_ref": ref}
        def work() -> dict[str, Any]:
            row = self.db.execute(
                "SELECT approved FROM creatives WHERE creative_id=? AND revision=?", (creative, rev)
            ).fetchone()
            if not row:
                raise DeskError("unknown creative revision")
            if row["approved"]:
                raise DeskError("creative revision already approved")
            self.db.execute(
                "UPDATE creatives SET approved=1,approval_ref=? WHERE creative_id=? AND revision=?",
                (ref, creative, rev),
            )
            self._event(_utc(occurred_at), "CREATIVE_APPROVED", f"{creative}@{rev}", payload)
            return {"creative_id": creative, "revision": rev, "state": "APPROVED"}
        return self._mutate(operation_key, occurred_at, "approve_creative", payload, work)

    def _slot_taken(self, slot_id: str, *, except_booking: str | None = None) -> bool:
        sql = "SELECT booking_id FROM bookings WHERE slot_id=? AND status IN ('BOOKED','DELIVERED','MISSED')"
        params: list[Any] = [slot_id]
        if except_booking is not None:
            sql += " AND booking_id<>?"
            params.append(except_booking)
        return self.db.execute(sql, params).fetchone() is not None

    def _approved_creative(self, creative_id: str, revision: int, campaign_id: str) -> None:
        row = self.db.execute(
            "SELECT campaign_id,approved FROM creatives WHERE creative_id=? AND revision=?",
            (creative_id, revision),
        ).fetchone()
        if not row:
            raise DeskError("unknown creative revision")
        if row["campaign_id"] != campaign_id:
            raise DeskError("creative belongs to another campaign")
        if not row["approved"]:
            raise DeskError("creative revision is not approved")

    def book(self, operation_key: Any, occurred_at: Any, *, booking_id: Any, campaign_id: Any,
             slot_id: Any, creative_id: Any, creative_revision: Any) -> dict[str, Any]:
        bid, cid, slot = _ident(booking_id, "booking_id"), _ident(campaign_id, "campaign_id"), _ident(slot_id, "slot_id")
        creative = _ident(creative_id, "creative_id")
        rev = _int(creative_revision, "creative_revision", minimum=1, maximum=1_000_000)
        payload = {"booking_id": bid, "campaign_id": cid, "slot_id": slot,
                   "creative_id": creative, "creative_revision": rev}
        def work() -> dict[str, Any]:
            campaign = self.db.execute("SELECT * FROM campaigns WHERE campaign_id=?", (cid,)).fetchone()
            if not campaign:
                raise DeskError("unknown campaign_id")
            srow = self.db.execute("SELECT air_date FROM slots WHERE slot_id=?", (slot,)).fetchone()
            if not srow:
                raise DeskError("unknown slot_id")
            if not campaign["start_date"] <= srow["air_date"] <= campaign["end_date"]:
                raise DeskError("slot is outside campaign flight window")
            if self._slot_taken(slot):
                raise DeskError("slot is already occupied")
            billable_count = self.db.execute(
                "SELECT COUNT(*) FROM bookings WHERE campaign_id=? AND billable=1 AND status<>'CANCELLED'", (cid,)
            ).fetchone()[0]
            if billable_count >= campaign["contracted_insertions"]:
                raise DeskError("contracted insertion count already allocated")
            self._approved_creative(creative, rev, cid)
            try:
                self.db.execute(
                    "INSERT INTO bookings(booking_id,campaign_id,slot_id,creative_id,creative_revision,status,billable,makegood_for) VALUES(?,?,?,?,?,'BOOKED',1,NULL)",
                    (bid, cid, slot, creative, rev),
                )
            except sqlite3.IntegrityError:
                raise DeskError("booking_id already exists") from None
            self._event(_utc(occurred_at), "BOOKED", bid, payload)
            return {"booking_id": bid, "state": "BOOKED", "billable": True}
        return self._mutate(operation_key, occurred_at, "book", payload, work)

    def cancel(self, operation_key: Any, occurred_at: Any, *, booking_id: Any, reason: Any) -> dict[str, Any]:
        bid, why = _ident(booking_id, "booking_id"), _text(reason, "reason")
        payload = {"booking_id": bid, "reason": why}
        def work() -> dict[str, Any]:
            row = self.db.execute("SELECT status FROM bookings WHERE booking_id=?", (bid,)).fetchone()
            if not row:
                raise DeskError("unknown booking_id")
            if row["status"] != "BOOKED":
                raise DeskError("only BOOKED placements may be cancelled")
            self.db.execute("UPDATE bookings SET status='CANCELLED' WHERE booking_id=?", (bid,))
            self._event(_utc(occurred_at), "CANCELLED", bid, payload)
            return {"booking_id": bid, "state": "CANCELLED"}
        return self._mutate(operation_key, occurred_at, "cancel", payload, work)

    def reschedule(self, operation_key: Any, occurred_at: Any, *, booking_id: Any, new_slot_id: Any) -> dict[str, Any]:
        bid, new_slot = _ident(booking_id, "booking_id"), _ident(new_slot_id, "new_slot_id")
        payload = {"booking_id": bid, "new_slot_id": new_slot}
        def work() -> dict[str, Any]:
            row = self.db.execute(
                "SELECT b.status,b.campaign_id,c.start_date,c.end_date,b.slot_id FROM bookings b JOIN campaigns c USING(campaign_id) WHERE b.booking_id=?",
                (bid,),
            ).fetchone()
            if not row:
                raise DeskError("unknown booking_id")
            if row["status"] != "BOOKED":
                raise DeskError("only BOOKED placements may be rescheduled")
            target = self.db.execute("SELECT air_date FROM slots WHERE slot_id=?", (new_slot,)).fetchone()
            if not target:
                raise DeskError("unknown new_slot_id")
            if not row["start_date"] <= target["air_date"] <= row["end_date"]:
                raise DeskError("target slot is outside campaign flight window")
            if self._slot_taken(new_slot, except_booking=bid):
                raise DeskError("target slot is already occupied")
            old_slot = row["slot_id"]
            self.db.execute("UPDATE bookings SET slot_id=? WHERE booking_id=?", (new_slot, bid))
            self._event(_utc(occurred_at), "RESCHEDULED", bid,
                        {**payload, "old_slot_id": old_slot})
            return {"booking_id": bid, "state": "BOOKED", "slot_id": new_slot}
        return self._mutate(operation_key, occurred_at, "reschedule", payload, work)

    def mark_delivery(self, operation_key: Any, occurred_at: Any, *, booking_id: Any, evidence_ref: Any) -> dict[str, Any]:
        bid, ref = _ident(booking_id, "booking_id"), _text(evidence_ref, "evidence_ref")
        payload = {"booking_id": bid, "evidence_ref": ref}
        def work() -> dict[str, Any]:
            row = self.db.execute("SELECT status FROM bookings WHERE booking_id=?", (bid,)).fetchone()
            if not row:
                raise DeskError("unknown booking_id")
            if row["status"] != "BOOKED":
                raise DeskError("only BOOKED placements may be marked delivered")
            self.db.execute("UPDATE bookings SET status='DELIVERED',evidence_ref=? WHERE booking_id=?", (ref, bid))
            self._event(_utc(occurred_at), "DELIVERED", bid, payload)
            return {"booking_id": bid, "state": "DELIVERED"}
        return self._mutate(operation_key, occurred_at, "mark_delivery", payload, work)

    def mark_missed(self, operation_key: Any, occurred_at: Any, *, booking_id: Any, evidence_ref: Any) -> dict[str, Any]:
        bid, ref = _ident(booking_id, "booking_id"), _text(evidence_ref, "evidence_ref")
        payload = {"booking_id": bid, "evidence_ref": ref}
        def work() -> dict[str, Any]:
            row = self.db.execute("SELECT status FROM bookings WHERE booking_id=?", (bid,)).fetchone()
            if not row:
                raise DeskError("unknown booking_id")
            if row["status"] != "BOOKED":
                raise DeskError("only BOOKED placements may be marked missed")
            self.db.execute("UPDATE bookings SET status='MISSED',evidence_ref=? WHERE booking_id=?", (ref, bid))
            self._event(_utc(occurred_at), "MISSED", bid, payload)
            return {"booking_id": bid, "state": "MISSED", "makegood_required": True}
        return self._mutate(operation_key, occurred_at, "mark_missed", payload, work)

    def makegood(self, operation_key: Any, occurred_at: Any, *, booking_id: Any, missed_booking_id: Any,
                 slot_id: Any, creative_id: Any, creative_revision: Any) -> dict[str, Any]:
        bid = _ident(booking_id, "booking_id")
        missed = _ident(missed_booking_id, "missed_booking_id")
        slot = _ident(slot_id, "slot_id")
        creative = _ident(creative_id, "creative_id")
        rev = _int(creative_revision, "creative_revision", minimum=1, maximum=1_000_000)
        payload = {"booking_id": bid, "missed_booking_id": missed, "slot_id": slot,
                   "creative_id": creative, "creative_revision": rev}
        def work() -> dict[str, Any]:
            source = self.db.execute(
                "SELECT b.status,b.campaign_id,c.start_date,c.end_date FROM bookings b JOIN campaigns c USING(campaign_id) WHERE b.booking_id=?",
                (missed,),
            ).fetchone()
            if not source:
                raise DeskError("unknown missed_booking_id")
            if source["status"] != "MISSED":
                raise DeskError("makegood source must be MISSED")
            if self.db.execute("SELECT 1 FROM bookings WHERE makegood_for=?", (missed,)).fetchone():
                raise DeskError("missed placement already has a makegood")
            target = self.db.execute("SELECT air_date FROM slots WHERE slot_id=?", (slot,)).fetchone()
            if not target:
                raise DeskError("unknown slot_id")
            if not source["start_date"] <= target["air_date"] <= source["end_date"]:
                raise DeskError("makegood slot is outside campaign flight window")
            if self._slot_taken(slot):
                raise DeskError("slot is already occupied")
            self._approved_creative(creative, rev, source["campaign_id"])
            try:
                self.db.execute(
                    "INSERT INTO bookings(booking_id,campaign_id,slot_id,creative_id,creative_revision,status,billable,makegood_for) VALUES(?,?,?,?,?,'BOOKED',0,?)",
                    (bid, source["campaign_id"], slot, creative, rev, missed),
                )
            except sqlite3.IntegrityError:
                raise DeskError("booking_id already exists") from None
            self._event(_utc(occurred_at), "MAKEGOOD_BOOKED", bid, payload)
            return {"booking_id": bid, "state": "BOOKED", "billable": False,
                    "makegood_for": missed}
        return self._mutate(operation_key, occurred_at, "makegood", payload, work)

    def invoice_draft(self, campaign_id: str) -> dict[str, Any]:
        cid = _ident(campaign_id, "campaign_id")
        campaign = self.db.execute("SELECT * FROM campaigns WHERE campaign_id=?", (cid,)).fetchone()
        if not campaign:
            raise DeskError("unknown campaign_id")
        rows = self.db.execute(
            "SELECT booking_id,status,billable,makegood_for FROM bookings WHERE campaign_id=? ORDER BY booking_id",
            (cid,),
        ).fetchall()
        delivered_billable = [r for r in rows if r["status"] == "DELIVERED" and r["billable"] == 1]
        unresolved = [r["booking_id"] for r in rows if r["status"] == "BOOKED"]
        missed_without_delivered_makegood: list[str] = []
        for r in rows:
            if r["status"] != "MISSED" or r["billable"] != 1:
                continue
            mg = self.db.execute(
                "SELECT status FROM bookings WHERE makegood_for=?", (r["booking_id"],)
            ).fetchone()
            if not mg or mg["status"] != "DELIVERED":
                missed_without_delivered_makegood.append(r["booking_id"])
        amount = len(delivered_billable) * campaign["unit_rate_cents"]
        allocated_original = sum(1 for r in rows if r["billable"] == 1 and r["status"] != "CANCELLED")
        reasons: list[str] = []
        if allocated_original < campaign["contracted_insertions"]:
            reasons.append("CONTRACTED_INSERTIONS_NOT_FULLY_ALLOCATED")
        if unresolved:
            reasons.append("PLACEMENTS_STILL_BOOKED")
        if missed_without_delivered_makegood:
            reasons.append("MISSED_PLACEMENT_MAKEGOOD_UNRESOLVED")
        state = "READY_FOR_OWNER_REVIEW" if not reasons else "HOLD"
        return {
            "campaign_id": cid,
            "currency": campaign["currency"],
            "unit_rate_cents": campaign["unit_rate_cents"],
            "contracted_insertions": campaign["contracted_insertions"],
            "delivered_billable_insertions": len(delivered_billable),
            "delivered_billable_booking_ids": [r["booking_id"] for r in delivered_billable],
            "draft_amount_cents": amount,
            "state": state,
            "reasons": reasons,
            "unresolved_booking_ids": unresolved,
            "missed_without_delivered_makegood": missed_without_delivered_makegood,
            "payment_authorized": False,
            "accounting_mutation_authorized": False,
            "revenue_recognized": False,
        }

    def snapshot(self) -> dict[str, Any]:
        def rows(table: str, order: str) -> list[dict[str, Any]]:
            return [dict(r) for r in self.db.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()]
        campaigns = rows("campaigns", "campaign_id")
        snap = {
            "schema": "commons.podcast-sponsorship-flight-ops.v1",
            "shows": rows("shows", "show_id"),
            "slots": rows("slots", "slot_id"),
            "campaigns": campaigns,
            "creatives": rows("creatives", "creative_id,revision"),
            "bookings": rows("bookings", "booking_id"),
            "events": rows("events", "seq"),
            "invoice_drafts": [self.invoice_draft(c["campaign_id"]) for c in campaigns],
            "authority": dict(AUTHORITY_FLAGS),
            "commercial_state": "PROPOSED_NOT_ACCEPTED",
        }
        snap["semantic_digest"] = _hash({k: v for k, v in snap.items() if k != "semantic_digest"})
        return snap

    def verify_db(self) -> dict[str, Any]:
        prior = "0" * 64
        for row in self.db.execute("SELECT * FROM events ORDER BY seq"):
            payload = json.loads(row["payload_json"])
            body = {"occurred_at": row["occurred_at"], "kind": row["kind"],
                    "entity_id": row["entity_id"], "payload": payload, "prev_hash": prior}
            expected = _hash(body)
            if row["prev_hash"] != prior or row["event_hash"] != expected:
                raise DeskError(f"audit chain mismatch at event {row['seq']}")
            prior = row["event_hash"]
        verify_snapshot(self.snapshot())
        return {"integrity_checked": True, "event_count": self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                **AUTHORITY_FLAGS}

    def export_bundle(self, directory: Path) -> dict[str, Any]:
        directory.mkdir(parents=True, exist_ok=True)
        snap = self.snapshot()
        verify_snapshot(snap)
        snapshot_bytes = _canonical(snap) + b"\n"

        placements_io = io.StringIO(newline="")
        writer = csv.writer(placements_io, lineterminator="\n")
        writer.writerow(["booking_id", "campaign_id", "slot_id", "creative", "status", "billable", "makegood_for", "evidence_ref"])
        for b in snap["bookings"]:
            writer.writerow([b["booking_id"], b["campaign_id"], b["slot_id"],
                             f"{b['creative_id']}@{b['creative_revision']}", b["status"], b["billable"],
                             b["makegood_for"] or "", b["evidence_ref"] or ""])
        placements_bytes = placements_io.getvalue().encode("utf-8")

        invoices_io = io.StringIO(newline="")
        writer = csv.writer(invoices_io, lineterminator="\n")
        writer.writerow(["campaign_id", "currency", "state", "delivered_billable_insertions", "draft_amount_cents", "reasons"])
        for inv in snap["invoice_drafts"]:
            writer.writerow([inv["campaign_id"], inv["currency"], inv["state"],
                             inv["delivered_billable_insertions"], inv["draft_amount_cents"],
                             "|".join(inv["reasons"])])
        invoices_bytes = invoices_io.getvalue().encode("utf-8")

        md = ["# Podcast Sponsorship Flight Operations Handoff", "",
              "Commercial state: **PROPOSED_NOT_ACCEPTED**.",
              "No advertiser/publisher contact, hosting mutation, ad insertion, payment, signature, or revenue recognition is authorized.", ""]
        for inv in snap["invoice_drafts"]:
            md.extend([f"## Campaign `{inv['campaign_id']}`",
                       f"- State: `{inv['state']}`",
                       f"- Delivered billable insertions: {inv['delivered_billable_insertions']}",
                       f"- Draft amount: {inv['draft_amount_cents']} {inv['currency']} minor units",
                       f"- Hold reasons: {', '.join(inv['reasons']) if inv['reasons'] else 'none'}", ""])
        handoff_bytes = ("\n".join(md).rstrip() + "\n").encode("utf-8")

        files = {"snapshot.json": snapshot_bytes, "placements.csv": placements_bytes,
                 "invoice_drafts.csv": invoices_bytes, "HANDOFF.md": handoff_bytes}
        receipt = {
            "schema": "commons.podcast-sponsorship-flight-ops.receipt.v1",
            "semantic_digest": snap["semantic_digest"],
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
            "authority": dict(AUTHORITY_FLAGS),
        }
        files["receipt.json"] = _canonical(receipt) + b"\n"
        for name, data in files.items():
            (directory / name).write_bytes(data)
        return receipt


def verify_snapshot(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict) or snapshot.get("schema") != "commons.podcast-sponsorship-flight-ops.v1":
        raise DeskError("unsupported snapshot schema")
    authority = snapshot.get("authority")
    if authority != AUTHORITY_FLAGS:
        raise DeskError("authority flags are not fail-closed")
    if snapshot.get("commercial_state") != "PROPOSED_NOT_ACCEPTED":
        raise DeskError("commercial_state must remain PROPOSED_NOT_ACCEPTED")
    unsigned = {k: v for k, v in snapshot.items() if k != "semantic_digest"}
    if snapshot.get("semantic_digest") != _hash(unsigned):
        raise DeskError("snapshot semantic digest mismatch")

    shows = {r["show_id"] for r in snapshot.get("shows", [])}
    slots = {r["slot_id"]: r for r in snapshot.get("slots", [])}
    campaigns = {r["campaign_id"]: r for r in snapshot.get("campaigns", [])}
    creatives = {(r["creative_id"], r["revision"]): r for r in snapshot.get("creatives", [])}
    seen_active: set[str] = set()
    bookings = snapshot.get("bookings", [])
    by_id = {r["booking_id"]: r for r in bookings}
    if len(by_id) != len(bookings):
        raise DeskError("duplicate booking_id in snapshot")
    for s in slots.values():
        if s["show_id"] not in shows:
            raise DeskError("slot references unknown show")
    for b in bookings:
        if b["campaign_id"] not in campaigns or b["slot_id"] not in slots:
            raise DeskError("booking reference is unresolved")
        c = creatives.get((b["creative_id"], b["creative_revision"]))
        if not c or c["campaign_id"] != b["campaign_id"] or not c["approved"]:
            raise DeskError("booking is not bound to an approved campaign creative")
        if b["status"] in BOOKING_ACTIVE:
            if b["slot_id"] in seen_active:
                raise DeskError("active slot collision")
            seen_active.add(b["slot_id"])
        if b["billable"] not in (0, 1):
            raise DeskError("billable flag must be 0 or 1")
        if b["makegood_for"]:
            parent = by_id.get(b["makegood_for"])
            if not parent or parent["status"] != "MISSED" or not parent["billable"] or b["billable"]:
                raise DeskError("invalid makegood relationship")

    expected_invoices: dict[str, dict[str, Any]] = {}
    for cid, campaign in campaigns.items():
        cbook = [b for b in bookings if b["campaign_id"] == cid]
        delivered = [b for b in cbook if b["status"] == "DELIVERED" and b["billable"] == 1]
        unresolved = sorted(b["booking_id"] for b in cbook if b["status"] == "BOOKED")
        missed_unresolved = []
        for b in cbook:
            if b["status"] == "MISSED" and b["billable"] == 1:
                mg = next((x for x in cbook if x["makegood_for"] == b["booking_id"]), None)
                if not mg or mg["status"] != "DELIVERED":
                    missed_unresolved.append(b["booking_id"])
        allocated = sum(1 for b in cbook if b["billable"] == 1 and b["status"] != "CANCELLED")
        reasons = []
        if allocated < campaign["contracted_insertions"]:
            reasons.append("CONTRACTED_INSERTIONS_NOT_FULLY_ALLOCATED")
        if unresolved:
            reasons.append("PLACEMENTS_STILL_BOOKED")
        if missed_unresolved:
            reasons.append("MISSED_PLACEMENT_MAKEGOOD_UNRESOLVED")
        expected_invoices[cid] = {
            "amount": len(delivered) * campaign["unit_rate_cents"],
            "delivered": sorted(b["booking_id"] for b in delivered),
            "unresolved": unresolved,
            "missed": sorted(missed_unresolved),
            "reasons": reasons,
            "state": "READY_FOR_OWNER_REVIEW" if not reasons else "HOLD",
        }
    invoices = snapshot.get("invoice_drafts", [])
    if {i["campaign_id"] for i in invoices} != set(campaigns):
        raise DeskError("invoice draft campaign set mismatch")
    for inv in invoices:
        exp = expected_invoices[inv["campaign_id"]]
        if (inv["draft_amount_cents"] != exp["amount"] or
                sorted(inv["delivered_billable_booking_ids"]) != exp["delivered"] or
                sorted(inv["unresolved_booking_ids"]) != exp["unresolved"] or
                sorted(inv["missed_without_delivered_makegood"]) != exp["missed"] or
                inv["reasons"] != exp["reasons"] or inv["state"] != exp["state"]):
            raise DeskError("invoice draft semantic mismatch")
        if inv.get("payment_authorized") or inv.get("accounting_mutation_authorized") or inv.get("revenue_recognized"):
            raise DeskError("invoice draft authority escaped fail-closed boundary")
    return {"integrity_checked": True, **AUTHORITY_FLAGS}


def verify_bundle(directory: Path) -> dict[str, Any]:
    receipt = load_json(directory / "receipt.json")
    if not isinstance(receipt, dict) or receipt.get("schema") != "commons.podcast-sponsorship-flight-ops.receipt.v1":
        raise DeskError("unsupported receipt schema")
    if receipt.get("authority") != AUTHORITY_FLAGS:
        raise DeskError("receipt authority flags are not fail-closed")
    expected = receipt.get("files")
    if not isinstance(expected, dict) or set(expected) != {"HANDOFF.md", "invoice_drafts.csv", "placements.csv", "snapshot.json"}:
        raise DeskError("receipt file set mismatch")
    for name, digest in expected.items():
        if _sha256(digest, f"files.{name}") != hashlib.sha256((directory / name).read_bytes()).hexdigest():
            raise DeskError(f"bundle file digest mismatch: {name}")
    snapshot = load_json(directory / "snapshot.json")
    verify_snapshot(snapshot)
    if snapshot["semantic_digest"] != receipt.get("semantic_digest"):
        raise DeskError("receipt semantic digest mismatch")
    return {"integrity_checked": True, "semantic_digest": snapshot["semantic_digest"], **AUTHORITY_FLAGS}


def apply_command(desk: Desk, command: Any) -> dict[str, Any]:
    if not isinstance(command, dict):
        raise DeskError("command must be a JSON object")
    allowed_top = {"operation_key", "occurred_at", "action", "args"}
    unknown = set(command) - allowed_top
    if unknown:
        raise DeskError("unknown command fields: " + ",".join(sorted(unknown)))
    action = _text(command.get("action"), "action", max_len=64)
    args = command.get("args")
    if not isinstance(args, dict):
        raise DeskError("args must be a JSON object")
    actions: dict[str, Callable[..., dict[str, Any]]] = {
        "add_show": desk.add_show,
        "add_slot": desk.add_slot,
        "add_campaign": desk.add_campaign,
        "add_creative": desk.add_creative,
        "approve_creative": desk.approve_creative,
        "book": desk.book,
        "cancel": desk.cancel,
        "reschedule": desk.reschedule,
        "mark_delivery": desk.mark_delivery,
        "mark_missed": desk.mark_missed,
        "makegood": desk.makegood,
    }
    if action not in actions:
        raise DeskError("unsupported action")
    try:
        return actions[action](command.get("operation_key"), command.get("occurred_at"), **args)
    except TypeError:
        raise DeskError(f"invalid arguments for action {action}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init"); p_init.add_argument("db", type=Path)
    p_apply = sub.add_parser("apply"); p_apply.add_argument("db", type=Path); p_apply.add_argument("command", type=Path)
    p_status = sub.add_parser("status"); p_status.add_argument("db", type=Path)
    p_verify = sub.add_parser("verify"); p_verify.add_argument("db", type=Path)
    p_export = sub.add_parser("export"); p_export.add_argument("db", type=Path); p_export.add_argument("directory", type=Path)
    p_vb = sub.add_parser("verify-bundle"); p_vb.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            with Desk(args.db) as desk:
                result = desk.verify_db()
        elif args.cmd == "apply":
            with Desk(args.db) as desk:
                result = apply_command(desk, load_json(args.command))
        elif args.cmd == "status":
            with Desk(args.db) as desk:
                result = desk.snapshot()
        elif args.cmd == "verify":
            with Desk(args.db) as desk:
                result = desk.verify_db()
        elif args.cmd == "export":
            with Desk(args.db) as desk:
                result = desk.export_bundle(args.directory)
        else:
            result = verify_bundle(args.directory)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    except (DeskError, OSError, sqlite3.Error, UnicodeError) as exc:
        parser.exit(2, f"podcast-flight-ops: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
