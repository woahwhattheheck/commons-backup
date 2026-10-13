#!/usr/bin/env python3
"""Commons-owned, provider-neutral model mail runtime.

Private addresses, recipients, RFC 822 bytes, and keys live in one SQLite file
outside the repository. Public events contain keyed commitments and opaque
references only. Dispatch is at-most-once automatically: a crash after the
durable dispatch claim becomes UNKNOWN_EFFECT and must be reconciled, never
blindly retried.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import importlib.util
import json
import math
import os
import re
import secrets
import sqlite3
import subprocess
import sys
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "revenue" / "swarm_mail" / "inboxes.json"
COMMERCE_PATH = ROOT / "revenue" / "outcome_commerce" / "catalog.json"
OUTREACH_RECEIPTS = ROOT / "revenue" / "payment_ready" / "outreach_receipts"
REPLY_INTAKE_PATH = ROOT / "revenue" / "production_survival" / "reply_intake.py"
PUBLICATION_POLICY_PATH = ROOT / "commons_publication_policy.py"
SCHEMA_VERSION = "commons-swarm-mail-event/v2"
KIND = "SWARM_MAIL_PUBLIC_EVENT"
CLASSIFICATIONS = {
    "OPT_OUT", "AUTO_RESPONSE", "NEGATIVE", "QUESTION", "POSITIVE_SCOPE", "NEEDS_HUMAN",
}
MTA_AUTH_VERDICTS = {"PASS", "FAIL", "UNMEASURED"}
EVENT_STATES = {
    "DRAFT_RECORDED": "NOT_SENT",
    "QUEUE_PLANNED": "NOT_SENT",
    "DISPATCH_CLAIMED": "UNKNOWN_EFFECT",
    "MTA_ACCEPTED": "MTA_ACCEPTED",
    "DISPATCH_UNKNOWN": "UNKNOWN_EFFECT",
    "DISPATCH_NOT_ACCEPTED": "FAILED",
    "PROVIDER_DELIVERY_REPORTED": "PROVIDER_REPORTED",
    "SOFT_BOUNCE_REPORTED": "PROVIDER_REPORTED",
    "HARD_BOUNCE_REPORTED": "FAILED",
    "COMPLAINT_REPORTED": "FAILED",
    "INBOUND_RECORDED": "INBOUND",
    "INBOX_MEASURED": "NOT_SENT",
}
SUPPRESSION_REASONS = {
    "OPT_OUT", "COMPLAINT", "PERMANENT_BOUNCE", "MANUAL_DNC", "CANONICAL_DO_NOT_RESEND",
}
PUBLIC_LIMITS = [
    "keyed commitments only; no address, header, subject, body, attachment, or transport secret",
    "automatic dispatch is at-most-once; UNKNOWN_EFFECT requires reconciliation",
    "provider-reported delivery is not a human reply, commercial acceptance, or bank-available cash",
]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMITMENT_RE = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")
OPAQUE_RE = re.compile(r"^opaque:[A-Za-z0-9._:-]{8,200}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,120}$")


class SwarmMailError(ValueError):
    """A transition failed closed."""


class CollisionError(SwarmMailError):
    """A durable key was reused with different bytes or attribution."""


class UnknownEffectError(SwarmMailError):
    """Transport may have observed the message; reconciliation is required."""


class OutboundIdentityError(SwarmMailError):
    """A private outward-identity hold; no transport or public event occurred."""

    def __init__(self, decision: dict[str, Any]):
        self.decision = dict(decision)
        super().__init__("outbound identity attribution blocked")


_IDENTITY_POLICY: Any | None = None
_IDENTITY_HOLD_FIELDS = (
    "allowed", "code", "rule", "incident", "delivered",
    "matched_fields", "matched_terms", "private_instruction",
)


def _identity_checker():
    global _IDENTITY_POLICY
    if _IDENTITY_POLICY is None:
        spec = importlib.util.spec_from_file_location(
            "commons_swarm_mail_publication_policy", PUBLICATION_POLICY_PATH,
        )
        if spec is None or spec.loader is None:
            raise SwarmMailError("outbound identity policy is unavailable")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            raise SwarmMailError("outbound identity policy is unavailable") from error
        _IDENTITY_POLICY = module
    checker = getattr(_IDENTITY_POLICY, "check_outbound_identity", None)
    if not callable(checker):
        raise SwarmMailError("outbound identity policy is unavailable")
    return checker


def _require_outbound_identity(fields: dict[str, str]) -> dict[str, Any]:
    decision = _identity_checker()(fields)
    if not isinstance(decision, dict) or type(decision.get("allowed")) is not bool:
        raise SwarmMailError("outbound identity policy returned an invalid decision")
    if decision["allowed"]:
        return decision
    missing = [field for field in _IDENTITY_HOLD_FIELDS if field not in decision]
    if missing or decision.get("incident") is not False or decision.get("delivered") is not False:
        raise SwarmMailError("outbound identity policy returned an unsafe hold")
    raise OutboundIdentityError(
        {field: decision[field] for field in _IDENTITY_HOLD_FIELDS}
    )


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> str:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as error:
        raise SwarmMailError(f"invalid date-time: {value}") from error
    if parsed.tzinfo is None:
        raise SwarmMailError("date-time must include a timezone")
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SwarmMailError(f"cannot read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise SwarmMailError(f"{path} must contain one JSON object")
    return value


def normalize_address(value: str) -> str:
    _display, address = parseaddr(value)
    address = address.strip().lower()
    if not EMAIL_RE.fullmatch(address) or len(address) > 254:
        raise SwarmMailError("invalid email address")
    return address


def _exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        raise SwarmMailError(
            f"{where} fields differ: missing={sorted(expected-actual)} extra={sorted(actual-expected)}"
        )


def load_manifest() -> dict[str, Any]:
    return read_json(MANIFEST_PATH)


def commerce_skus() -> set[str]:
    catalog = read_json(COMMERCE_PATH)
    listings = catalog.get("listings")
    if not isinstance(listings, list):
        raise SwarmMailError("commerce catalog listings must be an array")
    result = {item.get("id") for item in listings if isinstance(item, dict)}
    if None in result or not all(isinstance(item, str) for item in result):
        raise SwarmMailError("commerce listing ids are incomplete")
    return result


def validate_manifest(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    value = manifest if manifest is not None else load_manifest()
    _exact_keys(
        value,
        {"schema_version", "kind", "measured_at", "domain", "transport", "truth", "global_rules", "inboxes"},
        "manifest",
    )
    if value["schema_version"] != "commons-swarm-mail/v2" or value["kind"] != "SWARM_MAIL_PUBLIC_INBOX_MANIFEST":
        raise SwarmMailError("manifest version or kind is unsupported")
    parse_time(value["measured_at"])
    domain = value["domain"]
    _exact_keys(domain, {"state", "public_name", "proofs", "proof_bundle_commitment"}, "domain")
    _exact_keys(domain["proofs"], {"mx", "spf", "dkim", "dmarc"}, "domain.proofs")
    proof_values = set(domain["proofs"].values())
    if domain["state"] == "MEASURED":
        if proof_values != {"MEASURED"} or not isinstance(domain["public_name"], str):
            raise SwarmMailError("MEASURED domain requires a name and all four measured records")
        if not COMMITMENT_RE.fullmatch(str(domain["proof_bundle_commitment"])):
            raise SwarmMailError("MEASURED domain requires a keyed proof-bundle commitment")
    elif domain["state"] == "UNPROVISIONED":
        if domain["public_name"] is not None or proof_values != {"UNMEASURED"} or domain["proof_bundle_commitment"] is not None:
            raise SwarmMailError("UNPROVISIONED domain cannot publish measured values")
    else:
        raise SwarmMailError("domain state is invalid")
    transport = value["transport"]
    _exact_keys(transport, {"state", "adapter", "mta_acceptance_receipt", "provider_report_receipt"}, "transport")
    if transport["adapter"] != "LOCAL_MTA" or transport["state"] not in {
        "UNMEASURED", "MTA_ACCEPTANCE_MEASURED", "PROVIDER_REPORT_RECORDED",
    }:
        raise SwarmMailError("transport state or adapter is invalid")
    if transport["state"] == "UNMEASURED":
        if transport["mta_acceptance_receipt"] is not None or transport["provider_report_receipt"] is not None:
            raise SwarmMailError("UNMEASURED transport cannot cite receipts")
    elif transport["state"] == "MTA_ACCEPTANCE_MEASURED":
        if not OPAQUE_RE.fullmatch(str(transport["mta_acceptance_receipt"])) or transport["provider_report_receipt"] is not None:
            raise SwarmMailError("MTA_ACCEPTANCE_MEASURED requires exactly its MTA receipt")
    else:
        if not OPAQUE_RE.fullmatch(str(transport["mta_acceptance_receipt"])) or not OPAQUE_RE.fullmatch(str(transport["provider_report_receipt"])):
            raise SwarmMailError("PROVIDER_REPORT_RECORDED requires both transport receipts")
    inboxes = value["inboxes"]
    if not isinstance(inboxes, list) or not inboxes:
        raise SwarmMailError("manifest needs at least one inbox")
    inbox_fields = {
        "inbox_id", "agent_claim", "model_family", "local_part", "address_state", "public_address",
        "purpose", "send_mode", "daily_new_thread_limit", "sku_ids", "reply_owner", "handoff_classes",
    }
    seen_ids: set[str] = set()
    seen_parts: set[str] = set()
    assigned: list[str] = []
    for index, inbox in enumerate(inboxes):
        if not isinstance(inbox, dict):
            raise SwarmMailError(f"inboxes[{index}] must be an object")
        _exact_keys(inbox, inbox_fields, f"inboxes[{index}]")
        inbox_id = inbox["inbox_id"]
        local_part = inbox["local_part"]
        if not isinstance(inbox_id, str) or not ID_RE.fullmatch(inbox_id):
            raise SwarmMailError(f"invalid inbox_id at row {index}")
        if not isinstance(local_part, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,40}", local_part):
            raise SwarmMailError(f"invalid local_part at row {index}")
        if inbox_id in seen_ids or local_part in seen_parts:
            raise SwarmMailError("inbox ids and local parts must be unique")
        seen_ids.add(inbox_id)
        seen_parts.add(local_part)
        if inbox["purpose"] != "TARGETED_OUTREACH_AND_SALES":
            raise SwarmMailError("inbox purpose is invalid")
        if type(inbox["daily_new_thread_limit"]) is not int or not 1 <= inbox["daily_new_thread_limit"] <= 50:
            raise SwarmMailError("daily new-thread limit must be an integer from 1 to 50")
        if inbox["address_state"] == "UNPROVISIONED":
            if inbox["public_address"] is not None or inbox["send_mode"] != "DRAFT_ONLY":
                raise SwarmMailError("unprovisioned inbox must stay DRAFT_ONLY without an address")
        elif inbox["address_state"] == "MEASURED":
            public_address = normalize_address(inbox["public_address"])
            local, address_domain = public_address.split("@", 1)
            if domain["state"] != "MEASURED" or local != local_part or address_domain != domain["public_name"]:
                raise SwarmMailError("measured address must bind to the measured domain and local part")
            if inbox["send_mode"] != "INBOUND_AND_OUTBOUND":
                raise SwarmMailError("measured inbox must expose both directions")
        else:
            raise SwarmMailError("address state is invalid")
        skus = inbox["sku_ids"]
        if not isinstance(skus, list) or not skus or len(skus) != len(set(skus)):
            raise SwarmMailError("each inbox needs unique SKU ids")
        assigned.extend(skus)
        if set(inbox["handoff_classes"]) != {
            "QUESTION", "POSITIVE_SCOPE", "NEEDS_HUMAN", "OPT_OUT", "COMPLAINT", "BOUNCE",
        }:
            raise SwarmMailError("handoff classes must be complete")
    expected = commerce_skus()
    if set(assigned) != expected or len(assigned) != len(expected):
        raise SwarmMailError("every commerce SKU must route to exactly one inbox")
    if not isinstance(value["global_rules"], list) or len(value["global_rules"]) < 8:
        raise SwarmMailError("global rules are incomplete")
    truth = value["truth"]
    count_fields = {
        "measured_inboxes", "drafted_messages", "queued_messages", "unknown_effect_dispatches",
        "mta_accepted_messages", "provider_reported_deliveries", "verified_positive_replies", "paid_deliveries",
    }
    _exact_keys(truth, count_fields | {"bank_available_usd"}, "truth")
    if any(type(truth[field]) is not int or truth[field] < 0 for field in count_fields):
        raise SwarmMailError("truth counts must be non-negative integers")
    cash = truth["bank_available_usd"]
    if isinstance(cash, bool) or not isinstance(cash, (int, float)) or not math.isfinite(cash) or cash < 0:
        raise SwarmMailError("bank_available_usd must be one finite non-negative number")
    return value


def inbox_by_id(inbox_id: str) -> dict[str, Any]:
    for inbox in validate_manifest()["inboxes"]:
        if inbox["inbox_id"] == inbox_id:
            return inbox
    raise SwarmMailError(f"unknown inbox_id: {inbox_id}")


def route_sku(sku_id: str) -> dict[str, Any]:
    for inbox in validate_manifest()["inboxes"]:
        if sku_id in inbox["sku_ids"]:
            return {
                "sku_id": sku_id,
                "inbox_id": inbox["inbox_id"],
                "agent_claim": inbox["agent_claim"],
                "model_family": inbox["model_family"],
                "address_state": inbox["address_state"],
                "send_mode": inbox["send_mode"],
            }
    raise SwarmMailError(f"unrouted SKU: {sku_id}")


def assert_private_db(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        return resolved
    raise SwarmMailError("private mail database must be outside the Commons repository")


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS inboxes (
          inbox_id TEXT PRIMARY KEY,
          agent_claim TEXT NOT NULL,
          model_family TEXT NOT NULL,
          local_part TEXT NOT NULL UNIQUE,
          address TEXT UNIQUE,
          address_commitment TEXT UNIQUE,
          proof_bundle_sha256 TEXT,
          state TEXT NOT NULL CHECK (state IN ('UNPROVISIONED','MEASURED')),
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS suppressions (
          recipient_commitment TEXT PRIMARY KEY,
          reason TEXT NOT NULL,
          evidence_ref TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS drafts (
          send_key TEXT PRIMARY KEY,
          dedupe_commitment TEXT NOT NULL UNIQUE,
          inbox_id TEXT NOT NULL REFERENCES inboxes(inbox_id),
          recipient TEXT NOT NULL,
          recipient_commitment TEXT NOT NULL,
          sku_id TEXT NOT NULL,
          prospect_key TEXT NOT NULL,
          subject TEXT NOT NULL,
          body TEXT NOT NULL,
          payload_sha256 TEXT NOT NULL,
          payload_commitment TEXT NOT NULL,
          message_id TEXT NOT NULL UNIQUE,
          thread_key TEXT NOT NULL,
          created_at TEXT NOT NULL,
          state TEXT NOT NULL CHECK (state IN ('DRAFTED','QUEUED','DISPATCHING','UNKNOWN_EFFECT','MTA_ACCEPTED','DELIVERY_REPORTED','SUPPRESSED','NOT_ACCEPTED')),
          readiness TEXT NOT NULL,
          dispatch_ref TEXT,
          event_json BLOB NOT NULL,
          queued_at TEXT,
          mta_accepted_at TEXT,
          provider_reported_at TEXT
        );
        CREATE TABLE IF NOT EXISTS transport_events (
          transport_event_key TEXT PRIMARY KEY,
          send_key TEXT NOT NULL REFERENCES drafts(send_key),
          event_type TEXT NOT NULL,
          evidence_sha256 TEXT NOT NULL,
          occurred_at TEXT NOT NULL,
          event_json BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inbound_messages (
          message_key TEXT PRIMARY KEY,
          thread_key TEXT NOT NULL,
          inbox_id TEXT NOT NULL REFERENCES inboxes(inbox_id),
          sender TEXT NOT NULL,
          sender_commitment TEXT NOT NULL,
          linked_send_key TEXT,
          sku_id TEXT,
          prospect_key TEXT,
          payload BLOB NOT NULL,
          payload_sha256 TEXT NOT NULL,
          mta_evidence_sha256 TEXT NOT NULL,
          received_at TEXT NOT NULL,
          classification TEXT NOT NULL,
          attribution_state TEXT NOT NULL,
          canonical_reply_json BLOB,
          event_json BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          event_id TEXT PRIMARY KEY,
          event_type TEXT NOT NULL,
          occurred_at TEXT NOT NULL,
          event_json BLOB NOT NULL
        );
        CREATE INDEX IF NOT EXISTS drafts_recipient ON drafts(recipient_commitment);
        CREATE INDEX IF NOT EXISTS inbound_thread ON inbound_messages(thread_key);
        """
    )
    draft_columns = {row[1] for row in connection.execute("PRAGMA table_info(drafts)")}
    for name in ("queued_at", "mta_accepted_at", "provider_reported_at"):
        if name not in draft_columns:
            connection.execute(f"ALTER TABLE drafts ADD COLUMN {name} TEXT")
    if not connection.execute("SELECT 1 FROM meta WHERE key = 'commit_key'").fetchone():
        connection.execute("INSERT INTO meta VALUES ('commit_key', ?)", (secrets.token_hex(32),))


def _commit_key(connection: sqlite3.Connection) -> bytes:
    row = connection.execute("SELECT value FROM meta WHERE key = 'commit_key'").fetchone()
    if not row:
        raise SwarmMailError("private commitment key is missing")
    return bytes.fromhex(row[0])


def commitment(connection: sqlite3.Connection, purpose: str, material: bytes) -> str:
    digest = hmac.new(_commit_key(connection), purpose.encode("utf-8") + b"\0" + material, hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def opaque_ref(connection: sqlite3.Connection, prefix: str, material: bytes) -> str:
    digest = hmac.new(_commit_key(connection), prefix.encode("utf-8") + b"\0" + material, hashlib.sha256).hexdigest()
    return f"opaque:{prefix}:{digest[:32]}"


def _recipient_commitment(connection: sqlite3.Connection, address: str) -> str:
    return commitment(connection, "recipient", normalize_address(address).encode("utf-8"))


def _sync_routes(connection: sqlite3.Connection) -> None:
    now = utc_now()
    for inbox in validate_manifest()["inboxes"]:
        row = connection.execute("SELECT * FROM inboxes WHERE inbox_id = ?", (inbox["inbox_id"],)).fetchone()
        identity = (inbox["agent_claim"], inbox["model_family"], inbox["local_part"])
        if row:
            if (row["agent_claim"], row["model_family"], row["local_part"]) != identity:
                raise CollisionError("public inbox route changed after private initialization")
        else:
            connection.execute(
                "INSERT INTO inboxes VALUES (?,?,?,?,?,?,?,?,?)",
                (inbox["inbox_id"], *identity, None, None, None, "UNPROVISIONED", now),
            )


def _seed_canonical_dnc(connection: sqlite3.Connection) -> int:
    inserted = 0
    if not OUTREACH_RECEIPTS.is_dir():
        return inserted
    for path in sorted(OUTREACH_RECEIPTS.glob("*.json")):
        try:
            receipt = read_json(path)
        except SwarmMailError:
            continue
        dedupe = receipt.get("dedupe")
        address = receipt.get("recipient_email")
        if not isinstance(dedupe, dict) or dedupe.get("do_not_resend") is not True or not isinstance(address, str):
            continue
        recipient = _recipient_commitment(connection, address)
        evidence = "opaque:canonical-receipt:" + sha256_bytes(path.name.encode("utf-8"))[:24]
        if not connection.execute("SELECT 1 FROM suppressions WHERE recipient_commitment = ?", (recipient,)).fetchone():
            connection.execute(
                "INSERT INTO suppressions VALUES (?,?,?,?)",
                (recipient, "CANONICAL_DO_NOT_RESEND", evidence, utc_now()),
            )
            inserted += 1
    return inserted


def open_db(path: Path) -> sqlite3.Connection:
    db_path = assert_private_db(path)
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    _schema(connection)
    _sync_routes(connection)
    _seed_canonical_dnc(connection)
    connection.commit()
    try:
        os.chmod(db_path, 0o600)
    except OSError:
        pass
    return connection


def public_event(
    connection: sqlite3.Connection,
    event_type: str,
    *,
    inbox_id: str,
    occurred_at: str,
    payload_material: bytes,
    sku_id: str | None = None,
    prospect_key: str | None = None,
    thread_material: bytes | None = None,
    message_material: bytes | None = None,
    send_key: str | None = None,
    classification: str | None = None,
    evidence_material: bytes | None = None,
    readiness: str | None = None,
) -> dict[str, Any]:
    occurred_at = parse_time(occurred_at)
    if event_type not in EVENT_STATES:
        raise SwarmMailError("public event type is invalid")
    private_material = canonical_bytes({
        "event_type": event_type,
        "inbox_id": inbox_id,
        "occurred_at": occurred_at,
        "payload_sha256": sha256_bytes(payload_material),
        "sku_id": sku_id,
        "prospect_key": prospect_key,
        "thread_sha256": sha256_bytes(thread_material) if thread_material else None,
        "message_sha256": sha256_bytes(message_material) if message_material else None,
        "send_key": send_key,
        "classification": classification,
        "evidence_sha256": sha256_bytes(evidence_material) if evidence_material else None,
        "readiness": readiness,
    })
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "event_id": "mail-" + opaque_ref(connection, "event", private_material).rsplit(":", 1)[1][:24],
        "event_type": event_type,
        "occurred_at": occurred_at,
        "inbox_id": inbox_id,
        "thread_ref": opaque_ref(connection, "thread", thread_material) if thread_material else None,
        "message_ref": opaque_ref(connection, "message", message_material) if message_material else None,
        "sku_id": sku_id,
        "prospect_ref": opaque_ref(connection, "prospect", prospect_key.encode("utf-8")) if prospect_key else None,
        "payload_commitment": commitment(connection, "payload", payload_material),
        "send_ref": opaque_ref(connection, "send", send_key.encode("utf-8")) if send_key else None,
        "classification": classification,
        "transport_state": EVENT_STATES[event_type],
        "evidence_ref": opaque_ref(connection, "evidence", evidence_material) if evidence_material else None,
        "readiness": readiness,
        "limits": list(PUBLIC_LIMITS),
    }
    validate_public_event(event)
    return event


def validate_public_event(event: dict[str, Any]) -> None:
    fields = {
        "schema_version", "kind", "event_id", "event_type", "occurred_at", "inbox_id",
        "thread_ref", "message_ref", "sku_id", "prospect_ref", "payload_commitment", "send_ref",
        "classification", "transport_state", "evidence_ref", "readiness", "limits",
    }
    _exact_keys(event, fields, "public event")
    if event["schema_version"] != SCHEMA_VERSION or event["kind"] != KIND:
        raise SwarmMailError("public event version or kind is unsupported")
    if not re.fullmatch(r"mail-[0-9a-f]{24}", str(event["event_id"])):
        raise SwarmMailError("public event id is malformed")
    if event["event_type"] not in EVENT_STATES or event["transport_state"] != EVENT_STATES[event["event_type"]]:
        raise SwarmMailError("public event type and transport state disagree")
    parse_time(event["occurred_at"])
    if not ID_RE.fullmatch(str(event["inbox_id"])) or not COMMITMENT_RE.fullmatch(str(event["payload_commitment"])):
        raise SwarmMailError("public event inbox or commitment is malformed")
    for field in ("thread_ref", "message_ref", "prospect_ref", "send_ref", "evidence_ref"):
        if event[field] is not None and not OPAQUE_RE.fullmatch(str(event[field])):
            raise SwarmMailError(f"public event {field} is malformed")
    if event["sku_id"] is not None and not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,80}", str(event["sku_id"])):
        raise SwarmMailError("public event SKU is malformed")
    if event["classification"] is not None and event["classification"] not in CLASSIFICATIONS:
        raise SwarmMailError("public event classification is invalid")
    if event["event_type"] == "INBOUND_RECORDED":
        if event["classification"] is None or event["message_ref"] is None or event["evidence_ref"] is None:
            raise SwarmMailError("inbound event lacks classification or evidence")
    elif event["classification"] is not None:
        raise SwarmMailError("only inbound events carry a reply classification")
    if event["event_type"] == "QUEUE_PLANNED" and event["send_ref"] is None:
        raise SwarmMailError("queued event needs a send reference")
    if event["event_type"] not in {"DRAFT_RECORDED", "QUEUE_PLANNED"} and event["evidence_ref"] is None:
        raise SwarmMailError("measured transition requires evidence")
    if event["limits"] != PUBLIC_LIMITS:
        raise SwarmMailError("public event limits differ")


def store_public_event(connection: sqlite3.Connection, event: dict[str, Any]) -> None:
    validate_public_event(event)
    blob = canonical_bytes(event)
    row = connection.execute("SELECT event_json FROM events WHERE event_id = ?", (event["event_id"],)).fetchone()
    if row:
        if bytes(row["event_json"]) != blob:
            raise CollisionError("public event id reused with different bytes")
        return
    connection.execute("INSERT INTO events VALUES (?,?,?,?)", (event["event_id"], event["event_type"], event["occurred_at"], blob))


def provision_inbox(
    connection: sqlite3.Connection,
    inbox_id: str,
    address: str,
    proof_bundle: bytes,
    occurred_at: str,
) -> dict[str, Any]:
    spec = inbox_by_id(inbox_id)
    manifest = validate_manifest()
    normalized = normalize_address(address)
    if spec["address_state"] != "MEASURED" or spec["send_mode"] != "INBOUND_AND_OUTBOUND":
        raise SwarmMailError("public manifest has not measured this address")
    if normalized != normalize_address(spec["public_address"]):
        raise SwarmMailError("private address differs from the measured public address")
    domain = normalized.split("@", 1)[1]
    if manifest["domain"]["state"] != "MEASURED" or domain != manifest["domain"]["public_name"]:
        raise SwarmMailError("address domain differs from the measured domain")
    if not proof_bundle or len(proof_bundle) > 2_000_000:
        raise SwarmMailError("retained proof bundle is empty or too large")
    proof_sha = sha256_bytes(proof_bundle)
    public_commitment = commitment(connection, "domain-proof", proof_bundle)
    if public_commitment != manifest["domain"]["proof_bundle_commitment"]:
        raise SwarmMailError("retained proof bundle does not match the public commitment")
    occurred_at = parse_time(occurred_at)
    address_commitment = commitment(connection, "address", normalized.encode("utf-8"))
    row = connection.execute("SELECT * FROM inboxes WHERE inbox_id = ?", (inbox_id,)).fetchone()
    if row["state"] == "MEASURED":
        if row["address_commitment"] != address_commitment or row["proof_bundle_sha256"] != proof_sha:
            raise CollisionError("inbox already measured with different private evidence")
    else:
        connection.execute(
            "UPDATE inboxes SET address=?, address_commitment=?, proof_bundle_sha256=?, state='MEASURED', created_at=? WHERE inbox_id=?",
            (normalized, address_commitment, proof_sha, occurred_at, inbox_id),
        )
    event = public_event(
        connection, "INBOX_MEASURED", inbox_id=inbox_id, occurred_at=occurred_at,
        payload_material=proof_bundle, evidence_material=proof_bundle, readiness="MEASURED",
    )
    store_public_event(connection, event)
    connection.commit()
    return event


def proof_bundle_commitment(connection: sqlite3.Connection, proof_bundle: bytes) -> dict[str, Any]:
    """Compute the public commitment needed before a measured manifest can land."""
    if not proof_bundle or len(proof_bundle) > 2_000_000:
        raise SwarmMailError("retained proof bundle is empty or too large")
    return {
        "kind": "SWARM_MAIL_PROOF_BUNDLE_COMMITMENT",
        "proof_bundle_commitment": commitment(connection, "domain-proof", proof_bundle),
        "limits": [
            "commitment is keyed by the private runtime and does not expose the proof bundle hash",
            "publishing this value does not by itself measure DNS, an inbox, MTA acceptance, or delivery",
        ],
    }


def _put_suppression(
    connection: sqlite3.Connection,
    recipient: str,
    reason: str,
    evidence_ref: str,
    occurred_at: str,
) -> dict[str, Any]:
    if reason not in SUPPRESSION_REASONS or not OPAQUE_RE.fullmatch(evidence_ref):
        raise SwarmMailError("suppression reason or evidence is invalid")
    occurred_at = parse_time(occurred_at)
    recipient_ref = _recipient_commitment(connection, recipient)
    row = connection.execute("SELECT * FROM suppressions WHERE recipient_commitment = ?", (recipient_ref,)).fetchone()
    if row:
        if row["reason"] != reason and row["reason"] != "CANONICAL_DO_NOT_RESEND":
            raise CollisionError("recipient already has a different durable suppression")
    else:
        connection.execute("INSERT INTO suppressions VALUES (?,?,?,?)", (recipient_ref, reason, evidence_ref, occurred_at))
    return {
        "kind": "SWARM_MAIL_SUPPRESSION_RECEIPT",
        "recipient_ref": opaque_ref(connection, "recipient", normalize_address(recipient).encode("utf-8")),
        "reason": reason,
        "evidence_ref": opaque_ref(connection, "evidence", evidence_ref.encode("utf-8")),
        "occurred_at": occurred_at,
        "scope": "ALL_MODEL_INBOXES_ALL_SKUS",
    }


def suppress_recipient(connection: sqlite3.Connection, recipient: str, reason: str, evidence_ref: str, occurred_at: str) -> dict[str, Any]:
    result = _put_suppression(connection, recipient, reason, evidence_ref, occurred_at)
    connection.commit()
    return result


def _canonical_dedupe(recipient: str, sku_id: str) -> str:
    normalized = normalize_address(recipient)
    domain = normalized.split("@", 1)[1]
    return f"{domain}|{normalized}|{sku_id}|EMAIL"


def _draft_readiness(connection: sqlite3.Connection, spec: dict[str, Any], recipient_ref: str, occurred_at: str) -> str:
    if connection.execute("SELECT 1 FROM suppressions WHERE recipient_commitment = ?", (recipient_ref,)).fetchone():
        return "SUPPRESSED"
    inbox = connection.execute("SELECT state FROM inboxes WHERE inbox_id = ?", (spec["inbox_id"],)).fetchone()
    if spec["address_state"] != "MEASURED" or not inbox or inbox["state"] != "MEASURED":
        return "ADDRESS_UNMEASURED"
    queued_today = connection.execute(
        "SELECT COUNT(*) FROM drafts WHERE inbox_id=? AND substr(queued_at,1,10)=?",
        (spec["inbox_id"], occurred_at[:10]),
    ).fetchone()[0]
    if queued_today >= spec["daily_new_thread_limit"]:
        return "DAILY_BUDGET_REACHED"
    return "SEND_READY"


def queue_message(
    connection: sqlite3.Connection,
    *,
    recipient: str,
    sku_id: str,
    prospect_key: str,
    subject: str,
    body: str,
    send_key: str,
    occurred_at: str,
) -> dict[str, Any]:
    route = route_sku(sku_id)
    spec = inbox_by_id(route["inbox_id"])
    if not ID_RE.fullmatch(send_key) or not ID_RE.fullmatch(prospect_key):
        raise SwarmMailError("send_key and prospect_key must be stable private slugs")
    occurred_at = parse_time(occurred_at)
    normalized = normalize_address(recipient)
    if "\r" in subject or "\n" in subject or not subject.strip() or len(subject) > 200:
        raise SwarmMailError("subject is empty, over 200 characters, or contains a newline")
    if not body.strip() or len(body.encode("utf-8")) > 100_000:
        raise SwarmMailError("body is empty or over 100 KB")
    if not re.search(r"\b(?:unsubscribe|opt[ -]?out)\b", body, re.IGNORECASE):
        raise SwarmMailError("outreach body must contain a visible unsubscribe or opt-out route")
    _require_outbound_identity({"subject": subject, "body": body})
    payload = canonical_bytes({
        "inbox_id": spec["inbox_id"], "recipient": normalized, "sku_id": sku_id,
        "prospect_key": prospect_key, "subject": subject, "body": body,
    })
    payload_sha = sha256_bytes(payload)
    payload_commitment = commitment(connection, "payload", payload)
    recipient_ref = _recipient_commitment(connection, normalized)
    dedupe = commitment(connection, "canonical-dedupe", _canonical_dedupe(normalized, sku_id).encode("utf-8"))
    message_id = f"<swarm-{opaque_ref(connection, 'message-id', send_key.encode('utf-8')).rsplit(':', 1)[1]}@pending.invalid>"
    thread_key = opaque_ref(connection, "thread-private", send_key.encode("utf-8"))
    connection.commit()
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM drafts WHERE send_key = ?", (send_key,)).fetchone()
        if row:
            immutable = (
                row["payload_sha256"], row["dedupe_commitment"], row["inbox_id"],
                row["sku_id"], row["prospect_key"],
            )
            if immutable != (payload_sha, dedupe, spec["inbox_id"], sku_id, prospect_key):
                raise CollisionError("send key reused with different bytes or attribution")
            if row["state"] != "DRAFTED":
                return json.loads(row["event_json"])
        else:
            conflict = connection.execute(
                "SELECT send_key FROM drafts WHERE dedupe_commitment = ?", (dedupe,),
            ).fetchone()
            if conflict:
                raise CollisionError("canonical recipient/SKU/channel dedupe already exists")
        readiness = _draft_readiness(connection, spec, recipient_ref, occurred_at)
        target_state = "QUEUED" if readiness == "SEND_READY" else "DRAFTED"
        event_type = "QUEUE_PLANNED" if target_state == "QUEUED" else "DRAFT_RECORDED"
        queued_at = occurred_at if target_state == "QUEUED" else None
        if row:
            connection.execute(
                "UPDATE drafts SET state=?, readiness=?, queued_at=COALESCE(queued_at,?) WHERE send_key=?",
                (target_state, readiness, queued_at, send_key),
            )
        else:
            connection.execute(
                """
                INSERT INTO drafts (
                  send_key,dedupe_commitment,inbox_id,recipient,recipient_commitment,sku_id,prospect_key,
                  subject,body,payload_sha256,payload_commitment,message_id,thread_key,created_at,state,
                  readiness,dispatch_ref,event_json,queued_at,mta_accepted_at,provider_reported_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (send_key, dedupe, spec["inbox_id"], normalized, recipient_ref, sku_id, prospect_key,
                 subject, body, payload_sha, payload_commitment, message_id, thread_key, occurred_at,
                 target_state, readiness, None, b"{}", queued_at, None, None),
            )
        event = public_event(
            connection, event_type, inbox_id=spec["inbox_id"], occurred_at=occurred_at,
            payload_material=payload, sku_id=sku_id, prospect_key=prospect_key,
            thread_material=thread_key.encode("utf-8"), message_material=message_id.encode("utf-8"),
            send_key=send_key, readiness=readiness,
        )
        connection.execute("UPDATE drafts SET event_json=? WHERE send_key=?", (canonical_bytes(event), send_key))
        store_public_event(connection, event)
        return event


def _wire_message(connection: sqlite3.Connection, row: sqlite3.Row) -> bytes:
    inbox = connection.execute("SELECT address FROM inboxes WHERE inbox_id=? AND state='MEASURED'", (row["inbox_id"],)).fetchone()
    if not inbox or not inbox["address"]:
        raise SwarmMailError("inbox address is not measured in the private runtime")
    from_address = inbox["address"]
    domain = from_address.split("@", 1)[1]
    message_id = row["message_id"].replace("@pending.invalid>", f"@{domain}>")
    message = EmailMessage()
    message["From"] = from_address
    message["To"] = row["recipient"]
    message["Subject"] = row["subject"]
    message["Message-ID"] = message_id
    message["List-Unsubscribe"] = f"<mailto:{from_address}?subject=unsubscribe>"
    message["X-Commons-SKU"] = row["sku_id"]
    message["X-Commons-Send-Ref"] = opaque_ref(connection, "send", row["send_key"].encode("utf-8"))
    message.set_content(row["body"])
    _require_outbound_identity({
        "from": str(message["From"] or ""),
        "subject": str(message["Subject"] or ""),
        "body": row["body"],
    })
    return message.as_bytes(policy=policy.SMTP)


def dispatch_message(connection: sqlite3.Connection, send_key: str, sendmail_bin: Path, occurred_at: str) -> dict[str, Any]:
    if not sendmail_bin.is_absolute() or not sendmail_bin.is_file() or not os.access(sendmail_bin, os.X_OK):
        raise SwarmMailError("sendmail adapter must be an absolute executable file")
    occurred_at = parse_time(occurred_at)
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    row = connection.execute("SELECT * FROM drafts WHERE send_key=?", (send_key,)).fetchone()
    if not row:
        connection.rollback()
        raise SwarmMailError("unknown draft")
    if row["state"] == "MTA_ACCEPTED":
        connection.rollback()
        return json.loads(row["event_json"])
    if row["state"] in {"DISPATCHING", "UNKNOWN_EFFECT"}:
        connection.rollback()
        raise UnknownEffectError("dispatch has UNKNOWN_EFFECT; reconcile the existing attempt")
    if row["state"] != "QUEUED":
        connection.rollback()
        raise SwarmMailError(f"draft cannot dispatch from state {row['state']} ({row['readiness']})")
    if connection.execute(
        "SELECT 1 FROM suppressions WHERE recipient_commitment=?",
        (row["recipient_commitment"],),
    ).fetchone():
        payload = canonical_bytes({
            "inbox_id": row["inbox_id"], "recipient": row["recipient"], "sku_id": row["sku_id"],
            "prospect_key": row["prospect_key"], "subject": row["subject"], "body": row["body"],
        })
        blocked = public_event(
            connection, "DRAFT_RECORDED", inbox_id=row["inbox_id"], occurred_at=occurred_at,
            payload_material=payload, sku_id=row["sku_id"], prospect_key=row["prospect_key"],
            thread_material=row["thread_key"].encode("utf-8"),
            message_material=row["message_id"].encode("utf-8"), send_key=send_key,
            readiness="SUPPRESSED_AT_DISPATCH",
        )
        connection.execute(
            "UPDATE drafts SET state='SUPPRESSED', readiness='SUPPRESSED_AT_DISPATCH', event_json=? WHERE send_key=?",
            (canonical_bytes(blocked), send_key),
        )
        store_public_event(connection, blocked)
        connection.commit()
        raise SwarmMailError("recipient became suppressed before dispatch; no MTA handoff occurred")
    try:
        wire = _wire_message(connection, row)
    except OutboundIdentityError:
        connection.rollback()
        raise
    dispatch_ref = opaque_ref(connection, "dispatch", secrets.token_bytes(32))
    claim = public_event(
        connection, "DISPATCH_CLAIMED", inbox_id=row["inbox_id"], occurred_at=occurred_at,
        payload_material=wire, sku_id=row["sku_id"], prospect_key=row["prospect_key"],
        thread_material=row["thread_key"].encode("utf-8"), message_material=row["message_id"].encode("utf-8"),
        send_key=send_key, evidence_material=dispatch_ref.encode("utf-8"), readiness="DISPATCHING",
    )
    connection.execute("UPDATE drafts SET state='DISPATCHING', readiness='UNKNOWN_EFFECT', dispatch_ref=?, event_json=? WHERE send_key=?", (dispatch_ref, canonical_bytes(claim), send_key))
    store_public_event(connection, claim)
    connection.commit()
    from_address = connection.execute("SELECT address FROM inboxes WHERE inbox_id=?", (row["inbox_id"],)).fetchone()[0]
    try:
        completed = subprocess.run(
            [str(sendmail_bin), "-i", "-f", from_address, "-t"], input=wire,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        _mark_unknown(connection, row, wire, dispatch_ref, occurred_at, repr(error).encode("utf-8"))
        raise UnknownEffectError("MTA handoff raised after the durable dispatch claim") from error
    evidence = dispatch_ref.encode("utf-8") + b"\0" + completed.stdout + b"\0" + completed.stderr + b"\0" + str(completed.returncode).encode("ascii")
    if completed.returncode != 0:
        _mark_unknown(connection, row, wire, dispatch_ref, occurred_at, evidence)
        raise UnknownEffectError("MTA handoff returned nonzero after the durable dispatch claim")
    event = public_event(
        connection, "MTA_ACCEPTED", inbox_id=row["inbox_id"], occurred_at=occurred_at,
        payload_material=wire, sku_id=row["sku_id"], prospect_key=row["prospect_key"],
        thread_material=row["thread_key"].encode("utf-8"), message_material=row["message_id"].encode("utf-8"),
        send_key=send_key, evidence_material=evidence, readiness="MTA_ACCEPTED",
    )
    connection.execute("BEGIN IMMEDIATE")
    current = connection.execute("SELECT state,dispatch_ref FROM drafts WHERE send_key=?", (send_key,)).fetchone()
    if current["state"] != "DISPATCHING" or current["dispatch_ref"] != dispatch_ref:
        connection.rollback()
        raise UnknownEffectError("dispatch claim changed before MTA acceptance could be recorded")
    connection.execute(
        "UPDATE drafts SET state='MTA_ACCEPTED', readiness='MTA_ACCEPTED', mta_accepted_at=COALESCE(mta_accepted_at,?), event_json=? WHERE send_key=?",
        (occurred_at, canonical_bytes(event), send_key),
    )
    store_public_event(connection, event)
    connection.commit()
    return event


def _mark_unknown(connection: sqlite3.Connection, row: sqlite3.Row, wire: bytes, dispatch_ref: str, occurred_at: str, evidence: bytes) -> dict[str, Any]:
    event = public_event(
        connection, "DISPATCH_UNKNOWN", inbox_id=row["inbox_id"], occurred_at=occurred_at,
        payload_material=wire, sku_id=row["sku_id"], prospect_key=row["prospect_key"],
        thread_material=row["thread_key"].encode("utf-8"), message_material=row["message_id"].encode("utf-8"),
        send_key=row["send_key"], evidence_material=evidence, readiness="RECONCILE_REQUIRED",
    )
    connection.execute("BEGIN IMMEDIATE")
    changed = connection.execute(
        """
        UPDATE drafts SET state='UNKNOWN_EFFECT', readiness='RECONCILE_REQUIRED', event_json=?
        WHERE send_key=? AND dispatch_ref=? AND state='DISPATCHING'
        """,
        (canonical_bytes(event), row["send_key"], dispatch_ref),
    )
    if changed.rowcount != 1:
        connection.rollback()
        raise UnknownEffectError("dispatch state changed before UNKNOWN_EFFECT could be recorded")
    store_public_event(connection, event)
    connection.commit()
    return event


def reconcile_dispatch(
    connection: sqlite3.Connection,
    *,
    send_key: str,
    resolution: str,
    evidence_ref: str,
    evidence: bytes,
    occurred_at: str,
) -> dict[str, Any]:
    if resolution not in {"MTA_ACCEPTED", "NOT_ACCEPTED"} or not OPAQUE_RE.fullmatch(evidence_ref):
        raise SwarmMailError("dispatch resolution or evidence reference is invalid")
    if not evidence:
        raise SwarmMailError("dispatch reconciliation needs retained evidence bytes")
    occurred_at = parse_time(occurred_at)
    connection.commit()
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM drafts WHERE send_key=?", (send_key,)).fetchone()
        if not row or row["state"] not in {"DISPATCHING", "UNKNOWN_EFFECT"}:
            raise SwarmMailError("only an unknown dispatch can be reconciled")
        wire = _wire_message(connection, row)
        combined = evidence_ref.encode("utf-8") + b"\0" + evidence
        event_type = "MTA_ACCEPTED" if resolution == "MTA_ACCEPTED" else "DISPATCH_NOT_ACCEPTED"
        readiness = "MTA_ACCEPTED" if resolution == "MTA_ACCEPTED" else "NOT_ACCEPTED_FINAL"
        event = public_event(
            connection, event_type, inbox_id=row["inbox_id"], occurred_at=occurred_at,
            payload_material=wire, sku_id=row["sku_id"], prospect_key=row["prospect_key"],
            thread_material=row["thread_key"].encode("utf-8"), message_material=row["message_id"].encode("utf-8"),
            send_key=send_key, evidence_material=combined, readiness=readiness,
        )
        state = "MTA_ACCEPTED" if resolution == "MTA_ACCEPTED" else "NOT_ACCEPTED"
        accepted_at = occurred_at if resolution == "MTA_ACCEPTED" else None
        connection.execute(
            """
            UPDATE drafts SET state=?, readiness=?, mta_accepted_at=COALESCE(mta_accepted_at,?), event_json=?
            WHERE send_key=? AND state IN ('DISPATCHING','UNKNOWN_EFFECT')
            """,
            (state, readiness, accepted_at, canonical_bytes(event), send_key),
        )
        store_public_event(connection, event)
        return event


def record_transport_event(
    connection: sqlite3.Connection,
    *,
    send_key: str,
    transport_event_key: str,
    event_type: str,
    evidence_ref: str,
    evidence: bytes,
    occurred_at: str,
) -> dict[str, Any]:
    allowed = {"PROVIDER_DELIVERY_REPORTED", "SOFT_BOUNCE_REPORTED", "HARD_BOUNCE_REPORTED", "COMPLAINT_REPORTED"}
    if event_type not in allowed or not ID_RE.fullmatch(transport_event_key) or not OPAQUE_RE.fullmatch(evidence_ref) or not evidence:
        raise SwarmMailError("transport event key, type, or evidence is invalid")
    occurred_at = parse_time(occurred_at)
    evidence_sha = sha256_bytes(evidence_ref.encode("utf-8") + b"\0" + evidence)
    connection.commit()
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT * FROM transport_events WHERE transport_event_key=?", (transport_event_key,),
        ).fetchone()
        if existing:
            if (
                existing["send_key"], existing["event_type"], existing["evidence_sha256"], existing["occurred_at"]
            ) != (send_key, event_type, evidence_sha, occurred_at):
                raise CollisionError("transport event key reused with different evidence")
            return json.loads(existing["event_json"])
        row = connection.execute("SELECT * FROM drafts WHERE send_key=?", (send_key,)).fetchone()
        if not row or row["state"] not in {"MTA_ACCEPTED", "DELIVERY_REPORTED"}:
            raise SwarmMailError("transport report requires an MTA-accepted, non-final draft")
        if row["state"] == "DELIVERY_REPORTED" and event_type in {
            "PROVIDER_DELIVERY_REPORTED", "SOFT_BOUNCE_REPORTED",
        }:
            raise SwarmMailError("delivery report is already final for non-adverse transitions")
        if event_type == "PROVIDER_DELIVERY_REPORTED":
            state, readiness = "DELIVERY_REPORTED", "PROVIDER_REPORTED"
        elif event_type == "SOFT_BOUNCE_REPORTED":
            state, readiness = "MTA_ACCEPTED", "SOFT_BOUNCE_REPORTED"
        else:
            state, readiness = "SUPPRESSED", "DO_NOT_SEND"
        event_material = evidence_ref.encode("utf-8") + b"\0" + evidence
        event = public_event(
            connection, event_type, inbox_id=row["inbox_id"], occurred_at=occurred_at,
            payload_material=event_material, sku_id=row["sku_id"], prospect_key=row["prospect_key"],
            thread_material=row["thread_key"].encode("utf-8"), message_material=row["message_id"].encode("utf-8"),
            send_key=send_key, evidence_material=event_material, readiness=readiness,
        )
        connection.execute(
            "INSERT INTO transport_events VALUES (?,?,?,?,?,?)",
            (transport_event_key, send_key, event_type, evidence_sha, occurred_at, canonical_bytes(event)),
        )
        provider_at = occurred_at if event_type == "PROVIDER_DELIVERY_REPORTED" else None
        connection.execute(
            """
            UPDATE drafts SET state=?, readiness=?, provider_reported_at=COALESCE(provider_reported_at,?), event_json=?
            WHERE send_key=? AND state IN ('MTA_ACCEPTED','DELIVERY_REPORTED')
            """,
            (state, readiness, provider_at, canonical_bytes(event), send_key),
        )
        if event_type in {"HARD_BOUNCE_REPORTED", "COMPLAINT_REPORTED"}:
            reason = "PERMANENT_BOUNCE" if event_type == "HARD_BOUNCE_REPORTED" else "COMPLAINT"
            _put_suppression(connection, row["recipient"], reason, evidence_ref, occurred_at)
        store_public_event(connection, event)
        return event


def _load_reply_intake():
    spec = importlib.util.spec_from_file_location("commons_reply_intake", REPLY_INTAKE_PATH)
    if not spec or not spec.loader:
        raise SwarmMailError("canonical reply intake is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _linked_draft(connection: sqlite3.Connection, message: EmailMessage) -> sqlite3.Row | None:
    references = (message.get("References") or "").split()
    reply_to = (message.get("In-Reply-To") or "").split()
    for message_id in reversed(references + reply_to):
        row = connection.execute("SELECT * FROM drafts WHERE message_id=?", (message_id.strip(),)).fetchone()
        if row:
            return row
        match = re.fullmatch(r"(<swarm-[0-9a-f]{32})@[A-Za-z0-9.-]{1,253}>", message_id.strip())
        if match:
            rows = connection.execute(
                "SELECT * FROM drafts WHERE substr(message_id,1,instr(message_id,'@')-1)=? LIMIT 2",
                (match.group(1),),
            ).fetchall()
            if len(rows) == 1:
                return rows[0]
    return None


def ingest_message(
    connection: sqlite3.Connection,
    *,
    inbox_id: str,
    raw: bytes,
    requested_classification: str,
    mta_envelope_ref: str,
    mta_evidence: bytes,
    mta_auth_verdict: str,
    occurred_at: str,
) -> dict[str, Any]:
    if (
        requested_classification not in CLASSIFICATIONS
        or not OPAQUE_RE.fullmatch(mta_envelope_ref)
        or not mta_evidence
        or mta_auth_verdict not in MTA_AUTH_VERDICTS
    ):
        raise SwarmMailError("classification, MTA verdict, or MTA envelope evidence is invalid")
    occurred_at = parse_time(occurred_at)
    if not raw or len(raw) > 25_000_000:
        raise SwarmMailError("RFC 822 payload is empty or over 25 MB")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    sender = normalize_address(message.get("From", ""))
    recipients = [
        normalize_address(address)
        for _name, address in getaddresses(message.get_all("To", []) + message.get_all("Cc", []))
        if address
    ]
    connection.commit()
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        inbox = connection.execute(
            "SELECT * FROM inboxes WHERE inbox_id=? AND state='MEASURED'", (inbox_id,),
        ).fetchone()
        if not inbox:
            raise SwarmMailError("private inbox is not measured")
        if inbox["address"] not in recipients:
            raise SwarmMailError("message is not addressed to the selected inbox")
        sender_ref = _recipient_commitment(connection, sender)
        linked = _linked_draft(connection, message)
        attributed = bool(
            linked
            and linked["inbox_id"] == inbox_id
            and linked["recipient_commitment"] == sender_ref
            and linked["mta_accepted_at"] is not None
            and mta_auth_verdict == "PASS"
        )
        classification = requested_classification if attributed else "NEEDS_HUMAN"
        sku_id = linked["sku_id"] if attributed else None
        prospect_key = linked["prospect_key"] if attributed else None
        thread_private = linked["thread_key"] if attributed else opaque_ref(connection, "thread-private", raw)
        payload_sha = sha256_bytes(raw)
        evidence_material = (
            mta_auth_verdict.encode("ascii") + b"\0" + mta_envelope_ref.encode("utf-8") + b"\0" + mta_evidence
        )
        evidence_sha = sha256_bytes(evidence_material)
        header_id = (message.get("Message-ID") or "").strip()
        message_private = header_id.encode("utf-8") if header_id else raw
        message_key = opaque_ref(connection, "inbound-private", message_private)
        attribution_state = (
            "OUTBOUND_THREAD_AND_TRUSTED_MTA_AUTH_PASS"
            if attributed else "UNATTRIBUTED_NEEDS_HUMAN"
        )
        existing = connection.execute(
            "SELECT * FROM inbound_messages WHERE message_key=?", (message_key,),
        ).fetchone()
        immutable = (
            thread_private, inbox_id, sender_ref, linked["send_key"] if linked and attributed else None,
            sku_id, prospect_key, payload_sha, evidence_sha, classification, attribution_state,
        )
        if existing:
            recorded = (
                existing["thread_key"], existing["inbox_id"], existing["sender_commitment"],
                existing["linked_send_key"], existing["sku_id"], existing["prospect_key"],
                existing["payload_sha256"], existing["mta_evidence_sha256"], existing["classification"],
                existing["attribution_state"],
            )
            if recorded != immutable:
                raise CollisionError("inbound message replay changed bytes, evidence, attribution, or classification")
            if classification == "OPT_OUT" and not connection.execute(
                "SELECT 1 FROM suppressions WHERE recipient_commitment=?", (sender_ref,),
            ).fetchone():
                _put_suppression(connection, sender, "OPT_OUT", mta_envelope_ref, occurred_at)
            return json.loads(existing["event_json"])
        canonical_reply: bytes | None = None
        if attributed:
            reply_intake = _load_reply_intake()
            envelope = {
                "event_ref": opaque_ref(connection, "reply-envelope", mta_envelope_ref.encode("utf-8") + raw),
                "received_at": occurred_at,
                "prospect_key": prospect_key,
                "payload_sha256": payload_sha,
                "classification": classification,
            }
            reply_intake.validate_envelope(envelope)
            receipt = reply_intake.build_receipt(envelope)
            reply_intake.validate_receipt(receipt)
            canonical_reply = reply_intake.canonical_bytes(receipt)
        event = public_event(
            connection, "INBOUND_RECORDED", inbox_id=inbox_id, occurred_at=occurred_at,
            payload_material=raw, sku_id=sku_id, prospect_key=prospect_key,
            thread_material=thread_private.encode("utf-8"), message_material=message_private,
            send_key=linked["send_key"] if attributed else None, classification=classification,
            evidence_material=evidence_material, readiness=attribution_state,
        )
        connection.execute(
            "INSERT INTO inbound_messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (message_key, thread_private, inbox_id, sender, sender_ref, linked["send_key"] if attributed else None,
             sku_id, prospect_key, raw, payload_sha, evidence_sha, occurred_at, classification, attribution_state,
             canonical_reply, canonical_bytes(event)),
        )
        if classification == "OPT_OUT":
            _put_suppression(connection, sender, "OPT_OUT", mta_envelope_ref, occurred_at)
        store_public_event(connection, event)
        return event


def redacted_status(connection: sqlite3.Connection) -> dict[str, Any]:
    inboxes = []
    for row in connection.execute("SELECT * FROM inboxes ORDER BY inbox_id"):
        inboxes.append({
            "inbox_id": row["inbox_id"],
            "model_family": row["model_family"],
            "state": row["state"],
            "address_ref": opaque_ref(connection, "address", row["address"].encode("utf-8")) if row["address"] else None,
        })
    counts = {
        "measured_inboxes": connection.execute("SELECT COUNT(*) FROM inboxes WHERE state='MEASURED'").fetchone()[0],
        "drafted_messages": connection.execute("SELECT COUNT(*) FROM drafts").fetchone()[0],
        "queued_messages": connection.execute("SELECT COUNT(*) FROM drafts WHERE queued_at IS NOT NULL").fetchone()[0],
        "unknown_effect_dispatches": connection.execute("SELECT COUNT(*) FROM drafts WHERE state IN ('DISPATCHING','UNKNOWN_EFFECT')").fetchone()[0],
        "mta_accepted_messages": connection.execute("SELECT COUNT(*) FROM drafts WHERE mta_accepted_at IS NOT NULL").fetchone()[0],
        "provider_reported_deliveries": connection.execute("SELECT COUNT(*) FROM drafts WHERE provider_reported_at IS NOT NULL").fetchone()[0],
        "inbound_messages": connection.execute("SELECT COUNT(*) FROM inbound_messages").fetchone()[0],
        "global_suppressions": connection.execute("SELECT COUNT(*) FROM suppressions").fetchone()[0],
        "public_events": connection.execute("SELECT COUNT(*) FROM events").fetchone()[0],
    }
    return {
        "kind": "SWARM_MAIL_PRIVATE_RUNTIME_STATUS",
        "inboxes": inboxes,
        "counts": counts,
        "commercial_success": "UNMEASURED_BY_MAIL",
    }


def redacted_threads(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT thread_key, inbox_id, sku_id, prospect_key, COUNT(*) AS messages, MAX(received_at) AS last_at
        FROM inbound_messages GROUP BY thread_key, inbox_id, sku_id, prospect_key ORDER BY last_at DESC
        """
    ).fetchall()
    return {
        "kind": "SWARM_MAIL_REDACTED_THREADS",
        "threads": [
            {
                "thread_ref": opaque_ref(connection, "thread", row["thread_key"].encode("utf-8")),
                "inbox_id": row["inbox_id"],
                "sku_id": row["sku_id"],
                "prospect_ref": opaque_ref(connection, "prospect", row["prospect_key"].encode("utf-8")) if row["prospect_key"] else None,
                "messages": row["messages"],
                "last_at": row["last_at"],
            }
            for row in rows
        ],
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    route = sub.add_parser("route")
    route.add_argument("sku_id")
    init = sub.add_parser("init")
    init.add_argument("--db", type=Path, required=True)
    proof = sub.add_parser("commit-proof")
    proof.add_argument("--db", type=Path, required=True)
    proof.add_argument("--proof-bundle", type=Path, required=True)
    provision = sub.add_parser("provision")
    provision.add_argument("--db", type=Path, required=True)
    provision.add_argument("--inbox-id", required=True)
    provision.add_argument("--address", required=True)
    provision.add_argument("--proof-bundle", type=Path, required=True)
    provision.add_argument("--occurred-at")
    suppress = sub.add_parser("suppress")
    suppress.add_argument("--db", type=Path, required=True)
    suppress.add_argument("--recipient", required=True)
    suppress.add_argument("--reason", choices=sorted(SUPPRESSION_REASONS), required=True)
    suppress.add_argument("--evidence-ref", required=True)
    suppress.add_argument("--occurred-at")
    queue = sub.add_parser("draft")
    queue.add_argument("--db", type=Path, required=True)
    queue.add_argument("--recipient", required=True)
    queue.add_argument("--sku-id", required=True)
    queue.add_argument("--prospect-key", required=True)
    queue.add_argument("--subject-file", type=Path, required=True)
    queue.add_argument("--body-file", type=Path, required=True)
    queue.add_argument("--send-key", required=True)
    queue.add_argument("--occurred-at")
    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--db", type=Path, required=True)
    dispatch.add_argument("--send-key", required=True)
    dispatch.add_argument("--sendmail-bin", type=Path, required=True)
    dispatch.add_argument("--occurred-at")
    reconcile = sub.add_parser("reconcile-dispatch")
    reconcile.add_argument("--db", type=Path, required=True)
    reconcile.add_argument("--send-key", required=True)
    reconcile.add_argument("--resolution", choices=["MTA_ACCEPTED", "NOT_ACCEPTED"], required=True)
    reconcile.add_argument("--evidence-ref", required=True)
    reconcile.add_argument("--evidence-file", type=Path, required=True)
    reconcile.add_argument("--occurred-at")
    record = sub.add_parser("record-transport")
    record.add_argument("--db", type=Path, required=True)
    record.add_argument("--send-key", required=True)
    record.add_argument("--transport-event-key", required=True)
    record.add_argument("--event-type", choices=["PROVIDER_DELIVERY_REPORTED", "SOFT_BOUNCE_REPORTED", "HARD_BOUNCE_REPORTED", "COMPLAINT_REPORTED"], required=True)
    record.add_argument("--evidence-ref", required=True)
    record.add_argument("--evidence-file", type=Path, required=True)
    record.add_argument("--occurred-at")
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--db", type=Path, required=True)
    ingest.add_argument("--inbox-id", required=True)
    ingest.add_argument("--eml", type=Path, required=True)
    ingest.add_argument("--classification", choices=sorted(CLASSIFICATIONS), required=True)
    ingest.add_argument("--mta-envelope-ref", required=True)
    ingest.add_argument("--mta-evidence-file", type=Path, required=True)
    ingest.add_argument("--mta-auth-verdict", choices=sorted(MTA_AUTH_VERDICTS), required=True)
    ingest.add_argument("--occurred-at")
    status = sub.add_parser("status")
    status.add_argument("--db", type=Path, required=True)
    threads = sub.add_parser("threads")
    threads.add_argument("--db", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            manifest = validate_manifest()
            result: Any = {"status": "OK", "inboxes": len(manifest["inboxes"]), "skus": len(commerce_skus())}
        elif args.command == "route":
            result = route_sku(args.sku_id)
        else:
            connection = open_db(args.db)
            if args.command == "init":
                result = redacted_status(connection)
            elif args.command == "commit-proof":
                result = proof_bundle_commitment(connection, args.proof_bundle.read_bytes())
            elif args.command == "provision":
                result = provision_inbox(connection, args.inbox_id, args.address, args.proof_bundle.read_bytes(), args.occurred_at or utc_now())
            elif args.command == "suppress":
                result = suppress_recipient(connection, args.recipient, args.reason, args.evidence_ref, args.occurred_at or utc_now())
            elif args.command == "draft":
                result = queue_message(
                    connection, recipient=args.recipient, sku_id=args.sku_id, prospect_key=args.prospect_key,
                    subject=_read_text(args.subject_file), body=_read_text(args.body_file),
                    send_key=args.send_key, occurred_at=args.occurred_at or utc_now(),
                )
            elif args.command == "dispatch":
                result = dispatch_message(connection, args.send_key, args.sendmail_bin, args.occurred_at or utc_now())
            elif args.command == "reconcile-dispatch":
                result = reconcile_dispatch(
                    connection, send_key=args.send_key, resolution=args.resolution,
                    evidence_ref=args.evidence_ref, evidence=args.evidence_file.read_bytes(),
                    occurred_at=args.occurred_at or utc_now(),
                )
            elif args.command == "record-transport":
                result = record_transport_event(
                    connection, send_key=args.send_key, transport_event_key=args.transport_event_key,
                    event_type=args.event_type, evidence_ref=args.evidence_ref,
                    evidence=args.evidence_file.read_bytes(), occurred_at=args.occurred_at or utc_now(),
                )
            elif args.command == "ingest":
                result = ingest_message(
                    connection, inbox_id=args.inbox_id, raw=args.eml.read_bytes(),
                    requested_classification=args.classification, mta_envelope_ref=args.mta_envelope_ref,
                    mta_evidence=args.mta_evidence_file.read_bytes(), mta_auth_verdict=args.mta_auth_verdict,
                    occurred_at=args.occurred_at or utc_now(),
                )
            elif args.command == "status":
                result = redacted_status(connection)
            elif args.command == "threads":
                result = redacted_threads(connection)
            else:
                raise AssertionError(args.command)
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except OutboundIdentityError as error:
        print(
            json.dumps(error.decision, sort_keys=True, ensure_ascii=False),
            file=sys.stderr,
        )
        return 4
    except CollisionError as error:
        print(f"COLLISION: {error}", file=sys.stderr)
        return 2
    except UnknownEffectError as error:
        print(f"UNKNOWN_EFFECT: {error}", file=sys.stderr)
        return 3
    except (OSError, sqlite3.Error, subprocess.SubprocessError, SwarmMailError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
