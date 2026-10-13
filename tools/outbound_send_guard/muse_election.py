#!/usr/bin/env python3
"""Compile fail-closed Muse election observations without self-authenticating Slack.

Version 1 request/evidence artifacts are caller-supplied JSON.  They can prove
internal consistency, chronology, replay state, and candidate binding, but they
cannot authenticate that a Slack message was actually returned by the pinned
Muse identity.  Consequently this module never turns v1 caller evidence into a
satisfied election prerequisite.  A future provider/harness-authenticated
adapter must use a versioned attestation contract rather than a caller-settable
flag or arbitrary digest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping

REQUEST_SCHEMA = "outbound-muse-election-request/v1"
RECEIPT_SCHEMA = "outbound-muse-election-receipt/v1"
MUSE_USER_ID = "U0C0TKRTQHZ"
MUSE_DM_CONVERSATION_ID = "D0C1U7TUZEC"
RESPONSE_WINDOW_SECONDS = 600
REQUEST_TRANSPORT_SKEW_SECONDS = 60
RECEIPT_FRESHNESS_SECONDS = 600
UNVERIFIED_PROVENANCE_REASON = "SLACK_EVIDENCE_PROVENANCE_UNVERIFIED"
_HEX = frozenset("0123456789abcdef")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$")
_SLACK_TS_RE = re.compile(r"^[0-9]{10,}(?:\.[0-9]{1,6})?$")
_RESPONSE_RE = re.compile(
    r"^(SELECTED|NOT_SELECTED) ([A-Za-z0-9][A-Za-z0-9._:-]{7,159}) ([0-9a-f]{64})$"
)


class MuseElectionError(ValueError):
    pass


def _canon_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MuseElectionError("value is not canonical-JSON serializable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon_bytes(value)).hexdigest()


def _hex64(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or value != value.lower() or any(ch not in _HEX for ch in value):
        raise MuseElectionError(f"{label}: expected 64 lowercase hex characters")
    return value


def _text(value: Any, label: str, *, max_len: int = 256) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise MuseElectionError(f"{label}: nonempty bounded string required")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise MuseElectionError(f"{label}: control characters forbidden")
    return value


def _message_text(value: Any, label: str, *, max_len: int = 2048) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise MuseElectionError(f"{label}: nonempty bounded string required")
    for ch in value:
        code = ord(ch)
        if (code < 0x20 and ch != "\n") or code == 0x7F:
            raise MuseElectionError(f"{label}: only LF line breaks are permitted")
    return value


def _obj(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise MuseElectionError(f"{label}: object required")
    return value


def _exact(obj: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(obj) != fields:
        missing = sorted(fields - set(obj))
        extra = sorted(set(obj) - fields)
        raise MuseElectionError(f"{label}: exact fields required; missing={missing}; extra={extra}")


def _strict_pairs(pairs):
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise MuseElectionError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def parse_json_bytes(raw: bytes, label: str) -> Any:
    if type(raw) is not bytes:
        raise MuseElectionError(f"{label}: bytes required")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise MuseElectionError(f"{label}: UTF-8 JSON required") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                MuseElectionError(f"{label}: non-finite number {token}")
            ),
        )
    except MuseElectionError:
        raise
    except json.JSONDecodeError as exc:
        raise MuseElectionError(f"{label}: invalid JSON: {exc.msg}") from exc


def _utc(value: Any, label: str) -> datetime:
    text = _text(value, label, max_len=32)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise MuseElectionError(f"{label}: expected UTC RFC3339 seconds (YYYY-MM-DDTHH:MM:SSZ)") from exc
    return parsed


def _fmt(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slack_epoch(value: Any, label: str) -> Decimal:
    text = _text(value, label, max_len=32)
    if not _SLACK_TS_RE.fullmatch(text):
        raise MuseElectionError(f"{label}: canonical Slack timestamp required")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise MuseElectionError(f"{label}: invalid Slack timestamp") from exc
    if parsed <= 0:
        raise MuseElectionError(f"{label}: positive Slack timestamp required")
    return parsed


def _slack_dt(value: Any, label: str) -> datetime:
    return datetime.fromtimestamp(float(_slack_epoch(value, label)), tz=timezone.utc)


def _validate_candidate(raw: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _obj(raw, "candidate")
    fields = {
        "buyer_scope_sha256", "offer_scope_sha256", "intent_sha256", "body_sha256",
        "claimant", "operation_id",
    }
    _exact(candidate, fields, "candidate")
    return {
        "buyer_scope_sha256": _hex64(candidate["buyer_scope_sha256"], "candidate.buyer_scope_sha256"),
        "offer_scope_sha256": _hex64(candidate["offer_scope_sha256"], "candidate.offer_scope_sha256"),
        "intent_sha256": _hex64(candidate["intent_sha256"], "candidate.intent_sha256"),
        "body_sha256": _hex64(candidate["body_sha256"], "candidate.body_sha256"),
        "claimant": _text(candidate["claimant"], "candidate.claimant", max_len=120),
        "operation_id": _text(candidate["operation_id"], "candidate.operation_id", max_len=200),
    }


def _validate_request_id(value: Any) -> str:
    text = _text(value, "request_id", max_len=160)
    if not _REQUEST_ID_RE.fullmatch(text):
        raise MuseElectionError("request_id: expected 8-160 safe token characters")
    return text


def _request_message(*, request_id: str, candidate_sha256: str, claimant: str, operation_id: str) -> str:
    return (
        "MUSE OUTBOUND ELECTION v1\n"
        f"request_id={request_id}\n"
        f"candidate_sha256={candidate_sha256}\n"
        f"claimant={claimant}\n"
        f"operation_id={operation_id}\n"
        "Choose at most one claimant for this exact outbound candidate.\n"
        "Reply exactly one line: SELECTED <request_id> <candidate_sha256> "
        "or NOT_SELECTED <request_id> <candidate_sha256>."
    )


def prepare_request(candidate: Mapping[str, Any], *, request_id: str, requested_at: str) -> dict[str, Any]:
    normalized = _validate_candidate(candidate)
    rid = _validate_request_id(request_id)
    requested = _utc(requested_at, "requested_at")
    candidate_sha = _digest(normalized)
    message = _request_message(
        request_id=rid,
        candidate_sha256=candidate_sha,
        claimant=normalized["claimant"],
        operation_id=normalized["operation_id"],
    )
    payload = {
        "schema_version": REQUEST_SCHEMA,
        "request_id": rid,
        "candidate": normalized,
        "candidate_sha256": candidate_sha,
        "requested_at": _fmt(requested),
        "response_deadline_at": _fmt(requested + timedelta(seconds=RESPONSE_WINDOW_SECONDS)),
        "muse_user_id": MUSE_USER_ID,
        "muse_dm_conversation_id": MUSE_DM_CONVERSATION_ID,
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "external_send_authorized": False,
    }
    return {"payload": payload, "request_sha256": _digest(payload), "message": message}


def _validate_request(raw: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    request = _obj(raw, "request")
    _exact(request, {"payload", "request_sha256", "message"}, "request")
    payload = _obj(request["payload"], "request.payload")
    fields = {
        "schema_version", "request_id", "candidate", "candidate_sha256",
        "requested_at", "response_deadline_at", "muse_user_id",
        "muse_dm_conversation_id", "message_sha256", "external_send_authorized",
    }
    _exact(payload, fields, "request.payload")
    if payload["schema_version"] != REQUEST_SCHEMA:
        raise MuseElectionError("request: unsupported schema")
    candidate = _validate_candidate(payload["candidate"])
    candidate_sha = _hex64(payload["candidate_sha256"], "request.candidate_sha256")
    if _digest(candidate) != candidate_sha:
        raise MuseElectionError("request: candidate digest mismatch")
    rid = _validate_request_id(payload["request_id"])
    requested = _utc(payload["requested_at"], "request.requested_at")
    deadline = _utc(payload["response_deadline_at"], "request.response_deadline_at")
    if deadline != requested + timedelta(seconds=RESPONSE_WINDOW_SECONDS):
        raise MuseElectionError("request: response deadline mismatch")
    if payload["muse_user_id"] != MUSE_USER_ID or payload["muse_dm_conversation_id"] != MUSE_DM_CONVERSATION_ID:
        raise MuseElectionError("request: Muse routing identity mismatch")
    if payload["external_send_authorized"] is not False:
        raise MuseElectionError("request may never authorize external send")
    message = _message_text(request["message"], "request.message", max_len=2048)
    expected = _request_message(
        request_id=rid,
        candidate_sha256=candidate_sha,
        claimant=candidate["claimant"],
        operation_id=candidate["operation_id"],
    )
    if message != expected:
        raise MuseElectionError("request: exact message mismatch")
    if hashlib.sha256(message.encode("utf-8")).hexdigest() != _hex64(payload["message_sha256"], "request.message_sha256"):
        raise MuseElectionError("request: message digest mismatch")
    request_sha = _hex64(request["request_sha256"], "request.request_sha256")
    if _digest(payload) != request_sha:
        raise MuseElectionError("request: digest mismatch")
    return payload, request_sha, message


def _validate_evidence(raw: Mapping[str, Any]) -> dict[str, str]:
    evidence = _obj(raw, "evidence")
    fields = {
        "channel_id", "request_message_ts", "request_author_user_id", "request_text",
        "response_message_ts", "response_author_user_id", "response_text",
    }
    _exact(evidence, fields, "evidence")
    out = {
        "channel_id": _text(evidence["channel_id"], "evidence.channel_id", max_len=32),
        "request_message_ts": _text(evidence["request_message_ts"], "evidence.request_message_ts", max_len=32),
        "request_author_user_id": _text(evidence["request_author_user_id"], "evidence.request_author_user_id", max_len=32),
        "request_text": _message_text(evidence["request_text"], "evidence.request_text", max_len=2048),
        "response_message_ts": _text(evidence["response_message_ts"], "evidence.response_message_ts", max_len=32),
        "response_author_user_id": _text(evidence["response_author_user_id"], "evidence.response_author_user_id", max_len=32),
        "response_text": _text(evidence["response_text"], "evidence.response_text", max_len=512),
    }
    _slack_epoch(out["request_message_ts"], "evidence.request_message_ts")
    _slack_epoch(out["response_message_ts"], "evidence.response_message_ts")
    return out


def _receipt_payload(prior: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if not verify_receipt(prior):
        return None
    return prior["payload"]


def compile_receipt(
    request: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    observed_at: str,
    prior_receipts: Iterable[Mapping[str, Any]] = (),
    ledger_complete: bool,
) -> dict[str, Any]:
    """Compile a v1 observation receipt.

    V1 evidence is a caller-supplied dictionary.  The compiler can validate the
    observation's internal consistency but cannot authenticate Slack provenance,
    so a reported SELECTED response is always held.
    """
    req, request_sha, request_message = _validate_request(request)
    ev = _validate_evidence(evidence)
    observed = _utc(observed_at, "observed_at")
    requested = _utc(req["requested_at"], "request.requested_at")
    deadline = _utc(req["response_deadline_at"], "request.response_deadline_at")
    request_ts = _slack_dt(ev["request_message_ts"], "evidence.request_message_ts")
    response_ts = _slack_dt(ev["response_message_ts"], "evidence.response_message_ts")
    reasons: list[str] = []

    if type(ledger_complete) is not bool or ledger_complete is not True:
        reasons.append("PRIOR_ELECTION_LEDGER_INCOMPLETE")
    if ev["channel_id"] != MUSE_DM_CONVERSATION_ID:
        reasons.append("WRONG_MUSE_DM_CONVERSATION")
    if ev["response_author_user_id"] != MUSE_USER_ID:
        reasons.append("WRONG_MUSE_RESPONSE_AUTHOR")
    if ev["response_author_user_id"] == ev["request_author_user_id"]:
        reasons.append("SELF_AUTHORED_RESPONSE")
    if ev["request_text"] != request_message:
        reasons.append("REQUEST_TEXT_MISMATCH")
    if request_ts < requested or request_ts > requested + timedelta(seconds=REQUEST_TRANSPORT_SKEW_SECONDS):
        reasons.append("REQUEST_TRANSPORT_TIME_MISMATCH")
    if response_ts <= request_ts:
        reasons.append("RESPONSE_NOT_AFTER_REQUEST")
    if response_ts > deadline:
        reasons.append("MUSE_RESPONSE_AFTER_DEADLINE")
    if observed < response_ts:
        reasons.append("OBSERVATION_PRECEDES_RESPONSE")
    if observed > response_ts + timedelta(seconds=RECEIPT_FRESHNESS_SECONDS):
        reasons.append("MUSE_SELECTION_STALE")

    match = _RESPONSE_RE.fullmatch(ev["response_text"])
    outcome = "INVALID"
    if match is None:
        reasons.append("RESPONSE_FORMAT_INVALID")
    else:
        outcome, response_request_id, response_candidate_sha = match.groups()
        if response_request_id != req["request_id"]:
            reasons.append("RESPONSE_REQUEST_ID_MISMATCH")
        if response_candidate_sha != req["candidate_sha256"]:
            reasons.append("RESPONSE_CANDIDATE_DIGEST_MISMATCH")
        if outcome == "NOT_SELECTED":
            reasons.append("MUSE_NOT_SELECTED")
        elif outcome == "SELECTED":
            reasons.append(UNVERIFIED_PROVENANCE_REASON)

    evidence_sha = _digest(ev)
    for prior in prior_receipts:
        prior_payload = _receipt_payload(prior)
        if prior_payload is None:
            reasons.append("PRIOR_ELECTION_LEDGER_INVALID")
            continue
        if (
            prior_payload.get("request_sha256") == request_sha
            or prior_payload.get("evidence_sha256") == evidence_sha
            or prior_payload.get("response_message_ts") == ev["response_message_ts"]
        ):
            reasons.append("ELECTION_EVIDENCE_REPLAY")

    reasons = sorted(set(reasons))
    payload = {
        "schema_version": RECEIPT_SCHEMA,
        "request_sha256": request_sha,
        "candidate_sha256": req["candidate_sha256"],
        "request_id": req["request_id"],
        "claimant": req["candidate"]["claimant"],
        "operation_id": req["candidate"]["operation_id"],
        "evidence_sha256": evidence_sha,
        "response_message_ts": ev["response_message_ts"],
        "response_author_user_id": ev["response_author_user_id"],
        "outcome": outcome,
        "decision": "HOLD",
        "reasons": reasons,
        "observed_at": _fmt(observed),
        "muse_selected": False,
        "election_prerequisite_satisfied": False,
        "external_send_authorized": False,
        "side_effects_authorized": False,
    }
    return {"payload": payload, "receipt_sha256": _digest(payload)}


def verify_receipt(raw: Mapping[str, Any]) -> bool:
    """Verify a v1 receipt, rejecting legacy self-authenticating SELECTED shape."""
    try:
        receipt = _obj(raw, "receipt")
        _exact(receipt, {"payload", "receipt_sha256"}, "receipt")
        payload = _obj(receipt["payload"], "receipt.payload")
        fields = {
            "schema_version", "request_sha256", "candidate_sha256", "request_id",
            "claimant", "operation_id", "evidence_sha256", "response_message_ts",
            "response_author_user_id", "outcome", "decision", "reasons", "observed_at",
            "muse_selected", "election_prerequisite_satisfied",
            "external_send_authorized", "side_effects_authorized",
        }
        _exact(payload, fields, "receipt.payload")
        if payload["schema_version"] != RECEIPT_SCHEMA:
            return False
        _hex64(payload["request_sha256"], "receipt.request_sha256")
        _hex64(payload["candidate_sha256"], "receipt.candidate_sha256")
        _validate_request_id(payload["request_id"])
        _text(payload["claimant"], "receipt.claimant", max_len=120)
        _text(payload["operation_id"], "receipt.operation_id", max_len=200)
        _hex64(payload["evidence_sha256"], "receipt.evidence_sha256")
        _slack_epoch(payload["response_message_ts"], "receipt.response_message_ts")
        _text(payload["response_author_user_id"], "receipt.response_author_user_id", max_len=32)
        if payload["outcome"] not in {"SELECTED", "NOT_SELECTED", "INVALID"}:
            return False
        if type(payload["reasons"]) is not list or any(type(x) is not str or not x for x in payload["reasons"]):
            return False
        if payload["reasons"] != sorted(set(payload["reasons"])):
            return False
        _utc(payload["observed_at"], "receipt.observed_at")
        for key in (
            "muse_selected", "election_prerequisite_satisfied",
            "external_send_authorized", "side_effects_authorized",
        ):
            if type(payload[key]) is not bool:
                return False
        if payload["decision"] != "HOLD":
            return False
        if payload["muse_selected"] is not False or payload["election_prerequisite_satisfied"] is not False:
            return False
        if payload["external_send_authorized"] is not False or payload["side_effects_authorized"] is not False:
            return False
        if len(payload["reasons"]) == 0:
            return False
        if payload["outcome"] == "SELECTED" and UNVERIFIED_PROVENANCE_REASON not in payload["reasons"]:
            return False
        claimed = _hex64(receipt["receipt_sha256"], "receipt.receipt_sha256")
        return _digest(payload) == claimed
    except (MuseElectionError, TypeError, ValueError):
        return False


def _read_json(path: str, label: str) -> Any:
    raw = Path(path).read_bytes()
    if len(raw) > 2_000_000:
        raise MuseElectionError(f"{label}: file too large")
    return parse_json_bytes(raw, label)


def _write_json(value: Any) -> None:
    print(_canon_bytes(value).decode("utf-8"), end="")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="build an exact Muse election request")
    prep.add_argument("--buyer-scope-sha256", required=True)
    prep.add_argument("--offer-scope-sha256", required=True)
    prep.add_argument("--intent-sha256", required=True)
    prep.add_argument("--body-sha256", required=True)
    prep.add_argument("--claimant", required=True)
    prep.add_argument("--operation-id", required=True)
    prep.add_argument("--request-id", required=True)
    prep.add_argument("--requested-at", required=True)
    comp = sub.add_parser("compile", help="compile caller-supplied Slack observation evidence")
    comp.add_argument("--request", required=True)
    comp.add_argument("--evidence", required=True)
    comp.add_argument("--observed-at", required=True)
    comp.add_argument("--prior-ledger")
    comp.add_argument("--ledger-complete", action="store_true")
    verify = sub.add_parser("verify", help="verify a compiled v1 receipt")
    verify.add_argument("--receipt", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            candidate = {
                "buyer_scope_sha256": args.buyer_scope_sha256,
                "offer_scope_sha256": args.offer_scope_sha256,
                "intent_sha256": args.intent_sha256,
                "body_sha256": args.body_sha256,
                "claimant": args.claimant,
                "operation_id": args.operation_id,
            }
            _write_json(prepare_request(candidate, request_id=args.request_id, requested_at=args.requested_at))
            return 0
        if args.command == "compile":
            request = _read_json(args.request, "request")
            evidence = _read_json(args.evidence, "evidence")
            prior: list[Mapping[str, Any]] = []
            if args.prior_ledger:
                ledger = _read_json(args.prior_ledger, "prior ledger")
                if type(ledger) is not list:
                    raise MuseElectionError("prior ledger: array required")
                prior = ledger
            _write_json(
                compile_receipt(
                    request,
                    evidence,
                    observed_at=args.observed_at,
                    prior_receipts=prior,
                    ledger_complete=args.ledger_complete,
                )
            )
            return 2
        receipt = _read_json(args.receipt, "receipt")
        ok = verify_receipt(receipt)
        _write_json({"valid": ok})
        return 0 if ok else 2
    except (MuseElectionError, OSError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
