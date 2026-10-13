#!/usr/bin/env python3
"""Local-first channel partner deal-registration and commission evidence desk.

The desk deliberately performs no network calls and moves no money. It records
operator-supplied partner terms and evidence, prevents overlapping deal claims,
computes exact integer-minor-unit commission obligations, and exports a
content-addressed owner-review packet.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1
SAFE_INT = 9_000_000_000_000_000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
EVENT_KINDS = {
    "BUYER_ACCEPTED",
    "BUYER_DECLINED",
    "PAYMENT_SETTLED",
    "PAYMENT_REVERSED",
    "PARTNER_PAYMENT_RECORDED",
    "DEAL_CANCELLED",
}
AMOUNT_EVENTS = {"PAYMENT_SETTLED", "PAYMENT_REVERSED", "PARTNER_PAYMENT_RECORDED"}


class DeskError(ValueError):
    pass


class ConflictError(DeskError):
    pass


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeskError(f"{name} must be an object")
    return value


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise DeskError(f"invalid {name}")
    return value


def _text(value: Any, name: str, *, max_len: int = 300) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise DeskError(f"invalid {name}")
    if any(ord(ch) < 32 and ch not in "\t" for ch in value):
        raise DeskError(f"control character in {name}")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise DeskError(f"invalid {name}")
    return value


def _currency(value: Any) -> str:
    if not isinstance(value, str) or not CURRENCY_RE.fullmatch(value):
        raise DeskError("currency must be three uppercase ASCII letters")
    return value


def _integer(value: Any, name: str, *, minimum: int = 0, maximum: int = SAFE_INT) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeskError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise DeskError(f"{name} out of range")
    return value


def _utc(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise DeskError(f"{name} must be UTC text")
    if not value.endswith("Z"):
        raise DeskError(f"{name} must end in Z")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise DeskError(f"invalid {name}") from exc
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0) or dt.microsecond:
        raise DeskError(f"{name} must be whole-second UTC")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def strict_json_loads(data: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise DeskError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad_constant(value: str) -> Any:
        raise DeskError(f"non-finite JSON number: {value}")

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=bad_constant)
    except json.JSONDecodeError as exc:
        raise DeskError("invalid JSON") from exc


def _source(ref: Any, sha256: Any) -> tuple[str, str]:
    return _text(ref, "source_ref", max_len=500), _sha(sha256, "source_sha256")


def _op_payload(action: str, fields: Mapping[str, Any]) -> tuple[str, str]:
    packet = {"action": action, **fields}
    return digest(packet), canonical_bytes(packet).decode("utf-8")


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
    operation_key TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS partners (
    partner_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS partner_terms (
    terms_id TEXT PRIMARY KEY,
    partner_id TEXT NOT NULL REFERENCES partners(partner_id),
    revision INTEGER NOT NULL,
    commission_bps INTEGER NOT NULL,
    protection_days INTEGER NOT NULL,
    trigger TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    terms_sha256 TEXT NOT NULL,
    UNIQUE(partner_id, revision)
);
CREATE TABLE IF NOT EXISTS deals (
    deal_id TEXT PRIMARY KEY,
    partner_id TEXT NOT NULL REFERENCES partners(partner_id),
    terms_id TEXT NOT NULL REFERENCES partner_terms(terms_id),
    buyer_key TEXT NOT NULL,
    opportunity_key TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    protection_expires_at TEXT NOT NULL,
    scope_sha256 TEXT NOT NULL,
    currency TEXT NOT NULL,
    proposed_value_minor INTEGER NOT NULL,
    source_ref TEXT NOT NULL,
    source_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deal_registrations (
    buyer_key TEXT NOT NULL,
    opportunity_key TEXT NOT NULL,
    deal_id TEXT NOT NULL REFERENCES deals(deal_id),
    PRIMARY KEY(buyer_key, opportunity_key)
);
CREATE TABLE IF NOT EXISTS registration_conflicts (
    operation_key TEXT PRIMARY KEY,
    proposed_deal_id TEXT NOT NULL,
    existing_deal_id TEXT NOT NULL,
    buyer_key TEXT NOT NULL,
    opportunity_key TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    proposal_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deal_events (
    event_id TEXT PRIMARY KEY,
    deal_id TEXT NOT NULL REFERENCES deals(deal_id),
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    amount_minor INTEGER,
    currency TEXT,
    source_ref TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    event_sha256 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deal_events_deal ON deal_events(deal_id, occurred_at, event_id);
"""


_EVENT_ORDER = {
    "BUYER_ACCEPTED": 0,
    "BUYER_DECLINED": 0,
    "PAYMENT_SETTLED": 1,
    "PAYMENT_REVERSED": 2,
    "PARTNER_PAYMENT_RECORDED": 3,
    "DEAL_CANCELLED": 4,
}


def _validate_event_timeline(deal: Mapping[str, Any], terms: Mapping[str, Any], events: Iterable[Mapping[str, Any]]) -> None:
    registered_at = _parse_utc(deal["registered_at"])
    ordered = sorted(events, key=lambda row: (row["occurred_at"], _EVENT_ORDER[row["kind"]], row["event_id"]))
    disposition = False
    accepted = False
    cancelled = False
    settled = 0
    reversed_minor = 0
    paid = 0
    for row in ordered:
        if _parse_utc(row["occurred_at"]) < registered_at:
            raise DeskError("event cannot predate deal registration")
        if cancelled:
            raise DeskError("cancelled deal cannot have later events")
        kind = row["kind"]
        if kind in {"BUYER_ACCEPTED", "BUYER_DECLINED"}:
            if disposition:
                raise DeskError("buyer disposition already recorded")
            disposition = True
            accepted = kind == "BUYER_ACCEPTED"
            continue
        if kind == "DEAL_CANCELLED":
            cancelled = True
            continue
        if kind in AMOUNT_EVENTS:
            if not accepted:
                raise DeskError("financial event requires buyer acceptance evidence")
            amount = int(row["amount_minor"])
            if kind == "PAYMENT_SETTLED":
                settled += amount
            elif kind == "PAYMENT_REVERSED":
                reversed_minor += amount
                if reversed_minor > settled:
                    raise DeskError("reversals cannot exceed prior settled payment evidence")
            elif kind == "PARTNER_PAYMENT_RECORDED":
                paid += amount
            due = ((settled - reversed_minor) * int(terms["commission_bps"])) // 10_000
            if paid > due:
                raise DeskError("recorded partner payment exceeds commission supported at that event time")


class DealDesk:
    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 30000")
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO metadata(key,value) VALUES('schema_version',?)",
            (str(SCHEMA_VERSION),),
        )
        version = self.conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
        if version != str(SCHEMA_VERSION):
            raise DeskError(f"unsupported schema version {version}")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "DealDesk":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _mutate(self, operation_key: str, action: str, fields: Mapping[str, Any], fn: Any) -> dict[str, Any]:
        operation_key = _id(operation_key, "operation_key")
        payload_sha, _ = _op_payload(action, fields)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            prior = self.conn.execute(
                "SELECT action,payload_sha256,result_json FROM operations WHERE operation_key=?",
                (operation_key,),
            ).fetchone()
            if prior:
                if prior["action"] != action or prior["payload_sha256"] != payload_sha:
                    raise ConflictError("operation key reused with different payload")
                result = strict_json_loads(prior["result_json"])
                self.conn.execute("COMMIT")
                return result
            result = fn()
            result_json = canonical_bytes(result).decode("utf-8")
            self.conn.execute(
                "INSERT INTO operations(operation_key,action,payload_sha256,result_json,created_at) VALUES(?,?,?,?,?)",
                (operation_key, action, payload_sha, result_json, utc_now()),
            )
            self.conn.execute("COMMIT")
            return result
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def add_partner(
        self,
        *,
        operation_key: str,
        partner_id: str,
        display_name: str,
        created_at: str,
        source_ref: str,
        source_sha256: str,
    ) -> dict[str, Any]:
        partner_id = _id(partner_id, "partner_id")
        display_name = _text(display_name, "display_name", max_len=200)
        created_at = _utc(created_at, "created_at")
        source_ref, source_sha256 = _source(source_ref, source_sha256)
        fields = locals().copy(); fields.pop("self"); fields.pop("operation_key")

        def apply() -> dict[str, Any]:
            if self.conn.execute("SELECT 1 FROM partners WHERE partner_id=?", (partner_id,)).fetchone():
                raise ConflictError("partner_id already exists")
            self.conn.execute(
                "INSERT INTO partners VALUES(?,?,?,?,?)",
                (partner_id, display_name, created_at, source_ref, source_sha256),
            )
            return {"status": "PARTNER_RECORDED", "partner_id": partner_id}

        return self._mutate(operation_key, "ADD_PARTNER", fields, apply)

    def add_terms(
        self,
        *,
        operation_key: str,
        terms_id: str,
        partner_id: str,
        revision: int,
        commission_bps: int,
        protection_days: int,
        effective_at: str,
        source_ref: str,
        source_sha256: str,
        trigger: str = "SETTLED_PAYMENT",
    ) -> dict[str, Any]:
        terms_id = _id(terms_id, "terms_id")
        partner_id = _id(partner_id, "partner_id")
        revision = _integer(revision, "revision", minimum=1, maximum=1_000_000)
        commission_bps = _integer(commission_bps, "commission_bps", minimum=0, maximum=10_000)
        protection_days = _integer(protection_days, "protection_days", minimum=1, maximum=3_650)
        effective_at = _utc(effective_at, "effective_at")
        source_ref, source_sha256 = _source(source_ref, source_sha256)
        if trigger != "SETTLED_PAYMENT":
            raise DeskError("v1 only supports SETTLED_PAYMENT trigger")
        terms_projection = {
            "terms_id": terms_id,
            "partner_id": partner_id,
            "revision": revision,
            "commission_bps": commission_bps,
            "protection_days": protection_days,
            "trigger": trigger,
            "effective_at": effective_at,
            "source_ref": source_ref,
            "source_sha256": source_sha256,
        }
        terms_sha256 = digest(terms_projection)
        fields = {**terms_projection, "terms_sha256": terms_sha256}

        def apply() -> dict[str, Any]:
            if not self.conn.execute("SELECT 1 FROM partners WHERE partner_id=?", (partner_id,)).fetchone():
                raise DeskError("unknown partner")
            try:
                self.conn.execute(
                    "INSERT INTO partner_terms VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (terms_id, partner_id, revision, commission_bps, protection_days, trigger, effective_at,
                     source_ref, source_sha256, terms_sha256),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("terms id or partner revision already exists") from exc
            return {"status": "TERMS_RECORDED", "terms_id": terms_id, "terms_sha256": terms_sha256}

        return self._mutate(operation_key, "ADD_TERMS", fields, apply)

    def register_deal(
        self,
        *,
        operation_key: str,
        deal_id: str,
        partner_id: str,
        terms_id: str,
        buyer_key: str,
        opportunity_key: str,
        registered_at: str,
        scope_sha256: str,
        currency: str,
        proposed_value_minor: int,
        source_ref: str,
        source_sha256: str,
    ) -> dict[str, Any]:
        deal_id = _id(deal_id, "deal_id")
        partner_id = _id(partner_id, "partner_id")
        terms_id = _id(terms_id, "terms_id")
        buyer_key = _id(buyer_key, "buyer_key")
        opportunity_key = _id(opportunity_key, "opportunity_key")
        registered_at = _utc(registered_at, "registered_at")
        scope_sha256 = _sha(scope_sha256, "scope_sha256")
        currency = _currency(currency)
        proposed_value_minor = _integer(proposed_value_minor, "proposed_value_minor", minimum=0)
        source_ref, source_sha256 = _source(source_ref, source_sha256)
        fields = locals().copy(); fields.pop("self"); fields.pop("operation_key")

        def apply() -> dict[str, Any]:
            terms = self.conn.execute("SELECT * FROM partner_terms WHERE terms_id=?", (terms_id,)).fetchone()
            if not terms:
                raise DeskError("unknown terms")
            if terms["partner_id"] != partner_id:
                raise DeskError("terms belong to a different partner")
            if _parse_utc(registered_at) < _parse_utc(terms["effective_at"]):
                raise DeskError("deal registration predates bound terms")
            existing = self.conn.execute(
                "SELECT deal_id FROM deal_registrations WHERE buyer_key=? AND opportunity_key=?",
                (buyer_key, opportunity_key),
            ).fetchone()
            if existing:
                proposal_sha = digest(fields)
                self.conn.execute(
                    "INSERT INTO registration_conflicts VALUES(?,?,?,?,?,?,?)",
                    (operation_key, deal_id, existing["deal_id"], buyer_key, opportunity_key, utc_now(), proposal_sha),
                )
                return {
                    "status": "HOLD_REGISTRATION_CONFLICT",
                    "proposed_deal_id": deal_id,
                    "existing_deal_id": existing["deal_id"],
                    "buyer_key": buyer_key,
                    "opportunity_key": opportunity_key,
                    "proposal_sha256": proposal_sha,
                }
            if self.conn.execute("SELECT 1 FROM deals WHERE deal_id=?", (deal_id,)).fetchone():
                raise ConflictError("deal_id already exists")
            expires = (_parse_utc(registered_at) + timedelta(days=terms["protection_days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.conn.execute(
                "INSERT INTO deals VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (deal_id, partner_id, terms_id, buyer_key, opportunity_key, registered_at, expires,
                 scope_sha256, currency, proposed_value_minor, source_ref, source_sha256),
            )
            self.conn.execute(
                "INSERT INTO deal_registrations VALUES(?,?,?)", (buyer_key, opportunity_key, deal_id)
            )
            return {
                "status": "DEAL_REGISTERED",
                "deal_id": deal_id,
                "terms_id": terms_id,
                "protection_expires_at": expires,
            }

        return self._mutate(operation_key, "REGISTER_DEAL", fields, apply)

    def add_event(
        self,
        *,
        operation_key: str,
        event_id: str,
        deal_id: str,
        kind: str,
        occurred_at: str,
        source_ref: str,
        source_sha256: str,
        amount_minor: int | None = None,
        currency: str | None = None,
    ) -> dict[str, Any]:
        event_id = _id(event_id, "event_id")
        deal_id = _id(deal_id, "deal_id")
        if kind not in EVENT_KINDS:
            raise DeskError("unsupported event kind")
        occurred_at = _utc(occurred_at, "occurred_at")
        source_ref, source_sha256 = _source(source_ref, source_sha256)
        if kind in AMOUNT_EVENTS:
            amount_minor = _integer(amount_minor, "amount_minor", minimum=1)
            currency = _currency(currency)
        else:
            if amount_minor is not None or currency is not None:
                raise DeskError("non-financial event may not carry amount/currency")
        fields = {
            "event_id": event_id,
            "deal_id": deal_id,
            "kind": kind,
            "occurred_at": occurred_at,
            "source_ref": source_ref,
            "source_sha256": source_sha256,
            "amount_minor": amount_minor,
            "currency": currency,
        }
        event_sha256 = digest(fields)

        def apply() -> dict[str, Any]:
            deal = self.conn.execute("SELECT * FROM deals WHERE deal_id=?", (deal_id,)).fetchone()
            if not deal:
                raise DeskError("unknown deal")
            if currency is not None and currency != deal["currency"]:
                raise DeskError("event currency differs from deal currency")
            prior = self.conn.execute("SELECT * FROM deal_events WHERE event_id=?", (event_id,)).fetchone()
            if prior:
                raise ConflictError("event_id already exists")
            events = list(self.conn.execute(
                "SELECT * FROM deal_events WHERE deal_id=? ORDER BY occurred_at,event_id", (deal_id,)
            ))
            if any(row["kind"] == "DEAL_CANCELLED" for row in events):
                raise DeskError("cancelled deal cannot accept later events")
            if kind == "BUYER_ACCEPTED" and any(row["kind"] in {"BUYER_ACCEPTED", "BUYER_DECLINED"} for row in events):
                raise DeskError("buyer disposition already recorded")
            if kind == "BUYER_DECLINED" and any(row["kind"] in {"BUYER_ACCEPTED", "BUYER_DECLINED"} for row in events):
                raise DeskError("buyer disposition already recorded")
            accepted = [row for row in events if row["kind"] == "BUYER_ACCEPTED"]
            if kind in {"PAYMENT_SETTLED", "PAYMENT_REVERSED", "PARTNER_PAYMENT_RECORDED"}:
                if not accepted:
                    raise DeskError("financial event requires buyer acceptance evidence")
                if _parse_utc(occurred_at) < _parse_utc(accepted[0]["occurred_at"]):
                    raise DeskError("financial event cannot predate buyer acceptance evidence")
            settled = sum(row["amount_minor"] or 0 for row in events if row["kind"] == "PAYMENT_SETTLED")
            reversed_minor = sum(row["amount_minor"] or 0 for row in events if row["kind"] == "PAYMENT_REVERSED")
            paid = sum(row["amount_minor"] or 0 for row in events if row["kind"] == "PARTNER_PAYMENT_RECORDED")
            if kind == "PAYMENT_SETTLED":
                settled += int(amount_minor)
            elif kind == "PAYMENT_REVERSED":
                reversed_minor += int(amount_minor)
                if reversed_minor > settled:
                    raise DeskError("reversals cannot exceed settled payment evidence")
            terms = self.conn.execute("SELECT * FROM partner_terms WHERE terms_id=?", (deal["terms_id"],)).fetchone()
            candidate = {
                "event_id": event_id, "deal_id": deal_id, "kind": kind, "occurred_at": occurred_at,
                "amount_minor": amount_minor, "currency": currency, "source_ref": source_ref,
                "source_sha256": source_sha256, "event_sha256": event_sha256,
            }
            _validate_event_timeline(deal, terms, [*events, candidate])
            net = settled - reversed_minor
            due = (net * terms["commission_bps"]) // 10_000
            if kind == "PARTNER_PAYMENT_RECORDED":
                paid += int(amount_minor)
                if paid > due:
                    raise DeskError("recorded partner payment exceeds current computed commission")
            if kind == "PAYMENT_REVERSED" and paid > due:
                raise DeskError("reversal would make recorded partner payment exceed current commission")
            self.conn.execute(
                "INSERT INTO deal_events VALUES(?,?,?,?,?,?,?,?,?)",
                (event_id, deal_id, kind, occurred_at, amount_minor, currency, source_ref, source_sha256, event_sha256),
            )
            compiled = self.compile_deal(deal_id)
            return {"status": "EVENT_RECORDED", "event_id": event_id, "deal_state": compiled["state"]}

        return self._mutate(operation_key, "ADD_EVENT", fields, apply)

    def compile_deal(self, deal_id: str) -> dict[str, Any]:
        deal_id = _id(deal_id, "deal_id")
        deal = self.conn.execute("SELECT * FROM deals WHERE deal_id=?", (deal_id,)).fetchone()
        if not deal:
            raise DeskError("unknown deal")
        terms = self.conn.execute("SELECT * FROM partner_terms WHERE terms_id=?", (deal["terms_id"],)).fetchone()
        partner = self.conn.execute("SELECT * FROM partners WHERE partner_id=?", (deal["partner_id"],)).fetchone()
        events = list(self.conn.execute(
            "SELECT * FROM deal_events WHERE deal_id=? ORDER BY occurred_at,event_id", (deal_id,)
        ))
        _validate_event_timeline(deal, terms, events)
        accepted_rows = [row for row in events if row["kind"] == "BUYER_ACCEPTED"]
        declined = any(row["kind"] == "BUYER_DECLINED" for row in events)
        cancelled = any(row["kind"] == "DEAL_CANCELLED" for row in events)
        accepted_at = accepted_rows[0]["occurred_at"] if accepted_rows else None
        accepted_in_window = bool(accepted_at and _parse_utc(accepted_at) <= _parse_utc(deal["protection_expires_at"]))
        settled = sum(row["amount_minor"] or 0 for row in events if row["kind"] == "PAYMENT_SETTLED")
        reversed_minor = sum(row["amount_minor"] or 0 for row in events if row["kind"] == "PAYMENT_REVERSED")
        net = settled - reversed_minor
        commission = (net * terms["commission_bps"]) // 10_000
        paid = sum(row["amount_minor"] or 0 for row in events if row["kind"] == "PARTNER_PAYMENT_RECORDED")
        outstanding = commission - paid
        if cancelled:
            state = "CANCELLED"
        elif declined:
            state = "DECLINED"
        elif not accepted_at:
            state = "REGISTERED"
        elif not accepted_in_window:
            state = "HOLD_PROTECTION_EXPIRED"
        elif net == 0:
            state = "ATTRIBUTED_AWAITING_SETTLEMENT"
        elif commission == 0:
            state = "ATTRIBUTED_NO_COMMISSION"
        elif outstanding > 0:
            state = "COMMISSION_DUE_FOR_OWNER_REVIEW"
        elif commission > 0 and outstanding == 0:
            state = "PAID_EVIDENCE"
        else:
            state = "HOLD"
        return {
            "deal_id": deal["deal_id"],
            "partner_id": deal["partner_id"],
            "partner_name": partner["display_name"],
            "terms_id": deal["terms_id"],
            "terms_sha256": terms["terms_sha256"],
            "buyer_key": deal["buyer_key"],
            "opportunity_key": deal["opportunity_key"],
            "registered_at": deal["registered_at"],
            "protection_expires_at": deal["protection_expires_at"],
            "scope_sha256": deal["scope_sha256"],
            "currency": deal["currency"],
            "proposed_value_minor": deal["proposed_value_minor"],
            "commission_bps": terms["commission_bps"],
            "accepted_at": accepted_at,
            "accepted_within_protection": accepted_in_window,
            "settled_payment_minor": settled,
            "reversed_payment_minor": reversed_minor,
            "net_settled_minor": net,
            "computed_commission_minor": commission,
            "partner_payment_recorded_minor": paid,
            "commission_outstanding_minor": outstanding,
            "state": state,
            "event_count": len(events),
        }

    def snapshot(self) -> dict[str, Any]:
        partners = [dict(row) for row in self.conn.execute("SELECT * FROM partners ORDER BY partner_id")]
        terms = [dict(row) for row in self.conn.execute("SELECT * FROM partner_terms ORDER BY partner_id,revision,terms_id")]
        deal_ids = [row[0] for row in self.conn.execute("SELECT deal_id FROM deals ORDER BY deal_id")]
        deals = [self.compile_deal(deal_id) for deal_id in deal_ids]
        conflicts = [dict(row) for row in self.conn.execute(
            "SELECT proposed_deal_id,existing_deal_id,buyer_key,opportunity_key,observed_at,proposal_sha256 "
            "FROM registration_conflicts ORDER BY observed_at,proposed_deal_id"
        )]
        body = {
            "schema": "channel-partner-deal-desk/v1",
            "partners": partners,
            "terms": terms,
            "deals": deals,
            "registration_conflicts": conflicts,
            "authority": {
                "external_contact_performed": False,
                "provider_mutation_performed": False,
                "payment_moved": False,
                "accounting_conclusion": False,
                "recognized_revenue_claimed": False,
            },
        }
        return {**body, "snapshot_sha256": digest(body)}

    def export(self, directory: str | os.PathLike[str]) -> dict[str, str]:
        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        snapshot = self.snapshot()
        json_bytes = canonical_bytes(snapshot) + b"\n"
        rows = snapshot["deals"]
        csv_buf = io.StringIO(newline="")
        fields = [
            "deal_id", "partner_id", "buyer_key", "opportunity_key", "state", "currency",
            "net_settled_minor", "computed_commission_minor", "partner_payment_recorded_minor",
            "commission_outstanding_minor", "protection_expires_at",
        ]
        writer = csv.DictWriter(csv_buf, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        csv_bytes = csv_buf.getvalue().encode("utf-8")
        md = [
            "# Channel Partner Deal Desk — owner review",
            "",
            f"Snapshot SHA-256: `{snapshot['snapshot_sha256']}`",
            "",
            "| Deal | Partner | State | Net settled | Commission | Paid evidence | Outstanding |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for row in rows:
            md.append(
                f"| {row['deal_id']} | {row['partner_id']} | {row['state']} | "
                f"{row['net_settled_minor']} {row['currency']} minor | {row['computed_commission_minor']} | "
                f"{row['partner_payment_recorded_minor']} | {row['commission_outstanding_minor']} |"
            )
        if snapshot["registration_conflicts"]:
            md += ["", "## Registration conflicts"]
            for row in snapshot["registration_conflicts"]:
                md.append(f"- proposed `{row['proposed_deal_id']}` conflicts with `{row['existing_deal_id']}` for `{row['buyer_key']}` / `{row['opportunity_key']}`")
        md += [
            "",
            "`COMMISSION_DUE_FOR_OWNER_REVIEW` is arithmetic over supplied evidence, not a payment instruction.",
            "No network contact, provider mutation, money movement, or accounting conclusion is performed by this desk.",
            "",
        ]
        md_bytes = "\n".join(md).encode("utf-8")
        files = {
            "channel_partner_snapshot.json": json_bytes,
            "channel_partner_deals.csv": csv_bytes,
            "channel_partner_review.md": md_bytes,
        }
        receipt = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
        receipt["artifact_set_sha256"] = digest(receipt)
        files["SHA256SUMS.json"] = canonical_bytes(receipt) + b"\n"
        for name, data in files.items():
            _exclusive_write(out_dir / name, data)
        return {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}

    def verify_export(self, directory: str | os.PathLike[str]) -> bool:
        out_dir = Path(directory)
        expected_snapshot = canonical_bytes(self.snapshot()) + b"\n"
        actual = (out_dir / "channel_partner_snapshot.json").read_bytes()
        if actual != expected_snapshot:
            raise DeskError("snapshot export does not match current database")
        receipt = strict_json_loads((out_dir / "SHA256SUMS.json").read_text("utf-8"))
        for name in ("channel_partner_snapshot.json", "channel_partner_deals.csv", "channel_partner_review.md"):
            actual_sha = hashlib.sha256((out_dir / name).read_bytes()).hexdigest()
            if receipt.get(name) != actual_sha:
                raise DeskError(f"artifact hash mismatch: {name}")
        base = {k: v for k, v in receipt.items() if k != "artifact_set_sha256"}
        if receipt.get("artifact_set_sha256") != digest(base):
            raise DeskError("artifact set receipt mismatch")
        return True


def _exclusive_write(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_bounded_text(path: str | os.PathLike[str], *, limit: int = 1_048_576) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise DeskError("input must be a regular file")
        if info.st_size > limit:
            raise DeskError("input file too large")
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > limit:
            raise DeskError("input file too large")
        try:
            return bytes(data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DeskError("input must be UTF-8") from exc
    finally:
        os.close(fd)


def apply_mutation(desk: DealDesk, mutation: Any) -> dict[str, Any]:
    obj = _require_dict(mutation, "mutation")
    kind = obj.get("action")
    if not isinstance(kind, str):
        raise DeskError("mutation.action is required")
    envelopes = {
        "ADD_PARTNER": {"action", "operation_key", "partner_id", "display_name", "created_at", "source_ref", "source_sha256"},
        "ADD_TERMS": {"action", "operation_key", "terms_id", "partner_id", "revision", "commission_bps", "protection_days", "effective_at", "source_ref", "source_sha256", "trigger"},
        "REGISTER_DEAL": {"action", "operation_key", "deal_id", "partner_id", "terms_id", "buyer_key", "opportunity_key", "registered_at", "scope_sha256", "currency", "proposed_value_minor", "source_ref", "source_sha256"},
        "ADD_EVENT": {"action", "operation_key", "event_id", "deal_id", "kind", "occurred_at", "source_ref", "source_sha256", "amount_minor", "currency"},
    }
    fields = envelopes.get(kind)
    if fields is None:
        raise DeskError("mutation envelope does not match a recorded shape")
    required = {
        "ADD_PARTNER": envelopes["ADD_PARTNER"],
        "ADD_TERMS": envelopes["ADD_TERMS"] - {"trigger"},
        "REGISTER_DEAL": envelopes["REGISTER_DEAL"],
        "ADD_EVENT": envelopes["ADD_EVENT"] - {"amount_minor", "currency"},
    }[kind]
    if not required.issubset(obj):
        missing = sorted(required - set(obj))
        raise DeskError("missing mutation fields: " + ",".join(missing))
    extra = set(obj) - fields
    if extra:
        raise DeskError("unknown mutation fields: " + ",".join(sorted(extra)))
    payload = {key: value for key, value in obj.items() if key != "action"}
    if kind == "ADD_PARTNER":
        return desk.add_partner(**payload)
    if kind == "ADD_TERMS":
        return desk.add_terms(**payload)
    if kind == "REGISTER_DEAL":
        return desk.register_deal(**payload)
    if kind == "ADD_EVENT":
        return desk.add_event(**payload)
    raise AssertionError(kind)


def _hash_fixture(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def run_demo(db_path: str, out_dir: str) -> dict[str, Any]:
    now = "2026-09-16T20:00:00Z"
    with DealDesk(db_path) as desk:
        desk.add_partner(operation_key="demo.partner", partner_id="partner.demo", display_name="Example Integrator",
                         created_at=now, source_ref="synthetic:partner", source_sha256=_hash_fixture("partner"))
        desk.add_terms(operation_key="demo.terms", terms_id="terms.demo.v1", partner_id="partner.demo", revision=1,
                       commission_bps=1250, protection_days=90, effective_at=now,
                       source_ref="synthetic:terms", source_sha256=_hash_fixture("terms"))
        desk.register_deal(operation_key="demo.deal", deal_id="deal.demo.1", partner_id="partner.demo",
                           terms_id="terms.demo.v1", buyer_key="buyer.demo", opportunity_key="opportunity.demo",
                           registered_at="2026-09-16T20:01:00Z", scope_sha256=_hash_fixture("scope"),
                           currency="USD", proposed_value_minor=1_500_000,
                           source_ref="synthetic:registration", source_sha256=_hash_fixture("registration"))
        desk.add_event(operation_key="demo.accept", event_id="event.accept", deal_id="deal.demo.1", kind="BUYER_ACCEPTED",
                       occurred_at="2026-09-17T12:00:00Z", source_ref="synthetic:acceptance",
                       source_sha256=_hash_fixture("acceptance"))
        desk.add_event(operation_key="demo.settle", event_id="event.settle", deal_id="deal.demo.1", kind="PAYMENT_SETTLED",
                       occurred_at="2026-09-20T12:00:00Z", amount_minor=1_500_000, currency="USD",
                       source_ref="synthetic:settlement", source_sha256=_hash_fixture("settlement"))
        artifact_hashes = desk.export(out_dir)
        return {"deal": desk.compile_deal("deal.demo.1"), "artifacts": artifact_hashes}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init"); p.add_argument("db")
    p = sub.add_parser("demo"); p.add_argument("db"); p.add_argument("out_dir")
    p = sub.add_parser("apply"); p.add_argument("db"); p.add_argument("mutation_json")
    p = sub.add_parser("summary"); p.add_argument("db")
    p = sub.add_parser("export"); p.add_argument("db"); p.add_argument("out_dir")
    p = sub.add_parser("verify-export"); p.add_argument("db"); p.add_argument("out_dir")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "init":
            with DealDesk(args.db):
                pass
            print(canonical_bytes({"status": "INITIALIZED", "db": args.db}).decode())
        elif args.command == "demo":
            print(json.dumps(run_demo(args.db, args.out_dir), indent=2, sort_keys=True))
        elif args.command == "apply":
            mutation = strict_json_loads(_read_bounded_text(args.mutation_json))
            with DealDesk(args.db) as desk:
                result = apply_mutation(desk, mutation)
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.command == "summary":
            with DealDesk(args.db) as desk:
                print(json.dumps(desk.snapshot(), indent=2, sort_keys=True))
        elif args.command == "export":
            with DealDesk(args.db) as desk:
                print(json.dumps(desk.export(args.out_dir), indent=2, sort_keys=True))
        elif args.command == "verify-export":
            with DealDesk(args.db) as desk:
                desk.verify_export(args.out_dir)
            print("PASS")
        else:
            raise AssertionError(args.command)
        return 0
    except (DeskError, OSError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
