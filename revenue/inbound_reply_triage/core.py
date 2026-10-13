from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping
import unicodedata

INPUT_SCHEMA = "inbound-reply-triage-input/v1"
PACKET_SCHEMA = "inbound-reply-triage-packet/v1"
RECEIPT_SCHEMA = "inbound-reply-triage-receipt/v1"

EVENT_TYPES = {
    "MUSE_SELECTED", "SENT", "HUMAN_REPLY", "AUTO_REPLY", "HARD_BOUNCE",
    "SOFT_BOUNCE", "REJECTION", "DNR", "COLLISION", "RESPONSE_DRAFT_READY",
}
STATES = {
    "NEW_HUMAN_INBOUND", "AUTO_REPLY", "BOUNCE", "REJECTION",
    "WAITING_EXTERNAL", "DNR", "COLLISION_HOLD", "MUSE_REQUIRED",
    "RESPONSE_READY_OWNER_REVIEW",
}
AUTHORITY = {
    "external_send_authorized": False,
    "muse_selection_authorized": False,
    "buyer_acceptance_authorized": False,
    "contract_authorized": False,
    "invoice_authorized": False,
    "payment_mutation_authorized": False,
    "receivable_authorized": False,
    "revenue_recognition_authorized": False,
}
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,191}$")
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
STATE_PRIORITY = {
    "NEW_HUMAN_INBOUND": 0,
    "RESPONSE_READY_OWNER_REVIEW": 1,
    "COLLISION_HOLD": 2,
    "BOUNCE": 3,
    "REJECTION": 4,
    "AUTO_REPLY": 5,
    "MUSE_REQUIRED": 6,
    "WAITING_EXTERNAL": 7,
    "DNR": 8,
}
# Unicode Default_Ignorable_Code_Point members whose general category is not C.
# Category-C default ignorables are already rejected below. Keeping this explicit
# table avoids treating every combining mark as invisible while still rejecting
# variation selectors, grapheme joiners, Hangul fillers, and related controls.
DEFAULT_IGNORABLE_NON_C_RANGES = (
    (0x034F, 0x034F),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFFA0, 0xFFA0),
    (0xE0100, 0xE01EF),
)


class TriageError(ValueError):
    pass


def _reject_float(token: str) -> None:
    raise TriageError(f"floats/non-finite numbers are forbidden: {token}")


def _parse_int(token: str) -> int:
    digits = token[1:] if token.startswith("-") else token
    if len(digits) > 128:
        raise TriageError("integer token too long")
    return int(token)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise TriageError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    if type(raw) is not str:
        raise TriageError("JSON source must be text")
    if len(raw.encode("utf-8", "strict")) > 1_048_576:
        raise TriageError("JSON source exceeds 1 MiB")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_int=_parse_int,
            parse_constant=_reject_float,
        )
    except TriageError:
        raise
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError) as exc:
        raise TriageError(f"invalid JSON: {exc}") from None


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ) + "\n"
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise TriageError(f"cannot canonicalize: {exc}") from None


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _expect_map(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise TriageError(f"{where} must be an exact object")
    if any(type(k) is not str for k in value):
        raise TriageError(f"{where} requires string keys")
    return value


def _exact_keys(obj: Mapping[str, Any], expected: set[str], where: str) -> None:
    if set(obj) != expected:
        raise TriageError(
            f"{where} keys mismatch; missing={sorted(expected-set(obj))} "
            f"extra={sorted(set(obj)-expected)}"
        )


def _expect_list(value: Any, where: str, *, max_items: int) -> list[Any]:
    if type(value) is not list or len(value) > max_items:
        raise TriageError(f"{where} must be an array of <= {max_items} items")
    return value


def _text(value: Any, where: str, *, max_len: int) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise TriageError(f"{where} must be non-empty text <= {max_len}")
    if any(ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise TriageError(f"{where} contains forbidden control/surrogate text")
    return value


def _is_non_c_default_ignorable(ch: str) -> bool:
    cp = ord(ch)
    return any(start <= cp <= end for start, end in DEFAULT_IGNORABLE_NON_C_RANGES)


def _binding_text(value: Any, where: str, *, max_len: int) -> str:
    """Return an exact, collision-safe human binding label.

    Validate the caller-authored spelling before any whitespace canonicalization so
    trim-erased or default-ignorable Unicode cannot alias a clean lane. Only
    ordinary ASCII SPACE may be used as boundary whitespace and removed after the
    original text has passed the visibility and exact-NFKC fences.
    """
    original = _text(value, where, max_len=max_len)
    for ch in original:
        category = unicodedata.category(ch)
        if (
            category.startswith("C")
            or _is_non_c_default_ignorable(ch)
            or category in {"Zl", "Zp"}
            or (category == "Zs" and ch != " ")
        ):
            raise TriageError(f"{where} contains invisible/control text")
    if unicodedata.normalize("NFKC", original) != original:
        raise TriageError(f"{where} must be exact NFKC text")
    text = original.strip(" ")
    if not text:
        raise TriageError(f"{where} must remain non-empty after trimming")
    return text


def _token(value: Any, where: str) -> str:
    value = _text(value, where, max_len=192)
    if not TOKEN_RE.fullmatch(value):
        raise TriageError(f"{where} has invalid token characters")
    return value


def _int(value: Any, where: str, *, low: int, high: int) -> int:
    if type(value) is not int or value < low or value > high:
        raise TriageError(f"{where} must be integer in [{low}, {high}]")
    return value


def _timestamp(value: Any, where: str) -> tuple[str, datetime]:
    text = _text(value, where, max_len=32)
    if not text.endswith("Z") or "." in text:
        raise TriageError(f"{where} must be whole-second UTC RFC3339 Z")
    try:
        dt = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise TriageError(f"{where} is not a valid UTC instant") from None
    return text, dt


def _refs(value: Any, where: str) -> list[str]:
    items = _expect_list(value, where, max_items=16)
    if not items:
        raise TriageError(f"{where} must contain at least one retained evidence ref")
    out: list[str] = []
    for i, item in enumerate(items):
        ref = _text(item, f"{where}[{i}]", max_len=512)
        if ref in out:
            raise TriageError(f"{where} contains duplicate evidence ref")
        out.append(ref)
    return out


def _lease(value: Any, where: str, evaluation: datetime) -> dict[str, Any] | None:
    if value is None:
        return None
    obj = _expect_map(value, where)
    _exact_keys(obj, {"holder", "acquired_at", "expires_at", "evidence_refs"}, where)
    holder = _token(obj["holder"], f"{where}.holder")
    acquired_text, acquired = _timestamp(obj["acquired_at"], f"{where}.acquired_at")
    expires_text, expires = _timestamp(obj["expires_at"], f"{where}.expires_at")
    if expires <= acquired:
        raise TriageError(f"{where}: expires_at must be after acquired_at")
    if acquired > evaluation:
        raise TriageError(f"{where}: future lease")
    return {
        "holder": holder,
        "acquired_at": acquired_text,
        "expires_at": expires_text,
        "evidence_refs": _refs(obj["evidence_refs"], f"{where}.evidence_refs"),
        "active": expires > evaluation,
    }


def _event(value: Any, where: str, evaluation: datetime, previous: datetime | None) -> tuple[dict[str, Any], datetime]:
    obj = _expect_map(value, where)
    _exact_keys(obj, {"id", "type", "at", "evidence_refs"}, where)
    event_id = _token(obj["id"], f"{where}.id")
    typ = _text(obj["type"], f"{where}.type", max_len=32)
    if typ not in EVENT_TYPES:
        raise TriageError(f"{where}.type unsupported")
    at_text, at = _timestamp(obj["at"], f"{where}.at")
    if at > evaluation:
        raise TriageError(f"{where}: event occurs after evaluation_at")
    if previous is not None and at < previous:
        raise TriageError(f"{where}: chronology reverses")
    return {
        "id": event_id,
        "type": typ,
        "at": at_text,
        "evidence_refs": _refs(obj["evidence_refs"], f"{where}.evidence_refs"),
    }, at


def _latest(events: list[dict[str, Any]], typ: str) -> dict[str, Any] | None:
    for event in reversed(events):
        if event["type"] == typ:
            return event
    return None


def _after(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    return a is not None and (b is None or a["at"] > b["at"])


def _minutes_between(later: datetime, earlier_text: str) -> int:
    earlier = datetime.strptime(earlier_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return max(0, int((later - earlier).total_seconds() // 60))


def _validate_transition_shape(events: list[dict[str, Any]], lane_id: str) -> None:
    seen_ids: set[str] = set()
    for event in events:
        if event["id"] in seen_ids:
            raise TriageError(f"{lane_id}: duplicate event id")
        seen_ids.add(event["id"])

    terminalish = {"HUMAN_REPLY", "AUTO_REPLY", "HARD_BOUNCE", "REJECTION", "DNR", "COLLISION"}
    by_time: dict[str, set[str]] = {}
    for event in events:
        if event["type"] in terminalish:
            by_time.setdefault(event["at"], set()).add(event["type"])
    for at, kinds in by_time.items():
        if len(kinds) > 1:
            raise TriageError(f"{lane_id}: ambiguous same-time status evidence at {at}: {sorted(kinds)}")

    last_sent: dict[str, Any] | None = None
    last_human: dict[str, Any] | None = None
    last_muse: dict[str, Any] | None = None
    for event in events:
        typ = event["type"]
        if typ == "MUSE_SELECTED":
            last_muse = event
        elif typ == "SENT":
            if (
                last_muse is None
                or last_muse["at"] >= event["at"]
                or (last_sent is not None and last_muse["at"] <= last_sent["at"])
            ):
                raise TriageError(f"{lane_id}: SENT requires fresh prior MUSE_SELECTED")
            if last_sent is not None and (
                last_human is None
                or last_human["at"] <= last_sent["at"]
                or last_human["at"] >= event["at"]
            ):
                raise TriageError(f"{lane_id}: repeat SENT requires intervening prior HUMAN_REPLY")
            last_sent = event
        elif typ == "HUMAN_REPLY":
            last_human = event
        elif typ in {"AUTO_REPLY", "HARD_BOUNCE", "SOFT_BOUNCE"}:
            if last_sent is None:
                raise TriageError(f"{lane_id}: {typ} requires prior SENT")
        elif typ == "RESPONSE_DRAFT_READY":
            if last_human is None or last_human["at"] >= event["at"]:
                raise TriageError(f"{lane_id}: RESPONSE_DRAFT_READY requires strictly earlier HUMAN_REPLY")


def _classify(events: list[dict[str, Any]], lease: dict[str, Any] | None, evaluation: datetime, stale_after: int) -> dict[str, Any]:
    human = _latest(events, "HUMAN_REPLY")
    auto = _latest(events, "AUTO_REPLY")
    hard_bounce = _latest(events, "HARD_BOUNCE")
    rejection = _latest(events, "REJECTION")
    dnr = _latest(events, "DNR")
    collision = _latest(events, "COLLISION")
    muse = _latest(events, "MUSE_SELECTED")
    sent = _latest(events, "SENT")
    draft = _latest(events, "RESPONSE_DRAFT_READY")

    if dnr is not None and not _after(human, dnr):
        state = "DNR"
    elif collision is not None and not _after(muse, collision) and not _after(human, collision):
        state = "COLLISION_HOLD"
    elif rejection is not None and not _after(human, rejection):
        state = "REJECTION"
    elif hard_bounce is not None and not _after(human, hard_bounce):
        state = "BOUNCE"
    elif human is not None and _after(human, sent):
        if draft is not None and draft["at"] > human["at"]:
            state = "RESPONSE_READY_OWNER_REVIEW" if lease is not None and lease["active"] else "COLLISION_HOLD"
        else:
            state = "NEW_HUMAN_INBOUND"
    elif auto is not None and _after(auto, human) and (sent is None or auto["at"] >= sent["at"]):
        state = "AUTO_REPLY"
    elif sent is not None:
        state = "WAITING_EXTERNAL"
    else:
        state = "MUSE_REQUIRED"

    human_age = _minutes_between(evaluation, human["at"]) if human else None
    return {
        "state": state,
        "latest_human_reply_at": human["at"] if human else None,
        "human_reply_age_minutes": human_age,
        "human_reply_stale": human_age is not None and human_age >= stale_after,
        "latest_event_at": events[-1]["at"] if events else None,
        "active_lease_holder": lease["holder"] if lease is not None and lease["active"] else None,
        "next_gate": (
            "MUSE_REQUIRED_BEFORE_ANY_SEND"
            if state in {"NEW_HUMAN_INBOUND", "RESPONSE_READY_OWNER_REVIEW", "MUSE_REQUIRED"}
            else "NO_OUTBOUND_FROM_TRIAGE"
        ),
    }


def _lane(value: Any, where: str, evaluation: datetime, stale_after: int) -> dict[str, Any]:
    obj = _expect_map(value, where)
    _exact_keys(
        obj,
        {"id", "org_key", "route_key", "domain", "purpose_key", "thread_key", "lease", "events"},
        where,
    )
    lane_id = _token(obj["id"], f"{where}.id")
    org = _binding_text(obj["org_key"], f"{where}.org_key", max_len=192)
    route = _binding_text(obj["route_key"], f"{where}.route_key", max_len=320)
    domain = _text(obj["domain"], f"{where}.domain", max_len=253).lower()
    if not DOMAIN_RE.fullmatch(domain):
        raise TriageError(f"{where}.domain invalid")
    purpose = _token(obj["purpose_key"], f"{where}.purpose_key")
    thread = _token(obj["thread_key"], f"{where}.thread_key")
    lease = _lease(obj["lease"], f"{where}.lease", evaluation)
    raw_events = _expect_list(obj["events"], f"{where}.events", max_items=256)
    events: list[dict[str, Any]] = []
    previous: datetime | None = None
    for i, raw in enumerate(raw_events):
        event, previous = _event(raw, f"{where}.events[{i}]", evaluation, previous)
        events.append(event)
    _validate_transition_shape(events, lane_id)
    classification = _classify(events, lease, evaluation, stale_after)
    return {
        "id": lane_id,
        "binding": {
            "org_key": org,
            "route_key": route,
            "domain": domain,
            "purpose_key": purpose,
            "thread_key": thread,
        },
        "lease": lease,
        "events": events,
        "summary": classification,
    }


def compile_triage(raw: Any) -> dict[str, Any]:
    obj = _expect_map(raw, "input")
    _exact_keys(obj, {"schema", "evaluation_at", "stale_after_minutes", "lanes"}, "input")
    if obj["schema"] != INPUT_SCHEMA:
        raise TriageError("input.schema mismatch")
    evaluation_text, evaluation = _timestamp(obj["evaluation_at"], "input.evaluation_at")
    stale_after = _int(obj["stale_after_minutes"], "input.stale_after_minutes", low=15, high=60 * 24 * 30)
    raw_lanes = _expect_list(obj["lanes"], "input.lanes", max_items=4096)
    lanes = [_lane(item, f"input.lanes[{i}]", evaluation, stale_after) for i, item in enumerate(raw_lanes)]

    ids = [lane["id"] for lane in lanes]
    if len(ids) != len(set(ids)):
        raise TriageError("duplicate lane id")
    bindings = [
        (
            lane["binding"]["org_key"].casefold(),
            lane["binding"]["route_key"].casefold(),
            lane["binding"]["purpose_key"].casefold(),
            lane["binding"]["thread_key"].casefold(),
        )
        for lane in lanes
    ]
    if len(bindings) != len(set(bindings)):
        raise TriageError("duplicate org×route×purpose×thread binding")

    counts = {state: 0 for state in sorted(STATES)}
    for lane in lanes:
        counts[lane["summary"]["state"]] += 1

    queue = sorted(
        [
            {
                "lane_id": lane["id"],
                "state": lane["summary"]["state"],
                "latest_human_reply_at": lane["summary"]["latest_human_reply_at"],
                "human_reply_age_minutes": lane["summary"]["human_reply_age_minutes"],
                "human_reply_stale": lane["summary"]["human_reply_stale"],
                "active_lease_holder": lane["summary"]["active_lease_holder"],
                "next_gate": lane["summary"]["next_gate"],
            }
            for lane in lanes
        ],
        key=lambda row: (
            STATE_PRIORITY[row["state"]],
            -(row["human_reply_age_minutes"] if row["human_reply_age_minutes"] is not None else -1),
            row["lane_id"],
        ),
    )
    return {
        "schema": PACKET_SCHEMA,
        "evaluation_at": evaluation_text,
        "stale_after_minutes": stale_after,
        "authority": dict(AUTHORITY),
        "state_counts": counts,
        "lanes": sorted(lanes, key=lambda lane: lane["id"]),
        "owner_review_queue": queue,
    }


def make_receipt(raw: Any, packet: Mapping[str, Any]) -> dict[str, Any]:
    expected = compile_triage(raw)
    if type(packet) is not dict or packet != expected:
        raise TriageError("packet is not the exact compiled result")
    return {
        "schema": RECEIPT_SCHEMA,
        "input_sha256": _sha(raw),
        "packet_sha256": _sha(packet),
        "authority_sha256": _sha(AUTHORITY),
    }


def verify_triage(raw: Any, packet: Any, receipt: Any) -> bool:
    try:
        if type(packet) is not dict or type(receipt) is not dict:
            return False
        _exact_keys(receipt, {"schema", "input_sha256", "packet_sha256", "authority_sha256"}, "receipt")
        if receipt["schema"] != RECEIPT_SCHEMA:
            return False
        expected = compile_triage(raw)
        expected_receipt = make_receipt(raw, expected)
        return packet == expected and receipt == expected_receipt
    except (TriageError, TypeError, ValueError, RecursionError):
        return False


def _read(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise TriageError(f"cannot read {path}: {exc}") from None
    return strict_json_loads(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile evidence-bound inbound commercial reply triage.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        source = _read(args.input)
        packet = compile_triage(source)
        receipt = make_receipt(source, packet)
        if args.packet:
            args.packet.write_text(canonical_json(packet), encoding="utf-8")
        else:
            print(canonical_json(packet), end="")
        if args.receipt:
            args.receipt.write_text(canonical_json(receipt), encoding="utf-8")
        return 0
    except (TriageError, OSError, UnicodeError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
