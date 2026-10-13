#!/usr/bin/env python3
"""Private, offline payment-event ledger and dispute evidence packets.

The input adapter verifies Stripe webhook provenance. It stores a deliberately
small provider-neutral record, never the webhook body or customer/card fields.
This is an operator tool: it does not call providers or change Commons access.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "payment-defense/v1"
MAX_BODY = 8 * 1024 * 1024
MAX_EVIDENCE_FILE = 64 * 1024 * 1024
REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]{3,180}$")
TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,5}$")
CASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,79}$")
LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
CURRENCY_RE = re.compile(r"^[a-z]{3}$")
FINANCIAL_OPEN = {"needs_response", "under_review"}
INQUIRY_OPEN = {"warning_needs_response", "warning_under_review"}
CLOSED = {"won", "lost", "warning_closed", "prevented"}
RESPONSE_REQUIRED = {"needs_response", "warning_needs_response"}
SUPPORTED_TYPES = {
    "charge.succeeded", "charge.updated", "charge.captured", "charge.refunded",
    "charge.dispute.created", "charge.dispute.updated", "charge.dispute.closed",
    "charge.dispute.funds_withdrawn", "charge.dispute.funds_reinstated",
    "refund.created", "refund.updated", "refund.failed", "charge.refund.updated",
    "radar.early_fraud_warning.created", "radar.early_fraud_warning.updated",
    "payment_intent.succeeded", "payment_intent.payment_failed",
    "checkout.session.completed", "checkout.session.async_payment_succeeded",
}


class DefenseError(ValueError):
    """An operator-readable failure without secret or payload contents."""


class EventConflict(DefenseError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def iso(value: int) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def unix(value: Any, field: str, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 253402300799:
        raise DefenseError(field + " must be a non-negative Unix timestamp")
    return value


def amount(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10**18:
        raise DefenseError(field + " must be a non-negative integer in currency minor units")
    return value


def ref(value: Any, field: str, *, prefix: str | None = None, optional: bool = True) -> str | None:
    if value is None and optional:
        return None
    if isinstance(value, dict):
        value = value.get("id")
    if not isinstance(value, str) or not REF_RE.fullmatch(value):
        raise DefenseError(field + " must be a provider object ID")
    if prefix and not value.startswith(prefix + "_"):
        raise DefenseError(field + " has the wrong object type")
    return value


def label(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not LABEL_RE.fullmatch(value):
        raise DefenseError(field + " must be a provider status/category, not free text")
    return value


def currency(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not CURRENCY_RE.fullmatch(value):
        raise DefenseError("currency must be a lowercase three-letter currency code")
    return value


def boolean(value: Any, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise DefenseError(field + " must be a boolean")
    return value


def timestamp_argument(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return int(parsed.timestamp())
    except (ValueError, OverflowError):
        raise DefenseError("report timestamps must be ISO-8601 with a timezone") from None


def private_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise DefenseError("private storage/output paths must be absolute")
    if path.is_symlink():
        raise DefenseError("private storage/output must not be a symlink")
    path = path.resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise DefenseError("private storage/output must be outside the repository")
    for parent in [path, *path.parents]:
        if (parent / ".git").exists():
            raise DefenseError("private storage/output must be outside every Git checkout")
    public_roots = [Path("/var/www"), Path("/srv/www")]
    public_roots.extend(Path(p).expanduser().resolve() for p in os.environ.get("CHARGEBACK_PUBLIC_ROOTS", "").split(os.pathsep) if p)
    if any(path == root or root in path.parents for root in public_roots):
        raise DefenseError("private storage/output must be outside public serving roots")
    if any(p.name in {"_site", "public", "wwwroot"} for p in [path, *path.parents]):
        raise DefenseError("private storage/output must not be in a public build directory")
    return path


def private_directory(path: Path, *, create: bool) -> None:
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not path.is_dir():
        raise DefenseError("private directory does not exist; initialize an off-repository store")
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise DefenseError("private directory must be owned by this operator and have mode 700")


def check_private_file(path: Path) -> None:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
        raise DefenseError("private files must be regular, owned by this operator, mode 600, and not hard-linked")


def private_read(value: str, *, limit: int) -> bytes:
    path = private_path(value)
    private_directory(path.parent, create=False)
    if not path.exists():
        raise DefenseError("private input file does not exist")
    check_private_file(path)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise DefenseError("private input exceeds the supported size")
    return data


def new_private_file(value: str | Path):
    path = private_path(value)
    private_directory(path.parent, create=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise DefenseError("output already exists; select a new private output path") from None
    return os.fdopen(fd, "wb")


def connect(value: str, *, initialize: bool = False) -> sqlite3.Connection:
    path = private_path(value)
    private_directory(path.parent, create=initialize)
    if not path.exists():
        if not initialize:
            raise DefenseError("ledger does not exist; run init before reporting or ingesting")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    check_private_file(path)
    db = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA temp_store=MEMORY")
    if initialize:
        db.execute("PRAGMA journal_mode=DELETE")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if tables and (version != 1 or tables != {"events"}):
            db.close()
            raise DefenseError("existing file is not a compatible payment-defense ledger")
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, provider TEXT NOT NULL,
                account_id TEXT NOT NULL, livemode INTEGER NOT NULL,
                event_type TEXT NOT NULL, created INTEGER NOT NULL,
                received_at INTEGER NOT NULL, received_ns INTEGER NOT NULL,
                signature_timestamp INTEGER NOT NULL, payload_sha256 TEXT NOT NULL,
                kind TEXT NOT NULL, object_id TEXT, charge_id TEXT,
                payment_intent_id TEXT, record_json TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS events_charge ON events(charge_id)")
            db.execute("CREATE INDEX IF NOT EXISTS events_created ON events(created)")
            db.execute("PRAGMA user_version=1")
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            db.close()
            raise
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if db.execute("PRAGMA user_version").fetchone()[0] != 1 or tables != {"events"}:
        db.close()
        raise DefenseError("ledger schema is missing or unsupported")
    return db


def verify(raw: bytes, header: str, secret: str, tolerance: int) -> int:
    # Standalone equivalent of stripe_event_bridge.verify_signature, because
    # importing that bridge would require unrelated commerce dependencies.
    if not raw or len(raw) > MAX_BODY:
        raise DefenseError("raw webhook body must be nonempty and at most 8 MiB")
    if not secret or len(secret) > 4096:
        raise DefenseError("webhook endpoint signing secret is unavailable or invalid")
    if not 1 <= tolerance <= 3600:
        raise DefenseError("signature tolerance must be between 1 and 3600 seconds")
    if not header or len(header) > 8192 or "\n" in header or "\r" in header:
        raise DefenseError("Stripe-Signature header is missing or malformed")
    timestamps, signatures = [], []
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep:
            raise DefenseError("Stripe-Signature header is malformed")
        if key == "t":
            timestamps.append(value)
        elif key == "v1":
            signatures.append(value)
    if len(timestamps) != 1 or not timestamps[0].isdigit() or not signatures:
        raise DefenseError("Stripe-Signature requires one timestamp and a v1 signature")
    if len(timestamps[0]) > 12 or any(not re.fullmatch(r"[0-9a-fA-F]{64}", item) for item in signatures):
        raise DefenseError("Stripe-Signature timestamp or v1 signature is malformed")
    stamp = int(timestamps[0])
    if abs(int(time.time()) - stamp) > tolerance:
        raise DefenseError("Stripe-Signature timestamp is outside tolerance; use a fresh provider delivery")
    expected = hmac.new(secret.encode(), str(stamp).encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, item.lower()) for item in signatures):
        raise DefenseError("Stripe webhook signature verification failed")
    return stamp


def duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DefenseError("webhook JSON contains duplicate object keys")
        result[key] = value
    return result


def reject_constant(_: str):
    raise DefenseError("webhook JSON contains a non-finite numeric constant")


def normalize(raw: bytes) -> dict[str, Any]:
    try:
        event = json.loads(raw.decode("utf-8"), object_pairs_hook=duplicate_keys, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise DefenseError("verified webhook body is not valid UTF-8 JSON") from None
    if not isinstance(event, dict):
        raise DefenseError("verified webhook event must be an object")
    eid = ref(event.get("id"), "event.id", prefix="evt", optional=False)
    etype = event.get("type")
    if not isinstance(etype, str) or not TYPE_RE.fullmatch(etype):
        raise DefenseError("event.type is invalid")
    live = boolean(event.get("livemode"), "event.livemode")
    if live is None:
        raise DefenseError("event.livemode is required")
    record: dict[str, Any] = {
        "event_id": eid, "provider": "stripe", "account_id": ref(event.get("account"), "event.account", prefix="acct") or "direct",
        "livemode": live, "event_type": etype, "created": unix(event.get("created"), "event.created"),
        "kind": "unsupported", "object_id": None, "charge_id": None, "payment_intent_id": None,
    }
    # Unknown signed event types remain a provenance-only audit entry. No raw
    # object, metadata, descriptions, reasons, or customer data are retained.
    if etype not in SUPPORTED_TYPES:
        return record
    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        raise DefenseError("supported event is missing data.object")
    record["object_created"] = unix(obj.get("created"), "object.created", optional=True)
    record["amount_minor"] = amount(obj.get("amount"), "object.amount")
    record["currency"] = currency(obj.get("currency"))
    if etype.startswith("charge.dispute."):
        record.update(kind="dispute", object_id=ref(obj.get("id"), "dispute.id", prefix="dp", optional=False),
                      charge_id=ref(obj.get("charge"), "dispute.charge", prefix="ch", optional=False),
                      payment_intent_id=ref(obj.get("payment_intent"), "dispute.payment_intent", prefix="pi"),
                      status=label(obj.get("status"), "dispute.status"), reason=label(obj.get("reason"), "dispute.reason"))
        if record["status"] is None or record["amount_minor"] is None or record["currency"] is None:
            raise DefenseError("dispute status, amount and currency are required")
        details = obj.get("evidence_details")
        if details is not None and not isinstance(details, dict):
            raise DefenseError("dispute.evidence_details must be an object")
        record["due_by"] = unix((details or {}).get("due_by"), "dispute.evidence_details.due_by", optional=True)
    elif etype.startswith("radar.early_fraud_warning."):
        record.update(kind="early_fraud_warning", object_id=ref(obj.get("id"), "early_fraud_warning.id", optional=False),
                      charge_id=ref(obj.get("charge"), "early_fraud_warning.charge", prefix="ch", optional=False),
                      payment_intent_id=ref(obj.get("payment_intent"), "early_fraud_warning.payment_intent", prefix="pi"),
                      actionable=boolean(obj.get("actionable"), "early_fraud_warning.actionable"),
                      fraud_type=label(obj.get("fraud_type"), "early_fraud_warning.fraud_type"))
    elif etype.startswith("refund.") or etype == "charge.refund.updated":
        record.update(kind="refund", object_id=ref(obj.get("id"), "refund.id", prefix="re", optional=False),
                      charge_id=ref(obj.get("charge"), "refund.charge", prefix="ch"),
                      payment_intent_id=ref(obj.get("payment_intent"), "refund.payment_intent", prefix="pi"),
                      status=label(obj.get("status"), "refund.status"))
    elif etype.startswith("charge."):
        record.update(kind="charge", object_id=ref(obj.get("id"), "charge.id", prefix="ch", optional=False),
                      payment_intent_id=ref(obj.get("payment_intent"), "charge.payment_intent", prefix="pi"),
                      paid=boolean(obj.get("paid"), "charge.paid"), captured=boolean(obj.get("captured"), "charge.captured"),
                      amount_captured_minor=amount(obj.get("amount_captured"), "charge.amount_captured"),
                      amount_refunded_minor=amount(obj.get("amount_refunded"), "charge.amount_refunded"))
        record["charge_id"] = record["object_id"]
        if record["amount_captured_minor"] is None and record["captured"] is True:
            record["amount_captured_minor"] = record["amount_minor"]
    elif etype.startswith("payment_intent."):
        record.update(kind="payment_intent", object_id=ref(obj.get("id"), "payment_intent.id", prefix="pi", optional=False),
                      charge_id=ref(obj.get("latest_charge"), "payment_intent.latest_charge", prefix="ch"),
                      status=label(obj.get("status"), "payment_intent.status"),
                      amount_received_minor=amount(obj.get("amount_received"), "payment_intent.amount_received"))
        record["payment_intent_id"] = record["object_id"]
    else:
        record.update(kind="checkout", object_id=ref(obj.get("id"), "checkout.id", prefix="cs", optional=False),
                      payment_intent_id=ref(obj.get("payment_intent"), "checkout.payment_intent", prefix="pi"),
                      payment_status=label(obj.get("payment_status"), "checkout.payment_status"),
                      amount_total_minor=amount(obj.get("amount_total"), "checkout.amount_total"))
    if record["kind"] in {"charge", "dispute", "refund", "early_fraud_warning"} and record["object_created"] is None:
        raise DefenseError("snapshot object.created is required for this payment/dispute record")
    if record["kind"] in {"charge", "refund"} and (record["amount_minor"] is None or record["currency"] is None):
        raise DefenseError("snapshot amount and currency are required")
    if record["kind"] == "charge" and (record["paid"] is None or record["captured"] is None):
        raise DefenseError("charge snapshot paid and captured flags are required")
    if record["kind"] == "refund" and (record["status"] is None or not (record["charge_id"] or record["payment_intent_id"])):
        raise DefenseError("refund snapshot status and a payment reference are required")
    return record


def ingest(args: argparse.Namespace) -> dict[str, Any]:
    secret = private_read(args.secret_file, limit=4096).decode("utf-8").strip() if args.secret_file else os.environ.get(args.secret_env, "")
    header = private_read(args.signature_file, limit=8192).decode("utf-8").strip() if args.signature_file else os.environ.get(args.signature_env, "")
    raw = sys.stdin.buffer.read(MAX_BODY + 1) if args.body == "-" else private_read(args.body, limit=MAX_BODY)
    stamp = verify(raw, header, secret, args.tolerance)
    item = normalize(raw)
    digest = hashlib.sha256(raw).hexdigest()
    received_ns = time.time_ns()
    db = connect(args.db)
    try:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT payload_sha256 FROM events WHERE event_id=?", (item["event_id"],)).fetchone()
        if old:
            if old[0] != digest:
                raise EventConflict("event-ID conflict: verified delivery has different payload bytes; original ledger row preserved")
            db.execute("ROLLBACK")
            return {"schema_version": SCHEMA, "status": "duplicate", "event_id": item["event_id"], "record_count_added": 0}
        db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            item["event_id"], item["provider"], item["account_id"], int(item["livemode"]), item["event_type"], item["created"],
            received_ns // 10**9, received_ns, stamp, digest, item["kind"], item["object_id"], item["charge_id"], item["payment_intent_id"], canonical(item),
        ))
        db.execute("COMMIT")
        return {"schema_version": SCHEMA, "status": "recorded", "event_id": item["event_id"], "record_kind": item["kind"], "record_count_added": 1,
                "operator_flags": ["UNSUPPORTED_EVENT_RECORDED_WITHOUT_OBJECT_DATA"] if item["kind"] == "unsupported" else []}
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()


def read_rows(args: argparse.Namespace, *, as_of: int | None = None) -> list[dict[str, Any]]:
    if as_of is None:
        as_of = timestamp_argument(args.as_of) if getattr(args, "as_of", None) else int(time.time())
    mode = getattr(args, "mode", "live")
    account = getattr(args, "account", None)
    if account and account != "direct":
        ref(account, "account", prefix="acct", optional=False)
    clauses, parameters = ["created <= ?", "received_at <= ?"], [as_of, as_of]
    if mode != "all":
        clauses.append("livemode = ?")
        parameters.append(int(mode == "live"))
    if account:
        clauses.append("account_id = ?")
        parameters.append(account)
    db = connect(args.db)
    try:
        result = []
        for row in db.execute("SELECT * FROM events WHERE " + " AND ".join(clauses) + " ORDER BY created,received_ns,event_id", parameters):
            try:
                item = json.loads(row["record_json"])
            except json.JSONDecodeError:
                raise DefenseError("ledger contains a malformed normalized record") from None
            if not isinstance(item, dict) or item.get("event_id") != row["event_id"]:
                raise DefenseError("ledger contains an inconsistent normalized record")
            item.update(received_at=row["received_at"], received_ns=row["received_ns"], signature_timestamp=row["signature_timestamp"], payload_sha256=row["payload_sha256"])
            result.append(item)
        return result
    finally:
        db.close()


def event_export(args: argparse.Namespace) -> dict[str, Any]:
    rows = read_rows(args)
    with new_private_file(args.output) as out:
        for row in rows:
            out.write((canonical(row) + "\n").encode())
        out.flush()
        os.fsync(out.fileno())
    return {"schema_version": SCHEMA, "status": "exported", "events": len(rows), "output": str(private_path(args.output)), "contains_raw_payloads": False}


def summarize_scope(rows: list[dict[str, Any]], since: int, as_of: int, deadline_hours: int) -> dict[str, Any]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    ambiguous: set[tuple[str, str]] = set()
    for row in rows:
        if row["object_id"] is None:
            continue
        key = (row["kind"], row["object_id"])
        old = latest.get(key)
        if old and old["created"] == row["created"]:
            fields = set(old) | set(row)
            ignored = {"event_id", "event_type", "received_at", "received_ns", "signature_timestamp", "payload_sha256"}
            if any(old.get(field) != row.get(field) for field in fields - ignored):
                ambiguous.add(key)
        elif old and old["created"] < row["created"]:
            ambiguous.discard(key)
        latest[key] = row
    charges = {key[1]: value for key, value in latest.items() if key[0] == "charge"}
    disputes = [value for key, value in latest.items() if key[0] == "dispute"]
    efws = [value for key, value in latest.items() if key[0] == "early_fraud_warning"]
    refunds = [value for key, value in latest.items() if key[0] == "refund"]
    # Count each charge once, never payment-intent or checkout observations.
    capture_ids = {row["charge_id"] for row in rows if row["event_type"] in {"charge.succeeded", "charge.captured"}
                   and row.get("paid") is True and row.get("captured") is True and (row.get("amount_captured_minor") or 0) > 0}
    cohort = {cid for cid in capture_ids if charges.get(cid, {}).get("object_created") is not None
              and since <= charges[cid]["object_created"] <= as_of}
    financial_disputes = [row for row in disputes if row["status"] in FINANCIAL_OPEN | {"won", "lost"}]
    disputed_cohort = {row["charge_id"] for row in financial_disputes if row["charge_id"] in cohort}
    window_disputes = [row for row in financial_disputes if row.get("object_created") is not None and since <= row["object_created"] <= as_of]
    financial_open = [row for row in disputes if row["status"] in FINANCIAL_OPEN]
    inquiry_open = [row for row in disputes if row["status"] in INQUIRY_OPEN]
    unknown = [row for row in disputes if row["status"] not in FINANCIAL_OPEN | INQUIRY_OPEN | CLOSED]
    def totals(items: list[dict[str, Any]], field: str = "amount_minor") -> dict[str, int]:
        grouped: dict[str, int] = defaultdict(int)
        for item in items:
            if item.get(field) is not None and item.get("currency"):
                grouped[item["currency"]] += item[field]
        return dict(sorted(grouped.items()))
    due = [{"dispute_id": row["object_id"], "charge_id": row["charge_id"], "due_by": iso(row["due_by"]),
            "due_by_unix": row["due_by"], "reason": row.get("reason"), "status": row["status"], "overdue": row["due_by"] <= as_of}
           for row in disputes if row["status"] in RESPONSE_REQUIRED and row.get("due_by") is not None]
    due.sort(key=lambda item: (item["due_by_unix"], item["dispute_id"]))
    flags = ["PROVIDER_AND_ACCOUNT_COVERAGE_UNMEASURED"]
    if due and due[0]["due_by_unix"] <= as_of + deadline_hours * 3600:
        flags.append("DISPUTE_RESPONSE_DEADLINE_REQUIRES_OPERATOR_ACTION")
    if any(row["status"] in RESPONSE_REQUIRED and row.get("due_by") is None for row in disputes):
        flags.append("DISPUTE_RESPONSE_DEADLINE_MISSING")
    unmatched = [row["object_id"] for row in disputes if row["charge_id"] not in charges]
    if unmatched:
        flags.append("DISPUTE_CHARGE_SNAPSHOT_MISSING")
    if unknown:
        flags.append("UNKNOWN_DISPUTE_STATUS_REQUIRES_OPERATOR_ACTION")
    if ambiguous:
        flags.append("SAME_TIMESTAMP_SNAPSHOT_ORDER_UNCERTAIN")
    if not cohort:
        flags.append("NO_OBSERVED_CAPTURED_PAYMENT_DENOMINATOR")
    missing_creation = sum(row.get("object_created") is None for row in [*charges.values(), *disputes, *efws])
    if missing_creation:
        flags.append("OBJECT_CREATION_TIMESTAMPS_MISSING")
    return {
        "events_observed": len(rows), "event_type_counts": dict(sorted(Counter(row["event_type"] for row in rows).items())),
        "distinct_charge_snapshots": len(charges), "distinct_disputes": len(disputes),
        "open_financial_disputes": len(financial_open), "open_inquiries": len(inquiry_open),
        "unknown_status_disputes": len(unknown), "open_disputed_nominal_amount_minor_by_currency": totals(financial_open),
        "open_inquiry_nominal_amount_minor_by_currency": totals(inquiry_open),
        "amount_semantics": "Nominal disputed amounts; not proven cash withdrawn, net loss, fees, settlement, or bank cash. Currencies are never combined.",
        "response_deadlines": due, "earliest_response_deadline": due[0] if due else None,
        "missing_charge_dispute_ids": unmatched, "ambiguous_object_ids": sorted(key[1] for key in ambiguous),
        "early_fraud_warnings_observed": len(efws),
        "early_fraud_warnings_created_in_window": sum(row.get("object_created") is not None and since <= row["object_created"] <= as_of for row in efws),
        "refund_status_counts": dict(sorted(Counter(row.get("status") or "unknown" for row in refunds).items())),
        "succeeded_refund_amount_minor_by_currency": totals([row for row in refunds if row.get("status") == "succeeded"]),
        "charge_refund_cumulative_amount_minor_by_currency": totals(list(charges.values()), "amount_refunded_minor"),
        "refund_semantics": "Refund objects and cumulative charge snapshots are separate observations; do not add them together.",
        "observed_subset_rates": {
            "captured_payment_cohort_count": len(cohort), "disputes_created_in_window": len(window_disputes),
            "activity_ratio": len(window_disputes) / len(cohort) if cohort else None,
            "activity_definition": "Observed financial-dispute objects created in the window / observed captured charges created in the window; warning inquiries and prevented cases are excluded. Late disputes can concern earlier charges and this ratio can exceed 1.",
            "disputed_payment_cohort_count": len(disputed_cohort),
            "cohort_ratio": len(disputed_cohort) / len(cohort) if cohort else None,
            "cohort_definition": "Distinct observed captured charges created in the window with an observed financial dispute / that same captured-charge cohort, regardless of won/lost outcome. Warning inquiries and prevented cases are excluded.",
            "coverage": "OBSERVED_SUBSET_ONLY", "vamp_calculated": False,
        },
        "operator_flags": flags, "automated_provider_actions": [],
    }


def summary(args: argparse.Namespace) -> dict[str, Any]:
    as_of = timestamp_argument(args.as_of) if args.as_of else int(time.time())
    since = timestamp_argument(args.since) if args.since else int(datetime.fromtimestamp(as_of, timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
    if since > as_of:
        raise DefenseError("--since must not follow --as-of")
    if args.deadline_hours < 0 or args.deadline_hours > 24 * 365:
        raise DefenseError("--deadline-hours must be between 0 and 8760")
    rows = read_rows(args, as_of=as_of)
    groups: dict[tuple[str, bool], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["account_id"], row["livemode"])].append(row)
    return {"schema_version": SCHEMA, "kind": "PRIVATE_DISPUTE_OBSERVATION_REPORT", "as_of": iso(as_of), "window_start": iso(since),
            "as_of_semantics": "Only provider events created and locally received by as-of are included; latest provider event time wins. Equal-time differing snapshots are flagged.",
            "mode": args.mode, "events_observed": len(rows),
            "data_status": "OBSERVED_SUBSET_ONLY" if rows else "NO_VERIFIED_EVENTS_OBSERVED",
            "account_scopes": [{"account_id": key[0], "livemode": key[1], **summarize_scope(items, since, as_of, args.deadline_hours)} for key, items in sorted(groups.items())],
            "non_claims": ["No zero-fraud, no-dispute, complete-provider-coverage, VAMP-compliance, or bank-cash conclusion is possible from this local subset.",
                           "Operator flags do not pause payments, refund, submit disputes, contact customers, or change Commons admission/posting."]}


def bundle(args: argparse.Namespace) -> dict[str, Any]:
    if not CASE_RE.fullmatch(args.case_id):
        raise DefenseError("case ID must be an opaque 3-80 character label")
    charge_id = ref(args.charge_id, "charge ID", prefix="ch")
    selected = [row for row in read_rows(args) if row["charge_id"] == charge_id] if charge_id else []
    if charge_id and not selected:
        raise DefenseError("charge ID has no verified observation in this ledger")
    sources = []
    for value in args.file:
        path = Path(value).expanduser()
        if path.is_symlink() or not path.is_file():
            raise DefenseError("explicit evidence input must be an existing regular file, not a symlink")
        if path.stat().st_size > MAX_EVIDENCE_FILE:
            raise DefenseError("one evidence input exceeds 64 MiB")
        sources.append(path)
    destination = private_path(args.output_dir)
    private_directory(destination.parent, create=True)
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError:
        raise DefenseError("packet destination already exists; select a new directory") from None
    manifest_files = []
    for index, source in enumerate(sources, 1):
        name = "evidence-%03d.bin" % index
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as incoming, new_private_file(destination / name) as outgoing:
            while chunk := incoming.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_EVIDENCE_FILE:
                    raise DefenseError("evidence input grew beyond 64 MiB while being copied")
                outgoing.write(chunk)
                digest.update(chunk)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        manifest_files.append({"file": name, "source_basename": source.name, "bytes": size, "sha256": digest.hexdigest()})
    event_bytes = b"".join((canonical(row) + "\n").encode() for row in selected)
    with new_private_file(destination / "verified-events.jsonl") as out:
        out.write(event_bytes)
        out.flush()
        os.fsync(out.fileno())
    manifest_files.append({"file": "verified-events.jsonl", "bytes": len(event_bytes), "sha256": hashlib.sha256(event_bytes).hexdigest()})
    manifest = {"schema_version": SCHEMA, "kind": "PRIVATE_FILE_HASH_PACKET", "classification": "PAYMENT_LINKED_OPERATOR_FILES" if charge_id else "DOCUMENT_SOURCE_ONLY", "case_id": args.case_id,
                "created_at": iso(int(time.time())), "charge_id": charge_id, "verified_events_included": len(selected),
                "files": manifest_files, "claim": "These bytes were copied from explicitly selected local files and hashed; matched ledger rows previously passed webhook HMAC verification.",
                "non_claims": ["A file hash does not prove customer acceptance, service delivery, accuracy, eligibility, settlement, bank cash, or that an issuer accepts this packet.",
                               "No submission or provider/customer contact has occurred; selected evidence may contain private customer material and stays off-repository."]}
    with new_private_file(destination / "manifest.json") as out:
        out.write((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        out.flush()
        os.fsync(out.fileno())
    return {"schema_version": SCHEMA, "status": "packet_created", "output_dir": str(destination), "files": len(manifest_files),
            "verified_events_included": len(selected), "provider_submission": False}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = result.add_subparsers(dest="command", required=True)
    def storage(command: argparse.ArgumentParser) -> None:
        command.add_argument("--db", default=os.environ.get("CHARGEBACK_DB"), help="absolute private off-repository SQLite path, or CHARGEBACK_DB")
    def reporting(command: argparse.ArgumentParser) -> None:
        storage(command)
        command.add_argument("--as-of", help="offset-aware ISO-8601 timestamp; defaults to the current UTC clock")
        command.add_argument("--mode", choices=("live", "test", "all"), default="live", help="live and test events are never silently combined")
        command.add_argument("--account", help="direct or acct_...; absent means separate reports for all observed scopes")
    init = commands.add_parser("init", help="create a private ledger; never read zero events from a missing store")
    storage(init)
    incoming = commands.add_parser("ingest", help="verify exact raw Stripe webhook bytes and atomically append a minimized event")
    storage(incoming)
    incoming.add_argument("--body", default="-", help="exact raw body on stdin (-), or a mode-600 file in a private directory")
    secrets = incoming.add_mutually_exclusive_group()
    secrets.add_argument("--secret-env", default="STRIPE_WEBHOOK_SECRET", help="environment variable containing the endpoint signing secret")
    secrets.add_argument("--secret-file", help="mode-600 private file containing the endpoint signing secret")
    signatures = incoming.add_mutually_exclusive_group()
    signatures.add_argument("--signature-env", default="STRIPE_SIGNATURE_HEADER", help="environment variable containing the received Stripe-Signature header")
    signatures.add_argument("--signature-file", help="mode-600 private file containing the received Stripe-Signature header")
    incoming.add_argument("--tolerance", type=int, default=300, help="timestamp tolerance in seconds (1-3600, default 300)")
    export = commands.add_parser("event-export", help="write minimized ledger records to a new private JSONL file")
    reporting(export)
    export.add_argument("--output", required=True, help="new absolute private output file")
    report = commands.add_parser("summary", help="report observed counts, nominal open amounts, deadlines, and distinct activity/cohort ratios")
    reporting(report)
    report.add_argument("--since", help="window start; defaults to the first day of as-of's UTC month")
    report.add_argument("--deadline-hours", type=int, default=48, help="operator deadline flag horizon; never a scheduled reminder")
    packet = commands.add_parser("packet", aliases=["bundle"], help="copy explicitly selected files and matched verified events into a new private hash packet",
                                 description="Copy selected files into a private hash packet. Without --charge-id, no payment ledger is required or opened.")
    reporting(packet)
    packet.add_argument("--case-id", required=True, help="opaque operator case label, never a customer name/email")
    packet.add_argument("--charge-id", help="optional observed ch_... ID; requires --db or CHARGEBACK_DB when supplied; absent means files only, no payment assertion")
    packet.add_argument("--file", action="append", required=True, help="explicit local evidence file; repeat for more files")
    packet.add_argument("--output-dir", required=True, help="new absolute private packet directory")
    return result


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    args = parser().parse_args(argv)
    try:
        requires_ledger = args.command not in {"packet", "bundle"} or args.charge_id is not None
        if requires_ledger and not args.db:
            raise DefenseError("--db or CHARGEBACK_DB is required; there is no in-repository default store")
        if args.command == "init":
            db = connect(args.db, initialize=True)
            count = db.execute("SELECT count(*) FROM events").fetchone()[0]
            db.close()
            result = {"schema_version": SCHEMA, "status": "initialized", "events_observed": count, "financial_coverage": "UNMEASURED"}
        else:
            result = {"ingest": ingest, "event-export": event_export, "summary": summary, "packet": bundle, "bundle": bundle}[args.command](args)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except EventConflict as exc:
        print("chargeback-defense: " + str(exc), file=sys.stderr)
        return 3
    except DefenseError as exc:
        print("chargeback-defense: " + str(exc), file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error, UnicodeError, OverflowError) as exc:
        code = getattr(exc, "errno", None) or getattr(exc, "sqlite_errorname", None) or type(exc).__name__
        print("chargeback-defense: private input/storage operation failed (" + str(code) + ")", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
