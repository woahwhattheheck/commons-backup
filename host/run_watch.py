#!/usr/bin/env python3
"""Strict reducer for coordination run watches.

A watch binds one GitHub Actions run id to an exact head SHA and two declared
next steps.  The reducer emits a deterministic event only when an observed run
moves from a nonterminal state to SUCCESS or FAILED.  It never performs the
declared action itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

WATCH_SCHEMA = "commons-run-watch/v1"
STATE_SCHEMA = "commons-run-watch-state/v1"
OBSERVATION_SCHEMA = "commons-run-watch-observation/v1"
RESULT_SCHEMA = "commons-run-watch-result/v1"

HOSTED_STATES = frozenset(
    {
        "NOT_EXECUTED_QUEUED",
        "RUNNING",
        "APPROVAL_GATED",
        "CANCELLED_NOT_RUN",
        "FAILED",
        "SUCCESS",
    }
)
FIRING_STATES = frozenset({"FAILED", "SUCCESS"})
TERMINAL_STATES = frozenset({"CANCELLED_NOT_RUN", "FAILED", "SUCCESS"})
_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


class WatchError(ValueError):
    """Raised when a watch packet is malformed or internally inconsistent."""


def _reject_constant(value: str) -> None:
    raise WatchError(f"non-finite JSON constant is forbidden: {value}")


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise WatchError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: str | Path) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise WatchError(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WatchError(f"invalid JSON in {path}: {exc}") from exc


def _exact_dict(value: Any, *, where: str, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise WatchError(f"{where} must be an object")
    actual = set(value)
    if actual != keys:
        raise WatchError(
            f"{where} keys must be exactly {sorted(keys)}; got {sorted(actual)}"
        )
    return value


def _run_id(value: Any, *, where: str) -> int:
    if type(value) is not int or value <= 0:
        raise WatchError(f"{where} must be a positive exact JSON integer")
    return value


def _sha(value: Any, *, where: str) -> str:
    if type(value) is not str or _SHA_RE.fullmatch(value) is None:
        raise WatchError(f"{where} must be a lowercase 40-hex SHA")
    return value


def _hosted(value: Any, *, where: str) -> str:
    if type(value) is not str or value not in HOSTED_STATES:
        raise WatchError(f"{where} is not a known hosted state")
    return value


def _action(value: Any, *, where: str) -> dict[str, str]:
    row = _exact_dict(value, where=where, keys={"kind", "summary"})
    kind = row["kind"]
    summary = row["summary"]
    if type(kind) is not str or not kind.strip():
        raise WatchError(f"{where}.kind must be a non-empty string")
    if type(summary) is not str or not summary.strip():
        raise WatchError(f"{where}.summary must be a non-empty string")
    return {"kind": kind, "summary": summary}


def parse_watches(doc: Any) -> dict[int, dict[str, Any]]:
    root = _exact_dict(doc, where="watch document", keys={"schema", "watches"})
    if root["schema"] != WATCH_SCHEMA:
        raise WatchError(f"unsupported watch schema: {root['schema']!r}")
    if type(root["watches"]) is not list:
        raise WatchError("watches must be an array")

    out: dict[int, dict[str, Any]] = {}
    for index, value in enumerate(root["watches"]):
        where = f"watches[{index}]"
        row = _exact_dict(
            value,
            where=where,
            keys={"run_id", "head_sha", "on_success", "on_failure"},
        )
        run_id = _run_id(row["run_id"], where=f"{where}.run_id")
        if run_id in out:
            raise WatchError(f"duplicate watch run_id: {run_id}")
        out[run_id] = {
            "run_id": run_id,
            "head_sha": _sha(row["head_sha"], where=f"{where}.head_sha"),
            "on_success": _action(row["on_success"], where=f"{where}.on_success"),
            "on_failure": _action(row["on_failure"], where=f"{where}.on_failure"),
        }
    return out


def _parse_run_rows(
    values: Any,
    *,
    where: str,
    allowed_ids: set[int],
) -> dict[int, dict[str, Any]]:
    if type(values) is not list:
        raise WatchError(f"{where} must be an array")
    out: dict[int, dict[str, Any]] = {}
    for index, value in enumerate(values):
        item_where = f"{where}[{index}]"
        row = _exact_dict(
            value,
            where=item_where,
            keys={"run_id", "head_sha", "hosted"},
        )
        run_id = _run_id(row["run_id"], where=f"{item_where}.run_id")
        if run_id in out:
            raise WatchError(f"duplicate {where} run_id: {run_id}")
        if run_id not in allowed_ids:
            raise WatchError(f"{where} contains unregistered run_id: {run_id}")
        out[run_id] = {
            "run_id": run_id,
            "head_sha": _sha(row["head_sha"], where=f"{item_where}.head_sha"),
            "hosted": _hosted(row["hosted"], where=f"{item_where}.hosted"),
        }
    if set(out) != allowed_ids:
        missing = sorted(allowed_ids - set(out))
        raise WatchError(f"{where} is missing watched run ids: {missing}")
    return out


def parse_observation(doc: Any, watches: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    root = _exact_dict(
        doc,
        where="observation document",
        keys={"schema", "runs"},
    )
    if root["schema"] != OBSERVATION_SCHEMA:
        raise WatchError(f"unsupported observation schema: {root['schema']!r}")
    rows = _parse_run_rows(root["runs"], where="observation.runs", allowed_ids=set(watches))
    _require_heads(watches, rows, where="observation")
    return rows


def parse_state(doc: Any, watches: dict[int, dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], set[str]]:
    root = _exact_dict(
        doc,
        where="state document",
        keys={"schema", "runs", "fired_event_ids"},
    )
    if root["schema"] != STATE_SCHEMA:
        raise WatchError(f"unsupported state schema: {root['schema']!r}")
    rows = _parse_run_rows(root["runs"], where="state.runs", allowed_ids=set(watches))
    _require_heads(watches, rows, where="state")
    fired = root["fired_event_ids"]
    if type(fired) is not list:
        raise WatchError("fired_event_ids must be an array")
    event_ids: set[str] = set()
    for index, value in enumerate(fired):
        if type(value) is not str or re.fullmatch(r"rwev-[0-9a-f]{24}", value) is None:
            raise WatchError(f"fired_event_ids[{index}] is malformed")
        if value in event_ids:
            raise WatchError(f"duplicate fired event id: {value}")
        event_ids.add(value)
    return rows, event_ids


def _require_heads(
    watches: dict[int, dict[str, Any]],
    rows: dict[int, dict[str, Any]],
    *,
    where: str,
) -> None:
    for run_id, row in rows.items():
        expected = watches[run_id]["head_sha"]
        if row["head_sha"] != expected:
            raise WatchError(
                f"{where} head mismatch for run {run_id}: "
                f"{row['head_sha']} != {expected}"
            )


def _event_id(run_id: int, head_sha: str, hosted: str, action: dict[str, str]) -> str:
    payload = json.dumps(
        {
            "run_id": run_id,
            "head_sha": head_sha,
            "hosted": hosted,
            "action": action,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "rwev-" + hashlib.sha256(payload).hexdigest()[:24]


def initialize(watch_doc: Any, observation_doc: Any) -> dict[str, Any]:
    watches = parse_watches(watch_doc)
    observed = parse_observation(observation_doc, watches)
    return {
        "schema": STATE_SCHEMA,
        "runs": [observed[run_id] for run_id in sorted(observed)],
        "fired_event_ids": [],
    }


def reduce_watch(
    watch_doc: Any,
    state_doc: Any,
    observation_doc: Any,
) -> dict[str, Any]:
    watches = parse_watches(watch_doc)
    previous, fired = parse_state(state_doc, watches)
    observed = parse_observation(observation_doc, watches)
    events: list[dict[str, Any]] = []

    for run_id in sorted(watches):
        before = previous[run_id]["hosted"]
        after = observed[run_id]["hosted"]
        if before in TERMINAL_STATES and after != before:
            raise WatchError(
                f"terminal state regression for run {run_id}: {before} -> {after}"
            )
        if after in FIRING_STATES and before != after:
            action_key = "on_success" if after == "SUCCESS" else "on_failure"
            action = watches[run_id][action_key]
            event_id = _event_id(run_id, watches[run_id]["head_sha"], after, action)
            if event_id in fired:
                raise WatchError(
                    f"event {event_id} is already fired but state still precedes {after}"
                )
            fired.add(event_id)
            events.append(
                {
                    "event_id": event_id,
                    "run_id": run_id,
                    "head_sha": watches[run_id]["head_sha"],
                    "from": before,
                    "to": after,
                    "action": action,
                }
            )

    state = {
        "schema": STATE_SCHEMA,
        "runs": [observed[run_id] for run_id in sorted(observed)],
        "fired_event_ids": sorted(fired),
    }
    return {
        "schema": RESULT_SCHEMA,
        "state": state,
        "events": events,
    }


def _dump(value: Any) -> None:
    json.dump(value, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and reduce strict coordination run watches."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate", help="validate a watch file")
    validate_parser.add_argument("watch")

    init_parser = sub.add_parser("init", help="initialize state from a run observation")
    init_parser.add_argument("watch")
    init_parser.add_argument("observation")

    reduce_parser = sub.add_parser("reduce", help="reduce a new run observation")
    reduce_parser.add_argument("watch")
    reduce_parser.add_argument("state")
    reduce_parser.add_argument("observation")

    args = parser.parse_args(argv)
    try:
        watch_doc = load_json(args.watch)
        if args.command == "validate":
            parse_watches(watch_doc)
            return 0
        if args.command == "init":
            _dump(initialize(watch_doc, load_json(args.observation)))
            return 0
        _dump(
            reduce_watch(
                watch_doc,
                load_json(args.state),
                load_json(args.observation),
            )
        )
        return 0
    except WatchError as exc:
        print(f"run-watch: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
