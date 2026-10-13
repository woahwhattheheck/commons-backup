#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed, causal regression attribution for ordered TITAN builds.

The existing paired-game gate is the promotion authority.  This tool answers a
separate question: which adjacent build first regressed, and what was the first
causal action divergence on an identical observation stream?

Every engine, runner, build closure, config, terminal ledger, and step trace is
read exactly once, hashed, and parsed from the captured bytes.  A score change
without an action divergence, or observation drift before the first action
difference, is invalid evidence rather than an attributed regression.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from attribution_common import (
    AttributionError,
    CellKey,
    MAX_JSON_BYTES,
    MAX_JSONL_BYTES,
    _commit,
    _exact_keys,
    _key_contract,
    _loads_json,
    _loads_jsonl,
    _nonempty_string,
    _require_mapping,
    _snapshot_file,
    _snapshot_manifest,
    _strict_int,
)
from attribution_compare import _compare_scores, _json_diff, _trace_attribution
from attribution_parse import _parse_games, _parse_grid, _parse_policy, _parse_trace


def _load_build(
    base: Path,
    raw: Any,
    index: int,
    cells: Sequence[CellKey],
    steps: Sequence[int],
) -> dict[str, Any]:
    build = _require_mapping(raw, f"builds[{index}]")
    _exact_keys(
        build,
        {"name", "source_commit", "artifact", "config", "games", "trace"},
        f"builds[{index}]",
    )
    name = _nonempty_string(build["name"], f"builds[{index}].name")
    source_commit = _commit(build["source_commit"], f"builds[{index}].source_commit")
    artifact = _snapshot_file(base, build["artifact"], f"builds[{index}].artifact", MAX_JSONL_BYTES)
    config = _snapshot_file(base, build["config"], f"builds[{index}].config", MAX_JSON_BYTES)
    games_snapshot = _snapshot_file(base, build["games"], f"builds[{index}].games", MAX_JSONL_BYTES)
    trace_snapshot = _snapshot_file(base, build["trace"], f"builds[{index}].trace", MAX_JSONL_BYTES)
    config_value = _loads_json(config.data, f"{name}.config")
    if not isinstance(config_value, Mapping):
        raise AttributionError(f"{name}.config: root must be an object")
    games = _parse_games(_loads_jsonl(games_snapshot.data, f"{name}.games"), cells, f"{name}.games")
    trace = _parse_trace(
        _loads_jsonl(trace_snapshot.data, f"{name}.trace"), cells, steps, f"{name}.trace"
    )
    return {
        "name": name,
        "source_commit": source_commit,
        "artifact": artifact,
        "config": config,
        "config_value": dict(config_value),
        "games_snapshot": games_snapshot,
        "trace_snapshot": trace_snapshot,
        "games": games,
        "trace": trace,
    }


def _parse_comparisons(value: Any, builds: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    names = [build["name"] for build in builds]
    known = set(names)
    if value is None:
        return [
            {"id": f"adjacent-{index:02d}", "before": left, "after": right}
            for index, (left, right) in enumerate(zip(names, names[1:]), 1)
        ]
    if not isinstance(value, list) or not value:
        raise AttributionError("comparisons: expected a nonempty list when supplied")
    result: list[dict[str, str]] = []
    identifiers: set[str] = set()
    for index, raw in enumerate(value):
        row = _require_mapping(raw, f"comparisons[{index}]")
        _exact_keys(row, {"id", "before", "after"}, f"comparisons[{index}]")
        identifier = _nonempty_string(row["id"], f"comparisons[{index}].id")
        before = _nonempty_string(row["before"], f"comparisons[{index}].before")
        after = _nonempty_string(row["after"], f"comparisons[{index}].after")
        if identifier in identifiers:
            raise AttributionError(f"comparisons: duplicate id {identifier}")
        if before not in known or after not in known:
            raise AttributionError(
                f"comparisons[{index}]: unknown build reference; before={before}, after={after}"
            )
        if before == after:
            raise AttributionError(f"comparisons[{index}]: before and after must differ")
        identifiers.add(identifier)
        result.append({"id": identifier, "before": before, "after": after})
    return result


def _comparison_report(
    comparison_id: str,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    policy: Mapping[str, Any],
    cells: Sequence[CellKey],
    steps: Sequence[int],
) -> dict[str, Any]:
    score = _compare_scores(
        left["name"], right["name"], left["games"], right["games"], policy
    )
    trace = _trace_attribution(
        left["name"],
        right["name"],
        left["games"],
        right["games"],
        left["trace"],
        right["trace"],
        cells,
        steps,
    )
    return {
        "id": comparison_id,
        **score,
        "source_commits": {
            "before": left["source_commit"],
            "after": right["source_commit"],
        },
        "config_changes": _json_diff(left["config_value"], right["config_value"]),
        "trace_attribution": trace,
    }


def _manifest_receipt(build: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": build["name"],
        "source_commit": build["source_commit"],
        "artifact": build["artifact"].receipt(),
        "config": build["config"].receipt(),
        "games": build["games_snapshot"].receipt(),
        "trace": build["trace_snapshot"].receipt(),
    }


def run_attribution(manifest_path: str | Path) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    manifest_snapshot = _snapshot_manifest(manifest_path)
    manifest = _require_mapping(_loads_json(manifest_snapshot.data, "manifest"), "manifest")
    _key_contract(
        manifest,
        {"schema_version", "panel_id", "engine", "runner", "grid", "policy", "builds"},
        {"comparisons"},
        "manifest",
    )
    if _strict_int(manifest["schema_version"], "schema_version") != 1:
        raise AttributionError("schema_version: only version 1 is supported")
    panel_id = _nonempty_string(manifest["panel_id"], "panel_id")
    cells, steps, grid = _parse_grid(manifest["grid"])
    policy = _parse_policy(manifest["policy"])
    base = manifest_path.parent
    engine = _snapshot_file(base, manifest["engine"], "engine", MAX_JSONL_BYTES)
    runner = _snapshot_file(base, manifest["runner"], "runner", MAX_JSONL_BYTES)

    raw_builds = manifest["builds"]
    if not isinstance(raw_builds, list) or len(raw_builds) < 2:
        raise AttributionError("builds: at least two ordered builds are required")
    builds = [_load_build(base, raw, index, cells, steps) for index, raw in enumerate(raw_builds)]
    names = [build["name"] for build in builds]
    if len(set(names)) != len(names):
        raise AttributionError("builds: names must be unique")
    artifact_shas = [build["artifact"].sha256 for build in builds]
    if len(set(artifact_shas)) != len(artifact_shas):
        raise AttributionError("builds: executable closure artifacts must be byte-distinct")

    by_name = {build["name"]: build for build in builds}
    declared_plan = _parse_comparisons(manifest.get("comparisons"), builds)
    declared_comparisons = [
        _comparison_report(
            row["id"], by_name[row["before"]], by_name[row["after"]], policy, cells, steps
        )
        for row in declared_plan
    ]

    adjacent: list[dict[str, Any]] = []
    for index, (left, right) in enumerate(zip(builds, builds[1:]), 1):
        adjacent.append(
            _comparison_report(f"diagnostic-adjacent-{index:02d}", left, right, policy, cells, steps)
        )

    anchor = builds[0]
    anchor_comparisons: list[dict[str, Any]] = []
    for index, build in enumerate(builds[1:], 1):
        anchor_comparisons.append(
            _comparison_report(
                f"diagnostic-anchor-{index:02d}", anchor, build, policy, cells, steps
            )
        )

    first_regression = next(
        (item for item in declared_comparisons if item["verdict"] == "REGRESSION"), None
    )
    if first_regression is not None:
        first_regression = {
            "comparison_id": first_regression["id"],
            "before": first_regression["before"],
            "after": first_regression["after"],
            "source_commits": first_regression["source_commits"],
            "suspect_config_paths": [row["path"] for row in first_regression["config_changes"]],
            "policy_failures": first_regression["policy_failures"],
            "metrics": first_regression["metrics"],
            "earliest_divergence_step": first_regression["trace_attribution"]["earliest_divergence_step"],
            "divergence_categories": first_regression["trace_attribution"]["category_counts"],
        }

    verdict = "REGRESSION_FOUND" if first_regression else "NO_REGRESSION"
    return {
        "schema_version": 1,
        "verdict": verdict,
        "panel_id": panel_id,
        "manifest": manifest_snapshot.receipt(),
        "engine": engine.receipt(),
        "runner": runner.receipt(),
        "grid": grid,
        "policy": policy,
        "builds": [_manifest_receipt(build) for build in builds],
        "declared_comparisons": declared_comparisons,
        "adjacent_transitions": adjacent,
        "anchor_comparisons": anchor_comparisons,
        "first_regression": first_regression,
        "scope": (
            "Attribution identifies the first policy-regressing declared comparison and its first "
            "action difference on equal observations. It is not a leaderboard, promotion, or release claim."
        ),
    }


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_attribution(args.manifest)
    except AttributionError as exc:
        report = {
            "schema_version": 1,
            "verdict": "INVALID",
            "blockers": [{"code": "INVALID_EVIDENCE", "message": str(exc)}],
            "scope": "No regression attribution is valid when evidence is incomplete or causally misaligned.",
        }
        _atomic_write_json(args.report, report)
        return 2
    _atomic_write_json(args.report, report)
    return 3 if report["verdict"] == "REGRESSION_FOUND" else 0


if __name__ == "__main__":
    raise SystemExit(main())
