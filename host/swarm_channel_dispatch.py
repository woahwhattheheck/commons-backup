#!/usr/bin/env python3
"""Deterministic advisory routing for swarm work across specialist Slack feeds.

This module deliberately has no Slack client and grants no authority. It consumes an
explicit observation snapshot and produces a bounded routing suggestion. The caller
remains responsible for checking live state, taking a real claim, and performing any
provider action through the provider's own authority rail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SNAPSHOT_SCHEMA = "commons.swarm_channel_dispatch/v1"
RECEIPT_SCHEMA = "commons.swarm_channel_dispatch.receipt/v1"

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}$")
_CHANNEL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")

_ROOT_FIELDS = {"schema", "snapshot_id", "channels", "work_items"}
_CHANNEL_FIELDS = {
    "channel_id",
    "name",
    "specialty_tags",
    "active_claims",
    "messages_15m",
    "capacity",
    "verified_targets",
    "paused",
}
_WORK_FIELDS = {"work_id", "tags", "priority"}

_AUTHORITY_FALSE = {
    "authenticated": False,
    "claim_authority": False,
    "send_authority": False,
    "merge_authority": False,
    "provider_authority": False,
    "payment_authority": False,
    "freshness_attested": False,
    "source_authenticity_attested": False,
}


class DispatchInputError(ValueError):
    """Raised when the dispatch snapshot is malformed or ambiguous."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _expect_exact_fields(obj: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise DispatchInputError(f"{where} must be an object")
    keys = set(obj)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing or unknown:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if unknown:
            detail.append("unknown=" + ",".join(unknown))
        raise DispatchInputError(f"{where} fields invalid: {'; '.join(detail)}")
    return obj


def _text(value: Any, where: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise DispatchInputError(f"{where} has invalid text format")
    return value


def _int(value: Any, where: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise DispatchInputError(f"{where} must be an integer")
    if not minimum <= value <= maximum:
        raise DispatchInputError(f"{where} must be in [{minimum}, {maximum}]")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise DispatchInputError(f"{where} must be a boolean")
    return value


def _tags(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise DispatchInputError(f"{where} must be a non-empty list")
    if len(value) > 64:
        raise DispatchInputError(f"{where} exceeds 64 tags")
    out: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        tag = _text(raw, f"{where}[{index}]", _TAG_RE)
        if tag in seen:
            raise DispatchInputError(f"{where} contains duplicate tag {tag!r}")
        seen.add(tag)
        out.append(tag)
    return sorted(out)


def normalize_snapshot(snapshot: Any) -> dict[str, Any]:
    """Validate strictly and return a canonical order-independent snapshot."""
    root = _expect_exact_fields(snapshot, _ROOT_FIELDS, "snapshot")
    if root["schema"] != SNAPSHOT_SCHEMA:
        raise DispatchInputError(f"snapshot.schema must equal {SNAPSHOT_SCHEMA!r}")
    snapshot_id = _text(root["snapshot_id"], "snapshot.snapshot_id", _TOKEN_RE)

    channels_raw = root["channels"]
    if not isinstance(channels_raw, list) or not channels_raw:
        raise DispatchInputError("snapshot.channels must be a non-empty list")
    if len(channels_raw) > 512:
        raise DispatchInputError("snapshot.channels exceeds 512 rows")

    channels: list[dict[str, Any]] = []
    channel_ids: set[str] = set()
    channel_names: set[str] = set()
    for index, raw in enumerate(channels_raw):
        row = _expect_exact_fields(raw, _CHANNEL_FIELDS, f"channels[{index}]")
        channel_id = _text(row["channel_id"], f"channels[{index}].channel_id", _TOKEN_RE)
        name = _text(row["name"], f"channels[{index}].name", _CHANNEL_NAME_RE)
        if channel_id in channel_ids:
            raise DispatchInputError(f"duplicate channel_id {channel_id!r}")
        if name in channel_names:
            raise DispatchInputError(f"duplicate channel name {name!r}")
        channel_ids.add(channel_id)
        channel_names.add(name)
        channels.append(
            {
                "channel_id": channel_id,
                "name": name,
                "specialty_tags": _tags(row["specialty_tags"], f"channels[{index}].specialty_tags"),
                "active_claims": _int(row["active_claims"], f"channels[{index}].active_claims", minimum=0, maximum=100000),
                "messages_15m": _int(row["messages_15m"], f"channels[{index}].messages_15m", minimum=0, maximum=1000000),
                "capacity": _int(row["capacity"], f"channels[{index}].capacity", minimum=0, maximum=100000),
                "verified_targets": _int(row["verified_targets"], f"channels[{index}].verified_targets", minimum=0, maximum=1000000),
                "paused": _bool(row["paused"], f"channels[{index}].paused"),
            }
        )

    work_raw = root["work_items"]
    if not isinstance(work_raw, list):
        raise DispatchInputError("snapshot.work_items must be a list")
    if len(work_raw) > 4096:
        raise DispatchInputError("snapshot.work_items exceeds 4096 rows")

    work_items: list[dict[str, Any]] = []
    work_ids: set[str] = set()
    for index, raw in enumerate(work_raw):
        row = _expect_exact_fields(raw, _WORK_FIELDS, f"work_items[{index}]")
        work_id = _text(row["work_id"], f"work_items[{index}].work_id", _TOKEN_RE)
        if work_id in work_ids:
            raise DispatchInputError(f"duplicate work_id {work_id!r}")
        work_ids.add(work_id)
        work_items.append(
            {
                "work_id": work_id,
                "tags": _tags(row["tags"], f"work_items[{index}].tags"),
                "priority": _int(row["priority"], f"work_items[{index}].priority", minimum=0, maximum=100),
            }
        )

    channels.sort(key=lambda row: (row["channel_id"], row["name"]))
    work_items.sort(key=lambda row: row["work_id"])
    return {
        "schema": SNAPSHOT_SCHEMA,
        "snapshot_id": snapshot_id,
        "channels": channels,
        "work_items": work_items,
    }


def _remaining_headroom(channel: dict[str, Any], assigned_now: int) -> int:
    """Conservative new-work headroom bounded by capacity and verified targets."""
    capacity_headroom = channel["capacity"] - channel["active_claims"] - assigned_now
    target_headroom = channel["verified_targets"] - channel["active_claims"] - assigned_now
    return max(0, min(capacity_headroom, target_headroom))


def _pressure_score(channel: dict[str, Any], assigned_now: int, match_count: int) -> tuple[int, int, int, int, str, str]:
    """Lower is better; score is integer-only for cross-platform determinism."""
    capacity = channel["capacity"]
    post_claims = channel["active_claims"] + assigned_now + 1
    utilization_ppm = (post_claims * 1_000_000) // capacity
    return (
        utilization_ppm,
        channel["messages_15m"],
        len(channel["specialty_tags"]),
        -match_count,
        channel["name"],
        channel["channel_id"],
    )


def compile_dispatch(snapshot: Any) -> dict[str, Any]:
    """Compile a deterministic bounded advisory routing receipt."""
    normalized = normalize_snapshot(snapshot)
    channels = normalized["channels"]
    work_items = sorted(normalized["work_items"], key=lambda row: (-row["priority"], row["work_id"]))
    assigned_counts = {row["channel_id"]: 0 for row in channels}
    assignments: list[dict[str, Any]] = []
    holds: list[dict[str, Any]] = []
    channels_by_tag: dict[str, list[int]] = {}
    for index, channel in enumerate(channels):
        if channel["paused"] or _remaining_headroom(channel, 0) <= 0:
            continue
        for tag in channel["specialty_tags"]:
            channels_by_tag.setdefault(tag, []).append(index)

    for work in work_items:
        matches_by_channel: dict[int, list[str]] = {}
        # Normalized work tags are sorted, so each matched list keeps its
        # canonical order without scanning unrelated channel specialties.
        for tag in work["tags"]:
            for index in channels_by_tag.get(tag, ()):
                matches_by_channel.setdefault(index, []).append(tag)
        candidates: list[tuple[tuple[int, int, int, int, str, str], dict[str, Any], list[str]]] = []
        for index, matched in matches_by_channel.items():
            channel = channels[index]
            assigned_now = assigned_counts[channel["channel_id"]]
            if _remaining_headroom(channel, assigned_now) <= 0:
                continue
            candidates.append((_pressure_score(channel, assigned_now, len(matched)), channel, matched))

        if not candidates:
            holds.append(
                {
                    "work_id": work["work_id"],
                    "priority": work["priority"],
                    "reason": "NO_ELIGIBLE_RELEVANT_HEADROOM",
                }
            )
            continue

        _, selected, matched = min(candidates, key=lambda item: item[0])
        assigned_counts[selected["channel_id"]] += 1
        assignments.append(
            {
                "work_id": work["work_id"],
                "priority": work["priority"],
                "channel_id": selected["channel_id"],
                "channel_name": selected["name"],
                "matched_tags": matched,
                "reason": "LOWEST_PRESSURE_RELEVANT_HEADROOM",
            }
        )

    channel_summary = []
    for channel in channels:
        assigned = assigned_counts[channel["channel_id"]]
        channel_summary.append(
            {
                "channel_id": channel["channel_id"],
                "channel_name": channel["name"],
                "assigned": assigned,
                "remaining_headroom": _remaining_headroom(channel, assigned),
                "eligible_target_count": channel["verified_targets"],
                "paused": channel["paused"],
            }
        )

    routing_payload = {
        "assignments": assignments,
        "holds": holds,
        "channel_summary": channel_summary,
    }
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "snapshot_id": normalized["snapshot_id"],
        "advisory_only": True,
        "authority": dict(_AUTHORITY_FALSE),
        "input_sha256": _sha256(normalized),
        "routing_sha256": _sha256(routing_payload),
        **routing_payload,
    }
    return receipt


def verify_dispatch(snapshot: Any, receipt: Any) -> dict[str, Any]:
    """Recompile from source snapshot and fail closed on any receipt mutation."""
    expected = compile_dispatch(snapshot)
    if not isinstance(receipt, dict):
        return {"ok": False, "verdict": "INVALID_RECEIPT", "reason": "receipt must be an object"}
    if _canonical(receipt) != _canonical(expected):
        return {
            "ok": False,
            "verdict": "RECEIPT_MISMATCH",
            "expected_receipt_sha256": _sha256(expected),
            "observed_receipt_sha256": _sha256(receipt),
        }
    return {
        "ok": True,
        "verdict": "RECEIPT_MATCHES_SNAPSHOT",
        "receipt_sha256": _sha256(expected),
        "authority": dict(_AUTHORITY_FALSE),
    }


def _no_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DispatchInputError(f"duplicate JSON object key {key!r}")
        out[key] = value
    return out


def _load_json(path: str) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_object_pairs)
    except json.JSONDecodeError as exc:
        raise DispatchInputError(f"invalid JSON: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile or verify advisory swarm channel routing")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_parser = sub.add_parser("compile", help="compile an advisory routing receipt")
    compile_parser.add_argument("snapshot")
    verify_parser = sub.add_parser("verify", help="verify a receipt against its source snapshot")
    verify_parser.add_argument("snapshot")
    verify_parser.add_argument("receipt")
    args = parser.parse_args(argv)

    try:
        snapshot = _load_json(args.snapshot)
        if args.command == "compile":
            result = compile_dispatch(snapshot)
            ok = True
        else:
            receipt = _load_json(args.receipt)
            result = verify_dispatch(snapshot, receipt)
            ok = result.get("ok") is True
    except (OSError, DispatchInputError, ValueError) as exc:
        result = {"ok": False, "verdict": "INPUT_REJECTED", "reason": str(exc)}
        ok = False

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
