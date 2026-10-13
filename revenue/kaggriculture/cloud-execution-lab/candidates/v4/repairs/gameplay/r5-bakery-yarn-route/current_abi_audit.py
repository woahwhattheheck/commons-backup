#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed current-ABI audit for the preserved R5 BAKERY->YARN donor.

Historical R5 was one exact route-selection delta: at Shop Router step 144 the
BAKERY->YARN continuation changed from published tape 3 to existing tape 9.
A current-V4 implementation is a semantic *port* only if the current route bank
contains an identity-preserving image of the executed legacy baseline tail and
an exact target tail that is prefix-compatible with current MAIN. Otherwise a
new/approximate route would be a new policy hypothesis, not the preserved R5.

The retired broad apply_v4 generator is never imported or executed. We first
authenticate both historical donor files by exact Git-blob identity, then parse
its literal contract, decode only the data-only legacy tape bank, and compare it
with current Arlene, the route producer actually consumed by the scheduler.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[4]
DONOR = LAB / "candidates" / "v4" / "donor" / "overlay"
LEGACY_ROUTER = DONOR / "r04_full_router.py"
LEGACY_TAPES = DONOR / "r01_tapes.py"
CURRENT_ROUTER = LAB / "reference" / "next-panel" / "vendor" / "arlene.py"
MANIFEST = HERE / "MANIFEST.json"

EXPECTED_LEGACY_ROUTER_GIT_BLOB = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"
EXPECTED_LEGACY_TAPES_GIT_BLOB = "a43289b9cc5e34a2481fddf652762a7d92f427ef"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _require_historical_donor_identity() -> dict[str, str]:
    """Authenticate immutable R5 donor bytes before parsing or executing them."""
    observed = {
        "legacy_router_git_blob": _git_blob_sha1(LEGACY_ROUTER),
        "legacy_tapes_git_blob": _git_blob_sha1(LEGACY_TAPES),
    }
    expected = {
        "legacy_router_git_blob": EXPECTED_LEGACY_ROUTER_GIT_BLOB,
        "legacy_tapes_git_blob": EXPECTED_LEGACY_TAPES_GIT_BLOB,
    }
    mismatches = [
        name for name in expected
        if observed[name] != expected[name]
    ]
    if mismatches:
        details = ", ".join(
            f"{name}: expected {expected[name]}, got {observed[name]}"
            for name in mismatches
        )
        raise RuntimeError(f"historical donor identity mismatch: {details}")
    return observed


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module spec: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _literal_assignment(path: Path, name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                found.append(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                found.append(node.value)
    if len(found) != 1:
        raise RuntimeError(f"{path}: expected one literal assignment for {name}, found {len(found)}")
    return ast.literal_eval(found[0])


def _tail_equal(current_route: list, legacy_tape: list, step: int) -> bool:
    """Compare only the historical executable interval (legacy steps 0..718)."""
    if len(current_route) < len(legacy_tape):
        return False
    return current_route[step:len(legacy_tape)] == legacy_tape[step:]


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def audit() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    donor_identity = _require_historical_donor_identity()
    route_step = _literal_assignment(LEGACY_ROUTER, "ROUTE_STEP")
    shop_plans = _literal_assignment(LEGACY_ROUTER, "SHOP_PLANS")
    pair = ("BAKERY", "YARN_STORE")
    baseline_plan = shop_plans[pair]
    target_plan = 9

    tape_module = _load_module(LEGACY_TAPES, "_r5_legacy_tapes")
    legacy = tape_module.load_tapes()
    if len(legacy) != 13:
        raise RuntimeError(f"legacy tape bank changed: expected 13, got {len(legacy)}")
    if baseline_plan >= len(legacy) or target_plan >= len(legacy):
        raise RuntimeError("legacy R5 plan index outside tape bank")
    baseline_tape = legacy[baseline_plan]
    target_tape = legacy[target_plan]
    if len(baseline_tape) != len(target_tape):
        raise RuntimeError("legacy baseline/target tape lengths differ")

    current = _load_module(CURRENT_ROUTER, "_r5_current_arlene")
    routes = current.routes()
    current_main = current.MAIN
    if current_main not in routes:
        raise RuntimeError(f"current MAIN key missing from route bank: {current_main}")
    main_route = routes[current_main]

    baseline_matches = sorted(
        key for key, route in routes.items()
        if _tail_equal(route, baseline_tape, route_step)
    )
    target_matches = sorted(
        key for key, route in routes.items()
        if _tail_equal(route, target_tape, route_step)
    )
    current_main_matches_baseline = current_main in baseline_matches
    prefix_compatible_targets = sorted(
        key for key in target_matches
        if routes[key][:route_step] == main_route[:route_step]
    )
    portable_targets = prefix_compatible_targets if current_main_matches_baseline else []

    decisions = [list(row) for row in current.DECISIONS]
    step_decisions = [row for row in decisions if row and row[0] == route_step]
    historical_plan_prefix_equal = baseline_tape[:route_step] == target_tape[:route_step]

    if current_main_matches_baseline and portable_targets:
        verdict = "portable_exact_target"
        reasons = [
            "current_MAIN_is_exact_legacy_plan3_executable_tail",
            "current_route_bank_contains_prefix_compatible_exact_legacy_plan9_tail",
        ]
    else:
        verdict = "nonportable_no_current_authoritative_target"
        reasons = []
        if not current_main_matches_baseline:
            reasons.append("current_MAIN_is_not_legacy_plan3_executable_tail")
        if not target_matches:
            reasons.append("current_route_bank_has_no_exact_legacy_plan9_executable_tail")
        elif not prefix_compatible_targets:
            reasons.append("legacy_plan9_tail_exists_but_not_as_prefix_compatible_target_from_current_MAIN")
        elif not current_main_matches_baseline:
            reasons.append("exact_target_exists_but_current_baseline_is_not_the_preserved_R5_baseline")

    return {
        "schema": 1,
        "lane": manifest.get("name"),
        "manifest_status_before_audit": manifest.get("status"),
        "verdict": verdict,
        "reason_codes": reasons,
        "source_identity": {
            **donor_identity,
            "legacy_router_sha256": _sha256(LEGACY_ROUTER),
            "legacy_tapes_sha256": _sha256(LEGACY_TAPES),
            "current_router_sha256": _sha256(CURRENT_ROUTER),
            "manifest_sha256": _sha256(MANIFEST),
        },
        "legacy_contract": {
            "route_step": route_step,
            "shop_pair": list(pair),
            "baseline_plan": baseline_plan,
            "target_plan": target_plan,
            "tape_count": len(legacy),
            "tape_length": len(baseline_tape),
            "historical_plan_prefix_equal_informational_only": historical_plan_prefix_equal,
            "baseline_tail_sha256": _canonical_hash(baseline_tape[route_step:]),
            "target_tail_sha256": _canonical_hash(target_tape[route_step:]),
        },
        "current_contract": {
            "main": current_main,
            "route_count": len(routes),
            "route_keys": sorted(routes),
            "decisions": decisions,
            "route_step_decisions": step_decisions,
            "has_legacy_SHOP_PLANS_symbol": hasattr(current, "SHOP_PLANS"),
            "current_main_tail_sha256_on_legacy_interval": _canonical_hash(
                main_route[route_step:len(baseline_tape)]
            ),
        },
        "identity_mapping": {
            "current_MAIN_matches_legacy_plan3": current_main_matches_baseline,
            "legacy_plan3_tail_matches": baseline_matches,
            "legacy_plan9_tail_matches": target_matches,
            "prefix_compatible_legacy_plan9_targets": prefix_compatible_targets,
            "portable_exact_targets": portable_targets,
        },
        "policy_boundary": (
            "Only portable_exact_target authorizes a semantic-port implementation. "
            "The nonportable verdict forbids inventing a replacement route or restoring "
            "the retired broad materializer; R5 remains evidence/custody only."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", choices=(
        "portable_exact_target",
        "nonportable_no_current_authoritative_target",
    ))
    parser.add_argument("--json", action="store_true", help="emit canonical JSON")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print(report["verdict"])
    if args.expect and report["verdict"] != args.expect:
        print(f"EXPECTED {args.expect} GOT {report['verdict']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
