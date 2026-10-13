#!/usr/bin/env python3
"""Deterministic provider-history preflight for canonical Muse publication v2.

This module does not contact any provider. It consumes a candidate snapshot
checked against a separately supplied retained-authority ledger of
provider-normalized send receipts and do-not-recontact evidence. Its strongest
positive result is CLEAR_FOR_MUSE_PREFLIGHT: retained authority is complete,
current, and contains no matching DNR/prior send. It never authorizes an
external send.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from typing import Any

SNAPSHOT_SCHEMA = "outbound-provider-preflight-snapshot/v1"
AUTHORITY_SCHEMA = "outbound-provider-preflight-retained-authority/v1"
REQUEST_SCHEMA = "outbound-provider-preflight-request/v1"
REPORT_SCHEMA = "outbound-provider-preflight-report/v1"
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_ROWS = 4096
MAX_SAFE_INT = (1 << 53) - 1
MAX_INT_DIGITS = 16
MAX_TEXT = 512

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+<>=-]*$")
ROUTE_KINDS = frozenset({"EMAIL", "CONTACT_FORM", "DIRECT_MESSAGE", "PORTAL_MESSAGE"})
PROVIDERS = frozenset({"GMAIL", "SLACK", "GITHUB", "FORM", "PORTAL", "OTHER"})

RESULTS = frozenset({
    "CLEAR_FOR_MUSE_PREFLIGHT",
    "HOLD_LEDGER_INCOMPLETE",
    "HOLD_AFTER_DNR",
    "HOLD_EXACT_INTENT_ALREADY_SENT",
    "HOLD_PUBLICATION_ALREADY_SENT",
    "HOLD_EVIDENCE_ORDERING",
    "HOLD_SOURCE_CONFLICT",
    "HOLD_RETAINED_AUTHORITY_MISMATCH",
    "HOLD_NOT_CURRENT",
})

# Public convenience value only. compile_report() owns literal hard-false values
# so mutation/rebinding of this object cannot mint authority.
AUTHORITY_FALSE = {
    "externalSendAuthorized": False,
    "providerMutationAuthorized": False,
    "paymentAuthorized": False,
    "contractAuthorized": False,
    "submissionAuthorized": False,
    "revenueRecognized": False,
}


class PreflightError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise PreflightError(code)


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            _fail("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _reject_float(_: str) -> Any:
    _fail("FLOAT_NOT_ALLOWED")


def _reject_constant(_: str) -> Any:
    _fail("NONFINITE_NUMBER")


def _parse_int(text: str) -> int:
    if not isinstance(text, str):
        _fail("INT_OUT_OF_RANGE")
    digits = text[1:] if text.startswith("-") else text
    if not digits.isdigit() or len(digits) > MAX_INT_DIGITS:
        _fail("INT_OUT_OF_RANGE")
    try:
        value = int(text, 10)
    except ValueError as exc:
        raise PreflightError("INT_OUT_OF_RANGE") from exc
    if value > MAX_SAFE_INT or value < -MAX_SAFE_INT:
        _fail("INT_OUT_OF_RANGE")
    return value


def strict_json_loads(text: str) -> Any:
    if not isinstance(text, str):
        _fail("JSON_TEXT_REQUIRED")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_int=_parse_int,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except PreflightError:
        raise
    except (json.JSONDecodeError, UnicodeError, RecursionError, ValueError) as exc:
        raise PreflightError("INVALID_JSON") from exc


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise PreflightError("CANONICAL_JSON_FAILED") from exc


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def process_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dict(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(code)
    return value


def _list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(code)
    if len(value) > MAX_ROWS:
        _fail("ARRAY_TOO_LARGE")
    return value


def _exact(obj: dict[str, Any], fields: set[str]) -> None:
    if set(obj) != fields:
        _fail("UNKNOWN_OR_MISSING_FIELD")


def _text(value: Any, code: str, *, max_len: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        _fail(code)
    for ch in value:
        n = ord(ch)
        if n < 0x20 or n == 0x7F:
            _fail(code)
    return value


def _token(value: Any, code: str, *, max_len: int = 256) -> str:
    text = _text(value, code, max_len=max_len)
    if not TOKEN_RE.fullmatch(text):
        _fail(code)
    return text


def _hex64(value: Any, code: str = "SHA256_REQUIRED") -> str:
    if not isinstance(value, str) or not HEX64_RE.fullmatch(value):
        _fail(code)
    return value


def _utc(value: Any, code: str = "UTC_REQUIRED") -> str:
    text = _text(value, code, max_len=20)
    if not UTC_RE.fullmatch(text):
        _fail(code)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise PreflightError(code) from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        _fail(code)
    return text


def _route(value: Any) -> str:
    route = _text(value, "ROUTE_KIND_REQUIRED", max_len=32)
    if route not in ROUTE_KINDS:
        _fail("ROUTE_KIND_INVALID")
    return route


def _request(value: Any) -> dict[str, Any]:
    obj = _dict(value, "REQUEST_OBJECT_REQUIRED")
    _exact(obj, {
        "schema_version",
        "publication_key",
        "candidate_sha256",
        "intent_sha256",
        "buyer_scope_sha256",
        "recipient_fingerprint",
        "route_kind",
        "operation_id",
        "prepared_at",
    })
    if obj["schema_version"] != REQUEST_SCHEMA:
        _fail("REQUEST_SCHEMA_UNSUPPORTED")
    return {
        "schema_version": REQUEST_SCHEMA,
        "publication_key": _hex64(obj["publication_key"]),
        "candidate_sha256": _hex64(obj["candidate_sha256"]),
        "intent_sha256": _hex64(obj["intent_sha256"]),
        "buyer_scope_sha256": _hex64(obj["buyer_scope_sha256"]),
        "recipient_fingerprint": _hex64(obj["recipient_fingerprint"]),
        "route_kind": _route(obj["route_kind"]),
        "operation_id": _token(obj["operation_id"], "OPERATION_ID_REQUIRED", max_len=200),
        "prepared_at": _utc(obj["prepared_at"]),
    }


def _send(value: Any) -> dict[str, Any]:
    obj = _dict(value, "SEND_RECEIPT_OBJECT_REQUIRED")
    _exact(obj, {
        "provider",
        "provider_message_id",
        "sent_at",
        "publication_key",
        "candidate_sha256",
        "intent_sha256",
        "buyer_scope_sha256",
        "recipient_fingerprint",
        "route_kind",
        "operation_id",
    })
    provider = _text(obj["provider"], "PROVIDER_REQUIRED", max_len=24)
    if provider not in PROVIDERS:
        _fail("PROVIDER_INVALID")
    return {
        "provider": provider,
        "provider_message_id": _token(obj["provider_message_id"], "PROVIDER_MESSAGE_ID_REQUIRED", max_len=320),
        "sent_at": _utc(obj["sent_at"]),
        "publication_key": _hex64(obj["publication_key"]),
        "candidate_sha256": _hex64(obj["candidate_sha256"]),
        "intent_sha256": _hex64(obj["intent_sha256"]),
        "buyer_scope_sha256": _hex64(obj["buyer_scope_sha256"]),
        "recipient_fingerprint": _hex64(obj["recipient_fingerprint"]),
        "route_kind": _route(obj["route_kind"]),
        "operation_id": _token(obj["operation_id"], "OPERATION_ID_REQUIRED", max_len=200),
    }


def _dnr(value: Any) -> dict[str, Any]:
    obj = _dict(value, "DNR_RECEIPT_OBJECT_REQUIRED")
    _exact(obj, {
        "provider_ref",
        "observed_at",
        "buyer_scope_sha256",
        "recipient_fingerprint",
        "route_kind",
        "reason_code",
    })
    return {
        "provider_ref": _token(obj["provider_ref"], "PROVIDER_REF_REQUIRED", max_len=320),
        "observed_at": _utc(obj["observed_at"]),
        "buyer_scope_sha256": _hex64(obj["buyer_scope_sha256"]),
        "recipient_fingerprint": _hex64(obj["recipient_fingerprint"]),
        "route_kind": _route(obj["route_kind"]),
        "reason_code": _token(obj["reason_code"], "REASON_CODE_REQUIRED", max_len=96),
    }


def _normalized_rows(sends_raw: Any, dnr_raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sends = [_send(v) for v in _list(sends_raw, "SEND_RECEIPTS_REQUIRED")]
    dnr = [_dnr(v) for v in _list(dnr_raw, "DNR_RECEIPTS_REQUIRED")]
    if len({(s["provider"], s["provider_message_id"]) for s in sends}) != len(sends):
        _fail("DUPLICATE_PROVIDER_MESSAGE_ID")
    if len({d["provider_ref"] for d in dnr}) != len(dnr):
        _fail("DUPLICATE_DNR_PROVIDER_REF")
    return (
        sorted(sends, key=lambda x: (x["sent_at"], x["provider"], x["provider_message_id"])),
        sorted(dnr, key=lambda x: (x["observed_at"], x["provider_ref"])),
    )


def normalize_snapshot(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "ROOT_OBJECT_REQUIRED")
    _exact(obj, {
        "schema_version",
        "as_of_utc",
        "ledger_complete",
        "request",
        "send_receipts",
        "dnr_receipts",
        "source_observations",
    })
    if obj["schema_version"] != SNAPSHOT_SCHEMA:
        _fail("SNAPSHOT_SCHEMA_UNSUPPORTED")
    if not isinstance(obj["ledger_complete"], bool):
        _fail("LEDGER_COMPLETE_BOOL_REQUIRED")
    req = _request(obj["request"])
    sends, dnr = _normalized_rows(obj["send_receipts"], obj["dnr_receipts"])
    observations = [_hex64(v, "SOURCE_OBSERVATION_SHA_REQUIRED") for v in _list(obj["source_observations"], "SOURCE_OBSERVATIONS_REQUIRED")]
    if not observations:
        _fail("SOURCE_OBSERVATIONS_EMPTY")
    if len(set(observations)) != len(observations):
        _fail("DUPLICATE_SOURCE_OBSERVATION")
    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "as_of_utc": _utc(obj["as_of_utc"]),
        "ledger_complete": obj["ledger_complete"],
        "request": req,
        "send_receipts": sends,
        "dnr_receipts": dnr,
        "source_observations": sorted(observations),
    }


def normalize_authority(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "AUTHORITY_OBJECT_REQUIRED")
    _exact(obj, {
        "schema_version",
        "observed_at_utc",
        "ledger_complete",
        "send_receipts",
        "dnr_receipts",
    })
    if obj["schema_version"] != AUTHORITY_SCHEMA:
        _fail("AUTHORITY_SCHEMA_UNSUPPORTED")
    if not isinstance(obj["ledger_complete"], bool):
        _fail("LEDGER_COMPLETE_BOOL_REQUIRED")
    sends, dnr = _normalized_rows(obj["send_receipts"], obj["dnr_receipts"])
    return {
        "schema_version": AUTHORITY_SCHEMA,
        "observed_at_utc": _utc(obj["observed_at_utc"]),
        "ledger_complete": obj["ledger_complete"],
        "send_receipts": sends,
        "dnr_receipts": dnr,
    }


def _same_publication(row: dict[str, Any], req: dict[str, Any]) -> bool:
    return (
        row["publication_key"] == req["publication_key"]
        and row["buyer_scope_sha256"] == req["buyer_scope_sha256"]
        and row["recipient_fingerprint"] == req["recipient_fingerprint"]
        and row["route_kind"] == req["route_kind"]
    )


def _same_exact_intent(row: dict[str, Any], req: dict[str, Any]) -> bool:
    return (
        _same_publication(row, req)
        and row["candidate_sha256"] == req["candidate_sha256"]
        and row["intent_sha256"] == req["intent_sha256"]
    )


def _evaluate(snapshot: dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    req = snapshot["request"]
    as_of = snapshot["as_of_utc"]

    # A candidate digest is expected to bind exact prepared candidate semantics.
    # Reusing it with changed publication/intent/route/operation evidence is a
    # source-integrity failure, not merely "another prior send".
    rebound = [
        row for row in snapshot["send_receipts"]
        if row["candidate_sha256"] == req["candidate_sha256"]
        and (
            row["publication_key"] != req["publication_key"]
            or row["intent_sha256"] != req["intent_sha256"]
            or row["buyer_scope_sha256"] != req["buyer_scope_sha256"]
            or row["recipient_fingerprint"] != req["recipient_fingerprint"]
            or row["route_kind"] != req["route_kind"]
            or row["operation_id"] != req["operation_id"]
        )
    ]
    if rebound:
        return "HOLD_SOURCE_CONFLICT", ["CANDIDATE_DIGEST_REBOUND"], {
            "providerMessageId": rebound[-1]["provider_message_id"]
        }

    if req["prepared_at"] > as_of:
        return "HOLD_EVIDENCE_ORDERING", ["REQUEST_PREPARED_AFTER_AS_OF"], {}
    future_send = [r for r in snapshot["send_receipts"] if r["sent_at"] > as_of]
    if future_send:
        return "HOLD_EVIDENCE_ORDERING", ["SEND_RECEIPT_AFTER_AS_OF"], {
            "providerMessageId": future_send[0]["provider_message_id"]
        }
    future_dnr = [r for r in snapshot["dnr_receipts"] if r["observed_at"] > as_of]
    if future_dnr:
        return "HOLD_EVIDENCE_ORDERING", ["DNR_RECEIPT_AFTER_AS_OF"], {
            "providerRef": future_dnr[0]["provider_ref"]
        }

    if snapshot["ledger_complete"] is not True:
        return "HOLD_LEDGER_INCOMPLETE", ["PROVIDER_HISTORY_NOT_COMPLETE"], {}

    matching_dnr = [
        row for row in snapshot["dnr_receipts"]
        if row["buyer_scope_sha256"] == req["buyer_scope_sha256"]
        and row["recipient_fingerprint"] == req["recipient_fingerprint"]
        and row["route_kind"] == req["route_kind"]
    ]
    if matching_dnr:
        row = matching_dnr[-1]
        return "HOLD_AFTER_DNR", [f"DNR:{row['reason_code']}"], {
            "providerRef": row["provider_ref"]
        }

    exact = [r for r in snapshot["send_receipts"] if _same_exact_intent(r, req)]
    if exact:
        row = exact[-1]
        return "HOLD_EXACT_INTENT_ALREADY_SENT", ["EXACT_INTENT_SEND_RECEIPT_EXISTS"], {
            "provider": row["provider"],
            "providerMessageId": row["provider_message_id"],
            "sentAt": row["sent_at"],
        }

    publication = [r for r in snapshot["send_receipts"] if _same_publication(r, req)]
    if publication:
        row = publication[-1]
        return "HOLD_PUBLICATION_ALREADY_SENT", ["PUBLICATION_SEND_RECEIPT_EXISTS"], {
            "provider": row["provider"],
            "providerMessageId": row["provider_message_id"],
            "sentAt": row["sent_at"],
            "priorCandidateSha256": row["candidate_sha256"],
        }

    return "CLEAR_FOR_MUSE_PREFLIGHT", ["COMPLETE_PROVIDER_HISTORY_HAS_NO_SEND_OR_DNR_STOP"], {}


def _ledger_bytes(obj: dict[str, Any]) -> str:
    return canonical_json({
        "ledger_complete": obj["ledger_complete"],
        "send_receipts": obj["send_receipts"],
        "dnr_receipts": obj["dnr_receipts"],
    })


def compile_report(raw: Any, retained_authority: Any, *, now_utc: str | None = None) -> dict[str, Any]:
    snapshot = normalize_snapshot(raw)
    authority = normalize_authority(retained_authority)
    observed_now = _utc(now_utc) if now_utc is not None else process_utc_now()
    if _ledger_bytes(snapshot) != _ledger_bytes(authority):
        result, reasons, evidence = (
            "HOLD_RETAINED_AUTHORITY_MISMATCH",
            ["SNAPSHOT_DOES_NOT_MATCH_RETAINED_AUTHORITY"],
            {},
        )
    else:
        result, reasons, evidence = _evaluate(snapshot)
        if result == "CLEAR_FOR_MUSE_PREFLIGHT" and authority["observed_at_utc"] != observed_now:
            result, reasons, evidence = (
                "HOLD_NOT_CURRENT",
                ["RETAINED_AUTHORITY_NOT_CURRENT"],
                {
                    "observedAtUtc": authority["observed_at_utc"],
                    "nowUtc": observed_now,
                },
            )
    if result not in RESULTS:
        _fail("INTERNAL_RESULT_ERROR")
    req = snapshot["request"]
    payload = {
        "schema_version": REPORT_SCHEMA,
        "result": result,
        "reasons": reasons,
        "publication_key": req["publication_key"],
        "candidate_sha256": req["candidate_sha256"],
        "intent_sha256": req["intent_sha256"],
        "buyer_scope_sha256": req["buyer_scope_sha256"],
        "recipient_fingerprint": req["recipient_fingerprint"],
        "route_kind": req["route_kind"],
        "operation_id": req["operation_id"],
        "as_of_utc": snapshot["as_of_utc"],
        "authorityObservedAtUtc": authority["observed_at_utc"],
        "nowUtc": observed_now,
        "operationallyCurrent": result == "CLEAR_FOR_MUSE_PREFLIGHT",
        "evidence": evidence,
        "requiresCanonicalMuseElectionV2": True,
        "requiresFreshProviderPreflight": True,
        "authorities": {
            "contractAuthorized": False,
            "externalSendAuthorized": False,
            "paymentAuthorized": False,
            "providerMutationAuthorized": False,
            "revenueRecognized": False,
            "submissionAuthorized": False,
        },
        "sourceDigestSha256": sha256_text(canonical_json(snapshot)),
        "authorityDigestSha256": sha256_text(canonical_json(authority)),
    }
    return {
        "payload": payload,
        "receiptSha256": sha256_text(canonical_json(payload)),
    }


def verify_report(raw: Any, retained_authority: Any, report: Any, *, now_utc: str | None = None) -> dict[str, Any]:
    if now_utc is None and isinstance(report, dict):
        payload = report.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("nowUtc"), str):
            now_utc = payload["nowUtc"]
    expected = compile_report(raw, retained_authority, now_utc=now_utc)
    if not isinstance(report, dict):
        return {"valid": False, "reason": "REPORT_OBJECT_REQUIRED"}
    if set(report) != {"payload", "receiptSha256"}:
        return {"valid": False, "reason": "REPORT_SCHEMA_MISMATCH"}
    receipt = report.get("receiptSha256")
    if not isinstance(receipt, str) or not HEX64_RE.fullmatch(receipt):
        return {"valid": False, "reason": "REPORT_RECEIPT_INVALID"}
    try:
        digest = sha256_text(canonical_json(report.get("payload")))
    except PreflightError:
        return {"valid": False, "reason": "REPORT_PAYLOAD_INVALID"}
    if digest != receipt:
        return {"valid": False, "reason": "REPORT_RECEIPT_MISMATCH"}
    try:
        if canonical_json(report) != canonical_json(expected):
            return {"valid": False, "reason": "REPORT_SEMANTIC_MISMATCH"}
    except PreflightError:
        return {"valid": False, "reason": "REPORT_SEMANTIC_MISMATCH"}
    return {"valid": True, "reason": None}


def _read_regular_file(path: str) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise PreflightError("INPUT_OPEN_FAILED") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            _fail("INPUT_NOT_REGULAR_FILE")
        if info.st_size < 0 or info.st_size > MAX_INPUT_BYTES:
            _fail("INPUT_TOO_LARGE")
        chunks: list[bytes] = []
        remaining = MAX_INPUT_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_INPUT_BYTES:
            _fail("INPUT_TOO_LARGE")
        try:
            return data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise PreflightError("INPUT_NOT_UTF8") from exc
    finally:
        os.close(fd)


def _write_exclusive(path: str, text: str) -> None:
    parent = os.path.dirname(path) or "."
    if not os.path.isdir(parent):
        _fail("OUTPUT_PARENT_MISSING")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise PreflightError("OUTPUT_EXISTS") from exc
    except OSError as exc:
        raise PreflightError("OUTPUT_OPEN_FAILED") from exc
    try:
        data = text.encode("utf-8")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                _fail("OUTPUT_WRITE_FAILED")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _load_path(path: str) -> Any:
    return strict_json_loads(_read_regular_file(path))


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    compile_cmd = subs.add_parser("compile", help="compile provider-history preflight")
    compile_cmd.add_argument("snapshot")
    compile_cmd.add_argument("authority")
    compile_cmd.add_argument("output")
    verify_cmd = subs.add_parser("verify", help="verify report against exact snapshot and retained authority")
    verify_cmd.add_argument("snapshot")
    verify_cmd.add_argument("authority")
    verify_cmd.add_argument("report")
    args = parser.parse_args(argv)
    try:
        now_utc = process_utc_now()
        if args.command == "compile":
            report = compile_report(_load_path(args.snapshot), _load_path(args.authority), now_utc=now_utc)
            _write_exclusive(args.output, canonical_json(report) + "\n")
            print(report["payload"]["result"])
            return 0
        result = verify_report(
            _load_path(args.snapshot),
            _load_path(args.authority),
            _load_path(args.report),
        )
        if result["valid"]:
            print("VERIFIED")
            return 0
        print(result["reason"] or "VERIFY_FAILED", file=sys.stderr)
        return 2
    except PreflightError as exc:
        print(exc.code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
