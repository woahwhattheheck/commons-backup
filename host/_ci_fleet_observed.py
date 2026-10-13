#!/usr/bin/env python3
"""Plan and aggregate portable Commons CI battery shards without dispatching them.

The planner freezes the complete committed battery inventory, exact runner bytes,
and an explicit target runtime identity. Worker adapters execute the existing
``host/ci_battery.py`` command and return its raw NUL stream plus
``battery_report.py`` JSON. This module validates and aggregates that evidence.

It deliberately does not create cloud jobs, call provider APIs, register runners,
authenticate provider execution, mutate GitHub, or turn fixtures into executions.
Provider execution IDs remain observations that a coordinator must independently
read back through its provider road before claiming provider-authenticated proof.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any
import sys

try:
    from . import battery_report
except ImportError:
    import battery_report


PLAN_SCHEMA = "commons-ci-fleet-plan/v1"
ATTEMPT_SCHEMA = "commons-ci-fleet-attempt/v1"
AGGREGATE_SCHEMA = "commons-ci-fleet-aggregate/v1"
RUNNER_PATHS = ("host/ci_battery.py", "host/battery_report.py")
OUTPUT_SLOT = "{output_dir}"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_JSON_BYTES = 32 * 1024 * 1024

PLAN_KEYS = frozenset({
    "schema", "source_sha", "inventory", "inventory_sha256", "runtime",
    "runtime_sha256", "runner_inputs", "shard_count", "timeout_seconds",
    "shards", "plan_sha256",
})
INVENTORY_KEYS = frozenset({"path", "command", "source_blob_sha", "sha256"})
RUNNER_KEYS = frozenset({"path", "source_blob_sha", "sha256"})
SHARD_KEYS = frozenset({"index", "paths", "command_template", "command_sha256"})
ATTEMPT_KEYS = frozenset({
    "schema", "plan_sha256", "source_sha", "shard_index", "attempt",
    "parent_attempt_sha256", "runtime", "command", "output_dir",
    "provenance", "runner_inputs", "report", "raw_results_base64",
    "raw_results_sha256", "attempt_sha256",
})


class FleetError(ValueError):
    """Raised when a fleet plan or evidence packet violates its contract."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise FleetError(message)


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FleetError("value is not canonically serializable") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = digest({key: item for key, item in result.items() if key != field})
    return result


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FleetError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise FleetError("non-finite JSON value is forbidden: " + value)


def loads_json(raw: bytes) -> Any:
    require(len(raw) <= MAX_JSON_BYTES, "JSON input exceeds 32 MiB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FleetError("JSON input must be valid UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except FleetError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise FleetError("invalid JSON input") from exc


def load_json(path: Path) -> Any:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
    except OSError as exc:
        raise FleetError("could not read JSON input: " + str(path)) from exc
    return loads_json(raw)


def valid_path(path: Any) -> bool:
    if not isinstance(path, str) or not path or "\\" in path:
        return False
    pure = PurePosixPath(path)
    return (
        not pure.is_absolute()
        and ".." not in pure.parts
        and str(pure) == path
        and path != "."
    )


def valid_runtime(runtime: Any) -> None:
    require(isinstance(runtime, dict), "runtime identity must be an object")
    require(
        set(runtime) == {"python_version", "node_version", "platform", "architecture"},
        "runtime identity needs exact Python, Node, platform and architecture fields",
    )
    require(
        all(isinstance(value, str) and value.strip() for value in runtime.values()),
        "runtime identity fields must be observed nonempty strings",
    )


def discovery(paths: list[str]) -> list[tuple[str, str]]:
    """Reproduce ci_battery.discover ordering over committed repository paths."""
    python: list[str] = []
    node: list[str] = []
    for path in paths:
        if not isinstance(path, str):
            continue
        name = path.rsplit("/", 1)[-1]
        is_python = fnmatch.fnmatchcase(name, "test_*.py") and (
            "/" not in path or path.startswith("infra/")
        )
        is_node = "/" not in path and fnmatch.fnmatchcase(name, "test_*.js")
        if not (is_python or is_node):
            continue
        require(valid_path(path), "invalid repository-relative selected test path")
        if is_python:
            python.append(path)
        else:
            node.append(path)
    key = lambda path: os.fsencode(path)
    return (
        [("python3", path) for path in sorted(python, key=key)]
        + [("node", path) for path in sorted(node, key=key)]
    )


def git(root: Path, *args: str) -> bytes:
    """Read only already-present Git objects; never trigger a lazy network fetch."""
    try:
        return subprocess.run(
            [
                "git",
                "-c",
                "remote.origin.promisor=false",
                "-C",
                str(root),
                *args,
            ],
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise FleetError("required committed Git object is unavailable") from exc


def tree_entries(root: Path, source_sha: str) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for row in git(root, "ls-tree", "-r", "-z", "--full-tree", source_sha).split(b"\0"):
        if not row:
            continue
        try:
            metadata, raw_path = row.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8", "surrogateescape")
        except (ValueError, UnicodeDecodeError) as exc:
            raise FleetError("invalid Git tree entry") from exc
        require(path not in entries, "duplicate Git tree path")
        entries[path] = {"mode": mode, "kind": kind, "source_blob_sha": oid}
    return entries


def blob_hashes(root: Path, oids: list[str]) -> dict[str, str]:
    """SHA-256 blob contents using one bounded-stream ``git cat-file`` process."""
    unique = list(dict.fromkeys(oids))
    if not unique:
        return {}
    try:
        process = subprocess.Popen(
            [
                "git",
                "-c",
                "remote.origin.promisor=false",
                "-C",
                str(root),
                "cat-file",
                "--batch",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
        )
    except OSError as exc:
        raise FleetError("could not start Git blob reader") from exc
    require(process.stdin is not None and process.stdout is not None, "Git blob reader has no pipes")
    result: dict[str, str] = {}
    try:
        for oid in unique:
            require(bool(HEX40.fullmatch(oid)), "invalid source blob identity")
            process.stdin.write((oid + "\n").encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii").strip().split()
            require(
                len(header) == 3 and header[0] == oid and header[1] == "blob",
                "frozen blob is unavailable: " + oid,
            )
            try:
                remaining = int(header[2])
            except ValueError as exc:
                raise FleetError("invalid Git blob size") from exc
            require(remaining >= 0, "invalid Git blob size")
            hasher = hashlib.sha256()
            while remaining:
                chunk = process.stdout.read(min(remaining, 1024 * 1024))
                require(bool(chunk), "truncated frozen blob: " + oid)
                hasher.update(chunk)
                remaining -= len(chunk)
            require(process.stdout.read(1) == b"\n", "invalid Git blob framing")
            result[oid] = hasher.hexdigest()
        process.stdin.close()
        require(process.wait(timeout=10) == 0, "Git blob reader failed")
        return result
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FleetError("Git blob reader failed") from exc
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        for stream in (process.stdin, process.stdout):
            if stream is not None and not stream.closed:
                stream.close()


def shard_spec(
    inventory: list[dict[str, Any]],
    count: int,
    index: int,
    timeout: float,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "host/ci_battery.py",
        "--root",
        ".",
        "--shard-count",
        str(count),
        "--shard-index",
        str(index),
        "--timeout",
        str(timeout),
        "--output-dir",
        OUTPUT_SLOT,
    ]
    paths = [row["path"] for row in inventory[index::count]]
    return {
        "index": index,
        "paths": paths,
        "command_template": command,
        "command_sha256": digest(command),
    }


def build_plan(
    root: Path,
    source_sha: str,
    shard_count: int,
    runtime: dict[str, str],
    timeout: float = 0,
) -> dict[str, Any]:
    valid_runtime(runtime)
    require(
        isinstance(source_sha, str) and bool(HEX40.fullmatch(source_sha)),
        "source must be an exact 40-hex commit SHA",
    )
    actual = git(root, "rev-parse", "--verify", source_sha + "^{commit}").decode().strip()
    require(actual == source_sha, "source is not the requested commit")
    entries = tree_entries(root, source_sha)
    selected = discovery(list(entries))
    require(selected, "committed battery inventory is empty")
    require(
        type(shard_count) is int and 1 <= shard_count <= len(selected),
        "shard count must cover a nonempty inventory without empty shards",
    )
    require(
        type(timeout) in (int, float) and math.isfinite(timeout) and timeout >= 0,
        "timeout must be finite and nonnegative",
    )
    timeout = float(timeout)

    wanted = [path for _, path in selected] + list(RUNNER_PATHS)
    for path in wanted:
        entry = entries.get(path, {})
        require(
            entry.get("kind") == "blob" and entry.get("mode") in ("100644", "100755"),
            "planned source is not a tracked regular file: " + path,
        )
    hashes = blob_hashes(root, [entries[path]["source_blob_sha"] for path in wanted])

    def identity(path: str) -> dict[str, str]:
        oid = entries[path]["source_blob_sha"]
        return {
            "path": path,
            "source_blob_sha": oid,
            "sha256": hashes[oid],
        }

    inventory = [
        {**identity(path), "command": command}
        for command, path in selected
    ]
    runner_inputs = [identity(path) for path in RUNNER_PATHS]
    plan = {
        "schema": PLAN_SCHEMA,
        "source_sha": source_sha,
        "inventory": inventory,
        "inventory_sha256": digest(inventory),
        "runtime": dict(runtime),
        "runtime_sha256": digest(runtime),
        "runner_inputs": runner_inputs,
        "shard_count": shard_count,
        "timeout_seconds": timeout,
        "shards": [
            shard_spec(inventory, shard_count, index, timeout)
            for index in range(shard_count)
        ],
    }
    return seal(plan, "plan_sha256")


def validate_plan(plan: Any) -> dict[str, Any]:
    require(isinstance(plan, dict), "fleet plan must be an object")
    require(set(plan) == PLAN_KEYS, "fleet plan fields differ from the schema")
    require(plan.get("schema") == PLAN_SCHEMA, "invalid fleet plan schema")
    require(
        isinstance(plan.get("plan_sha256"), str)
        and bool(HEX64.fullmatch(plan["plan_sha256"])),
        "invalid plan digest",
    )
    require(
        plan["plan_sha256"] == seal(plan, "plan_sha256")["plan_sha256"],
        "plan digest mismatch",
    )
    require(
        isinstance(plan.get("source_sha"), str)
        and bool(HEX40.fullmatch(plan["source_sha"])),
        "invalid planned source",
    )
    valid_runtime(plan.get("runtime"))
    require(
        plan.get("runtime_sha256") == digest(plan["runtime"]),
        "runtime digest mismatch",
    )

    inventory = plan.get("inventory")
    require(isinstance(inventory, list) and bool(inventory), "empty inventory")
    paths: list[str] = []
    for row in inventory:
        require(isinstance(row, dict) and set(row) == INVENTORY_KEYS, "invalid inventory row")
        require(valid_path(row.get("path")), "invalid inventory path")
        require(row.get("command") in ("python3", "node"), "invalid inventory command")
        require(
            isinstance(row.get("source_blob_sha"), str)
            and bool(HEX40.fullmatch(row["source_blob_sha"])),
            "invalid inventory source blob",
        )
        require(
            isinstance(row.get("sha256"), str)
            and bool(HEX64.fullmatch(row["sha256"])),
            "invalid inventory SHA-256",
        )
        paths.append(row["path"])
    require(len(set(paths)) == len(paths), "duplicate inventory path")
    require(
        [(row["command"], row["path"]) for row in inventory] == discovery(paths),
        "inventory differs from battery discovery ordering",
    )
    require(
        plan.get("inventory_sha256") == digest(inventory),
        "inventory digest mismatch",
    )

    runners = plan.get("runner_inputs")
    require(
        isinstance(runners, list)
        and len(runners) == len(RUNNER_PATHS)
        and all(isinstance(row, dict) and set(row) == RUNNER_KEYS for row in runners),
        "invalid runner source closure",
    )
    require(
        [row["path"] for row in runners] == list(RUNNER_PATHS),
        "runner source closure differs",
    )
    for row in runners:
        require(
            bool(HEX40.fullmatch(row["source_blob_sha"]))
            and bool(HEX64.fullmatch(row["sha256"])),
            "invalid runner source identity",
        )

    count = plan.get("shard_count")
    timeout = plan.get("timeout_seconds")
    require(
        type(count) is int and 1 <= count <= len(inventory),
        "invalid shard count",
    )
    require(
        type(timeout) in (int, float) and math.isfinite(timeout) and timeout >= 0,
        "invalid timeout",
    )
    shards = plan.get("shards")
    require(
        isinstance(shards, list)
        and len(shards) == count
        and all(isinstance(row, dict) and set(row) == SHARD_KEYS for row in shards),
        "invalid shard specification list",
    )
    expected_shards = [
        shard_spec(inventory, count, index, float(timeout))
        for index in range(count)
    ]
    require(shards == expected_shards, "shards do not partition the inventory exactly once")
    return plan


def verify_plan_source(root: Path, plan: dict[str, Any]) -> str:
    """Rebuild a plan from independent committed Git objects and return its digest."""
    validate_plan(plan)
    expected = build_plan(
        root,
        plan["source_sha"],
        plan["shard_count"],
        plan["runtime"],
        plan["timeout_seconds"],
    )
    require(
        expected["plan_sha256"] == plan["plan_sha256"],
        "plan differs from complete independently read committed inventory or runner bytes",
    )
    return expected["plan_sha256"]


def make_attempt(
    plan: dict[str, Any],
    shard_index: int,
    attempt: int,
    report: dict[str, Any],
    raw_results: bytes,
    *,
    runtime: dict[str, str],
    command: list[str],
    output_dir: str,
    provenance: dict[str, Any],
    runner_inputs: list[dict[str, str]],
    parent_attempt_sha256: str | None = None,
) -> dict[str, Any]:
    """Package worker observations; this does not execute or authenticate a run."""
    validate_plan(plan)
    require(type(raw_results) is bytes, "raw results must be exact bytes")
    require(len(raw_results) <= MAX_JSON_BYTES, "raw result payload exceeds 32 MiB")
    payload = {
        "schema": ATTEMPT_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "source_sha": plan["source_sha"],
        "shard_index": shard_index,
        "attempt": attempt,
        "parent_attempt_sha256": parent_attempt_sha256,
        "runtime": runtime,
        "command": command,
        "output_dir": output_dir,
        "provenance": provenance,
        "runner_inputs": runner_inputs,
        "report": report,
        "raw_results_base64": base64.b64encode(raw_results).decode("ascii"),
        "raw_results_sha256": hashlib.sha256(raw_results).hexdigest(),
    }
    return seal(payload, "attempt_sha256")


def _decode_raw(attempt: dict[str, Any]) -> bytes:
    encoded = attempt.get("raw_results_base64")
    require(isinstance(encoded, str), "raw result payload must be base64 text")
    require(len(encoded) <= MAX_JSON_BYTES * 2, "raw result encoding is oversized")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise FleetError("invalid raw result encoding") from exc
    require(len(raw) <= MAX_JSON_BYTES, "raw result payload exceeds 32 MiB")
    require(
        hashlib.sha256(raw).hexdigest() == attempt.get("raw_results_sha256"),
        "raw result hash mismatch",
    )
    return raw


def inspect_attempt(
    plan: dict[str, Any],
    attempt: Any,
) -> tuple[str, list[str]]:
    validate_plan(plan)
    require(isinstance(attempt, dict), "attempt must be an object")
    require(set(attempt) == ATTEMPT_KEYS, "attempt fields differ from the schema")
    require(attempt.get("schema") == ATTEMPT_SCHEMA, "invalid attempt schema")
    require(
        isinstance(attempt.get("attempt_sha256"), str)
        and bool(HEX64.fullmatch(attempt["attempt_sha256"]))
        and attempt["attempt_sha256"] == seal(attempt, "attempt_sha256")["attempt_sha256"],
        "attempt digest mismatch",
    )
    require(
        attempt.get("plan_sha256") == plan["plan_sha256"]
        and attempt.get("source_sha") == plan["source_sha"],
        "stale or foreign attempt",
    )

    index = attempt.get("shard_index")
    number = attempt.get("attempt")
    require(type(index) is int and 0 <= index < plan["shard_count"], "invalid shard index")
    require(type(number) is int and number >= 1, "invalid attempt number")
    parent = attempt.get("parent_attempt_sha256")
    require(
        parent is None or (isinstance(parent, str) and bool(HEX64.fullmatch(parent))),
        "invalid parent attempt digest",
    )
    valid_runtime(attempt.get("runtime"))
    require(attempt["runtime"] == plan["runtime"], "runtime identity mismatch")
    require(attempt.get("runner_inputs") == plan["runner_inputs"], "runner source identity mismatch")

    provenance = attempt.get("provenance")
    require(isinstance(provenance, dict), "execution provenance must be an object")
    require(
        provenance.get("kind") == "executed"
        and provenance.get("measured") is True
        and all(
            isinstance(provenance.get(key), str) and provenance[key].strip()
            for key in ("provider", "execution_id")
        ),
        "missing observed execution provenance; fixtures are not runs",
    )
    provider_name = provenance["provider"].lower()
    require(
        not any(token in provider_name for token in ("fixture", "mock")),
        "fixture/mock provider is not execution evidence",
    )

    output = attempt.get("output_dir")
    require(
        isinstance(output, str) and output.strip() and output != OUTPUT_SLOT,
        "unresolved output directory",
    )
    expected_command = [
        output if part == OUTPUT_SLOT else part
        for part in plan["shards"][index]["command_template"]
    ]
    require(attempt.get("command") == expected_command, "runner command identity mismatch")

    raw = _decode_raw(attempt)
    sha, records, complete, problems = battery_report.parse_results(raw)
    require(sha == plan["source_sha"], "raw results source mismatch")

    report = attempt.get("report")
    require(
        isinstance(report, dict) and report.get("schema") == battery_report.SCHEMA,
        "invalid battery report",
    )
    require(report.get("checkout_sha") == sha, "report checkout mismatch")
    scope = {
        "kind": "full" if plan["shard_count"] == 1 else "shard",
        "requested": [],
        "shard_index": index,
        "shard_count": plan["shard_count"],
        "discovered_files": len(plan["inventory"]),
        "planned_files": len(plan["shards"][index]["paths"]),
    }
    require(report.get("scope") == scope, "partial or foreign discovery scope")

    execution = report.get("execution")
    require(
        isinstance(execution, dict)
        and execution.get("kind") == "direct-process"
        and execution.get("worktree_dirty_at_start") is False
        and execution.get("preflight_error") is None
        and execution.get("python_version") == plan["runtime"]["python_version"],
        "battery execution identity or clean-source preflight failed",
    )

    wanted = plan["shards"][index]["paths"]
    inventory = {row["path"]: row for row in plan["inventory"]}
    paths = [row["path"] for row in records]
    require(len(paths) == len(set(paths)), "duplicate result path")
    require(paths == wanted[:len(paths)], "result paths overlap, escape, or reorder their shard")

    expected_rows = []
    for row in records:
        source = inventory.get(row["path"])
        require(source is not None, "result path is outside the frozen inventory")
        require(
            row["command"] == [source["command"], "./" + row["path"]],
            "test command identity mismatch",
        )
        expected_rows.append({
            **row,
            "source_blob_sha": source["source_blob_sha"],
            "source_in_checkout_commit": True,
        })
    require(report.get("results") == expected_rows, "report differs from raw exits or planned source blobs")

    hashes = execution.get("test_file_sha256")
    require(isinstance(hashes, dict), "missing executed test hashes")
    require(
        set(paths).issubset(hashes)
        and set(hashes).issubset(wanted)
        and all(
            isinstance(value, str)
            and value == inventory[path]["sha256"]
            for path, value in hashes.items()
        ),
        "executed test bytes differ from the frozen plan",
    )

    failed = sum(row["exit_code"] != 0 for row in records)
    counts = {
        "completed_files": len(records),
        "passed_files": len(records) - failed,
        "failed_files": failed,
        "unresolved_source_files": 0,
    }
    require(report.get("counts") == counts, "report count mismatch")
    outcome = report.get("workflow_outcome")
    require(
        outcome in ("success", "failure", "cancelled", "skipped", "unknown"),
        "invalid battery outcome",
    )
    report_problems = report.get("problems")
    require(
        isinstance(report_problems, list)
        and all(isinstance(problem, str) for problem in report_problems)
        and all(problem in report_problems for problem in problems),
        "report lost raw result diagnostics",
    )

    if complete:
        require(paths == wanted, "completed stream is missing planned files")
        require(set(hashes) == set(wanted), "completed stream is missing test byte hashes")
    if (
        complete
        and not problems
        and not report_problems
        and outcome == "success"
        and not failed
        and report.get("complete") is True
        and report.get("conclusion") == "PASSED"
    ):
        return "PASSED", paths

    require(
        report.get("conclusion") != "PASSED",
        "passing report contradicts incomplete or failed execution",
    )
    if failed:
        return "FAILED", paths
    return "INCOMPLETE", paths


def aggregate(
    plan: dict[str, Any],
    attempts: list[dict[str, Any]],
    *,
    expected_plan_sha256: str | None = None,
) -> dict[str, Any]:
    validate_plan(plan)
    require(isinstance(attempts, list), "attempts must be a list")
    if expected_plan_sha256 is not None:
        require(
            isinstance(expected_plan_sha256, str)
            and bool(HEX64.fullmatch(expected_plan_sha256)),
            "expected plan digest must be SHA-256 hex",
        )

    findings: list[dict[str, Any]] = []
    by_shard: dict[int, list[tuple[dict[str, Any], str, list[str]]]] = {}
    execution_ids: set[tuple[str, str]] = set()

    for position, attempt in enumerate(attempts):
        try:
            state, paths = inspect_attempt(plan, attempt)
            key = (
                attempt["provenance"]["provider"],
                attempt["provenance"]["execution_id"],
            )
            require(key not in execution_ids, "duplicate provider execution identity")
            execution_ids.add(key)
            by_shard.setdefault(attempt["shard_index"], []).append(
                (attempt, state, paths)
            )
        except (FleetError, TypeError, KeyError, ValueError) as exc:
            findings.append({
                "code": "INVALID_ATTEMPT",
                "position": position,
                "detail": str(exc),
            })

    shards: list[dict[str, Any]] = []
    passed_paths: list[str] = []
    for index in range(plan["shard_count"]):
        history = sorted(by_shard.get(index, []), key=lambda item: item[0]["attempt"])
        if not history:
            shards.append({"index": index, "state": "MISSING", "latest_attempt": None})
            continue

        parent: str | None = None
        valid_lineage = True
        for expected_number, (attempt, _state, _paths) in enumerate(history, 1):
            if (
                attempt["attempt"] != expected_number
                or attempt.get("parent_attempt_sha256") != parent
            ):
                findings.append({
                    "code": "INVALID_LINEAGE",
                    "shard_index": index,
                    "detail": "attempts must be unique, contiguous and retain their exact predecessor",
                })
                valid_lineage = False
                break
            parent = attempt["attempt_sha256"]

        latest, state, paths = history[-1]
        if not valid_lineage:
            state = "INVALID"
        if state == "PASSED":
            passed_paths.extend(paths)
        shards.append({
            "index": index,
            "state": state,
            "latest_attempt": latest["attempt"],
            "attempt_sha256": latest["attempt_sha256"],
            "attempts_retained": len(history),
        })

    if findings:
        status = "INVALID"
    elif any(row["state"] == "FAILED" for row in shards):
        status = "FAILED"
    elif any(row["state"] == "INCOMPLETE" for row in shards):
        status = "INCOMPLETE"
    elif any(row["state"] == "INVALID" for row in shards):
        status = "INVALID"
    elif any(row["state"] == "MISSING" for row in shards):
        status = "PARTIAL"
    else:
        status = "PASSED"

    require(len(passed_paths) == len(set(passed_paths)), "aggregate contains overlapping coverage")
    if status == "PASSED":
        require(
            set(passed_paths) == {row["path"] for row in plan["inventory"]},
            "aggregate coverage is incomplete",
        )

    source_bound = expected_plan_sha256 == plan["plan_sha256"]
    if expected_plan_sha256 is not None and not source_bound:
        status = "INVALID"
        findings.append({
            "code": "SOURCE_BINDING_MISMATCH",
            "detail": "plan differs from the coordinator's independently verified source plan",
        })
    elif status == "PASSED" and not source_bound:
        status = "UNVERIFIED"

    aggregate_payload = {
        "schema": AGGREGATE_SCHEMA,
        "plan_sha256": plan["plan_sha256"],
        "source_sha": plan["source_sha"],
        "runtime_sha256": plan["runtime_sha256"],
        "status": status,
        "planned_files": len(plan["inventory"]),
        "passed_files": len(passed_paths),
        "planned_shards": plan["shard_count"],
        "passed_shards": sum(row["state"] == "PASSED" for row in shards),
        "shards": shards,
        "findings": findings,
        "source_binding": "coordinator-anchored" if source_bound else "unverified",
        "runtime_binding": "reported runtime matched; independent provider runtime readback remains external",
        "execution_authenticity": "worker-reported only; coordinator/provider execution readback remains external",
    }
    return seal(aggregate_payload, "aggregate_sha256")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan_parser = commands.add_parser("plan")
    plan_parser.add_argument("--root", type=Path, default=Path.cwd())
    plan_parser.add_argument("--source-sha", required=True)
    plan_parser.add_argument("--shards", type=int, required=True)
    plan_parser.add_argument("--runtime", type=Path, required=True)
    plan_parser.add_argument("--timeout", type=float, default=0)

    aggregate_parser = commands.add_parser("aggregate")
    aggregate_parser.add_argument("--plan", type=Path, required=True)
    aggregate_parser.add_argument("--attempt", type=Path, action="append", default=[])
    aggregate_parser.add_argument(
        "--source-root",
        type=Path,
        help="independent intended source checkout; required before a PASSED aggregate",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            runtime = load_json(args.runtime)
            result = build_plan(
                args.root,
                args.source_sha,
                args.shards,
                runtime,
                args.timeout,
            )
            code = 0
        else:
            plan = load_json(args.plan)
            attempts = [load_json(path) for path in args.attempt]
            anchor = verify_plan_source(args.source_root, plan) if args.source_root else None
            result = aggregate(plan, attempts, expected_plan_sha256=anchor)
            code = 0 if result["status"] == "PASSED" else 1
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return code
    except (FleetError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"schema": AGGREGATE_SCHEMA, "status": "INVALID", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
