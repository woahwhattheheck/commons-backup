#!/usr/bin/env python3
"""Audit declared TITAN game coverage before passing evidence to a score reporter.

Standard library only. This checks declared provenance, not whether an executor
really ran the pinned bytes. It makes no economic or statistical promotion claim.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from itertools import product
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

SCHEMA = "titan-paired-panel/v1"
ARMS = ("baseline", "candidate")
PINS = ("engine_sha256", "environment_sha256", "baseline_sha256", "candidate_sha256")
PLAN_FIELDS = {"schema", "panel_id", "purpose", "opponents", "seeds", "seats",
               "prior_plan_sha256", *PINS}
ROW_REQUIRED = {"plan_sha256", "arm", "opponent", "seed", "candidate_seat",
                "status", "agent_sha256", "opponent_sha256", "engine_sha256",
                "environment_sha256"}
ROW_OPTIONAL = {"scores", "activations", "trace_sha256", "error"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_ROWS = 100_000
MAX_FILE_BYTES = 32 * 1024 * 1024


class EvidenceError(ValueError):
    """Invalid, ambiguous, incomplete, or inconsistent declared evidence."""


def _check(condition: bool, message: str) -> None:
    # Explicit exceptions must survive python -O.
    if not condition:
        raise EvidenceError(message)


def _text(value: Any, label: str) -> None:
    _check(type(value) is str and bool(value) and value == value.strip(),
           f"{label} must be nonempty text without outer whitespace")


def _digest(value: Any, label: str) -> None:
    _check(type(value) is str and HEX64.fullmatch(value) is not None,
           f"{label} must be a lowercase SHA-256 digest")


def _integer(value: Any, label: str) -> None:
    _check(type(value) is int and value >= 0, f"{label} must be a nonnegative integer")


def _unique(values: Any, label: str, validator) -> None:
    _check(type(values) is list and bool(values), f"{label} must be a nonempty list")
    for value in values:
        validator(value, label)
    _check(len(set(values)) == len(values), f"{label} contains duplicates")


def plan_digest(plan: dict) -> str:
    """Identity of the manifest's JSON value (not its file whitespace)."""
    try:
        raw = json.dumps(plan, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise EvidenceError(f"manifest cannot be canonicalized: {exc}") from exc
    return sha256(raw).hexdigest()


def validate_plan(plan: Any) -> None:
    _check(type(plan) is dict, "manifest must be an object")
    _check(set(plan) == PLAN_FIELDS, "manifest fields differ from titan-paired-panel/v1")
    _check(plan["schema"] == SCHEMA, "unsupported manifest schema")
    _text(plan["panel_id"], "panel_id")
    _check(plan["purpose"] in ("explore", "confirm"), "purpose must be explore or confirm")
    for pin in PINS:
        _digest(plan[pin], pin)
    _unique(plan["seeds"], "seeds", _integer)
    _unique(plan["seats"], "seats", _integer)
    _check(set(plan["seats"]) == {0, 1}, "manifest must declare both seats 0 and 1")
    opponents = plan["opponents"]
    _check(type(opponents) is dict and bool(opponents), "opponents must map IDs to SHA-256")
    for name, digest in opponents.items():
        _text(name, "opponent ID")
        _digest(digest, "opponent digest")
    prior = plan["prior_plan_sha256"]
    _check(type(prior) is list, "prior_plan_sha256 must be a list")
    for digest in prior:
        _digest(digest, "prior plan digest")
    _check(len(prior) == len(set(prior)), "duplicate prior plan digest")
    _check(plan["purpose"] != "confirm" or bool(prior),
           "confirm requires explicitly pinned prior plans")
    _check(len(opponents) * len(plan["seeds"]) * len(plan["seats"]) * 2 <= MAX_ROWS,
           "declared panel exceeds the supported row limit")


def _row_key(row: Any) -> tuple[str, int, int, str]:
    _check(type(row) is dict, "result row must be an object")
    _check(ROW_REQUIRED <= set(row) <= ROW_REQUIRED | ROW_OPTIONAL,
           "result row has missing or unknown fields")
    _text(row["opponent"], "row opponent")
    _integer(row["seed"], "row seed")
    _check(type(row["candidate_seat"]) is int and row["candidate_seat"] in (0, 1),
           "row candidate_seat must be integer 0 or 1")
    _check(row["arm"] in ARMS, "row arm must be baseline or candidate")
    for pin in ("plan_sha256", "agent_sha256", "opponent_sha256",
                "engine_sha256", "environment_sha256"):
        _digest(row[pin], pin)
    _check(row["status"] in ("complete", "error", "timeout", "cancelled"),
           "unknown row status")
    if "activations" in row:
        _check(type(row["activations"]) is dict, "activations must map lane names to counts")
        for lane, count in row["activations"].items():
            _text(lane, "activation lane")
            _integer(count, "activation count")
    if "trace_sha256" in row:
        _digest(row["trace_sha256"], "trace_sha256")
    if "error" in row:
        _text(row["error"], "error")
        _check(row["status"] != "complete", "complete row cannot carry an error")
    if row["status"] == "complete":
        scores = row.get("scores")
        _check(type(scores) is list and len(scores) == 2,
               "complete scores must be player-ordered [seat0, seat1]")
        for score in scores:
            _check(type(score) in (int, float), "score must be a number, not bool")
            try:
                finite = math.isfinite(score)
            except OverflowError:
                finite = False
            _check(finite, "score must be finite and representable")
    return row["opponent"], row["seed"], row["candidate_seat"], row["arm"]


def _cell(key: tuple) -> dict:
    return dict(zip(("opponent", "seed", "candidate_seat", "arm"), key))


def audit_panel(plan: Any, rows: Any, prior_plans: Any = None) -> dict:
    """Return coverage diagnostics and, only on success, reporter-compatible cells.

    Exactly one result per declared opponent/seed/seat/arm is required. Failed
    attempts remain failures; duplicate attempts are never deduplicated or chosen
    by score. A changed opponent artifact is a different experiment, not a match.
    """
    validate_plan(plan)
    _check(type(rows) is list and len(rows) <= MAX_ROWS, "rows must be a bounded list")
    if prior_plans is None:
        prior_plans = []
    _check(type(prior_plans) is list, "prior plans must be a list")
    for prior in prior_plans:
        validate_plan(prior)
    prior_hashes = [plan_digest(p) for p in prior_plans]
    _check(len(set(prior_hashes)) == len(prior_hashes), "duplicate supplied prior plan")
    _check(set(prior_hashes) == set(plan["prior_plan_sha256"]),
           "supplied prior plans do not match the manifest's exact declared pins")
    _check(all(set(p["prior_plan_sha256"]) <= set(prior_hashes) for p in prior_plans),
           "supplied prior history omits referenced ancestor plans")

    errors = []
    if plan["purpose"] == "confirm":
        # Conservative world separation: changing opponents or seats does not
        # turn the same seed into a fresh confirmation world.
        for prior, digest in zip(prior_plans, prior_hashes):
            overlap = sorted(set(plan["seeds"]) & set(prior["seeds"]))
            if overlap:
                errors.append({"code": "confirmation_seed_overlap", "prior_sha256": digest,
                               "seeds": overlap})
    identity = plan_digest(plan)
    expected = set(product(plan["opponents"], plan["seeds"], plan["seats"], ARMS))
    counts: Counter = Counter()
    successful = {}
    for index, row in enumerate(rows):
        try:
            key = _row_key(row)
        except EvidenceError as exc:
            errors.append({"code": "invalid_row", "row": index, "detail": str(exc)})
            continue
        counts[key] += 1
        if key not in expected:
            errors.append({"code": "unexpected_cell", "row": index, **_cell(key)})
            continue
        matches = {
            "plan_sha256": identity,
            "engine_sha256": plan["engine_sha256"],
            "environment_sha256": plan["environment_sha256"],
            "agent_sha256": plan[row["arm"] + "_sha256"],
            "opponent_sha256": plan["opponents"][row["opponent"]],
        }
        mismatches = [pin for pin, value in matches.items() if row[pin] != value]
        if mismatches:
            errors.append({"code": "pin_mismatch", "row": index,
                           "fields": mismatches, **_cell(key)})
        if row["status"] != "complete":
            errors.append({"code": "failed_game", "row": index,
                           "status": row["status"], **_cell(key)})
        elif not mismatches and key not in successful:
            successful[key] = row
    for key in sorted(expected - set(counts)):
        errors.append({"code": "missing_cell", **_cell(key)})
    for key, count in sorted(counts.items()):
        if count > 1:
            errors.append({"code": "duplicate_cell", "count": count, **_cell(key)})
    complete_keys = {key for key in successful if counts[key] == 1}
    cells = sorted({key[:3] for key in expected})
    complete_pairs = sum(all((*cell, arm) in complete_keys for arm in ARMS) for cell in cells)
    out = {
        "schema": "titan-paired-panel-audit/v1", "ok": not errors,
        "panel_id": plan["panel_id"], "plan_sha256": identity,
        "purpose": plan["purpose"], "expected_pairs": len(cells),
        "expected_rows": len(expected), "observed_rows": len(rows),
        "successful_unique_rows": len(complete_keys), "complete_pairs": complete_pairs,
        "errors": errors,
        "scope": "declared coverage/provenance only; not execution attestation or promotion",
    }
    if not errors:
        # Deep-copy relevant values so consumers cannot mutate caller evidence.
        paired = []
        for opponent, seed, seat in cells:
            base = successful[(opponent, seed, seat, "baseline")]
            cand = successful[(opponent, seed, seat, "candidate")]
            cell = {"opponent": opponent, "seed": seed, "candidate_seat": seat,
                    "baseline": {"scores": list(base["scores"])},
                    "candidate": {"scores": list(cand["scores"])}}
            if "activations" in cand:
                cell["activations"] = dict(cand["activations"])
            paired.append(cell)
        out["paired_evidence"] = {
            "cells": paired, "plan_sha256": identity,
            "panel_manifest": json.loads(json.dumps(plan, allow_nan=False)),
        }
    return out


def _object(pairs: list) -> dict:
    out = {}
    for key, value in pairs:
        _check(key not in out, f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _constant(value: str) -> None:
    raise EvidenceError(f"nonstandard JSON number: {value}")


def loads(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, RecursionError) as exc:
        raise EvidenceError(f"invalid JSON: {exc}") from exc


def read_json(path: Path, *, jsonl: bool = False) -> Any:
    _check(path.stat().st_size <= MAX_FILE_BYTES, f"input too large: {path}")
    text = path.read_text(encoding="utf-8")
    if jsonl:
        # Empty lines carry no evidence; nonempty malformed lines never disappear.
        return [loads(line) for line in text.splitlines() if line.strip()]
    return loads(text)


def _write_atomic(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".paired-panel-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("results", type=Path, help="strict result rows as JSONL")
    parser.add_argument("--prior-plan", action="append", type=Path, default=[])
    parser.add_argument("--paired-out", type=Path, help="replace only after a complete valid audit")
    args = parser.parse_args(argv)
    try:
        inputs = [args.manifest, args.results, *args.prior_plan]
        if args.paired_out is not None:
            _check(all(args.paired_out.resolve() != p.resolve() for p in inputs),
                   "paired output must not overwrite an input")
        result = audit_panel(read_json(args.manifest), read_json(args.results, jsonl=True),
                             [read_json(p) for p in args.prior_plan])
        if result["ok"] and args.paired_out is not None:
            _write_atomic(args.paired_out, result["paired_evidence"])
        # Keep stdout a machine-readable audit; score data belongs to --paired-out.
        print(json.dumps({k: v for k, v in result.items() if k != "paired_evidence"},
                         indent=2, sort_keys=True, allow_nan=False))
        return 0 if result["ok"] else 2
    except (EvidenceError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "errors": [{"code": "input_error", "detail": str(exc)}]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
