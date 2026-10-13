#!/usr/bin/env python3
"""Trusted-boundary facade for portable Commons CI fleet evidence.

The internal observed-evidence core validates committed source, worker raw results,
reports, retry lineage, and coverage. This public module deliberately keeps that
worker evidence below release authority: complete worker observations stay
``UNVERIFIED`` until an independent coordinator/provider readback supplies a
trusted execution-authority receipt for every latest passing shard.

There is intentionally no CLI flag that accepts authority receipts. The CLI can
prove the source plan, but arbitrary files supplied by the same caller are not
provider authentication. Programmatic callers may pass
``trusted_execution_authorities`` only after independently reading the provider
execution record through a separate authenticated road.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from . import _ci_fleet_observed as _core
except ImportError:
    import _ci_fleet_observed as _core

# Re-export the source/attempt planner contract while replacing authoritative
# aggregate/main/attempt-inspection boundaries.
for _name in dir(_core):
    if not _name.startswith("_") and _name not in {"aggregate", "inspect_attempt", "main"}:
        globals()[_name] = getattr(_core, _name)

AUTHORITY_SCHEMA = "commons-ci-fleet-execution-authority/v1"
AUTHORITY_KEYS = frozenset({
    "schema", "plan_sha256", "attempt_sha256", "provider", "execution_id",
    "source_sha", "command_sha256", "runtime", "runtime_sha256",
    "runner_inputs_sha256", "raw_results_sha256", "report_sha256",
    "authority_sha256",
})


def _validate_execution_preflight(attempt: Any) -> None:
    """Require the runner's complete clean-source preflight observation."""
    require(isinstance(attempt, dict), "attempt must be an object")
    report = attempt.get("report")
    require(isinstance(report, dict), "attempt report must be an object")
    execution = report.get("execution")
    require(isinstance(execution, dict), "battery execution identity must be an object")
    ignored = execution.get("ignored_worktree_entries_at_start")
    require(
        type(ignored) is int and ignored == 0,
        "ignored working-tree inputs were present or not measured at execution start",
    )


def inspect_attempt(
    plan: dict[str, Any],
    attempt: Any,
) -> tuple[str, list[str]]:
    """Inspect one attempt without dropping the runner's ignored-input preflight."""
    state, paths = _core.inspect_attempt(plan, attempt)
    _validate_execution_preflight(attempt)
    return state, paths


def _validate_execution_authority(
    plan: dict[str, Any],
    attempt: dict[str, Any],
    authority: Any,
) -> None:
    """Validate binding of an authority receipt already trusted by the caller.

    The digest is tamper evidence, not provider authentication. Authenticity is
    established outside this module by the coordinator/provider readback road.
    """
    require(isinstance(authority, dict), "execution authority must be an object")
    require(set(authority) == AUTHORITY_KEYS, "execution authority fields differ from the schema")
    require(authority.get("schema") == AUTHORITY_SCHEMA, "invalid execution authority schema")
    require(
        isinstance(authority.get("authority_sha256"), str)
        and bool(HEX64.fullmatch(authority["authority_sha256"]))
        and authority["authority_sha256"]
        == seal(authority, "authority_sha256")["authority_sha256"],
        "execution authority digest mismatch",
    )
    provenance = attempt["provenance"]
    expected = {
        "plan_sha256": plan["plan_sha256"],
        "attempt_sha256": attempt["attempt_sha256"],
        "provider": provenance["provider"],
        "execution_id": provenance["execution_id"],
        "source_sha": plan["source_sha"],
        "command_sha256": digest(attempt["command"]),
        "runtime_sha256": plan["runtime_sha256"],
        "runner_inputs_sha256": digest(plan["runner_inputs"]),
        "raw_results_sha256": attempt["raw_results_sha256"],
        "report_sha256": digest(attempt["report"]),
    }
    for field, value in expected.items():
        require(authority.get(field) == value, "execution authority mismatch: " + field)
    valid_runtime(authority.get("runtime"))
    require(
        authority["runtime"] == plan["runtime"],
        "execution authority runtime differs from the frozen target runtime",
    )


def aggregate(
    plan: dict[str, Any],
    attempts: list[dict[str, Any]],
    *,
    expected_plan_sha256: str | None = None,
    trusted_execution_authorities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate observations; promote to PASSED only across both trust roots."""
    validate_plan(plan)
    require(isinstance(attempts, list), "attempts must be a list")
    authorities = [] if trusted_execution_authorities is None else trusted_execution_authorities
    require(isinstance(authorities, list), "trusted execution authorities must be a list")
    if expected_plan_sha256 is not None:
        require(
            isinstance(expected_plan_sha256, str)
            and bool(HEX64.fullmatch(expected_plan_sha256)),
            "expected plan digest must be SHA-256 hex",
        )

    preflight_findings: list[dict[str, Any]] = []
    for position, attempt in enumerate(attempts):
        try:
            _validate_execution_preflight(attempt)
        except (FleetError, TypeError, KeyError, ValueError) as exc:
            preflight_findings.append({
                "code": "INVALID_EXECUTION_PREFLIGHT",
                "position": position,
                "detail": str(exc),
            })

    # Never give the observed core a source authority input: its historical
    # PASSED state means internally coherent worker observations, not provider
    # readback. We add the two independent authority dimensions below.
    observed = _core.aggregate(plan, attempts, expected_plan_sha256=None)
    payload = {
        key: value
        for key, value in observed.items()
        if key not in {
            "aggregate_sha256", "status", "source_binding",
            "execution_binding", "execution_authenticity", "runtime_binding",
        }
    }
    findings = list(payload.get("findings") or []) + preflight_findings

    source_bound = expected_plan_sha256 == plan["plan_sha256"]
    status = observed["status"]
    if expected_plan_sha256 is not None and not source_bound:
        status = "INVALID"
        findings.append({
            "code": "SOURCE_BINDING_MISMATCH",
            "detail": "plan differs from the coordinator's independently verified source plan",
        })

    latest_by_sha: dict[str, dict[str, Any]] = {}
    latest_passes: set[str] = set()
    for shard in observed.get("shards", []):
        attempt_sha = shard.get("attempt_sha256")
        if not attempt_sha:
            continue
        matches = [
            row for row in attempts
            if isinstance(row, dict) and row.get("attempt_sha256") == attempt_sha
        ]
        if len(matches) == 1:
            latest_by_sha[attempt_sha] = matches[0]
            if shard.get("state") == "PASSED":
                latest_passes.add(attempt_sha)

    authority_by_attempt: dict[str, dict[str, Any]] = {}
    authority_execution_ids: set[tuple[str, str]] = set()
    for position, authority in enumerate(authorities):
        try:
            require(isinstance(authority, dict), "execution authority must be an object")
            attempt_sha = authority.get("attempt_sha256")
            require(
                isinstance(attempt_sha, str) and attempt_sha in latest_by_sha,
                "execution authority targets an unknown or non-latest attempt",
            )
            require(attempt_sha not in authority_by_attempt, "duplicate execution authority for attempt")
            attempt = latest_by_sha[attempt_sha]
            _validate_execution_authority(plan, attempt, authority)
            key = (authority["provider"], authority["execution_id"])
            require(key not in authority_execution_ids, "duplicate authoritative provider execution identity")
            authority_execution_ids.add(key)
            authority_by_attempt[attempt_sha] = authority
        except (FleetError, TypeError, KeyError, ValueError) as exc:
            findings.append({
                "code": "INVALID_EXECUTION_AUTHORITY",
                "position": position,
                "detail": str(exc),
            })

    complete_observed_pass = (
        status == "UNVERIFIED"
        and bool(latest_passes)
        and all(row.get("state") == "PASSED" for row in observed.get("shards", []))
    )
    execution_bound = (
        complete_observed_pass
        and set(authority_by_attempt) == latest_passes
    )
    if findings:
        status = "INVALID"
    elif complete_observed_pass:
        status = "PASSED" if source_bound and execution_bound else "UNVERIFIED"

    payload.update({
        "status": status,
        "findings": findings,
        "source_binding": "coordinator-anchored" if source_bound else "unverified",
        "execution_binding": (
            "trusted-provider-readback-bound" if execution_bound else "unverified"
        ),
        "execution_authenticity": (
            "trusted external provider/coordinator readback bound to latest attempts"
            if execution_bound
            else "worker-reported observations only; cannot authorize PASSED"
        ),
        "runtime_binding": (
            "trusted readback matched full frozen runtime identity"
            if execution_bound
            else "worker-reported runtime only; cannot authorize PASSED"
        ),
    })
    return seal(payload, "aggregate_sha256")


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
        help=(
            "independent intended source checkout; proves the source plan only. "
            "CLI worker evidence remains UNVERIFIED because this command has no "
            "provider-authenticated execution readback road"
        ),
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = build_plan(
                args.root,
                args.source_sha,
                args.shards,
                load_json(args.runtime),
                args.timeout,
            )
            code = 0
        else:
            plan = load_json(args.plan)
            validate_plan(plan)
            anchor = verify_plan_source(args.source_root, plan) if args.source_root else None
            result = aggregate(
                plan,
                [load_json(path) for path in args.attempt],
                expected_plan_sha256=anchor,
            )
            code = 0 if result["status"] == "PASSED" else 1
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return code
    except (FleetError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({
            "schema": AGGREGATE_SCHEMA,
            "status": "INVALID",
            "error": str(exc),
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
