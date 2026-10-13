#!/usr/bin/env python3
"""Build a public-safe Vercel deployment-capacity projection.

This module never calls Vercel. It converts a live connector observation into
an aggregate that intentionally excludes team/project/account identifiers.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "commons-vercel-capacity/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_PLAN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def _timestamp(value: str) -> str:
    if not value.endswith("Z"):
        raise ValueError("observed_at must use UTC Z")
    datetime.fromisoformat(value[:-1] + "+00:00")
    return value


def _count(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _safe_plans(plans: Iterable[str]) -> list[str]:
    result = []
    for plan in plans:
        if not isinstance(plan, str) or not SAFE_PLAN_RE.fullmatch(plan):
            raise ValueError("team plans must be public-safe plan labels")
        result.append(plan)
    return sorted(result)


def build_snapshot(
    *,
    observed_at: str,
    source_commit: str,
    team_plans: Iterable[str],
    project_count: int,
    deployments_queried: bool,
    deployment_count: int | None,
) -> dict[str, Any]:
    """Return an aggregate snapshot without Vercel identifiers."""
    observed_at = _timestamp(observed_at)
    if not SHA_RE.fullmatch(source_commit):
        raise ValueError("source_commit must be a full lowercase Git SHA")
    plans = _safe_plans(team_plans)
    project_count = _count(project_count, "project_count")
    if not isinstance(deployments_queried, bool):
        raise ValueError("deployments_queried must be boolean")

    if project_count == 0:
        if deployments_queried:
            raise ValueError("cannot query project-scoped deployments without a project")
        if deployment_count is not None:
            raise ValueError("deployment_count must be null when query is skipped")
        decision = "NO_PROJECT_READY"
        deployment_query = "SKIPPED_NO_PROJECTS"
        routes_ready = 0
    else:
        if not deployments_queried:
            raise ValueError("project inventory requires deployment enumeration")
        deployment_count = _count(deployment_count, "deployment_count")
        decision = "PROJECT_ROUTE_READY"
        deployment_query = "COMPLETE"
        routes_ready = project_count

    plan_counts = dict(sorted(Counter(plans).items()))
    return {
        "schema": SCHEMA,
        "observed_at": observed_at,
        "source_commit": source_commit,
        "source": {
            "kind": "AUTHENTICATED_VERCEL_CONNECTOR_AGGREGATE",
            "raw_identifiers_persisted": False,
            "team_names_persisted": False,
            "team_slugs_persisted": False,
            "team_ids_persisted": False,
            "project_details_persisted": False,
        },
        "aggregate": {
            "teams": len(plans),
            "team_plan_counts": plan_counts,
            "projects": project_count,
            "deployment_query": deployment_query,
            "deployments_observed": deployment_count,
            "deployment_routes_ready": routes_ready,
        },
        "consumer": {
            "name": "Commons Queue Manager and deployment routers",
            "decision": decision,
            "routing_rule": (
                "Assign no Vercel deployment work until a fresh aggregate "
                "contains at least one project; inspect that project separately."
            ),
        },
        "truth": {
            "connector_read_succeeded": True,
            "deployment_created": False,
            "project_mutated": False,
            "configuration_mutated": False,
            "environment_read": False,
            "domain_read": False,
            "secret_read": False,
            "zero_projects_is_not_zero_account_capacity": True,
        },
        "stale_after": "P7D_OR_NEXT_TEAM_OR_PROJECT_CHANGE",
    }


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--team-plan", action="append", default=[])
    parser.add_argument("--projects", required=True, type=int)
    parser.add_argument("--deployments", type=int)
    parser.add_argument("--deployments-queried", action="store_true")
    parser.add_argument("--output")
    parser.add_argument("--check")
    args = parser.parse_args()
    value = build_snapshot(
        observed_at=args.observed_at,
        source_commit=args.source_commit,
        team_plans=args.team_plan,
        project_count=args.projects,
        deployments_queried=args.deployments_queried,
        deployment_count=args.deployments,
    )
    payload = _json_bytes(value)
    if args.check:
        existing = Path(args.check).read_bytes()
        if existing != payload:
            raise SystemExit("MISMATCH")
        print(
            f"MATCH {value['aggregate']['teams']} teams "
            f"{value['aggregate']['projects']} projects "
            f"{value['consumer']['decision']}"
        )
        return 0
    if not args.output:
        parser.error("one of --output or --check is required")
    Path(args.output).write_bytes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
