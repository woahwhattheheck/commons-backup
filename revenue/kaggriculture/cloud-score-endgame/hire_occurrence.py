# SPDX-License-Identifier: Apache-2.0
"""Offline incidence scanner for explicit rival HIRE terminal hypotheses.

The scanner consumes already-retained evaluation traces. It never constructs an
agent, calls the game engine, or exposes a recorded rival queue to runtime. Its
purpose is narrower: determine whether a retained bank actually contains HIRE
at the terminal market decision, keeping earlier final-day hiring separate.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import lzma
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "titan.rival-hire-occurrence.v2"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _market(action: Any) -> list[list[Any]]:
    if not isinstance(action, dict):
        return []
    market = action.get("market", [])
    if not isinstance(market, list):
        raise ValueError("action.market must be a list")
    return market


def _operations(action: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    for order in _market(action):
        if not isinstance(order, list):
            raise ValueError("market order must be a list")
        if order and not isinstance(order[0], str):
            raise ValueError("market operation must be a string")
        if order:
            counts[order[0]] += 1
    return counts


def _validate_seat(value: Any) -> int:
    seat = int(value)
    if seat not in (0, 1):
        raise ValueError(f"candidate seat must be 0 or 1, got {value!r}")
    return seat


def read_poly_bank(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read POLY's compressed mapping of source-bound development records."""
    bank = json.loads(lzma.decompress(path.read_bytes()))
    if not isinstance(bank, dict) or not bank:
        raise ValueError("POLY bank must be a nonempty object")

    records: list[dict[str, Any]] = []
    for name, text in sorted(bank.items()):
        if not isinstance(name, str) or not isinstance(text, str):
            raise ValueError("POLY bank entries must map names to JSON text")
        record = json.loads(text)
        seat = _validate_seat(record.get("candidate_seat"))
        rival = 1 - seat
        terminal = int(record.get("steps", 0)) - 1
        if terminal < 0:
            raise ValueError(f"{name}: invalid steps")

        frames: list[dict[str, Any]] = []
        for frame in record.get("final_day", []):
            actions = frame.get("actions", [])
            if not isinstance(actions, list) or len(actions) != 2:
                raise ValueError(f"{name}: frame must contain two actions")
            observation = frame.get("observation", {})
            if not isinstance(observation, dict):
                raise ValueError(f"{name}: observation must be an object")
            frames.append(
                {
                    "decision": int(frame["step"]),
                    "day": observation.get("day"),
                    "hour": observation.get("hour"),
                    "action": actions[rival],
                }
            )
        if not any(frame["decision"] == terminal for frame in frames):
            raise ValueError(f"{name}: terminal decision {terminal} is missing")

        records.append(
            {
                "source": "poly-development-records",
                "record": name,
                "seed": record.get("seed"),
                "candidate_seat": seat,
                "opponent": record.get("opponent"),
                "arm": record.get("arm"),
                "terminal_decision": terminal,
                "frames": frames,
            }
        )

    return records, {
        "kind": "poly-development-records",
        "path": path.name,
        "sha256": _sha256_file(path),
        "records": len(records),
    }


def _orbit_summary_path(trace: Path) -> Path:
    # foo.jsonl.gz -> foo.json
    return trace.with_suffix("").with_suffix(".json")


def read_orbit_root(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read ORBIT's complete JSONL traces for current and control arms."""
    manifest_path = root / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current_archive = manifest.get("current_archive_sha256")
    traces = sorted(root.glob("results/*/*.jsonl.gz"))
    if not traces:
        raise ValueError("ORBIT root contains no retained traces")

    records: list[dict[str, Any]] = []
    for trace in traces:
        summary_path = _orbit_summary_path(trace)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        seat = _validate_seat(summary.get("candidate_seat"))
        rival = 1 - seat
        terminal = int(summary.get("steps", 0)) - 1
        if terminal < 0:
            raise ValueError(f"{trace}: invalid steps")

        frames: list[dict[str, Any]] = []
        decisions: list[int] = []
        with gzip.open(trace, "rt", encoding="utf-8") as handle:
            for raw in handle:
                frame = json.loads(raw)
                if frame.get("kind") != "transition":
                    continue
                actions = frame.get("actions", [])
                before = frame.get("before", [])
                if not isinstance(actions, list) or len(actions) != 2:
                    raise ValueError(f"{trace}: transition must contain two actions")
                if not isinstance(before, list) or len(before) != 2:
                    raise ValueError(f"{trace}: transition must contain two before states")
                # Trace index 1 is decision 0; index 719 is decision 718.
                decision = int(frame["index"]) - 1
                public = before[0]
                if not isinstance(public, dict):
                    raise ValueError(f"{trace}: before state must be an object")
                decisions.append(decision)
                frames.append(
                    {
                        "decision": decision,
                        "day": public.get("day"),
                        "hour": public.get("hour"),
                        "action": actions[rival],
                    }
                )
        if decisions != list(range(terminal + 1)):
            raise ValueError(f"{trace}: noncontiguous decision sequence")

        records.append(
            {
                "source": f"orbit-{trace.parent.name}",
                "record": str(trace.relative_to(root)),
                "seed": summary.get("seed"),
                "candidate_seat": seat,
                "opponent": summary.get("opponent"),
                "arm": summary.get("candidate_label"),
                "terminal_decision": terminal,
                "trace_sha256": summary.get("trace_sha256"),
                "retained_trace_sha256": summary.get("retained_trace_sha256"),
                "frames": frames,
            }
        )

    return records, {
        "kind": "orbit-current-lonespear",
        "manifest_path": manifest_path.name,
        "manifest_sha256": _sha256_file(manifest_path),
        "manifest_schema": manifest.get("schema"),
        "declared_unique_games": manifest.get("unique_games"),
        "current_archive_sha256": current_archive,
        "records": len(records),
    }


def _add_counts(target: Counter[str], source: Counter[str]) -> None:
    target.update(source)


def summarize(
    records: Iterable[dict[str, Any]], input_bindings: list[dict[str, Any]]
) -> dict[str, Any]:
    """Produce deterministic aggregate and per-record occurrence evidence."""
    records = list(records)
    if not records:
        raise ValueError("at least one record is required")

    terminal_ops: Counter[str] = Counter()
    preterminal_final_ops: Counter[str] = Counter()
    hire_by_day_hour: Counter[str] = Counter()
    hire_by_decision: Counter[int] = Counter()
    stream_groups: dict[str, list[str]] = defaultdict(list)
    source_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    detail: list[dict[str, Any]] = []

    for record in records:
        terminal = int(record["terminal_decision"])
        terminal_counts: Counter[str] = Counter()
        preterminal_counts: Counter[str] = Counter()
        final_day_hire_events: list[dict[str, Any]] = []
        for frame in record["frames"]:
            counts = _operations(frame["action"])
            if frame["decision"] == terminal:
                _add_counts(terminal_counts, counts)
                _add_counts(terminal_ops, counts)
            elif frame.get("day") == 29:
                _add_counts(preterminal_counts, counts)
                _add_counts(preterminal_final_ops, counts)
            if (
                frame["decision"] != terminal
                and frame.get("day") == 29
                and counts.get("HIRE", 0)
            ):
                count = counts["HIRE"]
                hire_by_decision[frame["decision"]] += count
                key = str(frame.get("hour"))
                hire_by_day_hour[key] += count
                final_day_hire_events.append(
                    {
                        "decision": frame["decision"],
                        "hour": frame.get("hour"),
                        "count": count,
                    }
                )

        terminal_frame = next(
            frame for frame in record["frames"] if frame["decision"] == terminal
        )
        terminal_queue_hash = _sha256_bytes(_json_bytes(_market(terminal_frame["action"])))
        # Source is included because POLY retains only final-day actions while ORBIT
        # retains whole games; those spans must never be treated as equivalent.
        stream_hash = _sha256_bytes(
            _json_bytes(
                {
                    "source": record["source"],
                    "frames": [
                        {"decision": f["decision"], "action": f["action"]}
                        for f in record["frames"]
                    ],
                }
            )
        )
        stream_groups[stream_hash].append(record["record"])

        row = {
            "source": record["source"],
            "record": record["record"],
            "seed": record.get("seed"),
            "candidate_seat": record.get("candidate_seat"),
            "opponent": record.get("opponent"),
            "arm": record.get("arm"),
            "terminal_decision": terminal,
            "terminal_rival_queue_sha256": terminal_queue_hash,
            "source_bound_rival_action_stream_sha256": stream_hash,
            "terminal_order_counts": dict(sorted(terminal_counts.items())),
            "preterminal_final_day_order_counts": dict(
                sorted(preterminal_counts.items())
            ),
            "preterminal_final_day_hire_events": final_day_hire_events,
        }
        detail.append(row)
        source_rows[record["source"]].append(row)

    per_source: dict[str, Any] = {}
    for source, rows in sorted(source_rows.items()):
        source_terminal: Counter[str] = Counter()
        source_preterminal: Counter[str] = Counter()
        unique_streams: set[str] = set()
        terminal_hire_records = 0
        preterminal_hire_records = 0
        for row in rows:
            source_terminal.update(row["terminal_order_counts"])
            source_preterminal.update(row["preterminal_final_day_order_counts"])
            unique_streams.add(row["source_bound_rival_action_stream_sha256"])
            terminal_hire_records += int(row["terminal_order_counts"].get("HIRE", 0) > 0)
            preterminal_hire_records += int(
                row["preterminal_final_day_order_counts"].get("HIRE", 0) > 0
            )
        per_source[source] = {
            "records": len(rows),
            "unique_source_bound_rival_action_streams": len(unique_streams),
            "records_with_terminal_hire": terminal_hire_records,
            "records_with_preterminal_final_day_hire": preterminal_hire_records,
            "terminal_operation_counts": dict(sorted(source_terminal.items())),
            "preterminal_final_day_operation_counts": dict(
                sorted(source_preterminal.items())
            ),
        }

    terminal_hire_records = sum(
        row["terminal_order_counts"].get("HIRE", 0) > 0 for row in detail
    )
    preterminal_hire_records = sum(
        row["preterminal_final_day_order_counts"].get("HIRE", 0) > 0
        for row in detail
    )

    orbit_by_key: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in detail:
        if row["source"] not in ("orbit-current", "orbit-control"):
            continue
        parts = Path(row["record"]).parts
        if len(parts) < 3:
            continue
        key = "/".join(parts[2:])
        orbit_by_key[key][row["source"]] = row
    paired_hire_sequences = 0
    identical_hire_sequences = 0
    different_hire_sequences: list[str] = []
    for key, arms in sorted(orbit_by_key.items()):
        if set(arms) != {"orbit-current", "orbit-control"}:
            continue
        paired_hire_sequences += 1
        if (
            arms["orbit-current"]["preterminal_final_day_hire_events"]
            == arms["orbit-control"]["preterminal_final_day_hire_events"]
        ):
            identical_hire_sequences += 1
        else:
            different_hire_sequences.append(key)

    result = {
        "schema": SCHEMA,
        "input_bindings": input_bindings,
        "records": len(records),
        "source_bound_unique_rival_action_streams": len(stream_groups),
        "records_with_terminal_hire": terminal_hire_records,
        "records_with_preterminal_final_day_hire": preterminal_hire_records,
        "terminal_operation_counts": dict(sorted(terminal_ops.items())),
        "preterminal_final_day_operation_counts": dict(
            sorted(preterminal_final_ops.items())
        ),
        "preterminal_final_day_hire_counts_by_hour": dict(
            sorted(hire_by_day_hour.items())
        ),
        "preterminal_final_day_hire_counts_by_decision": {
            str(key): value for key, value in sorted(hire_by_decision.items())
        },
        "per_source": per_source,
        "orbit_current_control_hire_sequence_comparison": {
            "paired_records": paired_hire_sequences,
            "identical_sequences": identical_hire_sequences,
            "different_record_keys": different_hire_sequences,
        },
        "stream_multiplicity": {
            key: len(value) for key, value in sorted(stream_groups.items())
        },
        "records_detail": detail,
        "runtime_conclusion": {
            "reached_terminal_hire_support": terminal_hire_records > 0,
            "canonical_feature_default": (
                "keep_off"
                if terminal_hire_records == 0
                else "requires_separate_causal_evaluation"
            ),
            "reason": (
                "No retained terminal decision contains HIRE. Earlier final-day "
                "HIRE occurs before terminal decision 718 and is not causally "
                "affected by a terminal sale-order choice."
                if terminal_hire_records == 0
                else "At least one retained terminal decision contains HIRE; incidence "
                "alone does not establish a beneficial policy or justify automatic activation."
            ),
            "scope": (
                "This is evaluation-only incidence in the named retained banks, "
                "not a claim that other opponents or future games never hire at terminal."
            ),
        },
        "execution": {"engine_calls": 0, "actor_calls": 0, "new_games": 0},
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poly-bank", type=Path, required=True)
    parser.add_argument("--orbit-root", type=Path, required=True)
    parser.add_argument("--poly-archive-sha256")
    parser.add_argument("--orbit-archive-sha256")
    parser.add_argument("--expected-current-archive-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    poly, poly_binding = read_poly_bank(args.poly_bank)
    orbit, orbit_binding = read_orbit_root(args.orbit_root)
    if args.poly_archive_sha256:
        poly_binding["container_archive_sha256"] = args.poly_archive_sha256
    if args.orbit_archive_sha256:
        orbit_binding["container_archive_sha256"] = args.orbit_archive_sha256
    if (
        args.expected_current_archive_sha256
        and orbit_binding.get("current_archive_sha256")
        != args.expected_current_archive_sha256
    ):
        raise ValueError("ORBIT current archive does not match expected checkpoint")

    result = summarize(poly + orbit, [poly_binding, orbit_binding])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "records": result["records"],
                "source_bound_unique_rival_action_streams": result[
                    "source_bound_unique_rival_action_streams"
                ],
                "records_with_terminal_hire": result[
                    "records_with_terminal_hire"
                ],
                "records_with_preterminal_final_day_hire": result[
                    "records_with_preterminal_final_day_hire"
                ],
                "terminal_operation_counts": result["terminal_operation_counts"],
                "preterminal_final_day_operation_counts": result[
                    "preterminal_final_day_operation_counts"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
