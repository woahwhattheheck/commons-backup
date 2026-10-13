#!/usr/bin/env python3
"""Local-first Warranty & RMA Operations Desk.

No external provider, carrier, storefront, payment, refund, accounting, or
customer-contact action is performed by this module. Consequential warranty and
resolution decisions are operator-authored and explicit.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA_VERSION = 1
MAX_JSON_BYTES = 256 * 1024
MAX_TEXT = 4000
MAX_EVIDENCE = 12
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MIME_RE = re.compile(r"^[a-z0-9.+-]+/[a-z0-9.+-]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DECISIONS = {"REQUEST_INFO", "APPROVE_RMA", "DENY"}
INSPECTIONS = {"FAULT_CONFIRMED", "NO_FAULT_FOUND", "DAMAGE_REVIEW", "UNDETERMINED"}
RESOLUTIONS = {"REPAIR", "REPLACEMENT", "REFUND", "RETURN_AS_IS"}
TERMINAL_STATUSES = {"DENIED", "CLOSED"}


class DeskError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = int(status)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message}


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes) -> Any:
    if not isinstance(raw, (bytes, bytearray)):
        raise TypeError("raw JSON must be bytes")
    if len(raw) > MAX_JSON_BYTES:
        raise DeskError(413, "BODY_TOO_LARGE", "request body exceeds limit")
    try:
        text = bytes(raw).decode("utf-8", "strict")
        return json.loads(
            text,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite number: {value}")),
        )
    except DeskError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DeskError(400, "INVALID_JSON", str(exc)) from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise DeskError(400, "INVALID_FIELD", f"{field} must be an object")
    return value


def _require_list(value: Any, field: str, *, max_items: int = 100) -> list[Any]:
    if type(value) is not list:
        raise DeskError(400, "INVALID_FIELD", f"{field} must be an array")
    if len(value) > max_items:
        raise DeskError(400, "INVALID_FIELD", f"{field} has too many items")
    return value


def _str(value: Any, field: str, *, min_len: int = 1, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str:
        raise DeskError(400, "INVALID_FIELD", f"{field} must be text")
    if len(value) < min_len or len(value) > max_len:
        raise DeskError(400, "INVALID_FIELD", f"{field} length is outside bounds")
    if "\x00" in value:
        raise DeskError(400, "INVALID_FIELD", f"{field} contains NUL")
    return value


def _opt_str(value: Any, field: str, *, max_len: int = MAX_TEXT) -> str:
    if value is None:
        return ""
    if type(value) is not str:
        raise DeskError(400, "INVALID_FIELD", f"{field} must be text")
    if len(value) > max_len or "\x00" in value:
        raise DeskError(400, "INVALID_FIELD", f"{field} is invalid")
    return value


def _safe_id(value: Any, field: str) -> str:
    value = _str(value, field, max_len=80)
    if not SAFE_ID_RE.fullmatch(value):
        raise DeskError(400, "INVALID_FIELD", f"{field} is not a safe identifier")
    return value


def _sha(value: Any, field: str) -> str:
    value = _str(value, field, min_len=64, max_len=64).lower()
    if not SHA256_RE.fullmatch(value):
        raise DeskError(400, "INVALID_FIELD", f"{field} must be a SHA-256 hex digest")
    return value


def _date(value: Any, field: str) -> str:
    value = _str(value, field, min_len=10, max_len=10)
    if not DATE_RE.fullmatch(value):
        raise DeskError(400, "INVALID_FIELD", f"{field} must be YYYY-MM-DD")
    try:
        _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise DeskError(400, "INVALID_FIELD", f"{field} is not a calendar date") from exc
    return value


def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise DeskError(400, "INVALID_FIELD", f"{field} must be boolean")
    return value


def _int(value: Any, field: str, *, lo: int = 0, hi: int = 1_000_000) -> int:
    if type(value) is not int:
        raise DeskError(400, "INVALID_FIELD", f"{field} must be integer")
    if value < lo or value > hi:
        raise DeskError(400, "INVALID_FIELD", f"{field} is outside bounds")
    return value


def _exact_keys(obj: dict[str, Any], *, required: Iterable[str], optional: Iterable[str] = ()) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = sorted(required_set - set(obj))
    unknown = sorted(set(obj) - allowed)
    if missing:
        raise DeskError(400, "MISSING_FIELD", f"missing fields: {', '.join(missing)}")
    if unknown:
        raise DeskError(400, "UNKNOWN_FIELD", f"unknown fields: {', '.join(unknown)}")


def _normalize_evidence(items: Any) -> list[dict[str, str]]:
    if items is None:
        return []
    rows = _require_list(items, "evidence", max_items=MAX_EVIDENCE)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, item in enumerate(rows):
        obj = _require_dict(item, f"evidence[{i}]")
        _exact_keys(obj, required=("evidence_id", "filename", "sha256", "mime"))
        evidence_id = _safe_id(obj["evidence_id"], f"evidence[{i}].evidence_id")
        if evidence_id in seen:
            raise DeskError(400, "DUPLICATE_EVIDENCE", "duplicate evidence_id")
        seen.add(evidence_id)
        filename = _str(obj["filename"], f"evidence[{i}].filename", max_len=180)
        if filename in {".", ".."} or "/" in filename or "\\" in filename:
            raise DeskError(400, "INVALID_FIELD", "evidence filename must be a basename")
        mime = _str(obj["mime"], f"evidence[{i}].mime", max_len=100).lower()
        if not MIME_RE.fullmatch(mime):
            raise DeskError(400, "INVALID_FIELD", "invalid evidence MIME type")
        out.append({
            "evidence_id": evidence_id,
            "filename": filename,
            "sha256": _sha(obj["sha256"], f"evidence[{i}].sha256"),
            "mime": mime,
        })
    return sorted(out, key=lambda x: x["evidence_id"])


class Store:
    def __init__(
        self,
        db_path: str | os.PathLike[str],
        *,
        now: Callable[[], str] = _utc_now,
        token_factory: Callable[[int], str] = secrets.token_urlsafe,
        id_factory: Callable[[int], str] = secrets.token_hex,
    ):
        self.db_path = str(db_path)
        self.now = now
        self.token_factory = token_factory
        self.id_factory = id_factory
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=FULL")
            self._init_schema()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
                sku TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                serial_required INTEGER NOT NULL CHECK(serial_required IN (0,1)),
                active_policy_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policies (
                policy_id TEXT PRIMARY KEY,
                sku TEXT NOT NULL REFERENCES products(sku) DEFERRABLE INITIALLY DEFERRED,
                version INTEGER NOT NULL,
                warranty_days INTEGER NOT NULL,
                instructions TEXT NOT NULL,
                policy_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(sku, version)
            );
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                intake_key TEXT NOT NULL UNIQUE,
                intake_digest TEXT NOT NULL,
                sku TEXT NOT NULL REFERENCES products(sku),
                serial TEXT NOT NULL,
                purchase_ref TEXT NOT NULL,
                purchase_date TEXT NOT NULL,
                issue_text TEXT NOT NULL,
                policy_id TEXT NOT NULL REFERENCES policies(policy_id),
                policy_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                revision INTEGER NOT NULL,
                status_token_sha256 TEXT NOT NULL,
                rma_ref TEXT UNIQUE,
                receive_ref TEXT UNIQUE,
                inspection TEXT NOT NULL DEFAULT '',
                resolution TEXT NOT NULL DEFAULT '',
                resolution_ref TEXT UNIQUE,
                completion_ref TEXT UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
                evidence_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                mime TEXT NOT NULL,
                PRIMARY KEY(case_id, evidence_id)
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
                op_key TEXT NOT NULL,
                op_digest TEXT NOT NULL,
                kind TEXT NOT NULL,
                public_message TEXT NOT NULL,
                internal_note TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(case_id, op_key)
            );
            CREATE INDEX IF NOT EXISTS idx_cases_serial ON cases(sku, serial, status);
            CREATE INDEX IF NOT EXISTS idx_events_case ON events(case_id, created_at, event_id);
            """
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
            (str(SCHEMA_VERSION),),
        )
        row = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None or int(row["value"]) != SCHEMA_VERSION:
            raise RuntimeError("unsupported schema version")

    def _begin(self) -> None:
        self.conn.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self.conn.execute("COMMIT")

    def _rollback(self) -> None:
        self.conn.execute("ROLLBACK")

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{self.id_factory(8)}"

    def _event_existing(self, case_id: str, op_key: str, digest: str) -> sqlite3.Row | None:
        row = self.conn.execute(
            "SELECT * FROM events WHERE case_id=? AND op_key=?",
            (case_id, op_key),
        ).fetchone()
        if row is not None and row["op_digest"] != digest:
            raise DeskError(409, "IDEMPOTENCY_CONFLICT", "operation key was already used with different content")
        return row

    def _record_event(
        self,
        *,
        case_id: str,
        op_key: str,
        op_digest: str,
        kind: str,
        public_message: str,
        internal_note: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        self.conn.execute(
            """INSERT INTO events(event_id,case_id,op_key,op_digest,kind,public_message,internal_note,payload_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                self._new_id("EVT"),
                case_id,
                op_key,
                op_digest,
                kind,
                public_message,
                internal_note,
                canonical_bytes(payload).decode("utf-8"),
                created_at,
            ),
        )

    def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = _require_dict(payload, "product")
        _exact_keys(obj, required=("sku", "model", "serial_required", "warranty_days", "instructions"))
        sku = _safe_id(obj["sku"], "sku")
        model = _str(obj["model"], "model", max_len=160)
        serial_required = _bool(obj["serial_required"], "serial_required")
        warranty_days = _int(obj["warranty_days"], "warranty_days", lo=0, hi=3650)
        instructions = _str(obj["instructions"], "instructions", max_len=2000)
        now = self.now()
        policy_id = f"{sku}:P1"
        policy_doc = {
            "sku": sku,
            "version": 1,
            "warranty_days": warranty_days,
            "instructions": instructions,
            "operator_review_required": True,
        }
        policy_sha = sha256_bytes(canonical_bytes(policy_doc))
        with self._lock:
            try:
                self._begin()
                if self.conn.execute("SELECT 1 FROM products WHERE sku=?", (sku,)).fetchone():
                    raise DeskError(409, "PRODUCT_EXISTS", "product already exists")
                # Deferrable FK permits policy/product creation in one transaction.
                self.conn.execute(
                    "INSERT INTO products(sku,model,serial_required,active_policy_id,created_at) VALUES(?,?,?,?,?)",
                    (sku, model, int(serial_required), policy_id, now),
                )
                self.conn.execute(
                    """INSERT INTO policies(policy_id,sku,version,warranty_days,instructions,policy_sha256,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (policy_id, sku, 1, warranty_days, instructions, policy_sha, now),
                )
                self._commit()
            except Exception:
                if self.conn.in_transaction:
                    self._rollback()
                raise
        return {
            "sku": sku,
            "model": model,
            "serial_required": serial_required,
            "active_policy_id": policy_id,
            "policy_sha256": policy_sha,
            "operator_review_required": True,
        }

    def revise_policy(self, sku: str, payload: dict[str, Any]) -> dict[str, Any]:
        sku = _safe_id(sku, "sku")
        obj = _require_dict(payload, "policy")
        _exact_keys(obj, required=("warranty_days", "instructions"))
        warranty_days = _int(obj["warranty_days"], "warranty_days", lo=0, hi=3650)
        instructions = _str(obj["instructions"], "instructions", max_len=2000)
        now = self.now()
        with self._lock:
            try:
                self._begin()
                product = self.conn.execute("SELECT * FROM products WHERE sku=?", (sku,)).fetchone()
                if product is None:
                    raise DeskError(404, "PRODUCT_NOT_FOUND", "unknown product")
                version = int(
                    self.conn.execute("SELECT COALESCE(MAX(version),0)+1 AS v FROM policies WHERE sku=?", (sku,)).fetchone()["v"]
                )
                policy_id = f"{sku}:P{version}"
                policy_doc = {
                    "sku": sku,
                    "version": version,
                    "warranty_days": warranty_days,
                    "instructions": instructions,
                    "operator_review_required": True,
                }
                policy_sha = sha256_bytes(canonical_bytes(policy_doc))
                self.conn.execute(
                    """INSERT INTO policies(policy_id,sku,version,warranty_days,instructions,policy_sha256,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (policy_id, sku, version, warranty_days, instructions, policy_sha, now),
                )
                self.conn.execute("UPDATE products SET active_policy_id=? WHERE sku=?", (policy_id, sku))
                self._commit()
            except Exception:
                if self.conn.in_transaction:
                    self._rollback()
                raise
        return {
            "sku": sku,
            "policy_id": policy_id,
            "version": version,
            "policy_sha256": policy_sha,
            "operator_review_required": True,
        }

    def list_products(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT p.sku,p.model,p.serial_required,p.active_policy_id,po.version,po.warranty_days,po.instructions,po.policy_sha256
                   FROM products p JOIN policies po ON po.policy_id=p.active_policy_id ORDER BY p.sku"""
            ).fetchall()
        return [
            {
                "sku": r["sku"],
                "model": r["model"],
                "serial_required": bool(r["serial_required"]),
                "active_policy_id": r["active_policy_id"],
                "policy": {
                    "version": r["version"],
                    "warranty_days": r["warranty_days"],
                    "instructions": r["instructions"],
                    "policy_sha256": r["policy_sha256"],
                    "operator_review_required": True,
                },
            }
            for r in rows
        ]

    def submit_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = _require_dict(payload, "case")
        _exact_keys(
            obj,
            required=("idempotency_key", "sku", "purchase_ref", "purchase_date", "issue"),
            optional=("serial", "evidence"),
        )
        intake_key = _safe_id(obj["idempotency_key"], "idempotency_key")
        sku = _safe_id(obj["sku"], "sku")
        purchase_ref = _str(obj["purchase_ref"], "purchase_ref", max_len=120)
        purchase_date = _date(obj["purchase_date"], "purchase_date")
        issue_text = _str(obj["issue"], "issue", max_len=2500)
        serial = _opt_str(obj.get("serial"), "serial", max_len=120).strip()
        evidence = _normalize_evidence(obj.get("evidence"))
        normalized = {
            "sku": sku,
            "serial": serial,
            "purchase_ref": purchase_ref,
            "purchase_date": purchase_date,
            "issue": issue_text,
            "evidence": evidence,
        }
        intake_digest = sha256_bytes(canonical_bytes(normalized))
        now = self.now()
        with self._lock:
            try:
                self._begin()
                existing = self.conn.execute("SELECT * FROM cases WHERE intake_key=?", (intake_key,)).fetchone()
                if existing is not None:
                    if existing["intake_digest"] != intake_digest:
                        raise DeskError(409, "IDEMPOTENCY_CONFLICT", "intake key was already used with different content")
                    self._commit()
                    return {
                        "created": False,
                        "case": self._public_case_row(existing),
                        "status_token": None,
                    }
                product = self.conn.execute(
                    """SELECT p.*,po.policy_sha256,po.version,po.warranty_days,po.instructions
                       FROM products p JOIN policies po ON po.policy_id=p.active_policy_id
                       WHERE p.sku=?""",
                    (sku,),
                ).fetchone()
                if product is None:
                    raise DeskError(404, "PRODUCT_NOT_FOUND", "unknown product")
                if bool(product["serial_required"]) and not serial:
                    raise DeskError(400, "SERIAL_REQUIRED", "serial is required for this product")
                if serial:
                    duplicate = self.conn.execute(
                        """SELECT case_id FROM cases
                           WHERE sku=? AND serial=? AND status NOT IN ('DENIED','CLOSED')
                           LIMIT 1""",
                        (sku, serial),
                    ).fetchone()
                    if duplicate is not None:
                        raise DeskError(409, "ACTIVE_SERIAL_CASE", "an active case already exists for this product serial")
                case_id = self._new_id("RMA")
                status_token = self.token_factory(32)
                token_hash = sha256_bytes(status_token.encode("utf-8"))
                self.conn.execute(
                    """INSERT INTO cases(
                        case_id,intake_key,intake_digest,sku,serial,purchase_ref,purchase_date,issue_text,
                        policy_id,policy_sha256,status,revision,status_token_sha256,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        case_id,
                        intake_key,
                        intake_digest,
                        sku,
                        serial,
                        purchase_ref,
                        purchase_date,
                        issue_text,
                        product["active_policy_id"],
                        product["policy_sha256"],
                        "SUBMITTED",
                        1,
                        token_hash,
                        now,
                        now,
                    ),
                )
                for row in evidence:
                    self.conn.execute(
                        "INSERT INTO evidence(case_id,evidence_id,filename,sha256,mime) VALUES(?,?,?,?,?)",
                        (case_id, row["evidence_id"], row["filename"], row["sha256"], row["mime"]),
                    )
                self._record_event(
                    case_id=case_id,
                    op_key=f"intake:{intake_key}",
                    op_digest=intake_digest,
                    kind="CASE_SUBMITTED",
                    public_message="Warranty/RMA request received for merchant review.",
                    internal_note="Customer intake does not authorize warranty coverage, shipping, replacement, or refund.",
                    payload={"evidence_count": len(evidence), "policy_id": product["active_policy_id"]},
                    created_at=now,
                )
                row = self.conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
                self._commit()
            except Exception:
                if self.conn.in_transaction:
                    self._rollback()
                raise
        if row is None:
            raise RuntimeError("case insert did not produce a readable row")
        return {"created": True, "case": self._public_case_row(row), "status_token": status_token}

    def _get_case(self, case_id: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if row is None:
            raise DeskError(404, "CASE_NOT_FOUND", "unknown case")
        return row

    def _public_case_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "case_id": row["case_id"],
            "sku": row["sku"],
            "status": row["status"],
            "revision": row["revision"],
            "policy_id": row["policy_id"],
            "purchase_date": row["purchase_date"],
            "rma_ref": row["rma_ref"] or None,
            "inspection": row["inspection"] or None,
            "resolution": row["resolution"] or None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _assert_customer_token(self, row: sqlite3.Row, token: str) -> None:
        if type(token) is not str or not token or len(token) > 256:
            raise DeskError(401, "INVALID_STATUS_TOKEN", "invalid status capability")
        supplied = sha256_bytes(token.encode("utf-8"))
        if not hmac.compare_digest(supplied, row["status_token_sha256"]):
            raise DeskError(403, "INVALID_STATUS_TOKEN", "invalid status capability")

    def customer_status(self, case_id: str, token: str) -> dict[str, Any]:
        case_id = _safe_id(case_id, "case_id")
        with self._lock:
            row = self._get_case(case_id)
            self._assert_customer_token(row, token)
            events = self.conn.execute(
                "SELECT kind,public_message,created_at FROM events WHERE case_id=? AND public_message<>'' ORDER BY created_at,rowid",
                (case_id,),
            ).fetchall()
            public = self._public_case_row(row)
        public["timeline"] = [
            {"kind": e["kind"], "message": e["public_message"], "created_at": e["created_at"]} for e in events
        ]
        public["external_authority"] = False
        return public

    def customer_supplement(self, case_id: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = _safe_id(case_id, "case_id")
        obj = _require_dict(payload, "supplement")
        _exact_keys(obj, required=("idempotency_key", "expected_revision", "message"), optional=("evidence",))
        op_key = f"customer-supplement:{_safe_id(obj['idempotency_key'], 'idempotency_key')}"
        expected_revision = _int(obj["expected_revision"], "expected_revision", lo=1)
        message = _str(obj["message"], "message", max_len=2500)
        evidence = _normalize_evidence(obj.get("evidence"))
        norm = {"expected_revision": expected_revision, "message": message, "evidence": evidence}
        digest = sha256_bytes(canonical_bytes(norm))
        now = self.now()
        with self._lock:
            try:
                self._begin()
                row = self._get_case(case_id)
                self._assert_customer_token(row, token)
                prior = self._event_existing(case_id, op_key, digest)
                if prior is not None:
                    self._commit()
                    return {"replayed": True, "case": self.customer_status(case_id, token)}
                if row["status"] != "NEEDS_INFO":
                    raise DeskError(409, "INVALID_TRANSITION", "case is not awaiting customer information")
                if row["revision"] != expected_revision:
                    raise DeskError(409, "STALE_REVISION", "case revision changed")
                for ev in evidence:
                    try:
                        self.conn.execute(
                            "INSERT INTO evidence(case_id,evidence_id,filename,sha256,mime) VALUES(?,?,?,?,?)",
                            (case_id, ev["evidence_id"], ev["filename"], ev["sha256"], ev["mime"]),
                        )
                    except sqlite3.IntegrityError as exc:
                        raise DeskError(409, "DUPLICATE_EVIDENCE", "evidence_id already exists") from exc
                new_rev = expected_revision + 1
                self.conn.execute(
                    "UPDATE cases SET issue_text=issue_text || ?,status='SUBMITTED',revision=?,updated_at=? WHERE case_id=?",
                    ("\n\nCustomer supplement: " + message, new_rev, now, case_id),
                )
                self._record_event(
                    case_id=case_id,
                    op_key=op_key,
                    op_digest=digest,
                    kind="CUSTOMER_SUPPLEMENT",
                    public_message="Additional information received for merchant review.",
                    internal_note="",
                    payload={"evidence_count": len(evidence)},
                    created_at=now,
                )
                self._commit()
            except Exception:
                if self.conn.in_transaction:
                    self._rollback()
                raise
        return {"replayed": False, "case": self.customer_status(case_id, token)}

    def operator_case(self, case_id: str) -> dict[str, Any]:
        case_id = _safe_id(case_id, "case_id")
        with self._lock:
            row = self._get_case(case_id)
            product = self.conn.execute("SELECT model,serial_required FROM products WHERE sku=?", (row["sku"],)).fetchone()
            policy = self.conn.execute("SELECT * FROM policies WHERE policy_id=?", (row["policy_id"],)).fetchone()
            evidence = self.conn.execute(
                "SELECT evidence_id,filename,sha256,mime FROM evidence WHERE case_id=? ORDER BY evidence_id",
                (case_id,),
            ).fetchall()
            events = self.conn.execute(
                "SELECT event_id,op_key,kind,public_message,internal_note,payload_json,created_at FROM events WHERE case_id=? ORDER BY created_at,rowid",
                (case_id,),
            ).fetchall()
        return {
            "case_id": row["case_id"],
            "intake_key": row["intake_key"],
            "sku": row["sku"],
            "model": product["model"] if product else "",
            "serial_required": bool(product["serial_required"]) if product else False,
            "serial": row["serial"],
            "purchase_ref": row["purchase_ref"],
            "purchase_date": row["purchase_date"],
            "issue": row["issue_text"],
            "status": row["status"],
            "revision": row["revision"],
            "policy": {
                "policy_id": row["policy_id"],
                "policy_sha256": row["policy_sha256"],
                "version": policy["version"] if policy else None,
                "warranty_days": policy["warranty_days"] if policy else None,
                "instructions": policy["instructions"] if policy else "",
                "operator_review_required": True,
            },
            "rma_ref": row["rma_ref"] or None,
            "receive_ref": row["receive_ref"] or None,
            "inspection": row["inspection"] or None,
            "resolution": row["resolution"] or None,
            "resolution_ref": row["resolution_ref"] or None,
            "completion_ref": row["completion_ref"] or None,
            "evidence": [dict(e) for e in evidence],
            "events": [
                {
                    "event_id": e["event_id"],
                    "op_key": e["op_key"],
                    "kind": e["kind"],
                    "public_message": e["public_message"],
                    "internal_note": e["internal_note"],
                    "payload": json.loads(e["payload_json"]),
                    "created_at": e["created_at"],
                }
                for e in events
            ],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "external_authority": False,
        }

    def list_cases(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM cases ORDER BY updated_at DESC,case_id").fetchall()
            return [self._public_case_row(r) for r in rows]

    def operator_decide(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = _safe_id(case_id, "case_id")
        obj = _require_dict(payload, "decision")
        _exact_keys(
            obj,
            required=("idempotency_key", "expected_revision", "policy_id", "decision", "public_message"),
            optional=("internal_note",),
        )
        op_key = f"decision:{_safe_id(obj['idempotency_key'], 'idempotency_key')}"
        expected_revision = _int(obj["expected_revision"], "expected_revision", lo=1)
        policy_id = _safe_id(obj["policy_id"], "policy_id")
        decision = _safe_id(obj["decision"], "decision")
        if decision not in DECISIONS:
            raise DeskError(400, "INVALID_DECISION", "unsupported decision")
        public_message = _str(obj["public_message"], "public_message", max_len=1000)
        internal_note = _opt_str(obj.get("internal_note"), "internal_note", max_len=2000)
        norm = {
            "expected_revision": expected_revision,
            "policy_id": policy_id,
            "decision": decision,
            "public_message": public_message,
            "internal_note": internal_note,
        }
        digest = sha256_bytes(canonical_bytes(norm))
        now = self.now()
        with self._lock:
            try:
                self._begin()
                row = self._get_case(case_id)
                prior = self._event_existing(case_id, op_key, digest)
                if prior is not None:
                    result = self.operator_case(case_id)
                    self._commit()
                    return {"replayed": True, "case": result}
                if row["revision"] != expected_revision:
                    raise DeskError(409, "STALE_REVISION", "case revision changed")
                if row["policy_id"] != policy_id:
                    raise DeskError(409, "POLICY_MISMATCH", "decision is not bound to the case policy revision")
                if row["status"] not in {"SUBMITTED", "NEEDS_INFO"}:
                    raise DeskError(409, "INVALID_TRANSITION", "case is not awaiting an operator decision")
                new_status = {"REQUEST_INFO": "NEEDS_INFO", "APPROVE_RMA": "APPROVED_RMA", "DENY": "DENIED"}[decision]
                new_rev = expected_revision + 1
                rma_ref = row["rma_ref"]
                payload_doc: dict[str, Any] = {"decision": decision, "policy_id": policy_id}
                if decision == "APPROVE_RMA":
                    rma_ref = self._new_id("RMAREF")
                    payload_doc["return_handoff"] = {
                        "rma_ref": rma_ref,
                        "state": "NOT_SENT",
                        "external_authority": False,
                    }
                self.conn.execute(
                    "UPDATE cases SET status=?,revision=?,rma_ref=?,updated_at=? WHERE case_id=?",
                    (new_status, new_rev, rma_ref, now, case_id),
                )
                self._record_event(
                    case_id=case_id,
                    op_key=op_key,
                    op_digest=digest,
                    kind=f"OPERATOR_{decision}",
                    public_message=public_message,
                    internal_note=internal_note,
                    payload=payload_doc,
                    created_at=now,
                )
                self._commit()
            except Exception:
                if self.conn.in_transaction:
                    self._rollback()
                raise
        return {"replayed": False, "case": self.operator_case(case_id)}

    def operator_receive(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = _safe_id(case_id, "case_id")
        obj = _require_dict(payload, "receive")
        _exact_keys(
            obj,
            required=("idempotency_key", "expected_revision", "rma_ref", "receive_ref", "public_message"),
            optional=("internal_note",),
        )
        op_key = f"receive:{_safe_id(obj['idempotency_key'], 'idempotency_key')}"
        expected_revision = _int(obj["expected_revision"], "expected_revision", lo=1)
        rma_ref = _safe_id(obj["rma_ref"], "rma_ref")
        receive_ref = _safe_id(obj["receive_ref"], "receive_ref")
        public_message = _str(obj["public_message"], "public_message", max_len=1000)
        internal_note = _opt_str(obj.get("internal_note"), "internal_note", max_len=2000)
        norm = {
            "expected_revision": expected_revision,
            "rma_ref": rma_ref,
            "receive_ref": receive_ref,
            "public_message": public_message,
            "internal_note": internal_note,
        }
        digest = sha256_bytes(canonical_bytes(norm))
        now = self.now()
        with self._lock:
            try:
                self._begin()
                row = self._get_case(case_id)
                prior = self._event_existing(case_id, op_key, digest)
                if prior is not None:
                    result = self.operator_case(case_id)
                    self._commit()
                    return {"replayed": True, "case": result}
                if row["revision"] != expected_revision:
                    raise DeskError(409, "STALE_REVISION", "case revision changed")
                if row["status"] != "APPROVED_RMA":
                    raise DeskError(409, "INVALID_TRANSITION", "case is not awaiting an authorized return")
                if row["rma_ref"] != rma_ref:
                    raise DeskError(409, "RMA_MISMATCH", "receive is not bound to this case RMA")
                new_rev = expected_revision + 1
                try:
                    self.conn.execute(
                        "UPDATE cases SET status='RECEIVED',revision=?,receive_ref=?,updated_at=? WHERE case_id=?",
                        (new_rev, receive_ref, now, case_id),
                    )
                except sqlite3.IntegrityError as exc:
                    raise DeskError(409, "RECEIVE_REF_CONFLICT", "receive_ref belongs to another case") from exc
                self._record_event(
                    case_id=case_id,
                    op_key=op_key,
                    op_digest=digest,
                    kind="RETURN_RECEIVED",
                    public_message=public_message,
                    internal_note=internal_note,
                    payload={"rma_ref": rma_ref, "receive_ref": receive_ref},
                    created_at=now,
                )
                self._commit()
            except Exception:
                if self.conn.in_transaction:
                    self._rollback()
                raise
        return {"replayed": False, "case": self.operator_case(case_id)}

    def operator_inspect(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = _safe_id(case_id, "case_id")
        obj = _require_dict(payload, "inspection")
        _exact_keys(
            obj,
            required=("idempotency_key", "expected_revision", "inspection", "public_message"),
            optional=("internal_note",),
        )
        op_key = f"inspect:{_safe_id(obj['idempotency_key'], 'idempotency_key')}"
        expected_revision = _int(obj["expected_revision"], "expected_revision", lo=1)
        inspection = _safe_id(obj["inspection"], "inspection")
        if inspection not in INSPECTIONS:
            raise DeskError(400, "INVALID_INSPECTION", "unsupported inspection disposition")
        public_message = _str(obj["public_message"], "public_message", max_len=1000)
        internal_note = _opt_str(obj.get("internal_note"), "internal_note", max_len=2000)
        norm = {
            "expected_revision": expected_revision,
            "inspection": inspection,
            "public_message": public_message,
            "internal_note": internal_note,
        }
        digest = sha256_bytes(canonical_bytes(norm))
        now = self.now()
        with self._lock:
            try:
                self._begin()
                row = self._get_case(case_id)
                prior = self._event_existing(case_id, op_key, digest)
                if prior is not None:
                    result = self.operator_case(case_id)
                    self._commit()
                    return {"replayed": True, "case": result}
                if row["revision"] != expected_revision:
                    raise DeskError(409, "STALE_REVISION", "case revision changed")
                if row["status"] != "RECEIVED":
                    raise DeskError(409, "INVALID_TRANSITION", "case must be received before inspection")
                new_rev = expected_revision + 1
                self.conn.execute(
                    "UPDATE cases SET status='INSPECTED',revision=?,inspection=?,updated_at=? WHERE case_id=?",
                    (new_rev, inspection, now, case_id),
                )
                self._record_event(
                    case_id=case_id,
                    op_key=op_key,
                    op_digest=digest,
                    kind="OPERATOR_INSPECTION",
                    public_message=public_message,
                    internal_note=internal_note,
                    payload={"inspection": inspection},
                    created_at=now,
                )
                self._commit()
            except Exception:
                if self.conn.in_transaction:
                    self._rollback()
                raise
        return {"replayed": False, "case": self.operator_case(case_id)}

    def operator_resolve(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = _safe_id(case_id, "case_id")
        obj = _require_dict(payload, "resolution")
        _exact_keys(
            obj,
            required=("idempotency_key", "expected_revision", "resolution", "public_message"),
            optional=("internal_note",),
        )
        op_key = f"resolve:{_safe_id(obj['idempotency_key'], 'idempotency_key')}"
        expected_revision = _int(obj["expected_revision"], "expected_revision", lo=1)
        resolution = _safe_id(obj["resolution"], "resolution")
        if resolution not in RESOLUTIONS:
            raise DeskError(400, "INVALID_RESOLUTION", "unsupported resolution")
        public_message = _str(obj["public_message"], "public_message", max_len=1000)
        internal_note = _opt_str(obj.get("internal_note"), "internal_note", max_len=2000)
        norm = {
            "expected_revision": expected_revision,
            "resolution": resolution,
            "public_message": public_message,
            "internal_note": internal_note,
        }
        digest = sha256_bytes(canonical_bytes(norm))
        now = self.now()
        with self._lock:
            try:
                self._begin()
                row = self._get_case(case_id)
                prior = self._event_existing(case_id, op_key, digest)
                if prior is not None:
                    result = self.operator_case(case_id)
                    self._commit()
                    return {"replayed": True, "case": result}
                if row["revision"] != expected_revision:
                    raise DeskError(409, "STALE_REVISION", "case revision changed")
                if row["status"] != "INSPECTED":
                    raise DeskError(409, "INVALID_TRANSITION", "case must be inspected before resolution")
                resolution_ref = self._new_id("RES")
                new_rev = expected_revision + 1
                self.conn.execute(
                    """UPDATE cases SET status='RESOLUTION_APPROVED',revision=?,resolution=?,resolution_ref=?,updated_at=?
                       WHERE case_id=?""",
                    (new_rev, resolution, resolution_ref, now, case_id),
                )
                self._record_event(
                    case_id=case_id,
                    op_key=op_key,
                    op_digest=digest,
                    kind="OPERATOR_RESOLUTION",
                    public_message=public_message,
                    internal_note=internal_note,
                    payload={
                        "resolution": resolution,
                        "resolution_ref": resolution_ref,
                        "handoff": {"state": "NOT_SENT", "external_authority": False},
                    },
                    created_at=now,
                )
                self._commit()
            except Exception:
                if self.conn.in_transaction:
                    self._rollback()
                raise
        return {"replayed": False, "case": self.operator_case(case_id)}

    def operator_close(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = _safe_id(case_id, "case_id")
        obj = _require_dict(payload, "close")
        _exact_keys(
            obj,
            required=("idempotency_key", "expected_revision", "completion_ref", "public_message"),
            optional=("internal_note",),
        )
        op_key = f"close:{_safe_id(obj['idempotency_key'], 'idempotency_key')}"
        expected_revision = _int(obj["expected_revision"], "expected_revision", lo=1)
        completion_ref = _safe_id(obj["completion_ref"], "completion_ref")
        public_message = _str(obj["public_message"], "public_message", max_len=1000)
        internal_note = _opt_str(obj.get("internal_note"), "internal_note", max_len=2000)
        norm = {
            "expected_revision": expected_revision,
            "completion_ref": completion_ref,
            "public_message": public_message,
            "internal_note": internal_note,
        }
        digest = sha256_bytes(canonical_bytes(norm))
        now = self.now()
        with self._lock:
            try:
                self._begin()
                row = self._get_case(case_id)
                prior = self._event_existing(case_id, op_key, digest)
                if prior is not None:
                    result = self.operator_case(case_id)
                    self._commit()
                    return {"replayed": True, "case": result}
                if row["revision"] != expected_revision:
                    raise DeskError(409, "STALE_REVISION", "case revision changed")
                if row["status"] != "RESOLUTION_APPROVED":
                    raise DeskError(409, "INVALID_TRANSITION", "resolution handoff must exist before closure")
                new_rev = expected_revision + 1
                try:
                    self.conn.execute(
                        "UPDATE cases SET status='CLOSED',revision=?,completion_ref=?,updated_at=? WHERE case_id=?",
                        (new_rev, completion_ref, now, case_id),
                    )
                except sqlite3.IntegrityError as exc:
                    raise DeskError(409, "COMPLETION_REF_CONFLICT", "completion_ref belongs to another case") from exc
                self._record_event(
                    case_id=case_id,
                    op_key=op_key,
                    op_digest=digest,
                    kind="CASE_CLOSED",
                    public_message=public_message,
                    internal_note=internal_note,
                    payload={
                        "completion_ref": completion_ref,
                        "merchant_observed_completion": True,
                        "provider_verified": False,
                    },
                    created_at=now,
                )
                self._commit()
            except Exception:
                if self.conn.in_transaction:
                    self._rollback()
                raise
        return {"replayed": False, "case": self.operator_case(case_id)}

    def export_case(self, case_id: str) -> bytes:
        case = self.operator_case(case_id)
        packet = {
            "schema": "warranty-rma-case-export/v1",
            "case": case,
            "authority": {
                "warranty_legal_determination": False,
                "product_safety_diagnosis": False,
                "customer_contact": False,
                "carrier_action": False,
                "payment_refund_action": False,
                "storefront_accounting_action": False,
                "external_action": False,
            },
        }
        packet["receipt_sha256"] = sha256_bytes(canonical_bytes(packet))
        return canonical_bytes(packet) + b"\n"


class OperatorAuth:
    def __init__(self, token: str):
        token = _str(token, "operator_token", min_len=16, max_len=256)
        self._digest = sha256_bytes(token.encode("utf-8"))

    def check(self, header: str | None) -> bool:
        if not header or not header.startswith("Bearer "):
            return False
        token = header[7:]
        if not token or len(token) > 256:
            return False
        return hmac.compare_digest(sha256_bytes(token.encode("utf-8")), self._digest)


def make_handler(store: Store, operator_auth: OperatorAuth, index_html: bytes) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "WarrantyRMA/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()

        def _send_json(self, status: int, obj: Any) -> None:
            raw = canonical_bytes(obj)
            self._headers(status, "application/json; charset=utf-8", len(raw))
            self.wfile.write(raw)

        def _error(self, exc: DeskError) -> None:
            self._send_json(exc.status, exc.as_dict())

        def _read_json(self) -> dict[str, Any]:
            if self.headers.get("Transfer-Encoding"):
                raise DeskError(400, "TRANSFER_ENCODING_UNSUPPORTED", "transfer encoding is not supported")
            raw_len = self.headers.get("Content-Length")
            if raw_len is None:
                raise DeskError(411, "LENGTH_REQUIRED", "Content-Length is required")
            try:
                length = int(raw_len)
            except ValueError as exc:
                raise DeskError(400, "INVALID_LENGTH", "invalid Content-Length") from exc
            if length < 0 or length > MAX_JSON_BYTES:
                raise DeskError(413, "BODY_TOO_LARGE", "request body exceeds limit")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise DeskError(400, "SHORT_BODY", "request body was truncated")
            value = loads_strict(raw)
            return _require_dict(value, "request")

        def _bearer(self) -> str:
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                raise DeskError(401, "AUTH_REQUIRED", "Bearer capability required")
            return header[7:]

        def _operator(self) -> None:
            if not operator_auth.check(self.headers.get("Authorization")):
                raise DeskError(403, "OPERATOR_AUTH_REQUIRED", "operator capability required")

        def do_GET(self) -> None:
            try:
                parsed = urllib.parse.urlsplit(self.path)
                path = parsed.path
                if path == "/":
                    self._headers(200, "text/html; charset=utf-8", len(index_html))
                    self.wfile.write(index_html)
                    return
                if path == "/api/products":
                    self._send_json(200, {"products": store.list_products()})
                    return
                if path.startswith("/api/customer/cases/"):
                    case_id = path.removeprefix("/api/customer/cases/")
                    self._send_json(200, store.customer_status(case_id, self._bearer()))
                    return
                if path == "/api/operator/cases":
                    self._operator()
                    self._send_json(200, {"cases": store.list_cases()})
                    return
                if path.startswith("/api/operator/cases/") and path.endswith("/export"):
                    self._operator()
                    case_id = path[len("/api/operator/cases/") : -len("/export")]
                    raw = store.export_case(case_id)
                    self._headers(200, "application/json; charset=utf-8", len(raw))
                    self.wfile.write(raw)
                    return
                if path.startswith("/api/operator/cases/"):
                    self._operator()
                    case_id = path.removeprefix("/api/operator/cases/")
                    self._send_json(200, store.operator_case(case_id))
                    return
                raise DeskError(404, "NOT_FOUND", "route not found")
            except DeskError as exc:
                self._error(exc)
            except Exception:
                self._send_json(500, {"error": "INTERNAL_ERROR", "message": "internal server error"})

        def do_POST(self) -> None:
            try:
                path = urllib.parse.urlsplit(self.path).path
                body = self._read_json()
                if path == "/api/customer/cases":
                    result = store.submit_case(body)
                    self._send_json(201 if result["created"] else 200, result)
                    return
                if path.startswith("/api/customer/cases/") and path.endswith("/supplement"):
                    case_id = path[len("/api/customer/cases/") : -len("/supplement")]
                    self._send_json(200, store.customer_supplement(case_id, self._bearer(), body))
                    return
                if path == "/api/operator/products":
                    self._operator()
                    self._send_json(201, store.create_product(body))
                    return
                if path.startswith("/api/operator/products/") and path.endswith("/policy"):
                    self._operator()
                    sku = path[len("/api/operator/products/") : -len("/policy")]
                    self._send_json(201, store.revise_policy(sku, body))
                    return
                prefix = "/api/operator/cases/"
                if path.startswith(prefix):
                    self._operator()
                    rest = path[len(prefix) :]
                    if "/" not in rest:
                        raise DeskError(404, "NOT_FOUND", "route not found")
                    case_id, action = rest.split("/", 1)
                    dispatch = {
                        "decision": store.operator_decide,
                        "receive": store.operator_receive,
                        "inspect": store.operator_inspect,
                        "resolve": store.operator_resolve,
                        "close": store.operator_close,
                    }
                    func = dispatch.get(action)
                    if func is None:
                        raise DeskError(404, "NOT_FOUND", "route not found")
                    self._send_json(200, func(case_id, body))
                    return
                raise DeskError(404, "NOT_FOUND", "route not found")
            except DeskError as exc:
                self._error(exc)
            except Exception:
                self._send_json(500, {"error": "INTERNAL_ERROR", "message": "internal server error"})

    return Handler


def demo(store: Store) -> dict[str, Any]:
    if not store.list_products():
        store.create_product(
            {
                "sku": "DEMO-COFFEE-01",
                "model": "Demo Countertop Brewer",
                "serial_required": True,
                "warranty_days": 365,
                "instructions": "Merchant reviews purchase evidence and issue description before any RMA decision.",
            }
        )
    case = store.submit_case(
        {
            "idempotency_key": "demo-intake-001",
            "sku": "DEMO-COFFEE-01",
            "serial": "DEMO-SERIAL-001",
            "purchase_ref": "DEMO-ORDER-1001",
            "purchase_date": "2026-09-01",
            "issue": "Synthetic demo: pump stops after startup.",
            "evidence": [
                {
                    "evidence_id": "photo-1",
                    "filename": "demo-brewer.jpg",
                    "sha256": "1" * 64,
                    "mime": "image/jpeg",
                }
            ],
        }
    )
    case_id = case["case"]["case_id"]
    current = store.operator_case(case_id)
    if current["status"] == "SUBMITTED":
        store.operator_decide(
            case_id,
            {
                "idempotency_key": "demo-approve-001",
                "expected_revision": current["revision"],
                "policy_id": current["policy"]["policy_id"],
                "decision": "APPROVE_RMA",
                "public_message": "Synthetic demo RMA approved for return inspection.",
                "internal_note": "No external carrier action performed.",
            },
        )
    current = store.operator_case(case_id)
    if current["status"] == "APPROVED_RMA":
        store.operator_receive(
            case_id,
            {
                "idempotency_key": "demo-receive-001",
                "expected_revision": current["revision"],
                "rma_ref": current["rma_ref"],
                "receive_ref": "DEMO-DOCK-001",
                "public_message": "Synthetic demo return received.",
                "internal_note": "Synthetic local receipt only.",
            },
        )
    current = store.operator_case(case_id)
    if current["status"] == "RECEIVED":
        store.operator_inspect(
            case_id,
            {
                "idempotency_key": "demo-inspect-001",
                "expected_revision": current["revision"],
                "inspection": "FAULT_CONFIRMED",
                "public_message": "Synthetic demo inspection completed.",
                "internal_note": "Synthetic observation, not a product-safety diagnosis.",
            },
        )
    current = store.operator_case(case_id)
    if current["status"] == "INSPECTED":
        store.operator_resolve(
            case_id,
            {
                "idempotency_key": "demo-resolve-001",
                "expected_revision": current["revision"],
                "resolution": "REPLACEMENT",
                "public_message": "Synthetic replacement workflow approved for merchant handoff.",
                "internal_note": "No storefront/payment/customer action performed.",
            },
        )
    current = store.operator_case(case_id)
    if current["status"] == "RESOLUTION_APPROVED":
        store.operator_close(
            case_id,
            {
                "idempotency_key": "demo-close-001",
                "expected_revision": current["revision"],
                "completion_ref": "DEMO-MERCHANT-COMPLETE-001",
                "public_message": "Synthetic demo workflow closed by merchant observation.",
                "internal_note": "Provider verification is explicitly false.",
            },
        )
    final = store.operator_case(case_id)
    return {
        "demo": "synthetic",
        "case_id": case_id,
        "final_status": final["status"],
        "resolution": final["resolution"],
        "external_actions_performed": 0,
        "export_sha256": sha256_bytes(store.export_case(case_id)),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Warranty & RMA Operations Desk")
    sub = parser.add_subparsers(dest="command", required=True)

    pserve = sub.add_parser("serve")
    pserve.add_argument("--db", required=True)
    pserve.add_argument("--host", default="127.0.0.1")
    pserve.add_argument("--port", type=int, default=8787)
    pserve.add_argument("--operator-token", required=True)

    pdemo = sub.add_parser("demo")
    pdemo.add_argument("--db", required=True)

    pexport = sub.add_parser("export")
    pexport.add_argument("--db", required=True)
    pexport.add_argument("--case-id", required=True)
    pexport.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.command == "serve":
        if args.host not in {"127.0.0.1", "::1", "localhost"}:
            raise SystemExit("serve binds loopback only")
        store = Store(args.db)
        auth = OperatorAuth(args.operator_token)
        index_path = Path(__file__).with_name("index.html")
        index_html = index_path.read_bytes()
        server = ThreadingHTTPServer((args.host, args.port), make_handler(store, auth, index_html))
        try:
            print(f"Warranty/RMA desk listening on http://{args.host}:{server.server_address[1]}/")
            server.serve_forever()
        finally:
            server.server_close()
            store.close()
        return 0
    if args.command == "demo":
        store = Store(args.db)
        try:
            print(canonical_bytes(demo(store)).decode("utf-8"))
        finally:
            store.close()
        return 0
    if args.command == "export":
        out = Path(args.out)
        if out.exists() or out.is_symlink():
            raise SystemExit("refusing to overwrite output")
        store = Store(args.db)
        try:
            raw = store.export_case(args.case_id)
        finally:
            store.close()
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
