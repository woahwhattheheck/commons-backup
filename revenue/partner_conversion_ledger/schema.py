from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

INPUT_SCHEMA = "partner-conversion-ledger/input-v1"
REPORT_SCHEMA = "partner-conversion-ledger/report-v1"
MAX_JSON_BYTES = 1_000_000
MAX_OPPORTUNITIES = 100
MAX_CANDIDATES = 100
MAX_EVENTS = 128
MAX_EVIDENCE = 32
MAX_EXCEPTIONS = 16

_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECRET_MARKERS = (
    "-----BEGIN ", "ghp_", "github_pat_", "sk_live_", "sk_test_", "xoxb-", "xoxp-",
    "AIza", "AKIA", "Bearer ", "password=", "api_key=", "apikey=", "secret=",
)


class LedgerError(ValueError):
    pass


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise LedgerError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        if len(raw) > MAX_JSON_BYTES:
            raise LedgerError("JSON input exceeds size limit")
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise LedgerError("JSON must be strict UTF-8") from exc
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > MAX_JSON_BYTES:
            raise LedgerError("JSON input exceeds size limit")
        text = raw
    else:
        raise LedgerError("JSON input must be bytes or str")
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=lambda token: (_ for _ in ()).throw(LedgerError(f"non-finite JSON number: {token}")),
        )
    except LedgerError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LedgerError("invalid JSON") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LedgerError("value is not canonical JSON") from exc


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _exact_keys(obj: Any, required: Iterable[str], optional: Iterable[str] = ()) -> dict[str, Any]:
    if type(obj) is not dict:
        raise LedgerError("expected object")
    required_set = set(required)
    allowed = required_set | set(optional)
    keys = set(obj)
    missing = sorted(required_set - keys)
    unknown = sorted(keys - allowed)
    if missing:
        raise LedgerError(f"missing keys: {','.join(missing)}")
    if unknown:
        raise LedgerError(f"unknown keys: {','.join(unknown)}")
    return obj


def _list(value: Any, *, minimum: int = 0, maximum: int, name: str) -> list[Any]:
    if type(value) is not list:
        raise LedgerError(f"{name} must be a list")
    if not minimum <= len(value) <= maximum:
        raise LedgerError(f"{name} length out of bounds")
    return value


def _safe_ref(value: Any, *, name: str) -> str:
    if type(value) is not str or not _SAFE_REF.fullmatch(value):
        raise LedgerError(f"{name} must be an opaque safe reference")
    lower = value.lower()
    if "@" in value or "/" in value or "\\" in value or "\n" in value or "\r" in value or "://" in value:
        raise LedgerError(f"{name} must not contain contact/body/path data")
    if any(marker.lower() in lower for marker in _SECRET_MARKERS):
        raise LedgerError(f"{name} looks secret-bearing")
    return value


def _digest(value: Any, *, name: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise LedgerError(f"{name} must be lowercase sha256")
    return value


def _canonical_time(value: Any, *, name: str) -> str:
    if type(value) is not str or len(value) != 20 or not value.endswith("Z"):
        raise LedgerError(f"{name} must be canonical UTC seconds")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise LedgerError(f"{name} must be canonical UTC seconds") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise LedgerError(f"{name} must be canonical UTC seconds")
    return value


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _utc_now_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_evidence(rows: Any, *, name: str) -> list[dict[str, str]]:
    rows = _list(rows, minimum=1, maximum=MAX_EVIDENCE, name=name)
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        row = _exact_keys(row, ["id", "digest"])
        rid = _safe_ref(row["id"], name=f"{name}.id")
        if rid in seen:
            raise LedgerError(f"duplicate {name} id: {rid}")
        seen.add(rid)
        out.append({"id": rid, "digest": _digest(row["digest"], name=f"{name}.digest")})
    return sorted(out, key=lambda r: r["id"])


def _validate_exception(row: Any, opp_id: str, cand_id: str) -> dict[str, str]:
    row = _exact_keys(
        row,
        ["exception_id", "opportunity_id", "candidate_id", "prior_send_event_id", "approved_at", "expires_at", "evidence_digest"],
    )
    out = {
        "exception_id": _safe_ref(row["exception_id"], name="exception_id"),
        "opportunity_id": _safe_ref(row["opportunity_id"], name="exception.opportunity_id"),
        "candidate_id": _safe_ref(row["candidate_id"], name="exception.candidate_id"),
        "prior_send_event_id": _safe_ref(row["prior_send_event_id"], name="exception.prior_send_event_id"),
        "approved_at": _canonical_time(row["approved_at"], name="exception.approved_at"),
        "expires_at": _canonical_time(row["expires_at"], name="exception.expires_at"),
        "evidence_digest": _digest(row["evidence_digest"], name="exception.evidence_digest"),
    }
    if out["opportunity_id"] != opp_id or out["candidate_id"] != cand_id:
        raise LedgerError("follow-up exception scope mismatch")
    if _dt(out["expires_at"]) < _dt(out["approved_at"]):
        raise LedgerError("follow-up exception expires before approval")
    return out


def _validate_event(row: Any) -> dict[str, Any]:
    if type(row) is not dict or type(row.get("type")) is not str:
        raise LedgerError("event must be an object with type")
    typ = row["type"]
    common = ["event_id", "type", "at", "evidence_digest"]
    if typ == "SENT":
        row = _exact_keys(row, common + ["provider_message_id", "provider_thread_id", "exception_id"])
        exception_id = row["exception_id"]
        if exception_id is not None:
            exception_id = _safe_ref(exception_id, name="event.exception_id")
        extra = {
            "provider_message_id": _safe_ref(row["provider_message_id"], name="event.provider_message_id"),
            "provider_thread_id": _safe_ref(row["provider_thread_id"], name="event.provider_thread_id"),
            "exception_id": exception_id,
        }
    elif typ == "REPLY":
        row = _exact_keys(row, common + ["provider_message_id", "provider_thread_id", "reply_class"])
        if row["reply_class"] not in {"POSITIVE", "CONDITIONAL", "NEGATIVE", "AMBIGUOUS"}:
            raise LedgerError("invalid reply_class")
        extra = {
            "provider_message_id": _safe_ref(row["provider_message_id"], name="event.provider_message_id"),
            "provider_thread_id": _safe_ref(row["provider_thread_id"], name="event.provider_thread_id"),
            "reply_class": row["reply_class"],
        }
    elif typ == "HANDOFF":
        row = _exact_keys(row, common + ["owner_ref"])
        extra = {"owner_ref": _safe_ref(row["owner_ref"], name="event.owner_ref")}
    elif typ == "TERMINAL":
        row = _exact_keys(row, common + ["terminal_class"])
        if row["terminal_class"] not in {"NO_FIT", "DECLINED", "CLOSED"}:
            raise LedgerError("invalid terminal_class")
        extra = {"terminal_class": row["terminal_class"]}
    else:
        raise LedgerError(f"unknown event type: {typ}")
    return {
        "event_id": _safe_ref(row["event_id"], name="event.event_id"),
        "type": typ,
        "at": _canonical_time(row["at"], name="event.at"),
        "evidence_digest": _digest(row["evidence_digest"], name="event.evidence_digest"),
        **extra,
    }


def _validate_candidate(row: Any, opp_id: str) -> dict[str, Any]:
    row = _exact_keys(row, ["candidate_id", "org_ref", "route_digest", "fit_evidence", "exceptions", "events"])
    cand_id = _safe_ref(row["candidate_id"], name="candidate_id")
    exceptions_raw = _list(row["exceptions"], maximum=MAX_EXCEPTIONS, name="exceptions")
    exceptions: list[dict[str, str]] = []
    exc_ids: set[str] = set()
    for exc in exceptions_raw:
        parsed = _validate_exception(exc, opp_id, cand_id)
        if parsed["exception_id"] in exc_ids:
            raise LedgerError("duplicate exception id")
        exc_ids.add(parsed["exception_id"])
        exceptions.append(parsed)
    events_raw = _list(row["events"], maximum=MAX_EVENTS, name="events")
    events: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    for event in events_raw:
        parsed_event = _validate_event(event)
        if parsed_event["event_id"] in event_ids:
            raise LedgerError("duplicate event id")
        event_ids.add(parsed_event["event_id"])
        events.append(parsed_event)
    return {
        "candidate_id": cand_id,
        "org_ref": _safe_ref(row["org_ref"], name="org_ref"),
        "route_digest": _digest(row["route_digest"], name="route_digest"),
        "fit_evidence": _validate_evidence(row["fit_evidence"], name="fit_evidence"),
        "exceptions": sorted(exceptions, key=lambda r: r["exception_id"]),
        "events": sorted(events, key=lambda r: (r["at"], {"SENT": 0, "REPLY": 1, "HANDOFF": 2, "TERMINAL": 3}[r["type"]], r["event_id"])),
    }


def validate_packet(packet: Any) -> dict[str, Any]:
    packet = _exact_keys(packet, ["schema", "ledger_id", "opportunities"])
    if packet["schema"] != INPUT_SCHEMA:
        raise LedgerError("unsupported input schema")
    opportunities_raw = _list(packet["opportunities"], minimum=1, maximum=MAX_OPPORTUNITIES, name="opportunities")
    opp_ids: set[str] = set()
    opportunities: list[dict[str, Any]] = []
    candidate_global: set[str] = set()
    exception_id_global: set[str] = set()
    exception_evidence_global: set[str] = set()
    for opp in opportunities_raw:
        opp = _exact_keys(opp, ["opportunity_id", "qualification", "candidates"])
        opp_id = _safe_ref(opp["opportunity_id"], name="opportunity_id")
        if opp_id in opp_ids:
            raise LedgerError("duplicate opportunity id")
        opp_ids.add(opp_id)
        q = _exact_keys(opp["qualification"], ["posture", "digest", "captured_at", "valid_until", "source_refs"])
        if q["posture"] != "PARTNER_FIRST":
            raise LedgerError("only PARTNER_FIRST opportunities are accepted")
        qualification = {
            "posture": "PARTNER_FIRST",
            "digest": _digest(q["digest"], name="qualification.digest"),
            "captured_at": _canonical_time(q["captured_at"], name="qualification.captured_at"),
            "valid_until": _canonical_time(q["valid_until"], name="qualification.valid_until"),
            "source_refs": _validate_evidence(q["source_refs"], name="qualification.source_refs"),
        }
        if _dt(qualification["valid_until"]) < _dt(qualification["captured_at"]):
            raise LedgerError("qualification validity precedes capture")
        candidates_raw = _list(opp["candidates"], minimum=1, maximum=MAX_CANDIDATES, name="candidates")
        candidates: list[dict[str, Any]] = []
        local_ids: set[str] = set()
        for cand in candidates_raw:
            parsed = _validate_candidate(cand, opp_id)
            cid = parsed["candidate_id"]
            if cid in local_ids or cid in candidate_global:
                raise LedgerError("candidate id must be globally unique")
            local_ids.add(cid)
            candidate_global.add(cid)
            for exc in parsed["exceptions"]:
                if exc["exception_id"] in exception_id_global:
                    raise LedgerError("follow-up exception id must be globally unique")
                if exc["evidence_digest"] in exception_evidence_global:
                    raise LedgerError("follow-up exception evidence must not be replayed")
                exception_id_global.add(exc["exception_id"])
                exception_evidence_global.add(exc["evidence_digest"])
            candidates.append(parsed)
        opportunities.append({"opportunity_id": opp_id, "qualification": qualification, "candidates": sorted(candidates, key=lambda c: c["candidate_id"])})
    return {"schema": INPUT_SCHEMA, "ledger_id": _safe_ref(packet["ledger_id"], name="ledger_id"), "opportunities": sorted(opportunities, key=lambda o: o["opportunity_id"])}
