from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "TJL_REVENUE_EXPERIMENT_ALLOCATOR_V1"
BUNDLE_SCHEMA = "TJL_REVENUE_EXPERIMENT_ALLOCATOR_BUNDLE_V1"
TRUTH_BOUNDARY = "AGGREGATED_RETAINED_OUTCOMES_NOT_PROVIDER_AUTHENTICATED"
ROUTE_KINDS = frozenset({"EMAIL", "CONTACT_FORM", "DIRECT_MESSAGE", "PORTAL_MESSAGE"})
_AUTHORITY_ITEMS = (
    ("external_send", False),
    ("recipient_selection", False),
    ("muse_selection", False),
    ("provider_mutation", False),
    ("contact_creation", False),
    ("payment_movement", False),
    ("receivable_establishment", False),
    ("accounting_assertion", False),
    ("revenue_recognition", False),
)
_SEGMENT_KEYS = {
    "segment_id",
    "offer_id",
    "route_kind",
    "audience_label",
    "evidence_observed_at",
    "evidence_ref",
    "evidence_sha256",
    "available_candidates",
    "attempts",
    "delivered",
    "human_replies",
    "positive_replies",
    "proposals",
    "accepted",
    "paid",
    "retained_cash_cents",
    "dnr_events",
    "collision_events",
    "fresh_census_complete",
    "route_available",
    "unresolved_collision",
}


class AllocationError(ValueError):
    pass


def _authority() -> dict[str, bool]:
    return dict(_AUTHORITY_ITEMS)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise AllocationError(f"not canonical JSON: {exc}") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _exact(value: Any, keys: set[str] | frozenset[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise AllocationError(f"{where}: exact object required")
    have, want = set(value), set(keys)
    if have != want:
        raise AllocationError(
            f"{where}: exact keys required; missing={sorted(want-have)}; extra={sorted(have-want)}"
        )
    return value


def _text(value: Any, where: str, maximum: int = 512) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise AllocationError(f"{where}: bounded nonempty string required")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise AllocationError(f"{where}: control characters forbidden")
    return value


def _semantic_identity_text(value: str, where: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    if any(unicodedata.category(ch).startswith("C") for ch in normalized):
        raise AllocationError(f"{where}: Unicode control/format characters forbidden")
    canonical = " ".join(normalized.split()).casefold()
    if not canonical:
        raise AllocationError(f"{where}: empty after semantic normalization")
    return canonical


def _semantic_segment_key(segment: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _semantic_identity_text(segment["offer_id"], f"{segment['segment_id']}.offer_id"),
        segment["route_kind"],
        _semantic_identity_text(segment["audience_label"], f"{segment['segment_id']}.audience_label"),
    )


def _sha(value: Any, where: str) -> str:
    text = _text(value, where, 64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise AllocationError(f"{where}: lowercase sha256 required")
    return text


def _uint(value: Any, where: str, maximum: int = 10**12) -> int:
    if type(value) is bool or type(value) is not int or value < 0 or value > maximum:
        raise AllocationError(f"{where}: bounded nonnegative integer required")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise AllocationError(f"{where}: boolean required")
    return value


def _time(value: Any, where: str) -> datetime:
    if type(value) is not str or "." in value or not value.endswith("Z"):
        raise AllocationError(f"{where}: whole-second UTC RFC3339 Z required")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise AllocationError(f"{where}: invalid timestamp") from exc


def _bps(num: int, den: int) -> int:
    return 0 if den <= 0 else (num * 10_000) // den


def _validate_segment(raw: Any, evaluation_at: datetime, max_age_hours: int) -> dict[str, Any]:
    row = _exact(raw, _SEGMENT_KEYS, "segment")
    sid = _text(row["segment_id"], "segment.segment_id", 120)
    observed = _time(row["evidence_observed_at"], f"{sid}.evidence_observed_at")
    if observed > evaluation_at:
        raise AllocationError(f"{sid}: future evidence")
    age_seconds = int((evaluation_at - observed).total_seconds())
    route_kind = _text(row["route_kind"], f"{sid}.route_kind", 40)
    if route_kind not in ROUTE_KINDS:
        raise AllocationError(f"{sid}: unsupported route kind")

    counts = {
        key: _uint(row[key], f"{sid}.{key}")
        for key in (
            "available_candidates",
            "attempts",
            "delivered",
            "human_replies",
            "positive_replies",
            "proposals",
            "accepted",
            "paid",
            "retained_cash_cents",
            "dnr_events",
            "collision_events",
        )
    }
    funnel = [counts[k] for k in ("attempts", "delivered", "human_replies", "positive_replies", "proposals", "accepted", "paid")]
    if any(left < right for left, right in zip(funnel, funnel[1:])):
        raise AllocationError(f"{sid}: retained funnel counts must be monotone")
    if counts["dnr_events"] > counts["attempts"] or counts["collision_events"] > counts["attempts"]:
        raise AllocationError(f"{sid}: DNR/collision count exceeds attempts")
    if counts["paid"] == 0 and counts["retained_cash_cents"] != 0:
        raise AllocationError(f"{sid}: retained cash without retained paid outcome")
    if counts["paid"] > 0 and counts["retained_cash_cents"] == 0:
        raise AllocationError(f"{sid}: paid outcome requires positive retained cash")

    stale = age_seconds > max_age_hours * 3600
    return {
        "segment_id": sid,
        "offer_id": _text(row["offer_id"], f"{sid}.offer_id", 160),
        "route_kind": route_kind,
        "audience_label": _text(row["audience_label"], f"{sid}.audience_label", 240),
        "evidence_observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_age_seconds": age_seconds,
        "evidence_stale": stale,
        "evidence_ref": _text(row["evidence_ref"], f"{sid}.evidence_ref", 1024),
        "evidence_sha256": _sha(row["evidence_sha256"], f"{sid}.evidence_sha256"),
        **counts,
        "fresh_census_complete": _bool(row["fresh_census_complete"], f"{sid}.fresh_census_complete"),
        "route_available": _bool(row["route_available"], f"{sid}.route_available"),
        "unresolved_collision": _bool(row["unresolved_collision"], f"{sid}.unresolved_collision"),
    }


def _maturity(segment: dict[str, Any]) -> tuple[str, int]:
    if segment["paid"]:
        return "RETAINED_PAID_SIGNAL", 0
    if segment["accepted"]:
        return "RETAINED_ACCEPTED_SIGNAL", 1
    if segment["proposals"]:
        return "RETAINED_PROPOSAL_SIGNAL", 2
    if segment["positive_replies"]:
        return "RETAINED_POSITIVE_REPLY_SIGNAL", 3
    if segment["human_replies"]:
        return "RETAINED_HUMAN_REPLY_SIGNAL", 4
    if segment["delivered"]:
        return "RETAINED_DELIVERY_ONLY", 5
    return "NO_RETAINED_DELIVERY_SIGNAL", 6


def _eligibility(segment: dict[str, Any]) -> tuple[str, str]:
    if segment["evidence_stale"]:
        return "HOLD_STALE_EVIDENCE", "Refresh segment outcome evidence before allocating more contact."
    if not segment["fresh_census_complete"]:
        return "HOLD_CENSUS_INCOMPLETE", "Complete current duplicate/DNR/ownership census before any recipient-level work."
    if segment["unresolved_collision"]:
        return "HOLD_COLLISION", "Resolve the active collision before any new recipient-level work."
    if not segment["route_available"]:
        return "HOLD_ROUTE_UNAVAILABLE", "Find a viable route before allocating contact work."
    if segment["available_candidates"] == 0:
        return "EXHAUSTED", "No fresh pre-deduped candidates remain in this segment."
    return "READY", "Eligible only for aggregate planning; every actual recipient still requires fresh census and Muse."


def _rank_key(segment: dict[str, Any]) -> tuple[Any, ...]:
    _, maturity_rank = _maturity(segment)
    attempts = segment["attempts"]
    cash_per_attempt = 0 if attempts == 0 else segment["retained_cash_cents"] // attempts
    paid_bps = _bps(segment["paid"], attempts)
    positive_bps = _bps(segment["positive_replies"], segment["delivered"])
    dnr_bps = _bps(segment["dnr_events"], attempts)
    collision_bps = _bps(segment["collision_events"], attempts)
    return (
        maturity_rank,
        -cash_per_attempt,
        -paid_bps,
        -positive_bps,
        dnr_bps,
        collision_bps,
        segment["segment_id"],
    )


def compile_packet(document: Any) -> dict[str, Any]:
    doc = _exact(
        document,
        {
            "schema",
            "evaluation_at",
            "batch_size",
            "max_segment_share_bps",
            "exploration_slots",
            "max_evidence_age_hours",
            "segments",
        },
        "document",
    )
    if doc["schema"] != SCHEMA:
        raise AllocationError("document.schema: unsupported")
    evaluation_at = _time(doc["evaluation_at"], "document.evaluation_at")
    batch_size = _uint(doc["batch_size"], "document.batch_size", 10_000)
    share_bps = _uint(doc["max_segment_share_bps"], "document.max_segment_share_bps", 10_000)
    if batch_size > 0 and share_bps == 0:
        raise AllocationError("document.max_segment_share_bps: must be positive for nonzero batch")
    exploration_slots = _uint(doc["exploration_slots"], "document.exploration_slots", batch_size)
    if exploration_slots > batch_size:
        raise AllocationError("document.exploration_slots: cannot exceed batch size")
    max_age_hours = _uint(doc["max_evidence_age_hours"], "document.max_evidence_age_hours", 24 * 365)
    if max_age_hours == 0:
        raise AllocationError("document.max_evidence_age_hours: must be positive")
    if type(doc["segments"]) is not list:
        raise AllocationError("document.segments: array required")
    segments = [_validate_segment(row, evaluation_at, max_age_hours) for row in doc["segments"]]
    ids = [s["segment_id"] for s in segments]
    if len(ids) != len(set(ids)):
        raise AllocationError("duplicate segment_id")
    semantic_keys = [_semantic_segment_key(s) for s in segments]
    if len(semantic_keys) != len(set(semantic_keys)):
        raise AllocationError("duplicate semantic segment: offer_id × route_kind × audience_label")
    evidence_bindings = [(s["evidence_ref"], s["evidence_sha256"]) for s in segments]
    if len(evidence_bindings) != len(set(evidence_bindings)):
        raise AllocationError("duplicate evidence binding across segments")

    rows: list[dict[str, Any]] = []
    ready: list[dict[str, Any]] = []
    for segment in sorted(segments, key=lambda s: s["segment_id"]):
        maturity, maturity_rank = _maturity(segment)
        state, reason = _eligibility(segment)
        attempts = segment["attempts"]
        delivered = segment["delivered"]
        row = {
            "segment_id": segment["segment_id"],
            "offer_id": segment["offer_id"],
            "route_kind": segment["route_kind"],
            "audience_label": segment["audience_label"],
            "evidence_observed_at": segment["evidence_observed_at"],
            "evidence_ref": segment["evidence_ref"],
            "evidence_sha256": segment["evidence_sha256"],
            "evidence_stale": segment["evidence_stale"],
            "available_candidates": segment["available_candidates"],
            "maturity": maturity,
            "maturity_rank": maturity_rank,
            "state": state,
            "state_reason": reason,
            "retained_signal": {
                "attempts": attempts,
                "delivered": delivered,
                "human_replies": segment["human_replies"],
                "positive_replies": segment["positive_replies"],
                "proposals": segment["proposals"],
                "accepted": segment["accepted"],
                "paid": segment["paid"],
                "retained_cash_cents": segment["retained_cash_cents"],
                "delivery_rate_bps": _bps(delivered, attempts),
                "human_reply_rate_bps": _bps(segment["human_replies"], delivered),
                "positive_reply_rate_bps": _bps(segment["positive_replies"], delivered),
                "paid_rate_bps": _bps(segment["paid"], attempts),
                "retained_cash_per_attempt_cents": (
                    0 if attempts == 0 else segment["retained_cash_cents"] // attempts
                ),
                "dnr_rate_bps": _bps(segment["dnr_events"], attempts),
                "collision_rate_bps": _bps(segment["collision_events"], attempts),
            },
            "allocated_slots": 0,
            "allocation_role": "NONE",
            "next_action": "NONE",
            "muse_required_before_any_external_contact": True,
            "fresh_recipient_census_required_before_any_external_contact": True,
            "external_send_authorized": False,
            "recipient_selection_authorized": False,
        }
        rows.append(row)
        if state == "READY":
            ready.append(segment)

    rows_by_id = {r["segment_id"]: r for r in rows}
    ready.sort(key=_rank_key)
    cap = 0 if batch_size == 0 else (batch_size * share_bps) // 10_000
    remaining_capacity = {
        s["segment_id"]: min(s["available_candidates"], cap) for s in ready
    }

    allocation: dict[str, int] = {s["segment_id"]: 0 for s in ready}
    roles: dict[str, set[str]] = {s["segment_id"]: set() for s in ready}
    remaining = batch_size

    # Reserve bounded exploration for the strongest collision-clean segment(s)
    # that have not yet produced retained paid signal. This keeps the fleet from
    # collapsing all contact into yesterday's winner while still preferring
    # evidence-rich segments.
    exploration = [s for s in ready if s["paid"] == 0]
    explore_remaining = min(exploration_slots, remaining)
    while explore_remaining > 0:
        progressed = False
        for segment in exploration:
            sid = segment["segment_id"]
            if allocation[sid] >= remaining_capacity[sid]:
                continue
            allocation[sid] += 1
            roles[sid].add("EXPLORATION")
            explore_remaining -= 1
            remaining -= 1
            progressed = True
            if explore_remaining == 0 or remaining == 0:
                break
        if not progressed:
            break

    # Fill remaining capacity round-robin in deterministic evidence order. The
    # hard per-segment cap prevents one apparent winner from consuming the batch.
    while remaining > 0:
        progressed = False
        for segment in ready:
            sid = segment["segment_id"]
            if allocation[sid] >= remaining_capacity[sid]:
                continue
            allocation[sid] += 1
            roles[sid].add("EXPLOITATION")
            remaining -= 1
            progressed = True
            if remaining == 0:
                break
        if not progressed:
            break

    orders: list[dict[str, Any]] = []
    for segment in ready:
        sid = segment["segment_id"]
        count = allocation[sid]
        if count <= 0:
            continue
        row = rows_by_id[sid]
        role = "+".join(sorted(roles[sid]))
        row["allocated_slots"] = count
        row["allocation_role"] = role
        row["next_action"] = "RECIPIENT_CENSUS_THEN_MUSE_ARBITRATION"
        orders.append(
            {
                "segment_id": sid,
                "offer_id": segment["offer_id"],
                "route_kind": segment["route_kind"],
                "allocated_slots": count,
                "allocation_role": role,
                "recipient_identifiers": None,
                "next_action": "RECIPIENT_CENSUS_THEN_MUSE_ARBITRATION",
                "authority": "PLANNING_ONLY_NOT_SEND_AUTHORITY",
            }
        )

    unallocated = batch_size - sum(allocation.values())
    return {
        "schema": SCHEMA,
        "evaluation_at": evaluation_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "truth_boundary": TRUTH_BOUNDARY,
        "authority": _authority(),
        "policy": {
            "batch_size": batch_size,
            "max_segment_share_bps": share_bps,
            "per_segment_slot_cap": cap,
            "exploration_slots": exploration_slots,
            "max_evidence_age_hours": max_age_hours,
            "rank_uses_headline_ticket_value": False,
            "rank_uses_retained_cash_assertions": True,
            "recipient_level_selection_performed": False,
            "fresh_recipient_census_required": True,
            "muse_arbitration_required": True,
        },
        "segments": rows,
        "orders": orders,
        "summary": {
            "segment_count": len(rows),
            "ready_segment_count": len(ready),
            "allocated_slot_count": sum(allocation.values()),
            "unallocated_slot_count": unallocated,
            "hold_count": sum(r["state"].startswith("HOLD_") for r in rows),
            "provider_authenticated_outcomes_available": False,
            "external_send_authorized": False,
            "revenue_recognized": False,
        },
    }


def compile_bundle(document: Any) -> dict[str, Any]:
    packet = compile_packet(document)
    normalized = json.loads(_canonical(document).decode("utf-8"))
    return {
        "schema": BUNDLE_SCHEMA,
        "input": normalized,
        "packet": packet,
        "receipt": {
            "schema": BUNDLE_SCHEMA,
            "input_sha256": _digest(normalized),
            "packet_sha256": _digest(packet),
            "authority": _authority(),
        },
    }


def verify_bundle(bundle: Any) -> bool:
    if type(bundle) is not dict or set(bundle) != {"schema", "input", "packet", "receipt"}:
        return False
    if bundle.get("schema") != BUNDLE_SCHEMA:
        return False
    receipt = bundle.get("receipt")
    if type(receipt) is not dict or set(receipt) != {
        "schema",
        "input_sha256",
        "packet_sha256",
        "authority",
    }:
        return False
    if receipt.get("schema") != BUNDLE_SCHEMA or receipt.get("authority") != _authority():
        return False
    try:
        return _canonical(compile_bundle(bundle["input"])) == _canonical(bundle)
    except (AllocationError, KeyError, TypeError, ValueError):
        return False


def load_json_strict(path: Path, limit: int = 8_000_000) -> Any:
    def fingerprint(value: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_nlink,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )

    def read_once(fd: int, expected_size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(131072, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > limit or len(raw) != expected_size:
            raise AllocationError("input exceeds bound or changed")
        return raw

    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
        raise AllocationError("input must be a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise AllocationError("input changed or is not regular")
        stable = fingerprint(before)
        if fingerprint(st) != stable:
            raise AllocationError("input changed before retained read")

        raw = read_once(fd, before.st_size)
        after_first = os.fstat(fd)
        if fingerprint(after_first) != stable:
            raise AllocationError("input changed while reading")

        os.lseek(fd, 0, os.SEEK_SET)
        replay = read_once(fd, before.st_size)
        after_replay = os.fstat(fd)
        if fingerprint(after_replay) != stable or replay != raw:
            raise AllocationError("input changed while reading")
    finally:
        os.close(fd)

    def reject_constant(value: str) -> None:
        raise AllocationError(f"non-finite JSON constant: {value}")

    def reject_float(value: str) -> None:
        raise AllocationError(f"floating JSON number forbidden: {value}")

    def bounded_int(value: str) -> int:
        digits = value[1:] if value.startswith("-") else value
        if len(digits) > 18:
            raise AllocationError("JSON integer exceeds bound")
        return int(value)

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AllocationError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
            parse_float=reject_float,
            parse_int=bounded_int,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AllocationError(f"invalid strict JSON: {exc}") from exc


def _publish_exclusive(path: Path, value: Any) -> None:
    payload = _canonical(value) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(fd, payload[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collision-safe revenue experiment allocator")
    sub = parser.add_subparsers(dest="command", required=True)
    comp = sub.add_parser("compile")
    comp.add_argument("input", type=Path)
    comp.add_argument("output", type=Path)
    ver = sub.add_parser("verify")
    ver.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            _publish_exclusive(args.output, compile_bundle(load_json_strict(args.input)))
            return 0
        if not verify_bundle(load_json_strict(args.bundle)):
            raise AllocationError("bundle verification failed")
        return 0
    except (OSError, AllocationError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
