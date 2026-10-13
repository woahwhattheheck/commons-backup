#!/usr/bin/env python3
"""Deterministic quiet-carrier deadline sweep.

Ranks only stale HOLD carriers that satisfy the reset-wave lane contract.  It
never sends, contacts, registers, signs, prices, or submits anything.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from typing import Any, Mapping, Sequence

SCHEMA = "quiet-carrier-deadline-sweep/v1"
OUTPUT_SCHEMA = "quiet-carrier-actionability/v1"
SOURCE_STATES = {
    "PUBLIC_CURRENT",
    "PUBLIC_NOT_RETAINED",
    "AUTH_REQUIRED",
    "UNRESOLVED",
}

class SweepError(ValueError):
    pass


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SweepError(f"{field} must be non-empty text")
    return value.strip()


def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise SweepError(f"{field} must be boolean")
    return value


def _ts(value: Any, field: str) -> dt.datetime:
    raw = _text(value, field)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise SweepError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SweepError(f"{field} must include timezone")
    return parsed.astimezone(dt.timezone.utc)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _minor(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise SweepError(f"{field} must be non-negative integer or null")
    return value


def compile_sweep(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise SweepError("payload must be object")
    if payload.get("schema") != SCHEMA:
        raise SweepError(f"schema must equal {SCHEMA}")
    as_of = _ts(payload.get("as_of"), "as_of")
    merged_start = _ts(payload.get("merged_window_start"), "merged_window_start")
    merged_end = _ts(payload.get("merged_window_end"), "merged_window_end")
    deadline_start = _ts(payload.get("deadline_window_start"), "deadline_window_start")
    deadline_end = _ts(payload.get("deadline_window_end"), "deadline_window_end")
    if not merged_start <= merged_end or not deadline_start <= deadline_end:
        raise SweepError("window start must not exceed end")
    rows = payload.get("candidates")
    if not isinstance(rows, list):
        raise SweepError("candidates must be array")

    seen: set[str] = set()
    qualified: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        field = f"candidates[{index}]"
        if not isinstance(raw, Mapping):
            raise SweepError(f"{field} must be object")
        cid = _text(raw.get("id"), f"{field}.id")
        if cid in seen:
            raise SweepError(f"duplicate candidate id {cid}")
        seen.add(cid)
        carrier_path = _text(raw.get("carrier_path"), f"{field}.carrier_path")
        merged_at = _ts(raw.get("merged_at"), f"{field}.merged_at")
        deadline = _ts(raw.get("deadline"), f"{field}.deadline")
        terminal_state = _text(raw.get("terminal_state"), f"{field}.terminal_state").upper()
        source_state = _text(raw.get("source_state"), f"{field}.source_state").upper()
        if source_state not in SOURCE_STATES:
            raise SweepError(f"{field}.source_state unsupported")
        active = _bool(raw.get("active_sep16_owner"), f"{field}.active_sep16_owner")
        sent = _bool(raw.get("sent"), f"{field}.sent")
        dnr = _bool(raw.get("dnr"), f"{field}.dnr")
        value_minor = _minor(raw.get("value_path_minor"), f"{field}.value_path_minor")
        blockers = raw.get("owner_fact_blockers")
        if not isinstance(blockers, list) or any(not isinstance(x, str) or not x.strip() for x in blockers):
            raise SweepError(f"{field}.owner_fact_blockers must be text array")
        base = {
            "id": cid,
            "carrier_path": carrier_path,
            "deadline": deadline.isoformat().replace("+00:00", "Z"),
            "value_path_minor": value_minor,
            "value_path": _text(raw.get("value_path"), f"{field}.value_path"),
            "source_state": source_state,
            "primary_blocker": _text(raw.get("primary_blocker"), f"{field}.primary_blocker"),
            "owner_only_step": _text(raw.get("owner_only_step"), f"{field}.owner_only_step"),
            "executable_next_action": _text(raw.get("executable_next_action"), f"{field}.executable_next_action"),
            "owner_fact_blockers": [x.strip() for x in blockers],
        }
        reasons: list[str] = []
        if not merged_start <= merged_at <= merged_end:
            reasons.append("MERGE_OUTSIDE_SEP1_15_WINDOW")
        if "HOLD" not in terminal_state:
            reasons.append("TERMINAL_STATE_NOT_HOLD")
        if not deadline_start <= deadline <= deadline_end:
            reasons.append("DEADLINE_OUTSIDE_SEP23_OCT15")
        if deadline <= as_of:
            reasons.append("DEADLINE_NOT_OPEN")
        if active:
            reasons.append("CURRENT_OWNER_AFTER_SEP16")
        if sent:
            reasons.append("SENT_EXISTS")
        if dnr:
            reasons.append("DNR_EXISTS")
        if reasons:
            excluded.append({**base, "excluded_reasons": reasons})
            continue
        # Deterministic actionability: public-current source beats public missing,
        # which beats auth-required/unresolved; fewer owner facts next; then
        # sooner deadline; then larger known value; then stable ID tie-break.
        source_rank = {
            "PUBLIC_CURRENT": 0,
            "PUBLIC_NOT_RETAINED": 1,
            "AUTH_REQUIRED": 2,
            "UNRESOLVED": 3,
        }[source_state]
        value_rank = -(value_minor if value_minor is not None else -1)
        sort_key = (source_rank, len(blockers), deadline, value_rank, cid)
        qualified.append({**base, "_sort_key": sort_key})

    qualified.sort(key=lambda row: row["_sort_key"])
    ranked = []
    for rank, row in enumerate(qualified, 1):
        clean = {k: v for k, v in row.items() if k != "_sort_key"}
        clean["rank"] = rank
        clean["external_action_authorized"] = False
        ranked.append(clean)
    excluded.sort(key=lambda row: (row["deadline"], row["id"]))
    normalized = {
        "schema": SCHEMA,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "merged_window_start": merged_start.isoformat().replace("+00:00", "Z"),
        "merged_window_end": merged_end.isoformat().replace("+00:00", "Z"),
        "deadline_window_start": deadline_start.isoformat().replace("+00:00", "Z"),
        "deadline_window_end": deadline_end.isoformat().replace("+00:00", "Z"),
        "candidates": rows,
    }
    return {
        "schema": OUTPUT_SCHEMA,
        "as_of": normalized["as_of"],
        "ranked_actionability": ranked,
        "excluded": excluded,
        "external_action_authorized": False,
        "input_digest_sha256": _digest(normalized),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Quiet-carrier deadline sweep — actionability",
        "",
        "No row authorizes external contact, registration, pricing, signature, or submission.",
        "",
        "| Rank | Carrier | Deadline (UTC) | Value path | One blocker | Owner-only step | Executable next action |",
        "|---:|---|---|---|---|---|---|",
    ]
    for row in report["ranked_actionability"]:
        vals = [
            str(row["rank"]), row["id"], row["deadline"], row["value_path"],
            row["primary_blocker"], row["owner_only_step"], row["executable_next_action"],
        ]
        vals = [v.replace("|", "\\|").replace("\n", " ") for v in vals]
        lines.append("| " + " | ".join(vals) + " |")
    lines.extend(["", "## Excluded by lane contract", ""])
    for row in report["excluded"]:
        lines.append(f"- **{row['id']}** — {', '.join(row['excluded_reasons'])}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    try:
        with open(args.input, encoding="utf-8") as handle:
            report = compile_sweep(json.load(handle))
    except (OSError, json.JSONDecodeError, SweepError) as exc:
        print(f"quiet-sweep-error: {exc}", file=sys.stderr)
        return 2
    if args.markdown:
        sys.stdout.write(render_markdown(report))
    else:
        print(json.dumps(report, sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
