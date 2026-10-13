#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Snapshot and compare current TITAN route tables around LAND admission."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _require_built_admission(agent: Any, *, apply_land: bool) -> None:
    """Prove package construction, not the probe, installed LAND admission."""
    wrapped = getattr(agent, "_land_admission_wrapped", False) is True
    if apply_land and not wrapped:
        raise ValueError(
            "candidate package construction did not install LAND admission"
        )
    if not apply_land and wrapped:
        raise ValueError("baseline package unexpectedly installed LAND admission")


def _admission_receipt(agent: Any, *, apply_land: bool) -> dict[str, Any] | None:
    if not apply_land:
        return None
    state = getattr(agent, "_land_admission_state", None)
    receipt = state.get("receipt") if isinstance(state, dict) else None
    if not isinstance(receipt, dict) or receipt.get("installed") is not True:
        raise ValueError(
            "candidate LAND wrapper did not emit an installed initialization receipt"
        )
    return json.loads(json.dumps(receipt, sort_keys=True))


def snapshot(package: Path, *, apply_land: bool) -> dict[str, Any]:
    package = package.resolve()
    sys.path.insert(0, str(package))
    try:
        module = _load_module("_titan_route_probe_main", package / "main.py")
        config = json.loads((package / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        agent = module._new_instance(package, config)
        _require_built_admission(agent, apply_land=apply_land)
        agent._initialize()
        admission_receipt = _admission_receipt(agent, apply_land=apply_land)
        controller = getattr(agent, "controller", None)
        routes = getattr(controller, "R", None) if controller is not None else None
        if not isinstance(routes, dict) or not routes:
            raise ValueError("initialized agent has no controller route table")
        normalized = json.loads(json.dumps(routes, sort_keys=True))
        return {
            "schema": "titan-v3-route-snapshot-v1",
            "package": str(package),
            "apply_land": apply_land,
            "land_admission_wrapped": apply_land,
            "land_admission_receipt": admission_receipt,
            "route_count": len(normalized),
            "routes_sha256": hashlib.sha256(_json_bytes(normalized)).hexdigest(),
            "routes": normalized,
        }
    finally:
        try:
            sys.path.remove(str(package))
        except ValueError:
            pass


def compare_snapshots(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    mechanism_path: Path,
) -> dict[str, Any]:
    mechanism = _load_module("_titan_route_compare_land", mechanism_path.resolve())
    expected = copy.deepcopy(baseline["routes"])
    receipt = mechanism.patch_routes(expected)

    if expected != candidate["routes"]:
        raise ValueError(
            "candidate route table differs from baseline plus the exact LAND transform"
        )

    first = None
    sites = []
    for route_name in sorted(set(baseline["routes"]) | set(candidate["routes"])):
        before_route = baseline["routes"].get(route_name)
        after_route = candidate["routes"].get(route_name)
        if before_route == after_route:
            continue
        if before_route is None or after_route is None:
            raise ValueError(f"route set changed at {route_name!r}")
        if len(before_route) != len(after_route):
            raise ValueError(f"route length changed at {route_name!r}")
        for step, (before_row, after_row) in enumerate(zip(before_route, after_route)):
            if before_row == after_row:
                continue
            site = {
                "route": route_name,
                "step": step,
                "before": before_row,
                "after": after_row,
            }
            sites.append(site)
            if first is None:
                first = site

    return {
        "schema": "titan-v3-land-route-diff-v1",
        "baseline_routes_sha256": baseline["routes_sha256"],
        "candidate_routes_sha256": candidate["routes_sha256"],
        "route_count": baseline["route_count"],
        "changed_rows": len(sites),
        "first_divergence": first,
        "sites": sites,
        "transform_receipt": receipt,
        "exact_transform_match": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--package", required=True, type=Path)
    snapshot_parser.add_argument("--apply-land", action="store_true")
    snapshot_parser.add_argument("--output", required=True, type=Path)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--baseline", required=True, type=Path)
    compare_parser.add_argument("--candidate", required=True, type=Path)
    compare_parser.add_argument("--mechanism", required=True, type=Path)
    compare_parser.add_argument("--output", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "snapshot":
        result = snapshot(args.package, apply_land=args.apply_land)
    else:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        result = compare_snapshots(baseline, candidate, args.mechanism)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
