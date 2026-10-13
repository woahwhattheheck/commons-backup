#!/usr/bin/env python3
"""Compile public-safe connected capability observations into an advisory route catalog.

This compiler does not authenticate, authorize, admit, or reject callers.  It
separates measured state so every Commons carrier can choose a working road.
The sole owner-handled row is Claude, by direct owner instruction.

Tool and skill counts belong to the observed snapshot, not this compiler's
source code. Census values must be non-negative integers; provided tool and
app-family breakdowns must reconcile. Preserve each component's observation
timestamp when combining fresh census data with retained resource observations.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

OBSERVATION_SCHEMA = "commons-connected-capability-observations/v1"
CATALOG_SCHEMA = "commons-connected-capabilities/v1"
REQUIRED_PROVIDER_FIELDS = {
    "id", "kind", "capacity", "stage", "condition", "authority", "holder",
    "consumers", "mutation", "route_state", "value", "last_use",
    "freshness", "source_kind", "evidence",
}
STAGES = {"DECLARED", "AVAILABLE", "REACHABLE", "ASSIGNED", "EXERCISED", "PRODUCING"}
CONDITIONS = {"LIVE", "IDLE", "CONSTRAINED", "DEGRADED", "DORMANT", "UNMEASURED",
              "ACTIVE_UNKNOWN", "HELD", "BLOCKED", "STALE", "SUPERSEDED", "ARCHIVED", "DEAD"}
AUTHORITIES = {"SHARED_ALL_CARRIERS", "OWNER_ONLY"}
ALLOCATION_BY_ROUTE_STATE = {
    "CALLABLE": "CALLABLE",
    "CALLABLE_WITH_CONSTRAINT": "CALLABLE_WITH_CONSTRAINT",
    "ACTIVATE_FIRST": "ACTIVATE_FIRST",
    "CONNECTOR_DISCOVERY": "DISCOVER_IN_CARRIER",
    "WAIT_FOR_RESET": "WAIT_FOR_RESET",
    "OWNER_HANDLED": "OWNER_HANDLED",
}
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:password|passwd|api[_ -]?key|client[_ -]?secret)\s*[:=]\s*\S+"),
    # GitHub and Stripe use underscores; retain legacy hyphen-shaped matches.
    re.compile(r"\b(?:(?:gh[pousr]|github_pat|sk_live|sk_test)[_-]|xox[baprs]-)[-A-Za-z0-9_]{8,}\b"),
    re.compile(r"(?i)[?&](?:token|code|secret|key|signature)=[^&\s]+"),
)

class CapabilityInventoryError(ValueError):
    """Observation or projection violates the public-safe inventory contract."""

def _scan_secrets(value: Any) -> None:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for pattern in SECRET_PATTERNS:
        if pattern.search(blob):
            raise CapabilityInventoryError("secret-shaped value found in public capability inventory")

def _count(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CapabilityInventoryError(f"{field} must be a non-negative integer")
    return value

def _validate_tool_fleet(fleet: Any) -> None:
    """Validate the observed census without pinning it to one historical harness."""
    if not isinstance(fleet, dict):
        raise CapabilityInventoryError("tool_fleet must be an object")
    total = _count(fleet.get("callable_tools"), "tool_fleet.callable_tools")
    connected = _count(fleet.get("connected_app_tools"), "tool_fleet.connected_app_tools")
    if connected > total:
        raise CapabilityInventoryError("connected app tools exceed callable tools")
    if "core_tools" in fleet:
        core = _count(fleet["core_tools"], "tool_fleet.core_tools")
        if total != connected + core:
            raise CapabilityInventoryError("tool census does not reconcile")
    _count(fleet.get("fully_paginated_skills"), "tool_fleet.fully_paginated_skills")
    if "app_family_counts" in fleet:
        families = fleet["app_family_counts"]
        if not isinstance(families, dict) or any(not isinstance(k, str) or not k for k in families):
            raise CapabilityInventoryError("app_family_counts must map nonempty names to counts")
        family_total = sum(_count(v, f"app_family_counts.{k}") for k, v in families.items())
        if family_total != connected:
            raise CapabilityInventoryError("app family counts do not reconcile with connected app tools")
        if "app_families" in fleet and _count(fleet["app_families"], "tool_fleet.app_families") != len(families):
            raise CapabilityInventoryError("app family total does not reconcile")
    automations = fleet.get("automations")
    if not isinstance(automations, dict):
        raise CapabilityInventoryError("tool_fleet.automations must be an object")
    counts = {name: _count(automations.get(name), f"automations.{name}")
              for name in ("total", "enabled", "disabled")}
    if counts["total"] != counts["enabled"] + counts["disabled"]:
        raise CapabilityInventoryError("automation totals do not reconcile")

def validate_observations(data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or data.get("schema") != OBSERVATION_SCHEMA:
        raise CapabilityInventoryError("wrong observation schema")
    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        raise CapabilityInventoryError("providers must be a nonempty list")
    ids: set[str] = set()
    owner_only: list[str] = []
    for provider in providers:
        if not isinstance(provider, dict):
            raise CapabilityInventoryError("provider rows must be objects")
        missing = REQUIRED_PROVIDER_FIELDS - provider.keys()
        if missing:
            raise CapabilityInventoryError(f"{provider.get('id', '<unknown>')} missing {sorted(missing)}")
        provider_id = provider["id"]
        if not isinstance(provider_id, str) or not provider_id:
            raise CapabilityInventoryError("provider id must be nonempty text")
        if provider_id in ids:
            raise CapabilityInventoryError(f"duplicate provider id: {provider_id}")
        ids.add(provider_id)
        if provider["stage"] not in STAGES:
            raise CapabilityInventoryError(f"{provider_id} has unknown stage")
        if provider["condition"] not in CONDITIONS:
            raise CapabilityInventoryError(f"{provider_id} has unknown condition")
        if provider["authority"] not in AUTHORITIES:
            raise CapabilityInventoryError(f"{provider_id} has unknown authority")
        if provider["route_state"] not in ALLOCATION_BY_ROUTE_STATE:
            raise CapabilityInventoryError(f"{provider_id} has unknown route_state")
        if provider["authority"] == "OWNER_ONLY":
            owner_only.append(provider_id)
    if owner_only != ["claude-code-max"]:
        raise CapabilityInventoryError("Claude must be the sole owner-handled resource")
    account_roles = data.get("account_roles") or {}
    business = (account_roles.get("business_gmail") or {}).get("address")
    if business != "tokenjunkielabs@gmail.com":
        raise CapabilityInventoryError("shared business Gmail identity is missing")
    _validate_tool_fleet(data.get("tool_fleet"))
    portfolio = data.get("github_portfolio") or {}
    total = portfolio.get("accessible_repositories")
    public = portfolio.get("public_repositories")
    private = portfolio.get("private_repositories")
    repositories = portfolio.get("repositories") or []
    if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
               for value in (total, public, private)):
        raise CapabilityInventoryError("repository totals must be non-negative integers")
    if total != public + private:
        raise CapabilityInventoryError("repository total does not reconcile")
    if len(repositories) != public:
        raise CapabilityInventoryError("public repository rows do not reconcile")
    if portfolio.get("private_details_persisted") is not False:
        raise CapabilityInventoryError("private repository details must not be persisted")
    for repository in repositories:
        if not isinstance(repository, dict) or repository.get("visibility") != "public":
            raise CapabilityInventoryError("repository detail rows must be public")
    _scan_secrets(data)

def compile_catalog(data: dict[str, Any]) -> dict[str, Any]:
    validate_observations(data)
    providers = sorted(copy.deepcopy(data["providers"]), key=lambda row: row["id"])
    for row in providers:
        row["allocation"] = ALLOCATION_BY_ROUTE_STATE[row["route_state"]]
    authority_counts = Counter(row["authority"] for row in providers)
    stage_counts = Counter(row["stage"] for row in providers)
    condition_counts = Counter(row["condition"] for row in providers)
    allocation_counts = Counter(row["allocation"] for row in providers)
    catalog = {
        "schema": CATALOG_SCHEMA,
        "snapshot": copy.deepcopy(data["snapshot"]),
        "policy": {
            "shared_resource_rule": "ALL_CARRIERS",
            "sole_owner_handled_resource": "claude-code-max",
            "metadata_only": True,
            "admission_gate": False,
            "secret_values_persisted": False,
        },
        "summary": {
            "resources": len(providers),
            "authority_counts": dict(sorted(authority_counts.items())),
            "stage_counts": dict(sorted(stage_counts.items())),
            "condition_counts": dict(sorted(condition_counts.items())),
            "allocation_counts": dict(sorted(allocation_counts.items())),
            "callable_now": sum(
                row["allocation"] in {"CALLABLE", "CALLABLE_WITH_CONSTRAINT"}
                for row in providers
            ),
            "activation_or_discovery": sum(
                row["allocation"] in {"ACTIVATE_FIRST", "DISCOVER_IN_CARRIER"}
                for row in providers
            ),
            "wait_for_reset": allocation_counts.get("WAIT_FOR_RESET", 0),
            "owner_handled": allocation_counts.get("OWNER_HANDLED", 0),
        },
        "account_roles": copy.deepcopy(data["account_roles"]),
        "tool_fleet": copy.deepcopy(data["tool_fleet"]),
        "component_freshness": copy.deepcopy(data.get("component_freshness") or {}),
        "github_portfolio": copy.deepcopy(data["github_portfolio"]),
        "providers": providers,
        "durable_evidence": copy.deepcopy(data.get("durable_evidence") or {}),
        "non_claims": list(data.get("non_claims") or []),
    }
    _scan_secrets(catalog)
    return catalog

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

def write_catalog(output: Path, rendered: str) -> None:
    """Replace the canonical catalog atomically while preserving output symlinks."""
    try:
        output = output.resolve()
    except RuntimeError as exc:
        raise OSError(f"cannot resolve catalog output: {output}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous_mode = output.stat().st_mode & 0o777
    except FileNotFoundError:
        previous_mode = None
    temporary = output.with_name(f".{output.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        if previous_mode is not None:
            temporary.chmod(previous_mode)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

def self_test() -> dict[str, Any]:
    sample = {
        "schema": OBSERVATION_SCHEMA,
        "snapshot": {"observed_at": "2026-09-01T00:00:00Z"},
        "account_roles": {"business_gmail": {"address": "tokenjunkielabs@gmail.com"}},
        "tool_fleet": {
            "callable_tools": 442,
            "connected_app_tools": 427,
            "fully_paginated_skills": 118,
            "automations": {"total": 14, "enabled": 7, "disabled": 7},
        },
        "github_portfolio": {
            "accessible_repositories": 0,
            "public_repositories": 0,
            "private_repositories": 0,
            "private_details_persisted": False,
            "repositories": [],
        },
        "providers": [
            {
                "id": "shared", "kind": "TEST", "capacity": "LIVE",
                "stage": "PRODUCING", "condition": "LIVE",
                "authority": "SHARED_ALL_CARRIERS", "holder": "Commons",
                "consumers": ["test"], "mutation": "TASK_SCOPED",
                "route_state": "CALLABLE", "value": "test", "last_use": "now",
                "freshness": "LIVE_PROBE", "source_kind": "TEST", "evidence": "test",
            },
            {
                "id": "claude-code-max", "kind": "MODEL", "capacity": "OWNER_HELD",
                "stage": "AVAILABLE", "condition": "HELD", "authority": "OWNER_ONLY",
                "holder": "Bryce", "consumers": ["Bryce"], "mutation": "OWNER_HANDLED",
                "route_state": "OWNER_HANDLED", "value": "owner handled",
                "last_use": "private", "freshness": "OWNER_DIRECTIVE",
                "source_kind": "TEST", "evidence": "owner handles",
            },
        ],
    }
    first = compile_catalog(sample)
    second = compile_catalog(copy.deepcopy(sample))
    return {
        "ok": first == second
        and first["summary"]["callable_now"] == 1
        and first["summary"]["owner_handled"] == 1
        and first["policy"]["admission_gate"] is False,
        "resources": first["summary"]["resources"],
        "callable_now": first["summary"]["callable_now"],
        "owner_handled": first["summary"]["owner_handled"],
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile connected capability observations")
    parser.add_argument("--input", default="inventory/resources/connected_capability_observations.json")
    parser.add_argument("--output", default="inventory/resources/connected_capabilities.json")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        report = self_test()
        print(canonical_json(report), end="")
        return 0 if report["ok"] else 1
    try:
        source = json.loads(Path(args.input).read_text(encoding="utf-8"))
        compiled = compile_catalog(source)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    rendered = canonical_json(compiled)
    output = Path(args.output)
    if args.verify:
        try:
            matches = output.is_file() and output.read_text(encoding="utf-8") == rendered
        except (OSError, UnicodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if not matches:
            print("MISMATCH")
            return 1
        print("MATCH")
        return 0
    try:
        write_catalog(output, rendered)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"WROTE {output} resources={compiled['summary']['resources']} callable={compiled['summary']['callable_now']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
