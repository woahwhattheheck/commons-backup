from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_CENTS = 10**12


class WorkspaceError(ValueError):
    """Base error for invalid or disallowed workspace operations."""


class NotFound(WorkspaceError):
    """Used for both missing entities and failed customer capabilities."""


class Conflict(WorkspaceError):
    """The requested mutation conflicts with already-authoritative state."""


class InvalidState(WorkspaceError):
    """The entity exists but is not in a state that permits the operation."""


@dataclass(frozen=True)
class LineItem:
    item_id: str
    description: str
    quantity: int
    unit_cents: int

    @property
    def total_cents(self) -> int:
        total = self.quantity * self.unit_cents
        if total > MAX_CENTS:
            raise WorkspaceError("line total exceeds supported bound")
        return total

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "description": self.description,
            "quantity": self.quantity,
            "unit_cents": self.unit_cents,
            "total_cents": self.total_cents,
        }


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkspaceError("value is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def verify_digest_envelope(value: Any, digest_field: str) -> bool:
    if type(value) is not dict or type(digest_field) is not str or digest_field not in value:
        return False
    candidate = value.get(digest_field)
    if type(candidate) is not str or not HEX64_RE.fullmatch(candidate):
        return False
    body = dict(value)
    body.pop(digest_field, None)
    try:
        actual = _digest(body)
    except WorkspaceError:
        return False
    return hmac.compare_digest(actual, candidate)


def _plain_dict(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise WorkspaceError(f"{name} must be a plain object")
    if any(type(k) is not str for k in value):
        raise WorkspaceError(f"{name} keys must be strings")
    return value


def _text(value: Any, name: str, *, max_len: int = 512) -> str:
    if type(value) is not str:
        raise WorkspaceError(f"{name} must be a string")
    if value != value.strip() or not value:
        raise WorkspaceError(f"{name} must be nonempty with no edge whitespace")
    if len(value) > max_len:
        raise WorkspaceError(f"{name} too long")
    return value


def _opaque_id(value: Any, name: str) -> str:
    text = _text(value, name, max_len=128)
    if not ID_RE.fullmatch(text):
        raise WorkspaceError(f"{name} must be an opaque identifier")
    return text


def _hex64(value: Any, name: str) -> str:
    text = _text(value, name, max_len=64)
    if not HEX64_RE.fullmatch(text):
        raise WorkspaceError(f"{name} must be lowercase SHA-256 hex")
    return text


def _money(value: Any, name: str) -> int:
    if type(value) is not int:
        raise WorkspaceError(f"{name} must be integer cents")
    if not 0 <= value <= MAX_CENTS:
        raise WorkspaceError(f"{name} outside supported bounds")
    return value


def _quantity(value: Any, name: str) -> int:
    if type(value) is not int or not 1 <= value <= 1000:
        raise WorkspaceError(f"{name} must be an integer in 1..1000")
    return value


def _currency(value: Any) -> str:
    text = _text(value, "currency", max_len=3)
    if not CURRENCY_RE.fullmatch(text):
        raise WorkspaceError("currency must be exactly three uppercase ASCII letters")
    return text


def _utc(value: Any, name: str) -> str:
    text = _text(value, name, max_len=20)
    if not UTC_RE.fullmatch(text):
        raise WorkspaceError(f"{name} must be canonical UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise WorkspaceError(f"{name} is not a valid UTC instant") from exc
    return text


def _token_digest(value: Any) -> str:
    token = _text(value, "customer_token", max_len=256)
    if len(token.encode("utf-8")) < 32:
        raise WorkspaceError("customer_token must be at least 32 bytes")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _request_key(value: Any) -> str:
    return _opaque_id(value, "request_key")


def _items(value: Any, name: str = "items") -> list[LineItem]:
    if type(value) is not list or not value:
        raise WorkspaceError(f"{name} must be a nonempty array")
    if len(value) > 200:
        raise WorkspaceError(f"{name} exceeds 200 line items")
    out: list[LineItem] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        obj = _plain_dict(raw, f"{name}[{index}]")
        required = {"item_id", "description", "quantity", "unit_cents"}
        if set(obj) != required:
            raise WorkspaceError(f"{name}[{index}] must have exactly {sorted(required)}")
        item_id = _opaque_id(obj["item_id"], f"{name}[{index}].item_id")
        if item_id in seen:
            raise WorkspaceError(f"duplicate item_id: {item_id}")
        seen.add(item_id)
        description = _text(obj["description"], f"{name}[{index}].description", max_len=240)
        quantity = _quantity(obj["quantity"], f"{name}[{index}].quantity")
        unit_cents = _money(obj["unit_cents"], f"{name}[{index}].unit_cents")
        item = LineItem(item_id, description, quantity, unit_cents)
        _ = item.total_cents
        out.append(item)
    if sum(item.total_cents for item in out) > MAX_CENTS:
        raise WorkspaceError("quote/change total exceeds supported bound")
    return out


class FieldServiceWorkspace:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS quotes (
                    quote_id TEXT PRIMARY KEY,
                    currency TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('DRAFT','OPEN','APPROVED','DECLINED')),
                    token_digest TEXT NOT NULL,
                    quote_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT,
                    decided_at TEXT,
                    base_total_cents INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quote_items (
                    quote_id TEXT NOT NULL REFERENCES quotes(quote_id) ON DELETE CASCADE,
                    item_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_cents INTEGER NOT NULL,
                    ordinal INTEGER NOT NULL,
                    PRIMARY KEY (quote_id, item_id)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    quote_id TEXT NOT NULL UNIQUE REFERENCES quotes(quote_id),
                    state TEXT NOT NULL CHECK(state IN ('OPEN','COMPLETED')),
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS schedules (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
                    resource_id TEXT NOT NULL,
                    start_at TEXT NOT NULL,
                    end_at TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_schedules_resource ON schedules(resource_id, start_at, end_at);
                CREATE TABLE IF NOT EXISTS change_orders (
                    change_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                    state TEXT NOT NULL CHECK(state IN ('PENDING','APPROVED','DECLINED')),
                    proposed_at TEXT NOT NULL,
                    decided_at TEXT,
                    total_cents INTEGER NOT NULL,
                    change_digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS change_items (
                    change_id TEXT NOT NULL REFERENCES change_orders(change_id) ON DELETE CASCADE,
                    item_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_cents INTEGER NOT NULL,
                    ordinal INTEGER NOT NULL,
                    PRIMARY KEY(change_id, item_id)
                );
                CREATE TABLE IF NOT EXISTS scope_items (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                    scope_key TEXT NOT NULL,
                    source_type TEXT NOT NULL CHECK(source_type IN ('BASE','CHANGE')),
                    source_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_cents INTEGER NOT NULL,
                    completed_at TEXT,
                    PRIMARY KEY(job_id, scope_key)
                );
                CREATE TABLE IF NOT EXISTS request_receipts (
                    request_key TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_kind TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    event_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    event_digest TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def _audit(self, conn: sqlite3.Connection, kind: str, entity_id: str, at: str, payload: Mapping[str, Any]) -> None:
        event = {
            "event_kind": kind,
            "entity_id": entity_id,
            "event_at": at,
            "payload": dict(payload),
        }
        conn.execute(
            "INSERT INTO audit_events(event_kind,entity_id,event_at,payload_json,event_digest) VALUES(?,?,?,?,?)",
            (kind, entity_id, at, _canonical(dict(payload)), _digest(event)),
        )

    def _mutate(
        self,
        *,
        request_key: str,
        operation: str,
        payload: Mapping[str, Any],
        effect: Callable[[sqlite3.Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        request_key = _request_key(request_key)
        payload_digest = _digest(dict(payload))
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute(
                "SELECT operation,payload_digest,result_json FROM request_receipts WHERE request_key=?",
                (request_key,),
            ).fetchone()
            if prior is not None:
                if prior["operation"] != operation or prior["payload_digest"] != payload_digest:
                    conn.rollback()
                    raise Conflict("request_key was already used with different content")
                result = json.loads(prior["result_json"])
                conn.rollback()
                return result
            result = effect(conn)
            conn.execute(
                "INSERT INTO request_receipts(request_key,operation,payload_digest,result_json) VALUES(?,?,?,?)",
                (request_key, operation, payload_digest, _canonical(result)),
            )
            conn.commit()
            return result

    def create_quote(
        self,
        *,
        quote_id: str,
        currency: str,
        customer_token: str,
        items: list[dict[str, Any]],
        created_at: str,
        request_key: str,
    ) -> dict[str, Any]:
        quote_id = _opaque_id(quote_id, "quote_id")
        currency = _currency(currency)
        token_digest = _token_digest(customer_token)
        created_at = _utc(created_at, "created_at")
        parsed = _items(items)
        normalized_items = [item.as_dict() for item in parsed]
        total = sum(item.total_cents for item in parsed)
        quote_digest = _digest({"schema": "hive-field-service-quote/v1", "quote_id": quote_id, "currency": currency, "items": normalized_items})
        payload = {
            "quote_id": quote_id,
            "currency": currency,
            "customer_token_digest": token_digest,
            "quote_digest": quote_digest,
            "items": normalized_items,
            "created_at": created_at,
        }

        def effect(conn: sqlite3.Connection) -> dict[str, Any]:
            if conn.execute("SELECT 1 FROM quotes WHERE quote_id=?", (quote_id,)).fetchone():
                raise Conflict("quote_id already exists")
            conn.execute(
                "INSERT INTO quotes(quote_id,currency,state,token_digest,quote_digest,created_at,base_total_cents) VALUES(?,?,'DRAFT',?,?,?,?)",
                (quote_id, currency, token_digest, quote_digest, created_at, total),
            )
            for ordinal, item in enumerate(parsed):
                conn.execute(
                    "INSERT INTO quote_items(quote_id,item_id,description,quantity,unit_cents,ordinal) VALUES(?,?,?,?,?,?)",
                    (quote_id, item.item_id, item.description, item.quantity, item.unit_cents, ordinal),
                )
            self._audit(conn, "QUOTE_CREATED", quote_id, created_at, {"currency": currency, "total_cents": total, "item_count": len(parsed)})
            return {"quote_id": quote_id, "state": "DRAFT", "currency": currency, "total_cents": total, "quote_digest": quote_digest}

        return self._mutate(request_key=request_key, operation="CREATE_QUOTE", payload=payload, effect=effect)

    def publish_quote(self, *, quote_id: str, published_at: str, request_key: str) -> dict[str, Any]:
        quote_id = _opaque_id(quote_id, "quote_id")
        published_at = _utc(published_at, "published_at")
        payload = {"quote_id": quote_id, "published_at": published_at}

        def effect(conn: sqlite3.Connection) -> dict[str, Any]:
            row = conn.execute("SELECT * FROM quotes WHERE quote_id=?", (quote_id,)).fetchone()
            if row is None:
                raise NotFound("quote not found")
            if row["state"] == "OPEN":
                return {"quote_id": quote_id, "state": "OPEN", "currency": row["currency"], "total_cents": row["base_total_cents"], "quote_digest": row["quote_digest"]}
            if row["state"] != "DRAFT":
                raise InvalidState("only a draft quote can be published")
            if published_at < row["created_at"]:
                raise WorkspaceError("published_at cannot predate created_at")
            conn.execute("UPDATE quotes SET state='OPEN',published_at=? WHERE quote_id=?", (published_at, quote_id))
            self._audit(conn, "QUOTE_PUBLISHED", quote_id, published_at, {"total_cents": row["base_total_cents"]})
            return {"quote_id": quote_id, "state": "OPEN", "currency": row["currency"], "total_cents": row["base_total_cents"], "quote_digest": row["quote_digest"]}

        return self._mutate(request_key=request_key, operation="PUBLISH_QUOTE", payload=payload, effect=effect)

    def _authorized_quote(self, conn: sqlite3.Connection, quote_id: str, customer_token: str) -> sqlite3.Row:
        token_digest = _token_digest(customer_token)
        row = conn.execute("SELECT * FROM quotes WHERE quote_id=?", (quote_id,)).fetchone()
        if row is None or not hmac.compare_digest(row["token_digest"], token_digest):
            # Same public error whether the ID or the capability was wrong: no existence oracle.
            raise NotFound("quote not found")
        return row

    def customer_quote(self, *, quote_id: str, customer_token: str) -> dict[str, Any]:
        quote_id = _opaque_id(quote_id, "quote_id")
        with self._conn() as conn:
            row = self._authorized_quote(conn, quote_id, customer_token)
            items = [dict(r) for r in conn.execute(
                "SELECT item_id,description,quantity,unit_cents,(quantity*unit_cents) AS total_cents FROM quote_items WHERE quote_id=? ORDER BY ordinal",
                (quote_id,),
            )]
            job = conn.execute("SELECT job_id,state FROM jobs WHERE quote_id=?", (quote_id,)).fetchone()
            changes: list[dict[str, Any]] = []
            if job is not None:
                for change_row in conn.execute(
                    "SELECT change_id,state,total_cents,change_digest,proposed_at,decided_at FROM change_orders WHERE job_id=? ORDER BY proposed_at,change_id",
                    (job["job_id"],),
                ):
                    change = dict(change_row)
                    change["items"] = [dict(item) for item in conn.execute(
                        "SELECT item_id,description,quantity,unit_cents,(quantity*unit_cents) AS total_cents FROM change_items WHERE change_id=? ORDER BY ordinal",
                        (change["change_id"],),
                    )]
                    changes.append(change)
            return {
                "quote_id": quote_id,
                "state": row["state"],
                "currency": row["currency"],
                "total_cents": row["base_total_cents"],
                "quote_digest": row["quote_digest"],
                "items": items,
                "job": dict(job) if job is not None else None,
                "changes": changes,
                "customer_contact_authorized": False,
                "payment_authorized": False,
            }

    def customer_decide_quote(
        self,
        *,
        quote_id: str,
        customer_token: str,
        expected_quote_digest: str,
        decision: str,
        decided_at: str,
        request_key: str,
    ) -> dict[str, Any]:
        quote_id = _opaque_id(quote_id, "quote_id")
        token_digest = _token_digest(customer_token)
        expected_quote_digest = _hex64(expected_quote_digest, "expected_quote_digest")
        decision = _text(decision, "decision", max_len=16).upper()
        if decision not in {"APPROVE", "DECLINE"}:
            raise WorkspaceError("decision must be APPROVE or DECLINE")
        decided_at = _utc(decided_at, "decided_at")
        payload = {"quote_id": quote_id, "customer_token_digest": token_digest, "expected_quote_digest": expected_quote_digest, "decision": decision, "decided_at": decided_at}

        def effect(conn: sqlite3.Connection) -> dict[str, Any]:
            row = self._authorized_quote(conn, quote_id, customer_token)
            if not hmac.compare_digest(row["quote_digest"], expected_quote_digest):
                raise Conflict("quote fingerprint does not match the customer-viewed scope")
            target_state = "APPROVED" if decision == "APPROVE" else "DECLINED"
            if row["state"] == target_state:
                job = conn.execute("SELECT job_id FROM jobs WHERE quote_id=?", (quote_id,)).fetchone()
                return {"quote_id": quote_id, "state": target_state, "job_id": job["job_id"] if job else None}
            if row["state"] != "OPEN":
                raise Conflict("quote already has a different terminal decision")
            if row["published_at"] is None or decided_at < row["published_at"]:
                raise WorkspaceError("decided_at cannot predate publication")
            conn.execute("UPDATE quotes SET state=?,decided_at=? WHERE quote_id=?", (target_state, decided_at, quote_id))
            job_id: str | None = None
            if decision == "APPROVE":
                job_id = "job-" + hashlib.sha256(quote_id.encode("utf-8")).hexdigest()[:20]
                conn.execute(
                    "INSERT INTO jobs(job_id,quote_id,state,created_at) VALUES(?,?, 'OPEN', ?)",
                    (job_id, quote_id, decided_at),
                )
                for item in conn.execute(
                    "SELECT item_id,description,quantity,unit_cents FROM quote_items WHERE quote_id=? ORDER BY ordinal",
                    (quote_id,),
                ):
                    scope_key = f"base:{item['item_id']}"
                    conn.execute(
                        "INSERT INTO scope_items(job_id,scope_key,source_type,source_id,item_id,description,quantity,unit_cents) VALUES(?,?,'BASE',?,?,?,?,?)",
                        (job_id, scope_key, quote_id, item["item_id"], item["description"], item["quantity"], item["unit_cents"]),
                    )
                self._audit(conn, "JOB_CREATED", job_id, decided_at, {"quote_id": quote_id})
            self._audit(conn, f"QUOTE_{target_state}", quote_id, decided_at, {"job_id": job_id, "quote_digest": row["quote_digest"]})
            return {"quote_id": quote_id, "state": target_state, "job_id": job_id}

        return self._mutate(request_key=request_key, operation="CUSTOMER_DECIDE_QUOTE", payload=payload, effect=effect)

    def schedule_job(
        self,
        *,
        job_id: str,
        resource_id: str,
        start_at: str,
        end_at: str,
        scheduled_at: str,
        request_key: str,
    ) -> dict[str, Any]:
        job_id = _opaque_id(job_id, "job_id")
        resource_id = _opaque_id(resource_id, "resource_id")
        start_at = _utc(start_at, "start_at")
        end_at = _utc(end_at, "end_at")
        scheduled_at = _utc(scheduled_at, "scheduled_at")
        if not start_at < end_at:
            raise WorkspaceError("schedule must be a nonempty half-open interval")
        if scheduled_at > start_at:
            raise WorkspaceError("scheduled_at cannot be after the scheduled start")
        payload = {"job_id": job_id, "resource_id": resource_id, "start_at": start_at, "end_at": end_at, "scheduled_at": scheduled_at}

        def effect(conn: sqlite3.Connection) -> dict[str, Any]:
            job = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None:
                raise NotFound("job not found")
            if job["state"] != "OPEN":
                raise InvalidState("completed job cannot be scheduled")
            if scheduled_at < job["created_at"]:
                raise WorkspaceError("scheduled_at cannot predate job approval")
            if start_at < job["created_at"]:
                raise WorkspaceError("scheduled start cannot predate job approval")
            existing = conn.execute("SELECT * FROM schedules WHERE job_id=?", (job_id,)).fetchone()
            if existing is not None:
                same = all(existing[k] == payload[k] for k in ("resource_id", "start_at", "end_at", "scheduled_at"))
                if same:
                    return dict(payload)
                raise Conflict("job is already scheduled differently")
            overlap = conn.execute(
                "SELECT job_id FROM schedules WHERE resource_id=? AND start_at < ? AND end_at > ? LIMIT 1",
                (resource_id, end_at, start_at),
            ).fetchone()
            if overlap is not None:
                raise Conflict("resource schedule overlaps another job")
            conn.execute(
                "INSERT INTO schedules(job_id,resource_id,start_at,end_at,scheduled_at) VALUES(?,?,?,?,?)",
                (job_id, resource_id, start_at, end_at, scheduled_at),
            )
            self._audit(conn, "JOB_SCHEDULED", job_id, scheduled_at, {"resource_id": resource_id, "start_at": start_at, "end_at": end_at})
            return dict(payload)

        return self._mutate(request_key=request_key, operation="SCHEDULE_JOB", payload=payload, effect=effect)

    def propose_change(
        self,
        *,
        job_id: str,
        change_id: str,
        items: list[dict[str, Any]],
        proposed_at: str,
        request_key: str,
    ) -> dict[str, Any]:
        job_id = _opaque_id(job_id, "job_id")
        change_id = _opaque_id(change_id, "change_id")
        parsed = _items(items, "change_items")
        normalized_items = [item.as_dict() for item in parsed]
        total = sum(i.total_cents for i in parsed)
        change_digest = _digest({"schema": "hive-field-service-change/v1", "job_id": job_id, "change_id": change_id, "items": normalized_items})
        proposed_at = _utc(proposed_at, "proposed_at")
        payload = {"job_id": job_id, "change_id": change_id, "change_digest": change_digest, "items": normalized_items, "proposed_at": proposed_at}

        def effect(conn: sqlite3.Connection) -> dict[str, Any]:
            job = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None:
                raise NotFound("job not found")
            if job["state"] != "OPEN":
                raise InvalidState("completed job cannot receive a change order")
            if proposed_at < job["created_at"]:
                raise WorkspaceError("proposed_at cannot predate job approval")
            if conn.execute("SELECT 1 FROM change_orders WHERE change_id=?", (change_id,)).fetchone():
                raise Conflict("change_id already exists")
            conn.execute(
                "INSERT INTO change_orders(change_id,job_id,state,proposed_at,total_cents,change_digest) VALUES(?,?,'PENDING',?,?,?)",
                (change_id, job_id, proposed_at, total, change_digest),
            )
            for ordinal, item in enumerate(parsed):
                conn.execute(
                    "INSERT INTO change_items(change_id,item_id,description,quantity,unit_cents,ordinal) VALUES(?,?,?,?,?,?)",
                    (change_id, item.item_id, item.description, item.quantity, item.unit_cents, ordinal),
                )
            self._audit(conn, "CHANGE_PROPOSED", change_id, proposed_at, {"job_id": job_id, "total_cents": total, "item_count": len(parsed)})
            return {"job_id": job_id, "change_id": change_id, "state": "PENDING", "total_cents": total, "change_digest": change_digest}

        return self._mutate(request_key=request_key, operation="PROPOSE_CHANGE", payload=payload, effect=effect)

    def customer_decide_change(
        self,
        *,
        job_id: str,
        change_id: str,
        customer_token: str,
        expected_change_digest: str,
        decision: str,
        decided_at: str,
        request_key: str,
    ) -> dict[str, Any]:
        job_id = _opaque_id(job_id, "job_id")
        change_id = _opaque_id(change_id, "change_id")
        token_digest = _token_digest(customer_token)
        expected_change_digest = _hex64(expected_change_digest, "expected_change_digest")
        decision = _text(decision, "decision", max_len=16).upper()
        if decision not in {"APPROVE", "DECLINE"}:
            raise WorkspaceError("decision must be APPROVE or DECLINE")
        decided_at = _utc(decided_at, "decided_at")
        payload = {"job_id": job_id, "change_id": change_id, "customer_token_digest": token_digest, "expected_change_digest": expected_change_digest, "decision": decision, "decided_at": decided_at}

        def effect(conn: sqlite3.Connection) -> dict[str, Any]:
            row = conn.execute(
                "SELECT c.*,q.quote_id,q.token_digest FROM change_orders c JOIN jobs j ON j.job_id=c.job_id JOIN quotes q ON q.quote_id=j.quote_id WHERE c.change_id=? AND c.job_id=?",
                (change_id, job_id),
            ).fetchone()
            if row is None or not hmac.compare_digest(row["token_digest"], token_digest):
                raise NotFound("change order not found")
            if not hmac.compare_digest(row["change_digest"], expected_change_digest):
                raise Conflict("change fingerprint does not match the customer-viewed scope")
            target = "APPROVED" if decision == "APPROVE" else "DECLINED"
            if row["state"] == target:
                return {"job_id": job_id, "change_id": change_id, "state": target, "total_cents": row["total_cents"], "change_digest": row["change_digest"]}
            if row["state"] != "PENDING":
                raise Conflict("change order already has a different terminal decision")
            if decided_at < row["proposed_at"]:
                raise WorkspaceError("decided_at cannot predate proposed_at")
            conn.execute("UPDATE change_orders SET state=?,decided_at=? WHERE change_id=?", (target, decided_at, change_id))
            if target == "APPROVED":
                for item in conn.execute(
                    "SELECT item_id,description,quantity,unit_cents FROM change_items WHERE change_id=? ORDER BY ordinal",
                    (change_id,),
                ):
                    scope_key = f"change:{change_id}:{item['item_id']}"
                    conn.execute(
                        "INSERT INTO scope_items(job_id,scope_key,source_type,source_id,item_id,description,quantity,unit_cents) VALUES(?,?,'CHANGE',?,?,?,?,?)",
                        (job_id, scope_key, change_id, item["item_id"], item["description"], item["quantity"], item["unit_cents"]),
                    )
            self._audit(conn, f"CHANGE_{target}", change_id, decided_at, {"job_id": job_id, "total_cents": row["total_cents"], "change_digest": row["change_digest"]})
            return {"job_id": job_id, "change_id": change_id, "state": target, "total_cents": row["total_cents"], "change_digest": row["change_digest"]}

        return self._mutate(request_key=request_key, operation="CUSTOMER_DECIDE_CHANGE", payload=payload, effect=effect)

    def complete_scope_item(self, *, job_id: str, scope_key: str, completed_at: str, request_key: str) -> dict[str, Any]:
        job_id = _opaque_id(job_id, "job_id")
        scope_key = _text(scope_key, "scope_key", max_len=300)
        completed_at = _utc(completed_at, "completed_at")
        payload = {"job_id": job_id, "scope_key": scope_key, "completed_at": completed_at}

        def effect(conn: sqlite3.Connection) -> dict[str, Any]:
            job = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None:
                raise NotFound("job not found")
            if job["state"] != "OPEN":
                raise InvalidState("job is already completed")
            schedule = conn.execute("SELECT * FROM schedules WHERE job_id=?", (job_id,)).fetchone()
            if schedule is None:
                raise InvalidState("job must be scheduled before scope can be completed")
            item = conn.execute("SELECT * FROM scope_items WHERE job_id=? AND scope_key=?", (job_id, scope_key)).fetchone()
            if item is None:
                raise NotFound("scope item not found")
            if item["completed_at"] is not None:
                return {"job_id": job_id, "scope_key": scope_key, "completed_at": item["completed_at"]}
            effective_at = job["created_at"]
            if item["source_type"] == "CHANGE":
                change = conn.execute("SELECT state,decided_at FROM change_orders WHERE change_id=?", (item["source_id"],)).fetchone()
                if change is None or change["state"] != "APPROVED" or change["decided_at"] is None:
                    raise InvalidState("change scope is not customer-approved")
                effective_at = change["decided_at"]
            earliest = max(schedule["start_at"], effective_at)
            if completed_at < earliest:
                raise WorkspaceError("completed_at cannot predate scheduled/effective approved scope")
            conn.execute("UPDATE scope_items SET completed_at=? WHERE job_id=? AND scope_key=?", (completed_at, job_id, scope_key))
            self._audit(conn, "SCOPE_COMPLETED", job_id, completed_at, {"scope_key": scope_key})
            return dict(payload)

        return self._mutate(request_key=request_key, operation="COMPLETE_SCOPE_ITEM", payload=payload, effect=effect)

    def complete_job(self, *, job_id: str, completed_at: str, request_key: str) -> dict[str, Any]:
        job_id = _opaque_id(job_id, "job_id")
        completed_at = _utc(completed_at, "completed_at")
        payload = {"job_id": job_id, "completed_at": completed_at}

        def effect(conn: sqlite3.Connection) -> dict[str, Any]:
            job = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None:
                raise NotFound("job not found")
            if job["state"] == "COMPLETED":
                return {"job_id": job_id, "state": "COMPLETED", "completed_at": job["completed_at"]}
            schedule = conn.execute("SELECT * FROM schedules WHERE job_id=?", (job_id,)).fetchone()
            if schedule is None:
                raise InvalidState("job is not scheduled")
            if completed_at < schedule["start_at"]:
                raise WorkspaceError("completed_at cannot predate scheduled start")
            pending = conn.execute("SELECT change_id FROM change_orders WHERE job_id=? AND state='PENDING' LIMIT 1", (job_id,)).fetchone()
            if pending is not None:
                raise InvalidState("job has a pending customer change decision")
            incomplete = conn.execute("SELECT scope_key FROM scope_items WHERE job_id=? AND completed_at IS NULL LIMIT 1", (job_id,)).fetchone()
            if incomplete is not None:
                raise InvalidState("job has incomplete approved scope")
            latest_scope = conn.execute("SELECT MAX(completed_at) FROM scope_items WHERE job_id=?", (job_id,)).fetchone()[0]
            if latest_scope is not None and completed_at < latest_scope:
                raise WorkspaceError("job completed_at cannot predate completed approved scope")
            conn.execute("UPDATE jobs SET state='COMPLETED',completed_at=? WHERE job_id=?", (completed_at, job_id))
            self._audit(conn, "JOB_COMPLETED", job_id, completed_at, {})
            return {"job_id": job_id, "state": "COMPLETED", "completed_at": completed_at}

        return self._mutate(request_key=request_key, operation="COMPLETE_JOB", payload=payload, effect=effect)

    def invoice_draft(self, *, job_id: str) -> dict[str, Any]:
        job_id = _opaque_id(job_id, "job_id")
        with self._conn() as conn:
            job = conn.execute(
                "SELECT j.*,q.currency,q.quote_id,q.base_total_cents FROM jobs j JOIN quotes q ON q.quote_id=j.quote_id WHERE j.job_id=?",
                (job_id,),
            ).fetchone()
            if job is None:
                raise NotFound("job not found")
            if job["state"] != "COMPLETED":
                raise InvalidState("invoice draft requires a completed job")
            lines = [dict(r) for r in conn.execute(
                "SELECT source_type,source_id,item_id,description,quantity,unit_cents,(quantity*unit_cents) AS total_cents FROM scope_items WHERE job_id=? ORDER BY source_type,source_id,item_id",
                (job_id,),
            )]
            total = sum(int(line["total_cents"]) for line in lines)
            draft = {
                "schema": "hive-field-service-invoice-draft/v1",
                "job_id": job_id,
                "quote_id": job["quote_id"],
                "currency": job["currency"],
                "line_items": lines,
                "total_cents": total,
                "draft_only": True,
                "send_authorized": False,
                "payment_authorized": False,
                "accounting_post_authorized": False,
                "recognized_revenue": False,
            }
            return {**draft, "draft_digest": _digest(draft)}

    def job_export(self, *, job_id: str) -> dict[str, Any]:
        job_id = _opaque_id(job_id, "job_id")
        with self._conn() as conn:
            job = conn.execute(
                "SELECT j.*,q.currency,q.quote_id,q.state AS quote_state,q.base_total_cents FROM jobs j JOIN quotes q ON q.quote_id=j.quote_id WHERE j.job_id=?",
                (job_id,),
            ).fetchone()
            if job is None:
                raise NotFound("job not found")
            schedule = conn.execute("SELECT resource_id,start_at,end_at,scheduled_at FROM schedules WHERE job_id=?", (job_id,)).fetchone()
            changes = [dict(r) for r in conn.execute(
                "SELECT change_id,state,total_cents,change_digest,proposed_at,decided_at FROM change_orders WHERE job_id=? ORDER BY proposed_at,change_id",
                (job_id,),
            )]
            scope = [dict(r) for r in conn.execute(
                "SELECT scope_key,source_type,source_id,item_id,description,quantity,unit_cents,completed_at FROM scope_items WHERE job_id=? ORDER BY scope_key",
                (job_id,),
            )]
            entity_ids = [job_id, job["quote_id"], *[c["change_id"] for c in changes]]
            placeholders = ",".join("?" for _ in entity_ids)
            audit = [dict(r) for r in conn.execute(
                f"SELECT event_kind,entity_id,event_at,payload_json,event_digest FROM audit_events WHERE entity_id IN ({placeholders}) ORDER BY seq",
                entity_ids,
            )]
            for event in audit:
                event["payload"] = json.loads(event.pop("payload_json"))
            body = {
                "schema": "hive-field-service-job-export/v1",
                "job": dict(job),
                "schedule": dict(schedule) if schedule else None,
                "changes": changes,
                "scope": scope,
                "audit": audit,
                "external_send_authorized": False,
                "payment_authorized": False,
            }
            return {**body, "export_digest": _digest(body)}

    def operator_summary(self) -> dict[str, Any]:
        with self._conn() as conn:
            counts = {
                "draft_quotes": conn.execute("SELECT COUNT(*) FROM quotes WHERE state='DRAFT'").fetchone()[0],
                "open_quotes": conn.execute("SELECT COUNT(*) FROM quotes WHERE state='OPEN'").fetchone()[0],
                "open_jobs": conn.execute("SELECT COUNT(*) FROM jobs WHERE state='OPEN'").fetchone()[0],
                "completed_jobs": conn.execute("SELECT COUNT(*) FROM jobs WHERE state='COMPLETED'").fetchone()[0],
                "pending_changes": conn.execute("SELECT COUNT(*) FROM change_orders WHERE state='PENDING'").fetchone()[0],
            }
            return {"schema": "hive-field-service-operator-summary/v1", **counts}


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(WorkspaceError(f"non-finite JSON: {token}")))


def _print(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local-first field-service quote-to-job workspace")
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-quote")
    create.add_argument("--input", required=True, help="JSON with quote_id,currency,customer_token,items,created_at,request_key")
    publish = sub.add_parser("publish-quote")
    publish.add_argument("quote_id"); publish.add_argument("published_at"); publish.add_argument("request_key")
    view = sub.add_parser("customer-view")
    view.add_argument("quote_id"); view.add_argument("customer_token")
    decide = sub.add_parser("customer-decide")
    decide.add_argument("quote_id"); decide.add_argument("customer_token"); decide.add_argument("expected_quote_digest"); decide.add_argument("decision"); decide.add_argument("decided_at"); decide.add_argument("request_key")
    schedule = sub.add_parser("schedule")
    schedule.add_argument("job_id"); schedule.add_argument("resource_id"); schedule.add_argument("start_at"); schedule.add_argument("end_at"); schedule.add_argument("scheduled_at"); schedule.add_argument("request_key")
    change = sub.add_parser("propose-change")
    change.add_argument("--input", required=True)
    change_decide = sub.add_parser("change-decide")
    change_decide.add_argument("job_id"); change_decide.add_argument("change_id"); change_decide.add_argument("customer_token"); change_decide.add_argument("expected_change_digest"); change_decide.add_argument("decision"); change_decide.add_argument("decided_at"); change_decide.add_argument("request_key")
    scope = sub.add_parser("complete-scope")
    scope.add_argument("job_id"); scope.add_argument("scope_key"); scope.add_argument("completed_at"); scope.add_argument("request_key")
    complete = sub.add_parser("complete-job")
    complete.add_argument("job_id"); complete.add_argument("completed_at"); complete.add_argument("request_key")
    invoice = sub.add_parser("invoice-draft"); invoice.add_argument("job_id")
    export = sub.add_parser("export-job"); export.add_argument("job_id")
    sub.add_parser("summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ws = FieldServiceWorkspace(args.db)
    try:
        if args.command == "create-quote":
            _print(ws.create_quote(**_load_json(args.input)))
        elif args.command == "publish-quote":
            _print(ws.publish_quote(quote_id=args.quote_id, published_at=args.published_at, request_key=args.request_key))
        elif args.command == "customer-view":
            _print(ws.customer_quote(quote_id=args.quote_id, customer_token=args.customer_token))
        elif args.command == "customer-decide":
            _print(ws.customer_decide_quote(quote_id=args.quote_id, customer_token=args.customer_token, expected_quote_digest=args.expected_quote_digest, decision=args.decision, decided_at=args.decided_at, request_key=args.request_key))
        elif args.command == "schedule":
            _print(ws.schedule_job(job_id=args.job_id, resource_id=args.resource_id, start_at=args.start_at, end_at=args.end_at, scheduled_at=args.scheduled_at, request_key=args.request_key))
        elif args.command == "propose-change":
            _print(ws.propose_change(**_load_json(args.input)))
        elif args.command == "change-decide":
            _print(ws.customer_decide_change(job_id=args.job_id, change_id=args.change_id, customer_token=args.customer_token, expected_change_digest=args.expected_change_digest, decision=args.decision, decided_at=args.decided_at, request_key=args.request_key))
        elif args.command == "complete-scope":
            _print(ws.complete_scope_item(job_id=args.job_id, scope_key=args.scope_key, completed_at=args.completed_at, request_key=args.request_key))
        elif args.command == "complete-job":
            _print(ws.complete_job(job_id=args.job_id, completed_at=args.completed_at, request_key=args.request_key))
        elif args.command == "invoice-draft":
            _print(ws.invoice_draft(job_id=args.job_id))
        elif args.command == "export-job":
            _print(ws.job_export(job_id=args.job_id))
        elif args.command == "summary":
            _print(ws.operator_summary())
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except WorkspaceError as exc:
        _print({"ok": False, "error": exc.__class__.__name__, "message": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
