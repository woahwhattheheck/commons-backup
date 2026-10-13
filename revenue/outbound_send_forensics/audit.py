#!/usr/bin/env python3
"""Offline, fail-closed audit of outbound sends against connector-native lease evidence."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from revenue.outbound_connector_lease.key import (
    BRANCH_PREFIX,
    LeaseKeyError,
    SUPPORTED_REPLY_PROVIDERS,
    compile_document as compile_lease_document,
)

LEGACY_INPUT_SCHEMA = "outbound-send-forensics/v1"
LABEL_INPUT_SCHEMA = "outbound-send-forensics/v2"
INPUT_SCHEMA = "outbound-send-forensics/v3"
RECEIPT_SCHEMA = "outbound-send-forensics-receipt/v3"
BATCH_SCHEMA = "outbound-send-forensics-batch/v3"
AUTHORITY_KEY_SCHEMA = "outbound-send-forensics-authority-key/v1"
AUTHORITY_ATTESTATION_SCHEMA = "outbound-send-forensics-authority-attestation/v1"
CANONICAL_LEASE_REPOSITORY = "woahwhattheheck/commons"
HOST_AUTHORITY_KEY_PATH = Path("/etc/commons/outbound-send-forensics/authority-key.json")
MAX_AUTHORITY_KEY_BYTES = 4096

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._:/+\-]{0,190}$")
_BRANCH_RE = re.compile(r"^outbound-connector-lease/v1/[0-9a-f]{64}$")
_RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
_REPOSITORY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}/[a-z0-9][a-z0-9._-]{0,99}$")

CLASS_PROTECTED = "PROTECTED_PRE_SEND"
CLASS_POST_SEND = "POST_SEND_LEASE_VIOLATION"
CLASS_MISSING = "MISSING_LEASE"
CLASS_MISMATCH = "SEAM_MISMATCH"
CLASS_UNTRUSTED = "AMBIGUOUS_UNTRUSTED_EVIDENCE"
DUPLICATE_FLAG = "DUPLICATE_SEND_SAME_SEAM"
CLASSIFICATIONS = (
    CLASS_PROTECTED,
    CLASS_POST_SEND,
    CLASS_MISSING,
    CLASS_MISMATCH,
    CLASS_UNTRUSTED,
)


class ForensicsError(ValueError):
    pass


def _strict_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ForensicsError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(raw):
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ForensicsError(f"non-finite JSON number: {token}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ForensicsError("invalid JSON") from exc
    if type(value) is not dict:
        raise ForensicsError("input must be a JSON object")
    return value


def _exact(value, fields, name):
    if type(value) is not dict:
        raise ForensicsError(f"{name} must be an object")
    actual = set(value)
    if actual != fields:
        missing = sorted(fields - actual)
        extra = sorted(actual - fields)
        bits = []
        if missing:
            bits.append("missing=" + ",".join(missing))
        if extra:
            bits.append("extra=" + ",".join(extra))
        raise ForensicsError(f"{name} requires exact fields ({'; '.join(bits)})")
    return value


def _token(value, field):
    if type(value) is not str:
        raise ForensicsError(f"{field} must be a string")
    token = value.strip().casefold()
    if not token or len(token) > 191 or _TOKEN_RE.fullmatch(token) is None:
        raise ForensicsError(f"{field} must use 1..191 lowercase-token chars [a-z0-9._:/+-]")
    return token


def _enum(value, allowed, field):
    if type(value) is not str:
        raise ForensicsError(f"{field} must be a string")
    normalized = value.strip().casefold()
    if normalized not in allowed:
        raise ForensicsError(f"{field} must be one of: {','.join(sorted(allowed))}")
    return normalized


def _sha256(value, field):
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ForensicsError(f"{field} must be exactly 64 lowercase hex characters")
    return value


def _sha1(value, field):
    if type(value) is not str or _SHA1_RE.fullmatch(value) is None:
        raise ForensicsError(f"{field} must be exactly 40 lowercase hex characters")
    return value


def _branch(value, field):
    if type(value) is not str or _BRANCH_RE.fullmatch(value) is None:
        raise ForensicsError(f"{field} must be {BRANCH_PREFIX}<64-lowercase-hex>")
    return value


def _repository(value, field):
    if type(value) is not str:
        raise ForensicsError(f"{field} must be a string")
    normalized = value.strip().casefold()
    if _REPOSITORY_RE.fullmatch(normalized) is None:
        raise ForensicsError(f"{field} must be owner/repository using GitHub-name characters")
    return normalized


def _timestamp(value, field):
    if type(value) is not str or not value.strip():
        raise ForensicsError(f"{field} must be a non-empty RFC3339 timestamp")
    raw = value.strip()
    if _RFC3339_RE.fullmatch(raw) is None:
        raise ForensicsError(f"{field} must be strict RFC3339 with T, seconds, and timezone")
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ForensicsError(f"{field} must be a valid RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ForensicsError(f"{field} must include an explicit timezone offset")
    utc = parsed.astimezone(timezone.utc)
    canonical = utc.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return utc, canonical


def _canonical_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _send_attestation_payload(send, seam_sha256):
    return {
        "schema": AUTHORITY_ATTESTATION_SCHEMA,
        "kind": "provider-send",
        "seam_sha256": seam_sha256,
        "provider": send["provider"],
        "event_id": send["event_id"],
        "sent_at": send["sent_at"],
        "status": send["status"],
        "receipt_sha256": send["receipt_sha256"],
    }


def _lease_attestation_payload(lease):
    return {
        "schema": AUTHORITY_ATTESTATION_SCHEMA,
        "kind": "github-branch-create",
        "repository_full_name": lease["repository_full_name"],
        "branch": lease["branch"],
        "created_at": lease["created_at"],
        "result": lease["result"],
        "base_sha": lease["base_sha"],
        "receipt_sha256": lease["receipt_sha256"],
    }


def _valid_attestation(key, payload, supplied_mac):
    if key is None:
        return False
    expected = hmac.new(key, _canonical_bytes(payload), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied_mac)


def _normalize_send(raw, input_schema, authority_key, seam_sha256):
    if input_schema == INPUT_SCHEMA:
        send = _exact(
            raw,
            {
                "provider",
                "event_id",
                "sent_at",
                "status",
                "receipt_sha256",
                "attestation_hmac_sha256",
            },
            "record.send",
        )
        authority_claim = None
    else:
        send = _exact(
            raw,
            {"provider", "event_id", "sent_at", "authority", "status", "receipt_sha256"},
            "record.send",
        )
        authority_claim = _enum(
            send["authority"],
            {"provider-receipt", "caller-assertion"},
            "record.send.authority",
        )
    provider = _enum(send["provider"], set(SUPPORTED_REPLY_PROVIDERS), "record.send.provider")
    event_id = _token(send["event_id"], "record.send.event_id")
    sent_dt, sent_at = _timestamp(send["sent_at"], "record.send.sent_at")
    status = _enum(send["status"], {"sent", "ambiguous"}, "record.send.status")
    receipt_sha256 = _sha256(send["receipt_sha256"], "record.send.receipt_sha256")
    normalized = {
        "provider": provider,
        "event_id": event_id,
        "sent_dt": sent_dt,
        "sent_at": sent_at,
        "status": status,
        "receipt_sha256": receipt_sha256,
        "authority_claim": authority_claim,
        "authority_authenticated": False,
    }
    if input_schema == INPUT_SCHEMA:
        supplied_mac = _sha256(
            send["attestation_hmac_sha256"], "record.send.attestation_hmac_sha256"
        )
        normalized["attestation_hmac_sha256"] = supplied_mac
        normalized["authority_authenticated"] = _valid_attestation(
            authority_key, _send_attestation_payload(normalized, seam_sha256), supplied_mac
        )
    else:
        normalized["attestation_hmac_sha256"] = None
    return normalized


def _normalize_lease(raw, input_schema, authority_key):
    if raw is None:
        return None
    common_fields = {
        "branch",
        "created_at",
        "result",
        "base_sha",
        "receipt_sha256",
    }
    if input_schema == LEGACY_INPUT_SCHEMA:
        lease = _exact(raw, common_fields | {"authority"}, "record.lease_create")
        repository_full_name = None
        authority_claim = _enum(
            lease["authority"],
            {"github-create-result", "caller-assertion"},
            "record.lease_create.authority",
        )
        supplied_mac = None
    elif input_schema == LABEL_INPUT_SCHEMA:
        lease = _exact(
            raw,
            common_fields | {"authority", "repository_full_name"},
            "record.lease_create",
        )
        repository_full_name = _repository(
            lease["repository_full_name"], "record.lease_create.repository_full_name"
        )
        authority_claim = _enum(
            lease["authority"],
            {"github-create-result", "caller-assertion"},
            "record.lease_create.authority",
        )
        supplied_mac = None
    else:
        lease = _exact(
            raw,
            common_fields | {"repository_full_name", "attestation_hmac_sha256"},
            "record.lease_create",
        )
        repository_full_name = _repository(
            lease["repository_full_name"], "record.lease_create.repository_full_name"
        )
        authority_claim = None
        supplied_mac = _sha256(
            lease["attestation_hmac_sha256"],
            "record.lease_create.attestation_hmac_sha256",
        )
    branch = _branch(lease["branch"], "record.lease_create.branch")
    created_dt, created_at = _timestamp(
        lease["created_at"], "record.lease_create.created_at"
    )
    result = _enum(
        lease["result"],
        {"created", "exists", "ambiguous", "failed"},
        "record.lease_create.result",
    )
    base_sha = _sha1(lease["base_sha"], "record.lease_create.base_sha")
    receipt_sha256 = _sha256(
        lease["receipt_sha256"], "record.lease_create.receipt_sha256"
    )
    normalized = {
        "repository_full_name": repository_full_name,
        "branch": branch,
        "created_dt": created_dt,
        "created_at": created_at,
        "result": result,
        "base_sha": base_sha,
        "receipt_sha256": receipt_sha256,
        "authority_claim": authority_claim,
        "authority_authenticated": False,
        "attestation_hmac_sha256": supplied_mac,
    }
    if input_schema == INPUT_SCHEMA:
        normalized["authority_authenticated"] = _valid_attestation(
            authority_key, _lease_attestation_payload(normalized), supplied_mac
        )
    return normalized


def _normalize_record(raw, input_schema, authority_key):
    record = _exact(raw, {"record_id", "seam", "send", "lease_create"}, "record")
    record_id = _token(record["record_id"], "record.record_id")
    try:
        compiled = compile_lease_document(record["seam"])
    except LeaseKeyError as exc:
        raise ForensicsError(f"record.seam invalid: {exc}") from exc
    return {
        "record_id": record_id,
        "compiled": compiled,
        "send": _normalize_send(
            record["send"], input_schema, authority_key, compiled["seam_sha256"]
        ),
        "lease": _normalize_lease(record["lease_create"], input_schema, authority_key),
        "input_schema": input_schema,
    }


def _classify(record):
    send = record["send"]
    lease = record["lease"]
    expected_branch = record["compiled"]["branch"]
    if not send["authority_authenticated"] or send["status"] != "sent":
        return CLASS_UNTRUSTED, [
            "provider send lacks a valid host attestation over exact SENT receipt evidence"
        ]
    if lease is None:
        return CLASS_MISSING, [
            "host-attested provider SENT exists but no lease-create evidence was supplied"
        ]
    if not lease["authority_authenticated"] or lease["result"] != "created":
        return CLASS_UNTRUSTED, [
            "lease evidence lacks a valid host attestation over an exact successful GitHub create result"
        ]
    if lease["repository_full_name"] != CANONICAL_LEASE_REPOSITORY:
        return CLASS_UNTRUSTED, [
            f"lease create evidence is not from canonical repository {CANONICAL_LEASE_REPOSITORY}"
        ]
    if lease["branch"] != expected_branch:
        return CLASS_MISMATCH, [
            "host-attested lease evidence is for a different canonical seam branch"
        ]
    if lease["created_dt"] >= send["sent_dt"]:
        return CLASS_POST_SEND, [
            "host-attested lease create was not strictly earlier than provider SENT"
        ]
    return CLASS_PROTECTED, [
        "host-attested matching lease create in the canonical repository is strictly earlier than host-attested provider SENT"
    ]


def _payload(record):
    classification, reasons = _classify(record)
    send = record["send"]
    lease = record["lease"]
    return {
        "schema": RECEIPT_SCHEMA,
        "record_id": record["record_id"],
        "source_input_schema": record["input_schema"],
        "classification": classification,
        "reasons": reasons,
        "dnr": True,
        "expected_lease_repository": CANONICAL_LEASE_REPOSITORY,
        "expected_branch": record["compiled"]["branch"],
        "seam_sha256": record["compiled"]["seam_sha256"],
        "send_provider": send["provider"],
        "send_event_id": send["event_id"],
        "send_at_utc": send["sent_at"],
        "send_receipt_sha256": send["receipt_sha256"],
        "send_authority_authenticated": send["authority_authenticated"],
        "lease_authority_authenticated": False if lease is None else lease["authority_authenticated"],
        "lease_repository_full_name": None if lease is None else lease["repository_full_name"],
        "lease_branch": None if lease is None else lease["branch"],
        "lease_created_at_utc": None if lease is None else lease["created_at"],
        "lease_receipt_sha256": None if lease is None else lease["receipt_sha256"],
        "batch_flags": [],
        "same_seam_send_count": 1,
    }


def _seal(payload):
    bare = dict(payload)
    bare.pop("receipt_sha256", None)
    return {**bare, "receipt_sha256": _digest(bare)}


def _input_schema(top):
    if type(top["schema"]) is not str:
        raise ForensicsError("input.schema must be a string")
    schema = top["schema"]
    allowed = (LEGACY_INPUT_SCHEMA, LABEL_INPUT_SCHEMA, INPUT_SCHEMA)
    if schema not in allowed:
        raise ForensicsError("input.schema must be one of: " + ",".join(allowed))
    return schema


def _audit_document(document, authority_key=None):
    top = _exact(document, {"schema", "records"}, "input")
    input_schema = _input_schema(top)
    if type(top["records"]) is not list or not top["records"]:
        raise ForensicsError("input.records must be a non-empty array")
    records = [
        _normalize_record(item, input_schema, authority_key)
        for item in top["records"]
    ]
    ids = [record["record_id"] for record in records]
    duplicate_ids = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        raise ForensicsError("duplicate record_id: " + ",".join(duplicate_ids))

    seen = {}
    for record in records:
        key = (record["send"]["provider"], record["send"]["event_id"])
        if key in seen:
            previous = seen[key]
            if (
                previous["send"]["sent_at"] != record["send"]["sent_at"]
                or previous["send"]["receipt_sha256"] != record["send"]["receipt_sha256"]
                or previous["compiled"]["branch"] != record["compiled"]["branch"]
            ):
                raise ForensicsError(
                    "contradictory duplicate provider event: " + ":".join(key)
                )
            raise ForensicsError("duplicate provider event: " + ":".join(key))
        seen[key] = record

    receipts = [_payload(record) for record in records]
    by_branch = defaultdict(list)
    for record, receipt in zip(records, receipts):
        send = record["send"]
        if send["authority_authenticated"] and send["status"] == "sent":
            by_branch[receipt["expected_branch"]].append(receipt)

    incidents = []
    for branch, group in sorted(by_branch.items()):
        if len(group) <= 1:
            continue
        for receipt in group:
            receipt["batch_flags"] = [DUPLICATE_FLAG]
            receipt["same_seam_send_count"] = len(group)
        incidents.append(
            {
                "expected_branch": branch,
                "send_count": len(group),
                "record_ids": sorted(item["record_id"] for item in group),
                "provider_events": sorted(
                    f"{item['send_provider']}:{item['send_event_id']}" for item in group
                ),
            }
        )

    sealed = sorted(
        (_seal(receipt) for receipt in receipts),
        key=lambda item: item["record_id"],
    )
    counts = Counter(item["classification"] for item in sealed)
    summary = {
        "records": len(sealed),
        "dnr_records": sum(1 for item in sealed if item["dnr"]),
        "duplicate_seams": len(incidents),
        "duplicate_send_records": sum(
            1 for item in sealed if DUPLICATE_FLAG in item["batch_flags"]
        ),
        **{name: counts.get(name, 0) for name in CLASSIFICATIONS},
    }
    payload = {
        "schema": BATCH_SCHEMA,
        "summary": summary,
        "incident_seams": incidents,
        "receipts": sealed,
    }
    return {**payload, "batch_sha256": _digest(payload)}


def audit_document(document):
    """Historical/claim-only audit. Never authenticates caller-supplied authority."""
    return _audit_document(document, authority_key=None)


def audit_json(raw):
    return audit_document(strict_loads(raw))


def _open_host_authority_key():
    path = HOST_AUTHORITY_KEY_PATH
    if not path.is_absolute():
        raise ForensicsError("host authority key path must be absolute")
    file_flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        file_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        file_flags |= os.O_NOFOLLOW

    if os.name != "posix" or not hasattr(os, "O_DIRECTORY"):
        try:
            return os.open(path, file_flags)
        except OSError as exc:
            raise ForensicsError(f"host authority key unavailable: {path}") from exc

    dir_flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        dir_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        dir_flags |= os.O_NOFOLLOW
    try:
        parent_fd = os.open("/", dir_flags)
    except OSError as exc:
        raise ForensicsError("cannot open filesystem root for host authority key") from exc
    try:
        for component in path.parts[1:-1]:
            try:
                next_fd = os.open(component, dir_flags, dir_fd=parent_fd)
            except OSError as exc:
                raise ForensicsError(
                    f"host authority key ancestor is unavailable or symlinked: {component}"
                ) from exc
            os.close(parent_fd)
            parent_fd = next_fd
        try:
            return os.open(path.name, file_flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ForensicsError(f"host authority key unavailable: {path}") from exc
    finally:
        os.close(parent_fd)


def _read_host_authority_key():
    path = HOST_AUTHORITY_KEY_PATH
    fd = _open_host_authority_key()
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ForensicsError("host authority key must be a regular file")
        if os.name == "posix" and (stat.S_IMODE(before.st_mode) & 0o077):
            raise ForensicsError("host authority key must not be group/other accessible")
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, min(4096, MAX_AUTHORITY_KEY_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_AUTHORITY_KEY_BYTES:
                raise ForensicsError("host authority key exceeds size limit")
        after = os.fstat(fd)
        stable_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            getattr(before, "st_mtime_ns", int(before.st_mtime * 1_000_000_000)),
            getattr(before, "st_ctime_ns", int(before.st_ctime * 1_000_000_000)),
        )
        stable_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            getattr(after, "st_mtime_ns", int(after.st_mtime * 1_000_000_000)),
            getattr(after, "st_ctime_ns", int(after.st_ctime * 1_000_000_000)),
        )
        if stable_before != stable_after:
            raise ForensicsError("host authority key changed during read")
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ForensicsError("host authority key must be UTF-8 JSON") from exc
    key_doc = _exact(
        strict_loads(text),
        {"schema", "key_hex"},
        "host authority key",
    )
    if type(key_doc["schema"]) is not str or key_doc["schema"] != AUTHORITY_KEY_SCHEMA:
        raise ForensicsError(f"host authority key schema must be {AUTHORITY_KEY_SCHEMA}")
    key_hex = _sha256(key_doc["key_hex"], "host authority key.key_hex")
    return bytes.fromhex(key_hex)


def audit_current_document(document):
    """Current-authority audit. v3 evidence is authenticated by the fixed host key."""
    top = _exact(document, {"schema", "records"}, "input")
    schema = _input_schema(top)
    key = _read_host_authority_key() if schema == INPUT_SCHEMA else None
    return _audit_document(top, authority_key=key)


def audit_current_json(raw):
    return audit_current_document(strict_loads(raw))


def main(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Audit provider sends against canonical pre-send lease evidence"
    )
    parser.add_argument(
        "input", nargs="?", default="-", help="input JSON path, or '-' for stdin"
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        raw = (
            sys.stdin.read()
            if args.input == "-"
            else Path(args.input).read_text(encoding="utf-8")
        )
        result = audit_current_json(raw)
    except (ForensicsError, OSError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            result,
            sort_keys=True,
            indent=2 if args.pretty else None,
            separators=None if args.pretty else (",", ":"),
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())