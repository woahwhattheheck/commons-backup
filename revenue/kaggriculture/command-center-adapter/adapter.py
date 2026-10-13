#!/usr/bin/env python3
"""Read-only TITAN fleet record adapter; standard-library JSON/JSONL interface."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone
from typing import Any

SCHEMA = "titan.command-center-adapter.v1"
KINDS = {"source", "session", "vm", "artifact", "operation"}
TERMINAL = {"succeeded", "failed", "cancelled"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps require an explicit timezone")
    return result.astimezone(timezone.utc)


def make_record(kind: str, subject_id: str, data: dict[str, Any], *,
                observed_at: str | None, recorded_at: str | None = None,
                source: dict[str, Any] | None = None,
                provider: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create an observation without deriving provider state from a board or ACK.

    source.kind is descriptive provenance (board, local_measurement,
    provider_response, ...). A provider result may be supplied explicitly; a
    reference to a session or an acknowledgment alone supplies no such result.
    """
    if kind not in KINDS or not isinstance(subject_id, str) or not subject_id:
        raise ValueError("record needs a supported kind and nonempty subject_id")
    recorded_at = recorded_at or utc_now()
    parse_time(recorded_at)
    parse_time(observed_at)
    source = {"kind": None, "ref": None, "published_at": None, **(source or {})}
    provider = {"operation_id": None, "status": None, "event_at": None,
                "completed_at": None, "receipt_ref": None, **(provider or {})}
    for value in (source["published_at"], provider["event_at"], provider["completed_at"]):
        parse_time(value)
    record = {"schema_version": SCHEMA, "kind": kind, "subject_id": subject_id,
              "observed_at": observed_at, "recorded_at": recorded_at,
              "source": copy.deepcopy(source), "provider": copy.deepcopy(provider),
              "data": copy.deepcopy(data)}
    # Observation identity excludes ingestion time, so replaying a record dedupes.
    identity = {key: value for key, value in record.items() if key != "recorded_at"}
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    record["record_id"] = hashlib.sha256(encoded.encode()).hexdigest()
    return record


def freshness(record: dict[str, Any], *, as_of: str, max_age_seconds: float) -> dict[str, Any]:
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be nonnegative")
    now, observed = parse_time(as_of), parse_time(record.get("observed_at"))
    if now is None:
        raise ValueError("as_of is required")
    if observed is None:
        return {"state": "unknown", "age_seconds": None}
    age = (now - observed).total_seconds()
    state = "future" if age < 0 else "stale" if age > max_age_seconds else "fresh"
    return {"state": state, "age_seconds": age}


def operation_summary(record: dict[str, Any]) -> dict[str, Any]:
    """Separate acknowledgment coverage, a reported outcome, and provider result.

    expected_parts=null means the total is unknown. Even full acknowledgment
    coverage is only delivery coverage; it never establishes completion.
    """
    data = record["data"]
    expected = data.get("expected_parts")
    acks = data.get("acknowledgments") or []
    accepted = {ack["part_id"] for ack in acks
                if ack.get("part_id") is not None and ack.get("status") == "accepted"}
    if expected is None:
        coverage, missing = "unknown", None
    else:
        missing = sorted(set(expected) - accepted)
        coverage = "complete" if not missing else "partial" if accepted else "none"
    provider = record["provider"]
    direct = record["source"].get("kind") == "provider_response"
    matching_operation = provider.get("operation_id") == record["subject_id"]
    status = provider.get("status")
    terminal = status in TERMINAL
    observed = parse_time(record.get("observed_at"))
    completed = parse_time(provider.get("completed_at"))
    timing_consistent = None if observed is None or completed is None else completed <= observed
    # Provider success is an explicit receipt for this operation, not a UI state,
    # dispatch acknowledgment, observed file, or elapsed local timer.
    completion = (status if direct and matching_operation and terminal
                  and provider.get("receipt_ref") and timing_consistent is not False else "unknown")
    return {"acknowledgment_coverage": coverage, "missing_parts": missing,
            "reported_status": data.get("reported_status"),
            "provider_completion": completion,
            "provider_completed_at": provider.get("completed_at"),
            "completion_time_consistent": timing_consistent,
            "completion_time_known": bool(completion != "unknown" and provider.get("completed_at"))}


def snapshot(records: list[dict[str, Any]], *, as_of: str,
             max_age_seconds: float = 1800) -> dict[str, Any]:
    """Retain all observations; newest source observation drives each summary.

    A later ingestion of old evidence cannot replace newer evidence. Undated
    observations and future timestamps remain visible but never override a
    dated observation at or before as_of. Conflicting equal-time observations
    remain explicitly ambiguous instead of choosing by file order.
    """
    now = parse_time(as_of)
    if now is None or max_age_seconds < 0:
        raise ValueError("as_of is required and max_age_seconds must be nonnegative")
    groups: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for raw in records:
        if raw.get("schema_version") not in (None, SCHEMA):
            raise ValueError("unsupported schema_version")
        record = make_record(raw["kind"], raw["subject_id"], raw.get("data", {}),
                             observed_at=raw.get("observed_at"),
                             recorded_at=raw.get("recorded_at"),
                             source=raw.get("source"), provider=raw.get("provider"))
        groups.setdefault((record["kind"], record["subject_id"]), {})[record["record_id"]] = record
    entities = []
    for (kind, subject_id), unique in sorted(groups.items()):
        history = sorted(unique.values(), key=lambda r: (r["observed_at"] or "", r["record_id"]))
        dated = [r for r in history if parse_time(r["observed_at"]) is not None
                 and parse_time(r["observed_at"]) <= now]
        if dated:
            latest_time = max(parse_time(r["observed_at"]) for r in dated)
            candidates = [r for r in dated if parse_time(r["observed_at"]) == latest_time]
        else:
            candidates = history
        selected = candidates[0] if len(candidates) == 1 else None
        entity = {"kind": kind, "subject_id": subject_id,
                  "selection": "ambiguous" if selected is None else "observed",
                  "latest": selected, "observations": history,
                  "freshness": (freshness(selected, as_of=as_of, max_age_seconds=max_age_seconds)
                                if selected else {"state": "unknown", "age_seconds": None})}
        if kind == "operation":
            entity["operation"] = operation_summary(selected) if selected else None
        entities.append(entity)
    return {"schema_version": SCHEMA, "generated_at": as_of,
            "max_age_seconds": max_age_seconds, "entities": entities}


def _read_number(path: str) -> int | None:
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def measure_vm(vm_id: str, directory: str = ".") -> dict[str, Any]:
    """Measure this Python process's VM locally; performs no network or shell IO."""
    now = utc_now()
    try:
        affinity = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity = None
    try:
        memory = {line.split(":", 1)[0]: int(line.split()[1]) * 1024
                  for line in Path("/proc/meminfo").read_text().splitlines()
                  if line.startswith(("MemTotal:", "MemAvailable:"))}
    except (OSError, ValueError):
        memory = {}
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        cpu_quota = None if quota == "max" else int(quota) / int(period)
    except (OSError, ValueError, ZeroDivisionError):
        cpu_quota = None
    disk = shutil.disk_usage(directory)
    return make_record("vm", vm_id, {
        "cpu_logical": os.cpu_count(), "cpu_affinity": affinity,
        "cpu_cgroup_quota": cpu_quota,
        "memory_total_bytes": memory.get("MemTotal"),
        "memory_available_bytes": memory.get("MemAvailable"),
        "memory_cgroup_limit_bytes": _read_number("/sys/fs/cgroup/memory.max"),
        "memory_cgroup_current_bytes": _read_number("/sys/fs/cgroup/memory.current"),
        "disk_total_bytes": disk.total, "disk_free_bytes": disk.free,
        "disk_path": str(Path(directory).resolve()),
        "network_egress": None, "session_url": None,
    }, observed_at=now, recorded_at=now,
        source={"kind": "local_measurement", "ref": "python-process-and-local-filesystem"})


def catalog_records(catalog: dict[str, Any], *, recorded_at: str) -> list[dict[str, Any]]:
    """Expand the saved board catalog without pretending to refresh providers."""
    source = catalog["provenance"]
    return [make_record(item["kind"], item["subject_id"], item["data"],
                        observed_at=item.get("observed_at", source["observed_at"]),
                        recorded_at=recorded_at,
                        source={**{k: v for k, v in source.items() if k != "observed_at"},
                                "kind": "saved_board", "ref": item.get("source_ref", source["ref"]),
                                "published_at": item.get("published_at", source.get("published_at"))})
            for item in catalog["records"]]


def read_records(path: str) -> list[dict[str, Any]]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return value if isinstance(value, list) else [value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inventory", help="emit saved source/session/artifact observations")
    inventory.add_argument("--catalog", default=str(Path(__file__).with_name("fleet.json")))
    view = commands.add_parser("snapshot", help="reconcile JSON or JSONL observations")
    view.add_argument("--input", default="-")
    view.add_argument("--as-of", default=None)
    view.add_argument("--max-age-seconds", type=float, default=1800)
    vm = commands.add_parser("local-vm", help="emit a current local measurement")
    vm.add_argument("--vm-id", required=True)
    vm.add_argument("--directory", default=".")
    args = parser.parse_args(argv)
    if args.command == "inventory":
        for record in catalog_records(json.loads(Path(args.catalog).read_text()), recorded_at=utc_now()):
            print(json.dumps(record, sort_keys=True, allow_nan=False))
    else:
        output = (measure_vm(args.vm_id, args.directory) if args.command == "local-vm" else
                  snapshot(read_records(args.input), as_of=args.as_of or utc_now(),
                           max_age_seconds=args.max_age_seconds))
        print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
