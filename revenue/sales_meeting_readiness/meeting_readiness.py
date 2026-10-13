"""Deterministic, offline sales-meeting readiness compiler.

The module never contacts a calendar or counterparty.  It consumes a meeting
request plus independently retained availability evidence and produces a
conservative owner-review disposition and preparation brief.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA = "sales-meeting-readiness/v1"
RECEIPT_SCHEMA = "sales-meeting-readiness-receipt/v1"

READY = "READY_FOR_OWNER_SCHEDULING_REVIEW"
CALENDAR_REQUIRED = "CALENDAR_CHECK_REQUIRED"
SLOT_CONFLICT = "SLOT_CONFLICT"
PREP_REQUIRED = "PREP_REQUIRED"
REQUEST_STALE = "REQUEST_STALE"
HOLD = "HOLD"
STATES = {READY, CALENDAR_REQUIRED, SLOT_CONFLICT, PREP_REQUIRED, REQUEST_STALE, HOLD}

DEFAULT_POLICY = {
    "schema": "sales-meeting-readiness-policy/v1",
    "max_inbound_age_seconds": 7 * 24 * 3600,
    "max_availability_age_seconds": 30 * 60,
    "max_slot_horizon_seconds": 45 * 24 * 3600,
    "max_duration_minutes": 240,
    "max_windows": 16,
    "max_busy_windows": 128,
    "max_prep_items": 16,
    "max_text_chars": 2400,
}

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}(?!\d)")
_SECRET = re.compile(r"(?i)\b(?:sk_live_|ghp_|github_pat_|AIza|xox[baprs]-)[A-Za-z0-9_\-]{8,}")

PREP_SCALARS = ("objective", "recommended_opening", "recommended_closing")
PREP_LISTS = ("key_questions", "likely_asks", "risks_commitments_to_avoid", "owner_actions")


class MeetingReadinessError(ValueError):
    """Raised when packet structure or integrity is invalid."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _object_pairs_no_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise MeetingReadinessError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict(data: str | bytes) -> Any:
    try:
        return json.loads(data, object_pairs_hook=_object_pairs_no_duplicates)
    except MeetingReadinessError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MeetingReadinessError(f"invalid JSON: {exc}") from exc


def _require_exact_keys(obj: Any, required: set[str], optional: set[str] = set(), *, where: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise MeetingReadinessError(f"{where} must be an object")
    keys = set(obj)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        raise MeetingReadinessError(f"{where} missing keys: {sorted(missing)}")
    if unknown:
        raise MeetingReadinessError(f"{where} unknown keys: {sorted(unknown)}")
    return obj


def _require_str(value: Any, *, where: str, max_chars: int = 256, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise MeetingReadinessError(f"{where} must be a string")
    if (not allow_empty and not value) or len(value) > max_chars:
        raise MeetingReadinessError(f"{where} length invalid")
    if "\x00" in value:
        raise MeetingReadinessError(f"{where} contains NUL")
    return value


def _safe_id(value: Any, *, where: str) -> str:
    text = _require_str(value, where=where, max_chars=128)
    if not _ID.fullmatch(text) or _EMAIL.search(text) or _PHONE.search(text) or _SECRET.search(text):
        raise MeetingReadinessError(f"{where} must be a safe opaque identifier")
    return text


def _sha(value: Any, *, where: str) -> str:
    text = _require_str(value, where=where, max_chars=64)
    if not _SHA.fullmatch(text):
        raise MeetingReadinessError(f"{where} must be lowercase SHA-256")
    return text


def _integer(value: Any, *, where: str, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise MeetingReadinessError(f"{where} must be an integer")
    if not minimum <= value <= maximum:
        raise MeetingReadinessError(f"{where} outside bounds")
    return value


def _parse_utc(value: Any, *, where: str) -> datetime:
    text = _require_str(value, where=where, max_chars=32)
    if not text.endswith("Z"):
        raise MeetingReadinessError(f"{where} must be canonical UTC ending Z")
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise MeetingReadinessError(f"{where} invalid UTC timestamp") from exc
    if dt.tzinfo != timezone.utc or dt.microsecond:
        raise MeetingReadinessError(f"{where} must be UTC seconds")
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise MeetingReadinessError(f"{where} must be canonical UTC seconds")
    return dt


def _utc_text(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise MeetingReadinessError("trusted as_of must be timezone-aware")
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _timezone_name(value: Any, *, where: str) -> str:
    name = _require_str(value, where=where, max_chars=64)
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise MeetingReadinessError(f"{where} is not an IANA timezone") from exc
    return name


def _private_text(value: Any, *, where: str, max_chars: int) -> str:
    text = _require_str(value, where=where, max_chars=max_chars)
    if _EMAIL.search(text) or _PHONE.search(text) or _SECRET.search(text):
        raise MeetingReadinessError(f"{where} contains disallowed direct contact/secret material")
    return text


def _validate_interval(obj: Any, *, where: str) -> tuple[dict[str, str], datetime, datetime]:
    item = _require_exact_keys(obj, {"start", "end"}, where=where)
    start = _parse_utc(item["start"], where=f"{where}.start")
    end = _parse_utc(item["end"], where=f"{where}.end")
    if end <= start:
        raise MeetingReadinessError(f"{where} end must be after start")
    return {"start": _utc_text(start), "end": _utc_text(end)}, start, end


def _validate_intervals(items: Any, *, where: str, maximum: int) -> tuple[list[dict[str, str]], list[tuple[datetime, datetime]]]:
    if type(items) is not list or not items or len(items) > maximum:
        raise MeetingReadinessError(f"{where} must be a nonempty bounded list")
    normalized: list[dict[str, str]] = []
    parsed: list[tuple[datetime, datetime]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(items):
        item, start, end = _validate_interval(raw, where=f"{where}[{index}]")
        key = (item["start"], item["end"])
        if key in seen:
            raise MeetingReadinessError(f"duplicate interval in {where}")
        seen.add(key)
        normalized.append(item)
        parsed.append((start, end))
    order = sorted(range(len(normalized)), key=lambda i: (normalized[i]["start"], normalized[i]["end"]))
    return [normalized[i] for i in order], [parsed[i] for i in order]


def _request_binding(opportunity_id: str, thread_ref: str, request: dict[str, Any]) -> dict[str, Any]:
    windows = sorted(request["windows"], key=lambda item: (item["start"], item["end"]))
    return {
        "opportunity_id": opportunity_id,
        "thread_ref": thread_ref,
        "duration_minutes": request["duration_minutes"],
        "timezone": request["timezone"],
        "windows": windows,
    }


def request_digest(opportunity_id: str, thread_ref: str, request: dict[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(_request_binding(opportunity_id, thread_ref, request)))


def busy_digest(busy_windows: list[dict[str, str]]) -> str:
    ordered = sorted(busy_windows, key=lambda item: (item["start"], item["end"]))
    return sha256_hex(canonical_json_bytes(ordered))


def _validate_policy(policy: Any) -> dict[str, Any]:
    required = set(DEFAULT_POLICY)
    p = _require_exact_keys(policy, required, where="policy")
    if p["schema"] != DEFAULT_POLICY["schema"]:
        raise MeetingReadinessError("unsupported policy schema")
    out = {"schema": p["schema"]}
    for key in required - {"schema"}:
        maximum = 10**9 if key.endswith("seconds") else 100000
        out[key] = _integer(p[key], where=f"policy.{key}", minimum=1, maximum=maximum)
    return out


def _validate_prep(prep: Any, policy: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    required = {"context", *PREP_SCALARS, *PREP_LISTS}
    obj = _require_exact_keys(prep, required, where="prep")
    normalized: dict[str, Any] = {}
    missing: list[str] = []

    context = obj["context"]
    if type(context) is not list or len(context) > policy["max_prep_items"]:
        raise MeetingReadinessError("prep.context must be a bounded list")
    ctx_out: list[dict[str, str]] = []
    seen_facts: set[tuple[str, str]] = set()
    for i, raw in enumerate(context):
        fact = _require_exact_keys(raw, {"text", "source_ref"}, where=f"prep.context[{i}]")
        text = _private_text(fact["text"], where=f"prep.context[{i}].text", max_chars=policy["max_text_chars"])
        source_ref = _safe_id(fact["source_ref"], where=f"prep.context[{i}].source_ref")
        key = (text, source_ref)
        if key in seen_facts:
            raise MeetingReadinessError("duplicate prep context fact")
        seen_facts.add(key)
        ctx_out.append({"text": text, "source_ref": source_ref})
    if not ctx_out:
        missing.append("context")
    normalized["context"] = sorted(ctx_out, key=lambda x: (x["source_ref"], x["text"]))

    for key in PREP_SCALARS:
        value = obj[key]
        if type(value) is not str:
            raise MeetingReadinessError(f"prep.{key} must be a string")
        if value:
            normalized[key] = _private_text(value, where=f"prep.{key}", max_chars=policy["max_text_chars"])
        else:
            normalized[key] = ""
            missing.append(key)

    for key in PREP_LISTS:
        value = obj[key]
        if type(value) is not list or len(value) > policy["max_prep_items"]:
            raise MeetingReadinessError(f"prep.{key} must be a bounded list")
        out: list[str] = []
        seen: set[str] = set()
        for i, item in enumerate(value):
            text = _private_text(item, where=f"prep.{key}[{i}]", max_chars=policy["max_text_chars"])
            if text in seen:
                raise MeetingReadinessError(f"duplicate prep.{key} item")
            seen.add(text)
            out.append(text)
        if not out:
            missing.append(key)
        normalized[key] = out
    return normalized, missing


def _validate_packet(packet: Any, policy: dict[str, Any]) -> dict[str, Any]:
    obj = _require_exact_keys(
        packet,
        {"schema", "opportunity_id", "owner_ref", "counterparty_ref", "thread_ref", "inbound", "request", "prep"},
        {"availability"},
        where="packet",
    )
    if obj["schema"] != SCHEMA:
        raise MeetingReadinessError("unsupported packet schema")

    opportunity_id = _safe_id(obj["opportunity_id"], where="packet.opportunity_id")
    owner_ref = _safe_id(obj["owner_ref"], where="packet.owner_ref")
    counterparty_ref = _safe_id(obj["counterparty_ref"], where="packet.counterparty_ref")
    thread_ref = _safe_id(obj["thread_ref"], where="packet.thread_ref")

    inbound = _require_exact_keys(obj["inbound"], {"observation_id", "content_sha256", "received_at"}, where="packet.inbound")
    inbound_norm = {
        "observation_id": _safe_id(inbound["observation_id"], where="packet.inbound.observation_id"),
        "content_sha256": _sha(inbound["content_sha256"], where="packet.inbound.content_sha256"),
        "received_at": _utc_text(_parse_utc(inbound["received_at"], where="packet.inbound.received_at")),
    }

    request = _require_exact_keys(obj["request"], {"duration_minutes", "timezone", "windows"}, where="packet.request")
    duration = _integer(request["duration_minutes"], where="packet.request.duration_minutes", minimum=5, maximum=policy["max_duration_minutes"])
    tz = _timezone_name(request["timezone"], where="packet.request.timezone")
    windows, _ = _validate_intervals(request["windows"], where="packet.request.windows", maximum=policy["max_windows"])
    request_norm = {"duration_minutes": duration, "timezone": tz, "windows": windows}

    prep_norm, prep_missing = _validate_prep(obj["prep"], policy)

    availability_norm = None
    if "availability" in obj and obj["availability"] is not None:
        availability = _require_exact_keys(
            obj["availability"],
            {
                "observation_id", "provider_ref", "captured_at", "opportunity_id", "thread_ref",
                "timezone", "duration_minutes", "request_digest", "busy_windows", "busy_digest",
                "result", "proposed_slot",
            },
            {"owner_ref"},
            where="packet.availability",
        )
        busy, _ = _validate_intervals(
            availability["busy_windows"], where="packet.availability.busy_windows", maximum=policy["max_busy_windows"]
        ) if availability["busy_windows"] else ([], [])
        slot, _, _ = _validate_interval(availability["proposed_slot"], where="packet.availability.proposed_slot")
        result = _require_str(availability["result"], where="packet.availability.result", max_chars=16)
        if result not in {"FREE", "BUSY", "UNKNOWN"}:
            raise MeetingReadinessError("packet.availability.result invalid")
        availability_norm = {
            "observation_id": _safe_id(availability["observation_id"], where="packet.availability.observation_id"),
            "provider_ref": _safe_id(availability["provider_ref"], where="packet.availability.provider_ref"),
            "captured_at": _utc_text(_parse_utc(availability["captured_at"], where="packet.availability.captured_at")),
            "owner_ref": (
                _safe_id(availability["owner_ref"], where="packet.availability.owner_ref")
                if "owner_ref" in availability
                else None
            ),
            "opportunity_id": _safe_id(availability["opportunity_id"], where="packet.availability.opportunity_id"),
            "thread_ref": _safe_id(availability["thread_ref"], where="packet.availability.thread_ref"),
            "timezone": _timezone_name(availability["timezone"], where="packet.availability.timezone"),
            "duration_minutes": _integer(availability["duration_minutes"], where="packet.availability.duration_minutes", minimum=5, maximum=policy["max_duration_minutes"]),
            "request_digest": _sha(availability["request_digest"], where="packet.availability.request_digest"),
            "busy_windows": busy,
            "busy_digest": _sha(availability["busy_digest"], where="packet.availability.busy_digest"),
            "result": result,
            "proposed_slot": slot,
        }

    return {
        "schema": SCHEMA,
        "opportunity_id": opportunity_id,
        "owner_ref": owner_ref,
        "counterparty_ref": counterparty_ref,
        "thread_ref": thread_ref,
        "inbound": inbound_norm,
        "request": request_norm,
        "prep": prep_norm,
        "_prep_missing": prep_missing,
        "availability": availability_norm,
    }


def _interval_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _slot_evaluation(packet: dict[str, Any], policy: dict[str, Any], as_of: datetime) -> tuple[str, list[str]]:
    reasons: list[str] = []
    inbound_at = _parse_utc(packet["inbound"]["received_at"], where="normalized.inbound.received_at")
    if inbound_at > as_of:
        return HOLD, ["inbound evidence is in the future"]
    if (as_of - inbound_at).total_seconds() > policy["max_inbound_age_seconds"]:
        return REQUEST_STALE, ["meeting request evidence is stale"]

    availability = packet["availability"]
    if availability is None:
        return CALENDAR_REQUIRED, ["independent calendar availability evidence is missing"]

    captured = _parse_utc(availability["captured_at"], where="normalized.availability.captured_at")
    if captured > as_of:
        return HOLD, ["availability evidence is in the future"]
    if (as_of - captured).total_seconds() > policy["max_availability_age_seconds"]:
        return CALENDAR_REQUIRED, ["availability evidence is stale"]

    expected_req = request_digest(packet["opportunity_id"], packet["thread_ref"], packet["request"])
    expected_busy = busy_digest(availability["busy_windows"])
    bindings = [
        (availability["owner_ref"] == packet["owner_ref"], "availability owner binding mismatch"),
        (availability["opportunity_id"] == packet["opportunity_id"], "availability opportunity binding mismatch"),
        (availability["thread_ref"] == packet["thread_ref"], "availability thread binding mismatch"),
        (availability["timezone"] == packet["request"]["timezone"], "availability timezone binding mismatch"),
        (availability["duration_minutes"] == packet["request"]["duration_minutes"], "availability duration binding mismatch"),
        (availability["request_digest"] == expected_req, "availability request digest mismatch"),
        (availability["busy_digest"] == expected_busy, "availability busy digest mismatch"),
    ]
    for ok, reason in bindings:
        if not ok:
            reasons.append(reason)
    if reasons:
        return HOLD, reasons

    slot, slot_start, slot_end = _validate_interval(availability["proposed_slot"], where="normalized.availability.proposed_slot")
    duration_seconds = int((slot_end - slot_start).total_seconds())
    if duration_seconds != packet["request"]["duration_minutes"] * 60:
        return HOLD, ["proposed slot duration does not match request"]
    if (slot_start - as_of).total_seconds() > policy["max_slot_horizon_seconds"]:
        return HOLD, ["proposed slot exceeds policy horizon"]
    if slot_start <= as_of:
        return REQUEST_STALE, ["proposed slot has already started"]

    request_ranges = [
        (_parse_utc(w["start"], where="window.start"), _parse_utc(w["end"], where="window.end"))
        for w in packet["request"]["windows"]
    ]
    if not any(start <= slot_start and slot_end <= end for start, end in request_ranges):
        return HOLD, ["proposed slot is outside requested windows"]

    busy_ranges = [
        (_parse_utc(w["start"], where="busy.start"), _parse_utc(w["end"], where="busy.end"))
        for w in availability["busy_windows"]
    ]
    overlaps = any(_interval_overlap(slot_start, slot_end, start, end) for start, end in busy_ranges)
    if availability["result"] == "UNKNOWN":
        return CALENDAR_REQUIRED, ["calendar provider returned UNKNOWN"]
    if availability["result"] == "FREE" and overlaps:
        return HOLD, ["calendar result says FREE but busy evidence overlaps proposed slot"]
    if availability["result"] == "BUSY" and not overlaps:
        return HOLD, ["calendar result says BUSY but busy evidence does not overlap proposed slot"]
    if overlaps or availability["result"] == "BUSY":
        return SLOT_CONFLICT, ["proposed slot conflicts with retained busy evidence"]

    if packet["_prep_missing"]:
        return PREP_REQUIRED, ["meeting preparation incomplete: " + ", ".join(packet["_prep_missing"])]
    return READY, ["calendar evidence is current and free; preparation packet is complete"]


def _public_packet(normalized: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(normalized)
    out.pop("_prep_missing", None)
    return out


def compile_meeting_readiness(packet: Any, *, as_of: datetime, policy: Any = DEFAULT_POLICY) -> dict[str, Any]:
    """Compile a deterministic owner-review receipt at trusted ``as_of``.

    Callers must treat ``as_of`` as verifier-owned time.  The production CLI
    captures it internally; explicit injection exists for tests/offline proof.
    """

    p = _validate_policy(policy)
    trusted_as_of = as_of.astimezone(timezone.utc).replace(microsecond=0) if as_of.tzinfo else None
    if trusted_as_of is None:
        raise MeetingReadinessError("trusted as_of must be timezone-aware")
    normalized = _validate_packet(packet, p)
    public_packet = _public_packet(normalized)
    state, reasons = _slot_evaluation(normalized, p, trusted_as_of)
    packet_sha = sha256_hex(canonical_json_bytes(public_packet))
    policy_sha = sha256_hex(canonical_json_bytes(p))
    receipt_core = {
        "schema": RECEIPT_SCHEMA,
        "state": state,
        "as_of": _utc_text(trusted_as_of),
        "packet_sha256": packet_sha,
        "policy_sha256": policy_sha,
        "opportunity_id": normalized["opportunity_id"],
        "owner_ref": normalized["owner_ref"],
        "thread_ref": normalized["thread_ref"],
        "reasons": reasons,
        "authority": {
            "owner_review_only": True,
            "calendar_query": False,
            "calendar_mutation": False,
            "send_or_reply": False,
            "scheduling_confirmation": False,
            "commercial_commitment": False,
        },
        "meeting": {
            "timezone": normalized["request"]["timezone"],
            "duration_minutes": normalized["request"]["duration_minutes"],
            "proposed_slot": normalized["availability"]["proposed_slot"] if normalized["availability"] else None,
        },
        "prep": normalized["prep"],
    }
    receipt_sha = sha256_hex(canonical_json_bytes(receipt_core))
    return {**receipt_core, "receipt_sha256": receipt_sha}


def render_markdown(receipt: dict[str, Any]) -> str:
    if type(receipt) is not dict or receipt.get("schema") != RECEIPT_SCHEMA:
        raise MeetingReadinessError("invalid receipt")
    prep = receipt["prep"]
    lines = [
        "# Sales meeting readiness",
        "",
        f"**State:** `{receipt['state']}`",
        f"**Opportunity:** `{receipt['opportunity_id']}`",
        f"**Owner:** `{receipt['owner_ref']}`",
        f"**Thread:** `{receipt['thread_ref']}`",
        f"**Verified at:** `{receipt['as_of']}`",
        "",
        "## Calendar gate",
        "",
        f"- Timezone: `{receipt['meeting']['timezone']}`",
        f"- Duration: {receipt['meeting']['duration_minutes']} minutes",
    ]
    slot = receipt["meeting"]["proposed_slot"]
    if slot:
        lines.append(f"- Proposed slot: `{slot['start']}` → `{slot['end']}`")
    else:
        lines.append("- Proposed slot: not independently verified")
    lines += ["", "### Disposition evidence", ""]
    lines += [f"- {reason}" for reason in receipt["reasons"]]
    lines += ["", "## Meeting brief", "", "### Context", ""]
    if prep["context"]:
        lines += [f"- {fact['text']} (`{fact['source_ref']}`)" for fact in prep["context"]]
    else:
        lines.append("- _Missing_ ")
    lines += ["", "### Objective", "", prep["objective"] or "_Missing_", ""]
    for heading, key in (
        ("Key questions", "key_questions"),
        ("Likely asks", "likely_asks"),
        ("Risks / commitments to avoid", "risks_commitments_to_avoid"),
        ("Owner actions", "owner_actions"),
    ):
        lines += [f"### {heading}", ""]
        items = prep[key]
        lines += [f"- {item}" for item in items] if items else ["- _Missing_"]
        lines.append("")
    lines += ["### Recommended opening", "", prep["recommended_opening"] or "_Missing_", ""]
    lines += ["### Recommended closing", "", prep["recommended_closing"] or "_Missing_", ""]
    lines += [
        "## Authority ceiling",
        "",
        "This receipt is for owner review only. It does not authorize a calendar query or mutation, invite, send/reply, scheduling confirmation, commercial commitment, acceptance, payment, award, or revenue recognition.",
        "",
        f"Receipt SHA-256: `{receipt['receipt_sha256']}`",
    ]
    return "\n".join(lines) + "\n"


def verify_receipt(packet: Any, receipt: Any, *, policy: Any = DEFAULT_POLICY) -> bool:
    if type(receipt) is not dict or receipt.get("schema") != RECEIPT_SCHEMA:
        raise MeetingReadinessError("invalid receipt schema")
    expected_keys = {
        "schema", "state", "as_of", "packet_sha256", "policy_sha256", "opportunity_id", "owner_ref",
        "thread_ref", "reasons", "authority", "meeting", "prep", "receipt_sha256",
    }
    if set(receipt) != expected_keys:
        raise MeetingReadinessError("receipt keys invalid")
    if receipt["state"] not in STATES:
        raise MeetingReadinessError("receipt state invalid")
    as_of = _parse_utc(receipt["as_of"], where="receipt.as_of")
    rebuilt = compile_meeting_readiness(packet, as_of=as_of, policy=policy)
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(receipt):
        raise MeetingReadinessError("receipt does not verify")
    return True
