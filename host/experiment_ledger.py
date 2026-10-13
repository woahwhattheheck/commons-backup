#!/usr/bin/env python3
"""Deterministic hypothesis-keyed experiment ledger for Commons.

The ledger keeps the four evidence stages for one hypothesis side by side:
forensic estimate, small gate, field gate, and frozen panel.  It records what
was observed under one declared objective; it does not decide promotion or
rewrite completed evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
import time
from collections.abc import Mapping
from typing import Any, Dict, Iterable, List, Optional

try:
    from host.swarm_runtime import locks as _process_locks
except ModuleNotFoundError:
    from swarm_runtime import locks as _process_locks

SCHEMA = "commons-experiment-ledger/v1"
BENCHES = ("forensic_estimate", "small_gate", "field_gate", "frozen_panel")
STATES = {"NOT_EXECUTED", "RUNNING", "COMPLETE", "INVALID"}
TERMINAL_STATES = {"COMPLETE", "INVALID"}
DIRECTIONS = {"maximize", "minimize"}
_HYPOTHESIS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,95}$")


def _strict_object(pairs: Iterable[tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key: %s" % key)
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_strict_object,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError("non-finite JSON value: %s" % value)
        ),
    )


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % field)
    return value.strip()


def _finite_number(value: Any, field: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a finite number" % field)
    if not math.isfinite(value):
        raise ValueError("%s must be a finite number" % field)
    return value


def _sample_size(value: Any, *, allow_none: bool) -> Optional[int]:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("sample_size must be a non-negative integer")
    return value


def normalize_objective(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("objective must be an object")
    allowed = {"metric", "direction", "unit", "threshold"}
    extra = set(value) - allowed
    missing = {"metric", "direction", "unit"} - set(value)
    if missing:
        raise ValueError("missing objective fields: %s" % ", ".join(sorted(missing)))
    if extra:
        raise ValueError("unexpected objective fields: %s" % ", ".join(sorted(extra)))
    direction = _nonempty(value["direction"], "objective.direction").lower()
    if direction not in DIRECTIONS:
        raise ValueError("objective.direction must be maximize or minimize")
    out: Dict[str, Any] = {
        "direction": direction,
        "metric": _nonempty(value["metric"], "objective.metric"),
        "unit": _nonempty(value["unit"], "objective.unit"),
    }
    if "threshold" in value:
        out["threshold"] = _finite_number(value["threshold"], "objective.threshold")
    return {key: out[key] for key in sorted(out)}


def empty_bench() -> Dict[str, Any]:
    return {"state": "NOT_EXECUTED", "sample_size": None, "metrics": {}, "evidence": []}


def normalize_bench(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("bench must be an object")
    allowed = {"state", "sample_size", "metrics", "evidence", "panel"}
    extra = set(value) - allowed
    missing = {"state", "sample_size"} - set(value)
    if missing:
        raise ValueError("missing bench fields: %s" % ", ".join(sorted(missing)))
    if extra:
        raise ValueError("unexpected bench fields: %s" % ", ".join(sorted(extra)))

    state = _nonempty(value["state"], "bench.state").upper()
    if state not in STATES:
        raise ValueError("unsupported bench state: %s" % state)
    sample_size = _sample_size(value.get("sample_size"), allow_none=(state == "NOT_EXECUTED"))
    if state == "NOT_EXECUTED" and sample_size is not None:
        raise ValueError("NOT_EXECUTED sample_size must be null")
    if state in TERMINAL_STATES and (sample_size is None or sample_size <= 0):
        raise ValueError("terminal bench sample_size must be a positive integer")

    metrics_in = value.get("metrics", {})
    if not isinstance(metrics_in, Mapping):
        raise ValueError("bench.metrics must be an object")
    metrics: Dict[str, float | int] = {}
    for key in sorted(metrics_in):
        name = _nonempty(key, "metric name")
        metrics[name] = _finite_number(metrics_in[key], "bench.metrics.%s" % name)

    evidence_in = value.get("evidence", [])
    if not isinstance(evidence_in, list):
        raise ValueError("bench.evidence must be a list")
    evidence = sorted(set(_nonempty(item, "bench.evidence item") for item in evidence_in))

    out: Dict[str, Any] = {
        "state": state,
        "sample_size": sample_size,
        "metrics": metrics,
        "evidence": evidence,
    }
    if "panel" in value:
        out["panel"] = _nonempty(value["panel"], "bench.panel")
    return out


def empty_ledger() -> Dict[str, Any]:
    return {"schema": SCHEMA, "hypotheses": {}}


def normalize_hypothesis(value: Mapping[str, Any], key: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("hypothesis row must be an object: %s" % key)
    allowed = {"hypothesis_id", "statement", "objective", "benches", "labels"}
    extra = set(value) - allowed
    missing = {"hypothesis_id", "statement", "objective", "benches"} - set(value)
    if missing:
        raise ValueError("missing hypothesis fields for %s: %s" % (key, ", ".join(sorted(missing))))
    if extra:
        raise ValueError("unexpected hypothesis fields for %s: %s" % (key, ", ".join(sorted(extra))))

    hypothesis_id = _nonempty(value["hypothesis_id"], "hypothesis_id")
    if not _HYPOTHESIS_RE.fullmatch(hypothesis_id):
        raise ValueError("invalid hypothesis_id: %s" % hypothesis_id)
    if hypothesis_id != key:
        raise ValueError("hypothesis row id must match its key: %s" % key)

    benches_in = value["benches"]
    if not isinstance(benches_in, Mapping):
        raise ValueError("benches must be an object")
    if set(benches_in) != set(BENCHES):
        raise ValueError("benches must contain exactly: %s" % ", ".join(BENCHES))
    benches = {name: normalize_bench(benches_in[name]) for name in BENCHES}

    labels_in = value.get("labels", [])
    if not isinstance(labels_in, list):
        raise ValueError("labels must be a list")
    labels = sorted(set(_nonempty(item, "label") for item in labels_in))

    out: Dict[str, Any] = {
        "hypothesis_id": hypothesis_id,
        "statement": _nonempty(value["statement"], "statement"),
        "objective": normalize_objective(value["objective"]),
        "benches": benches,
    }
    if labels:
        out["labels"] = labels
    return out


def validate_ledger(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("ledger must be a JSON object")
    if set(value) != {"schema", "hypotheses"}:
        raise ValueError("ledger must contain exactly schema and hypotheses")
    if value.get("schema") != SCHEMA:
        raise ValueError("unsupported ledger schema")
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, Mapping):
        raise ValueError("hypotheses must be an object")
    normalized = {key: normalize_hypothesis(hypotheses[key], key) for key in sorted(hypotheses)}
    return {"schema": SCHEMA, "hypotheses": normalized}


def add_hypothesis(ledger: Mapping[str, Any], hypothesis_id: str, statement: str,
                   objective: Mapping[str, Any], labels: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    current = validate_ledger(ledger)
    hypothesis_id = _nonempty(hypothesis_id, "hypothesis_id")
    if not _HYPOTHESIS_RE.fullmatch(hypothesis_id):
        raise ValueError("invalid hypothesis_id: %s" % hypothesis_id)
    row: Dict[str, Any] = {
        "hypothesis_id": hypothesis_id,
        "statement": _nonempty(statement, "statement"),
        "objective": normalize_objective(objective),
        "benches": {name: empty_bench() for name in BENCHES},
    }
    clean_labels = sorted(set(_nonempty(item, "label") for item in (labels or [])))
    if clean_labels:
        row["labels"] = clean_labels
    row = normalize_hypothesis(row, hypothesis_id)
    existing = current["hypotheses"].get(hypothesis_id)
    if existing is not None:
        # Evidence advances independently of the immutable declaration. A rerun
        # of the same declaration must retain, not reject or reset, its benches.
        declaration = {key: value for key, value in row.items() if key != "benches"}
        original = {key: value for key, value in existing.items() if key != "benches"}
        if original != declaration:
            raise ValueError("hypothesis_id already exists with different declaration: %s" % hypothesis_id)
        return current
    current["hypotheses"][hypothesis_id] = row
    return validate_ledger(current)


def _transition_allowed(old: str, new: str) -> bool:
    if old == new:
        return True
    if old == "NOT_EXECUTED":
        return new in {"RUNNING", "COMPLETE", "INVALID"}
    if old == "RUNNING":
        return new in {"COMPLETE", "INVALID"}
    return False


def record_bench(ledger: Mapping[str, Any], hypothesis_id: str, bench_name: str,
                 record: Mapping[str, Any]) -> Dict[str, Any]:
    current = validate_ledger(ledger)
    if hypothesis_id not in current["hypotheses"]:
        raise ValueError("unknown hypothesis_id: %s" % hypothesis_id)
    if bench_name not in BENCHES:
        raise ValueError("unknown bench: %s" % bench_name)
    new = normalize_bench(record)
    old = current["hypotheses"][hypothesis_id]["benches"][bench_name]
    if old in ({}, None):
        old = empty_bench()
    if old["state"] in TERMINAL_STATES and old != new:
        raise ValueError("terminal bench evidence is immutable: %s/%s" % (hypothesis_id, bench_name))
    if not _transition_allowed(old["state"], new["state"]):
        raise ValueError("invalid bench transition %s -> %s" % (old["state"], new["state"]))
    if old["state"] == "RUNNING" and new["state"] in {"RUNNING", "COMPLETE", "INVALID"}:
        old_n = old.get("sample_size") or 0
        new_n = new.get("sample_size") or 0
        if new_n < old_n:
            raise ValueError("RUNNING sample_size cannot decrease")
    current["hypotheses"][hypothesis_id]["benches"][bench_name] = new
    return validate_ledger(current)


def load_ledger(path: str, *, allow_missing: bool = True) -> Dict[str, Any]:
    """Load saved evidence; only explicit initialization may treat absence as empty.

    The default preserves the existing Python initialization API. Read-only CLI
    operations and recording to an existing hypothesis require a real file.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return validate_ledger(loads_strict(fh.read()))
    except FileNotFoundError:
        if allow_missing:
            return empty_ledger()
        raise


def dump_ledger(ledger: Mapping[str, Any]) -> str:
    return json.dumps(validate_ledger(ledger), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_ledger(path: str, ledger: Mapping[str, Any]) -> None:
    """Replace a snapshot; use the file mutation APIs for shared updates."""
    path = os.path.realpath(os.fspath(path))
    text = dump_ledger(ledger)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".experiment-ledger-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _update_ledger_file(path, update, *, allow_missing=False, lock_timeout=10.0):
    if not math.isfinite(lock_timeout) or lock_timeout < 0:
        raise ValueError("lock timeout must be a finite non-negative number")
    # Aliases share one publication target and one stable sidecar lock.
    path = os.path.realpath(os.fspath(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    deadline = time.monotonic() + lock_timeout
    while True:
        try:
            handle = _process_locks.take(path + ".lock")
        except _process_locks.LockUnavailable as error:
            raise OSError("experiment ledger lock unavailable: %s" % path) from error
        if handle is not None:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("experiment ledger is busy: %s (waited %.3gs)" % (path, lock_timeout))
        time.sleep(min(0.05, remaining))
    try:
        # Reread after admission so both independent additions and terminal
        # evidence checks see every preceding writer's completed transaction.
        ledger = update(load_ledger(path, allow_missing=allow_missing))
        write_ledger(path, ledger)
        return ledger
    finally:
        _process_locks.release(handle)


def add_hypothesis_file(path: str, hypothesis_id: str, statement: str,
                        objective: Mapping[str, Any], labels: Optional[Iterable[str]] = None,
                        *, lock_timeout: float = 10.0) -> Dict[str, Any]:
    """Add a declaration without losing concurrent evidence or declarations."""
    return _update_ledger_file(
        path, lambda ledger: add_hypothesis(ledger, hypothesis_id, statement, objective, labels),
        allow_missing=True, lock_timeout=lock_timeout,
    )


def record_bench_file(path: str, hypothesis_id: str, bench_name: str,
                      record: Mapping[str, Any], *, lock_timeout: float = 10.0) -> Dict[str, Any]:
    """Record evidence against the latest ledger while holding its writer lock."""
    return _update_ledger_file(
        path, lambda ledger: record_bench(ledger, hypothesis_id, bench_name, record),
        lock_timeout=lock_timeout,
    )


def _json_object(text: str, field: str) -> Dict[str, Any]:
    value = loads_strict(text)
    if not isinstance(value, dict):
        raise ValueError("%s must decode to an object" % field)
    return value


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Commons hypothesis-keyed experiment ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("ledger")
    get = sub.add_parser("get")
    get.add_argument("ledger")
    get.add_argument("hypothesis_id")
    add = sub.add_parser("add")
    add.add_argument("ledger")
    add.add_argument("hypothesis_id")
    add.add_argument("--statement", required=True)
    add.add_argument("--objective-json", required=True)
    add.add_argument("--label", action="append", default=[])
    record = sub.add_parser("record")
    record.add_argument("ledger")
    record.add_argument("hypothesis_id")
    record.add_argument("bench", choices=BENCHES)
    record.add_argument("--record-json", required=True)
    for writer in (add, record):
        writer.add_argument("--lock-timeout", type=float, default=10.0,
                            help="seconds to wait for another ledger writer (default: 10)")
    args = parser.parse_args(argv)

    try:
        if args.command in ("validate", "get"):
            ledger = load_ledger(args.ledger, allow_missing=False)
        if args.command == "validate":
            print(dump_ledger(ledger), end="")
            return 0
        if args.command == "get":
            row = ledger["hypotheses"].get(args.hypothesis_id)
            if row is None:
                raise ValueError("hypothesis not found: %s" % args.hypothesis_id)
            print(json.dumps(row, sort_keys=True, indent=2, ensure_ascii=False))
            return 0
        if args.command == "add":
            ledger = add_hypothesis_file(
                args.ledger,
                args.hypothesis_id,
                args.statement,
                _json_object(args.objective_json, "--objective-json"),
                args.label,
                lock_timeout=args.lock_timeout,
            )
        else:
            ledger = record_bench_file(
                args.ledger,
                args.hypothesis_id,
                args.bench,
                _json_object(args.record_json, "--record-json"),
                lock_timeout=args.lock_timeout,
            )
        print(json.dumps(ledger["hypotheses"][args.hypothesis_id], sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
