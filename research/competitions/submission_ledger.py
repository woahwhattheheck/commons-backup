#!/usr/bin/env python3
"""Append-only competition submission ledger with a protected best slot."""

from __future__ import annotations
import argparse
import json
import math
from pathlib import Path


class LedgerError(ValueError):
    pass


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{path}:{line_no}: invalid JSON") from exc
        if not isinstance(event, dict):
            raise LedgerError(f"{path}:{line_no}: event must be an object")
        events.append(event)
    return events


def append_event(path: Path, event: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    return event


def records(events: list[dict], competition: str) -> dict[str, dict]:
    out = {}
    for event in events:
        if event.get("event") != "submission" or event.get("competition") != competition:
            continue
        submission_id = event.get("submission_id")
        if not isinstance(submission_id, str) or not submission_id:
            raise LedgerError("invalid submission_id in ledger")
        if submission_id in out:
            raise LedgerError(f"duplicate immutable submission_id {submission_id!r}")
        out[submission_id] = event
    return out


def slots(events: list[dict], competition: str) -> dict[str, str]:
    out = {}
    for event in events:
        if event.get("event") == "selection" and event.get("competition") == competition:
            out[event["slot"]] = event["submission_id"]
    return out


def record(path: Path, competition: str, submission_id: str, sha256: str, direction: str,
           score: float | None, config: dict, recorded_at: str) -> dict:
    events = read_events(path)
    existing = records(events, competition)
    if submission_id in existing:
        raise LedgerError("submission ID already recorded; append a new ID instead")
    if direction not in {"maximize", "minimize"}:
        raise LedgerError("direction must be maximize or minimize")
    directions = {row["direction"] for row in existing.values()}
    if directions and directions != {direction}:
        raise LedgerError("score direction cannot change inside a competition")
    sha256 = sha256.lower()
    if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        raise LedgerError("artifact SHA-256 must be 64 hex characters")
    if score is not None and not math.isfinite(score):
        raise LedgerError("public score must be finite")
    if not isinstance(config, dict):
        raise LedgerError("config must be a JSON object")
    return append_event(path, {
        "event": "submission",
        "competition": competition,
        "submission_id": submission_id,
        "artifact_sha256": sha256,
        "direction": direction,
        "public_score": score,
        "config": config,
        "recorded_at": recorded_at,
    })


def select(path: Path, competition: str, submission_id: str, slot: str,
           selected_at: str, reason: str, allow_regression: bool = False) -> dict:
    events = read_events(path)
    by_id = records(events, competition)
    candidate = by_id.get(submission_id)
    if candidate is None:
        raise LedgerError("selection references an unknown submission ID")
    selected = slots(events, competition)
    incumbent_id = selected.get(slot)
    if incumbent_id == submission_id:
        raise LedgerError("submission is already selected in this slot")

    override_used = False
    if slot == "protected-best" and incumbent_id is not None:
        incumbent = by_id[incumbent_id]
        new_score, old_score = candidate["public_score"], incumbent["public_score"]
        direction = candidate["direction"]
        better = (
            new_score is not None
            and old_score is not None
            and ((direction == "maximize" and new_score > old_score)
                 or (direction == "minimize" and new_score < old_score))
        )
        if not better and not allow_regression:
            raise LedgerError("protected-best refuses a score regression or equality")
        override_used = not better

    event = {
        "event": "selection",
        "competition": competition,
        "submission_id": submission_id,
        "slot": slot,
        "selected_at": selected_at,
        "reason": reason,
        "regression_override_used": override_used,
    }
    if incumbent_id is not None:
        event["replaces_submission_id"] = incumbent_id
    return append_event(path, event)


def state(path: Path, competition: str) -> dict:
    events = read_events(path)
    return {
        "competition": competition,
        "submissions": records(events, competition),
        "selected_final_slots": slots(events, competition),
    }


def json_object(raw: str) -> dict:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("expected JSON object")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--ledger", type=Path, required=True)
    rec.add_argument("--competition", required=True)
    rec.add_argument("--submission-id", required=True)
    rec.add_argument("--artifact-sha256", required=True)
    rec.add_argument("--direction", choices=("maximize", "minimize"), required=True)
    rec.add_argument("--public-score", type=float)
    rec.add_argument("--config-json", type=json_object, default={})
    rec.add_argument("--recorded-at", required=True)
    sel = sub.add_parser("select")
    sel.add_argument("--ledger", type=Path, required=True)
    sel.add_argument("--competition", required=True)
    sel.add_argument("--submission-id", required=True)
    sel.add_argument("--slot", required=True)
    sel.add_argument("--selected-at", required=True)
    sel.add_argument("--reason", required=True)
    sel.add_argument("--allow-regression", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("--ledger", type=Path, required=True)
    show.add_argument("--competition", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            result = record(args.ledger, args.competition, args.submission_id,
                            args.artifact_sha256, args.direction, args.public_score,
                            args.config_json, args.recorded_at)
        elif args.command == "select":
            result = select(args.ledger, args.competition, args.submission_id, args.slot,
                            args.selected_at, args.reason, args.allow_regression)
        else:
            result = state(args.ledger, args.competition)
    except (LedgerError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
