#!/usr/bin/env python3
"""Fail-closed composition graph validator for the sole canonical TITAN V4 tree."""

from __future__ import annotations

import argparse
import fnmatch
import heapq
import json
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

ALLOWED_STATES = {"compose", "blocked", "evidence_only"}
CANONICAL_BRANCH = "main"
CANONICAL_ROOT = "revenue/kaggriculture/cloud-execution-lab/candidates/v4"
REQUIRED_DISCOVERY_ROOTS = frozenset({"repairs", "research"})
REQUIRED_DISCOVERY_PATTERNS = frozenset({
    "port_current_runtime.py",
    "build_native_d4.py",
    "row_shed_sell_order.py",
    "repairs/performance/funding-replay/apply_town_funding.py",
    "repairs/runtime/joint-unit-projection/compose.py",
    "repairs/performance/funding-replay/apply_funding_replay.py",
    "repairs/performance/funding-replay/compose_funding_capacity.py",
    "repairs/performance/compose_scoped_constructor.py",
    "repairs/performance/projection-state-clone/compose.py",
    "research/sale-window-engagement/compose_current_h3s420.py",
    "repairs/gameplay/v218-legal-movement/check_current_native_binding.py",
    "repairs/gameplay/ghost-plant-admission/ghost_plant_admission.py",
    "repairs/gameplay/redundant-hire-two-seat/repair_redundant_hire_two_seat.py",
    "repairs/gameplay/redundant-hire-two-seat/compose_laborflow_multi_detour.py",
    "repairs/gameplay/defensive-guard/r04_defensive_guards.py",
    "repairs/gameplay/exec-pace/r04_exec_pace.py",
})


def _issue(code: str, component: str | None = None, **details: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code}
    if component is not None:
        out["component"] = component
    out.update(details)
    return out


def _safe_relpath(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    p = PurePosixPath(value)
    return not p.is_absolute() and ".." not in p.parts and "." not in p.parts


def _stable_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, separators=(",", ":")))


def _path_status(root: Path, rel: str, *, expected: str | None = None) -> str:
    try:
        if root.is_symlink():
            return "symlink"
        root_real = root.resolve()
        candidate = root_real
        for part in PurePosixPath(rel).parts:
            candidate = candidate / part
            if candidate.is_symlink():
                return "symlink"
        resolved = candidate.resolve()
        resolved.relative_to(root_real)
    except (OSError, RuntimeError, ValueError):
        return "escape"
    if not resolved.exists():
        return "missing"
    if expected == "file" and not resolved.is_file():
        return "not_file"
    if expected == "directory" and not resolved.is_dir():
        return "not_directory"
    return "ok"


def _reachable(start: str, target: str, edges: dict[str, set[str]]) -> bool:
    todo = [start]
    seen: set[str] = set()
    while todo:
        cur = todo.pop()
        if cur == target:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        todo.extend(sorted(edges.get(cur, ()), reverse=True))
    return False


def _toposort(nodes: set[str], edges: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    indeg = {n: 0 for n in nodes}
    for src in nodes:
        for dst in edges.get(src, ()):
            if dst in indeg:
                indeg[dst] += 1
    heap = [n for n, deg in indeg.items() if deg == 0]
    heapq.heapify(heap)
    out: list[str] = []
    while heap:
        cur = heapq.heappop(heap)
        out.append(cur)
        for dst in sorted(edges.get(cur, ())):
            if dst not in indeg:
                continue
            indeg[dst] -= 1
            if indeg[dst] == 0:
                heapq.heappush(heap, dst)
    cyclic = sorted(nodes - set(out))
    return out, cyclic


def _discover(root: Path, discovery: dict[str, Any]) -> tuple[set[str], set[str]]:
    found: set[str] = set()
    unsafe: set[str] = set()
    roots = discovery.get("roots", [])
    patterns = discovery.get("patterns", [])
    if not isinstance(roots, list) or not isinstance(patterns, list):
        return found, unsafe
    for scan_root in roots:
        if not _safe_relpath(scan_root):
            continue
        base = root / PurePosixPath(scan_root)
        if _path_status(root, scan_root, expected="directory") != "ok":
            unsafe.add(scan_root)
            continue
        for path in base.rglob("*"):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                unsafe.add(rel)
                continue
            if not path.is_file():
                continue
            if any(
                isinstance(pattern, str)
                and (fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(rel, pattern))
                for pattern in patterns
            ):
                found.add(rel)
    return found, unsafe


def _validate_discovery_schema(discovery: Any, errors: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(discovery, dict):
        errors.append(_issue("discovery_not_object"))
        return None

    if discovery.get("strict") is not True:
        errors.append(_issue("discovery_not_strict", actual=discovery.get("strict")))

    roots = discovery.get("roots")
    if not isinstance(roots, list):
        errors.append(_issue("discovery_roots_not_list"))
    elif not roots:
        errors.append(_issue("discovery_roots_empty"))
    else:
        for index, scan_root in enumerate(roots):
            if not _safe_relpath(scan_root):
                errors.append(_issue("bad_discovery_root", index=index, path=scan_root))
        safe_roots = {scan_root for scan_root in roots if _safe_relpath(scan_root)}
        for required in sorted(REQUIRED_DISCOVERY_ROOTS - safe_roots):
            errors.append(_issue("missing_required_discovery_root", root=required))

    patterns = discovery.get("patterns")
    if not isinstance(patterns, list):
        errors.append(_issue("discovery_patterns_not_list"))
    elif not patterns:
        errors.append(_issue("discovery_patterns_empty"))
    else:
        for index, pattern in enumerate(patterns):
            if not isinstance(pattern, str) or not pattern:
                errors.append(_issue("bad_discovery_pattern", index=index, pattern=pattern))
        safe_patterns = {pattern for pattern in patterns if isinstance(pattern, str) and pattern}
        for required in sorted(REQUIRED_DISCOVERY_PATTERNS - safe_patterns):
            errors.append(_issue("missing_required_discovery_pattern", pattern=required))

    raw_ignore = discovery.get("ignore")
    if not isinstance(raw_ignore, list):
        errors.append(_issue("discovery_ignore_not_list"))
    else:
        if raw_ignore:
            errors.append(_issue("discovery_ignore_not_empty", count=len(raw_ignore)))
        for index, item in enumerate(raw_ignore):
            if isinstance(item, str):
                if _safe_relpath(item):
                    errors.append(_issue("ignore_without_reason", path=item))
                else:
                    errors.append(_issue("bad_discovery_ignore_path", index=index, path=item))
                continue
            if not isinstance(item, dict):
                errors.append(_issue("bad_discovery_ignore_item", index=index))
                continue
            path = item.get("path")
            reason = item.get("reason")
            if not _safe_relpath(path):
                errors.append(_issue("bad_discovery_ignore_path", index=index, path=path))
            if not isinstance(reason, str) or not reason.strip():
                errors.append(_issue("ignore_without_reason", path=path))

    return discovery


def validate_manifest(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if manifest.get("schema") != "titan-v4-composition/v1":
        errors.append(_issue("bad_schema", actual=manifest.get("schema")))
    if manifest.get("mode") != "fail_closed":
        errors.append(_issue("mode_not_fail_closed", actual=manifest.get("mode")))
    if manifest.get("canonical_branch") != CANONICAL_BRANCH:
        errors.append(_issue("wrong_canonical_branch", actual=manifest.get("canonical_branch"), expected=CANONICAL_BRANCH))
    if manifest.get("canonical_root") != CANONICAL_ROOT:
        errors.append(_issue("wrong_canonical_root", actual=manifest.get("canonical_root"), expected=CANONICAL_ROOT))

    raw_components = manifest.get("components")
    if not isinstance(raw_components, list):
        return {
            "ok": False,
            "plan": [],
            "blocked": [],
            "evidence_only": [],
            "unregistered": [],
            "errors": _stable_issues(errors + [_issue("components_not_list")]),
            "warnings": [],
        }

    by_id: dict[str, dict[str, Any]] = {}
    entrypoint_owner: dict[str, str] = {}
    blocked: list[str] = []
    evidence_only: list[str] = []

    for idx, comp in enumerate(raw_components):
        if not isinstance(comp, dict):
            errors.append(_issue("component_not_object", index=idx))
            continue
        cid = comp.get("id")
        if not isinstance(cid, str) or not cid:
            errors.append(_issue("bad_component_id", index=idx))
            continue
        if cid in by_id:
            errors.append(_issue("duplicate_component_id", cid))
            continue
        by_id[cid] = comp

        state = comp.get("state")
        if state not in ALLOWED_STATES:
            errors.append(_issue("bad_state", cid, actual=state))
        if state == "blocked":
            blocked.append(cid)
            if not isinstance(comp.get("reason"), str) or not comp["reason"].strip():
                errors.append(_issue("blocked_without_reason", cid))
        elif state == "evidence_only":
            evidence_only.append(cid)

        package = comp.get("package")
        if not _safe_relpath(package):
            errors.append(_issue("unsafe_package_path", cid, path=package))
        else:
            status = _path_status(root, package, expected="directory")
            if status == "missing":
                errors.append(_issue("missing_package", cid, path=package))
            elif status != "ok":
                errors.append(_issue("unsafe_package_resolution", cid, path=package, reason=status))

        eps = comp.get("entrypoints", [])
        if not isinstance(eps, list):
            errors.append(_issue("entrypoints_not_list", cid))
            eps = []
        for ep in eps:
            if not _safe_relpath(ep):
                errors.append(_issue("unsafe_entrypoint_path", cid, path=ep))
                continue
            status = _path_status(root, ep, expected="file")
            if status == "missing":
                errors.append(_issue("missing_entrypoint", cid, path=ep))
            elif status != "ok":
                errors.append(_issue("unsafe_entrypoint_resolution", cid, path=ep, reason=status))
            prior = entrypoint_owner.get(ep)
            if prior is not None and prior != cid:
                errors.append(_issue("duplicate_entrypoint_owner", cid, path=ep, other=prior))
            else:
                entrypoint_owner[ep] = cid

        for field in ("requires", "before", "after", "conflicts"):
            vals = comp.get(field, [])
            if not isinstance(vals, list) or any(not isinstance(v, str) or not v for v in vals):
                errors.append(_issue("bad_relation_list", cid, field=field))
            elif cid in vals:
                errors.append(_issue("self_relation", cid, field=field))

        transforms = comp.get("transforms", [])
        if not isinstance(transforms, list):
            errors.append(_issue("transforms_not_list", cid))
            transforms = []
        for t_index, transform in enumerate(transforms):
            if not isinstance(transform, dict):
                errors.append(_issue("transform_not_object", cid, index=t_index))
                continue
            for field in ("surface", "input_identity", "output_identity"):
                if not isinstance(transform.get(field), str) or not transform[field]:
                    errors.append(_issue("bad_transform_field", cid, index=t_index, field=field))

    all_ids = set(by_id)
    for cid, comp in by_id.items():
        for field in ("requires", "before", "after", "conflicts"):
            vals = comp.get(field, [])
            if not isinstance(vals, list):
                continue
            for other in vals:
                if isinstance(other, str) and other not in all_ids:
                    errors.append(_issue("unknown_relation_target", cid, field=field, target=other))

    active = {cid for cid, comp in by_id.items() if comp.get("state") == "compose"}
    edges: dict[str, set[str]] = {cid: set() for cid in active}

    for cid in active:
        comp = by_id[cid]
        for req in comp.get("requires", []):
            if req not in by_id:
                continue
            if by_id[req].get("state") != "compose":
                errors.append(_issue("active_requires_noncompose", cid, required=req, required_state=by_id[req].get("state")))
            else:
                edges[req].add(cid)
        for prior in comp.get("after", []):
            if prior in active:
                edges[prior].add(cid)
        for later in comp.get("before", []):
            if later in active:
                edges[cid].add(later)
        for conflict in comp.get("conflicts", []):
            if conflict in active:
                errors.append(_issue("active_conflict", cid, other=conflict))

    plan, cyclic = _toposort(active, edges)
    if cyclic:
        errors.append(_issue("dependency_cycle", components=cyclic))

    if not cyclic:
        by_surface: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        output_seen: dict[tuple[str, str], str] = {}
        for cid in sorted(active):
            transforms = by_id[cid].get("transforms", [])
            if not isinstance(transforms, list):
                continue
            for transform in transforms:
                if not isinstance(transform, dict):
                    continue
                surface = transform.get("surface")
                inp = transform.get("input_identity")
                out = transform.get("output_identity")
                if not all(isinstance(x, str) and x for x in (surface, inp, out)):
                    continue
                by_surface[surface].append((cid, transform))
                key = (surface, out)
                if key in output_seen and output_seen[key] != cid:
                    errors.append(_issue("duplicate_output_identity", cid, surface=surface, output_identity=out, other=output_seen[key]))
                else:
                    output_seen[key] = cid

        pos = {cid: i for i, cid in enumerate(plan)}
        for surface, transforms in sorted(by_surface.items()):
            transforms.sort(key=lambda item: (pos[item[0]], item[0]))
            ids = [cid for cid, _ in transforms]
            for left, right in zip(ids, ids[1:]):
                if not _reachable(left, right, edges):
                    errors.append(_issue("unordered_surface_overlap", left, surface=surface, right=right))
            for (left_id, left_t), (right_id, right_t) in zip(transforms, transforms[1:]):
                if _reachable(left_id, right_id, edges) and left_t["output_identity"] != right_t["input_identity"]:
                    errors.append(_issue(
                        "stale_preimage",
                        right_id,
                        surface=surface,
                        predecessor=left_id,
                        expected_input=left_t["output_identity"],
                        actual_input=right_t["input_identity"],
                    ))

    discovery = _validate_discovery_schema(manifest.get("discovery"), errors)
    unregistered: list[str] = []
    if discovery is not None:
        found, unsafe_discovery = _discover(root, discovery)
        for path in sorted(unsafe_discovery):
            errors.append(_issue("unsafe_discovery_path", path=path))
        for path in sorted(set(entrypoint_owner) - found):
            errors.append(_issue("registered_entrypoint_not_discovered", path=path))
        unregistered = sorted(found - set(entrypoint_owner))
        for path in unregistered:
            errors.append(_issue("unregistered_entrypoint", path=path))

    return {
        "ok": not errors,
        "plan": plan if not cyclic else [],
        "blocked": sorted(blocked),
        "evidence_only": sorted(evidence_only),
        "unregistered": unregistered,
        "errors": _stable_issues(errors),
        "warnings": _stable_issues(warnings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(Path(__file__).with_name("COMPOSITION.json")))
    parser.add_argument("--root", default=str(Path(__file__).parent))
    parser.add_argument("--json", action="store_true", help="emit one deterministic JSON object")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    root = Path(args.root)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result = {
            "ok": False,
            "plan": [],
            "blocked": [],
            "evidence_only": [],
            "unregistered": [],
            "errors": [_issue("manifest_load_error", error=str(exc))],
            "warnings": [],
        }
    else:
        result = validate_manifest(manifest, root)

    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print("OK" if result["ok"] else "FAIL")
        print("plan:", " -> ".join(result["plan"]) or "(empty)")
        for key in ("blocked", "evidence_only", "unregistered"):
            print(f"{key}:", ", ".join(result[key]) or "(none)")
        for kind in ("errors", "warnings"):
            for item in result[kind]:
                print(f"{kind[:-1].upper()} {json.dumps(item, sort_keys=True)}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
