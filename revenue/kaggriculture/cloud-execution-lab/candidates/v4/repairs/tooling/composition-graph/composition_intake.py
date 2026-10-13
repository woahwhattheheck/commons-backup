#!/usr/bin/env python3
"""Read-only intake census from TITAN V4 INTEGRATION into the sole COMPOSITION graph.

This module never edits either ledger and never infers transform identities or ordering.
It only makes graph coverage gaps mechanically visible to the existing LOOM/native assembler.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

INTEGRATION_SCHEMA = "titan-v4-integration-ledger/v1"
COMPOSITION_SCHEMA = "titan-v4-composition/v1"
OUTPUT_SCHEMA = "titan-v4-composition-intake/v1"
ALLOWED_GRAPH_STATES = {"compose", "blocked", "evidence_only"}

# Deliberately conservative: these names strongly imply source-to-source/package materialization.
# Ordinary policy helpers, runners, tests, or research analyzers are not auto-classified as transforms.
TRANSFORM_NAME_PATTERNS = (
    re.compile(r"^compose(?:_|\.).*\.py$"),
    re.compile(r"^materialize(?:_|\.).*\.py$"),
    re.compile(r"^port_current.*\.py$"),
    re.compile(r"^build_native.*\.py$"),
    re.compile(r"^rebase_current.*\.py$"),
)


class StrictJSONError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise StrictJSONError(f"non-finite JSON constant: {value}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise StrictJSONError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StrictJSONError(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, StrictJSONError) as exc:
        raise StrictJSONError(f"invalid strict JSON in {path}: {exc}") from exc


def _safe_relpath(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and "." not in path.parts and ".." not in path.parts


def _inside(root: Path, rel: str) -> tuple[Path | None, str | None]:
    if not _safe_relpath(rel):
        return None, "unsafe_path"
    candidate = root / PurePosixPath(rel)
    try:
        root_real = root.resolve()
        if candidate.is_symlink():
            return None, "symlink"
        resolved = candidate.resolve()
        resolved.relative_to(root_real)
    except (OSError, RuntimeError, ValueError):
        return None, "path_escape"
    if not resolved.exists():
        return None, "missing"
    return resolved, None


def _is_under(rel: str, package: str) -> bool:
    if not (_safe_relpath(rel) and _safe_relpath(package)):
        return False
    rel_parts = PurePosixPath(rel).parts
    package_parts = PurePosixPath(package).parts
    return len(rel_parts) > len(package_parts) and rel_parts[: len(package_parts)] == package_parts


def _looks_like_transform(path: Path) -> bool:
    name = path.name
    return any(pattern.match(name) for pattern in TRANSFORM_NAME_PATTERNS)


def _discover_transform_candidates(root: Path, repair_path: str) -> tuple[list[str], list[dict[str, Any]]]:
    base, problem = _inside(root, repair_path)
    if problem is not None:
        return [], [{"code": "repair_path_unusable", "path": repair_path, "reason": problem}]
    assert base is not None
    if not base.is_dir():
        return [], [{"code": "repair_path_not_directory", "path": repair_path}]

    found: list[str] = []
    errors: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*.py")):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            errors.append({"code": "discovery_escape", "path": str(path)})
            continue
        if path.is_symlink():
            errors.append({"code": "discovery_symlink", "path": rel})
            continue
        resolved, issue = _inside(root, rel)
        if issue is not None or resolved is None or not resolved.is_file():
            errors.append({"code": "discovery_unusable", "path": rel, "reason": issue or "not_file"})
            continue
        if _looks_like_transform(path):
            found.append(rel)
    return found, errors


def _component_matches_package(component: dict[str, Any], repair_path: str) -> bool:
    package = component.get("package")
    if package == repair_path:
        return True
    entrypoints = component.get("entrypoints", [])
    if not isinstance(entrypoints, list):
        return False
    # A broad graph package (e.g. repairs/performance) only covers a narrower ledger package
    # when a declared graph entrypoint actually lives under that exact ledger package.
    return any(isinstance(ep, str) and _is_under(ep, repair_path) for ep in entrypoints)


def _stable(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))


def _row_lane(row: dict[str, Any], index: int) -> str:
    lane = row.get("lane")
    return lane if isinstance(lane, str) and lane.strip() else f"<row:{index}>"


def census(integration: dict[str, Any], composition: dict[str, Any], root: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if integration.get("schema") != INTEGRATION_SCHEMA:
        errors.append({"code": "bad_integration_schema", "actual": integration.get("schema")})
    if composition.get("schema") != COMPOSITION_SCHEMA:
        errors.append({"code": "bad_composition_schema", "actual": composition.get("schema")})

    raw_rows = integration.get("landed")
    if not isinstance(raw_rows, list):
        errors.append({"code": "integration_landed_not_list"})
        raw_rows = []
    raw_components = composition.get("components")
    if not isinstance(raw_components, list):
        errors.append({"code": "composition_components_not_list"})
        raw_components = []

    components: list[dict[str, Any]] = []
    seen_component_ids: set[str] = set()
    for index, component in enumerate(raw_components):
        if not isinstance(component, dict):
            errors.append({"code": "component_not_object", "index": index})
            continue
        cid = component.get("id")
        state = component.get("state")
        package = component.get("package")
        if not isinstance(cid, str) or not cid:
            errors.append({"code": "bad_component_id", "index": index})
            continue
        if cid in seen_component_ids:
            errors.append({"code": "duplicate_component_id", "component": cid})
            continue
        seen_component_ids.add(cid)
        if state not in ALLOWED_GRAPH_STATES:
            errors.append({"code": "bad_component_state", "component": cid, "actual": state})
        if not _safe_relpath(package):
            errors.append({"code": "bad_component_package", "component": cid, "path": package})
        entrypoints = component.get("entrypoints", [])
        if not isinstance(entrypoints, list) or any(not _safe_relpath(ep) for ep in entrypoints):
            errors.append({"code": "bad_component_entrypoints", "component": cid})
        components.append(component)

    lane_seen: dict[str, int] = {}
    by_package: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    unroutable: list[dict[str, Any]] = []

    for index, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            errors.append({"code": "integration_row_not_object", "index": index})
            continue
        lane = _row_lane(row, index)
        if lane in lane_seen:
            errors.append({"code": "duplicate_lane", "lane": lane, "first_index": lane_seen[lane], "index": index})
        else:
            lane_seen[lane] = index
        repair_path = row.get("repair_path")
        if repair_path is None:
            unroutable.append({"index": index, "lane": lane, "reason": "repair_path_missing"})
            continue
        if not _safe_relpath(repair_path):
            errors.append({"code": "unsafe_repair_path", "index": index, "lane": lane, "path": repair_path})
            unroutable.append({"index": index, "lane": lane, "reason": "repair_path_unsafe"})
            continue
        by_package[repair_path].append((index, row))

    packages: list[dict[str, Any]] = []
    for repair_path in sorted(by_package):
        rows = by_package[repair_path]
        lanes = sorted(_row_lane(row, index) for index, row in rows)
        base, path_problem = _inside(root, repair_path)
        if path_problem is not None or base is None or not base.is_dir():
            errors.append({
                "code": "repair_package_unusable",
                "path": repair_path,
                "reason": path_problem or "not_directory",
                "lanes": lanes,
            })
            candidate_entrypoints: list[str] = []
            discovery_errors: list[dict[str, Any]] = []
        else:
            candidate_entrypoints, discovery_errors = _discover_transform_candidates(root, repair_path)
            errors.extend({**item, "lanes": lanes} for item in discovery_errors)

        matches = [component for component in components if _component_matches_package(component, repair_path)]
        matched = sorted(
            (
                {
                    "id": component.get("id"),
                    "state": component.get("state"),
                    "package": component.get("package"),
                    "entrypoints": sorted(component.get("entrypoints", [])),
                }
                for component in matches
            ),
            key=lambda item: (str(item["id"]), str(item["state"])),
        )
        states = {item["state"] for item in matched}
        if "compose" in states:
            classification = "graph_covered"
        elif "blocked" in states:
            classification = "explicitly_blocked"
        elif "evidence_only" in states:
            classification = "evidence_only"
        elif candidate_entrypoints:
            classification = "unregistered_transform_candidate"
        else:
            classification = "source_only_no_transform"

        if len(rows) > 1:
            warnings.append({"code": "shared_repair_package", "path": repair_path, "lanes": lanes})

        packages.append({
            "repair_path": repair_path,
            "lanes": lanes,
            "classification": classification,
            "candidate_entrypoints": candidate_entrypoints,
            "composition": matched,
        })

    counts = defaultdict(int)
    for package in packages:
        counts[package["classification"]] += 1
    counts["unroutable_rows"] = len(unroutable)
    counts["repair_packages"] = len(packages)
    counts["integration_rows"] = len(raw_rows)

    queue = [
        {
            "repair_path": package["repair_path"],
            "lanes": package["lanes"],
            "candidate_entrypoints": package["candidate_entrypoints"],
            "disposition": "LOOM_REVIEW_REQUIRED",
        }
        for package in packages
        if package["classification"] == "unregistered_transform_candidate"
    ]

    return {
        "schema": OUTPUT_SCHEMA,
        "ok": not errors,
        "authority": "read_only_intake_census_no_composition_or_promotion_authority",
        "counts": {key: counts[key] for key in sorted(counts)},
        "packages": packages,
        "queue": queue,
        "unroutable_rows": sorted(unroutable, key=lambda item: (item["index"], item["lane"])),
        "errors": _stable(errors),
        "warnings": _stable(warnings),
    }


def run(root: Path, integration_path: Path | None = None, composition_path: Path | None = None) -> dict[str, Any]:
    integration_path = integration_path or (root / "INTEGRATION.json")
    composition_path = composition_path or (root / "COMPOSITION.json")
    try:
        integration = load_json_strict(integration_path)
        composition = load_json_strict(composition_path)
    except StrictJSONError as exc:
        return {
            "schema": OUTPUT_SCHEMA,
            "ok": False,
            "authority": "read_only_intake_census_no_composition_or_promotion_authority",
            "counts": {},
            "packages": [],
            "queue": [],
            "unroutable_rows": [],
            "errors": [{"code": "ledger_load_error", "error": str(exc)}],
            "warnings": [],
        }
    if not isinstance(integration, dict) or not isinstance(composition, dict):
        return {
            "schema": OUTPUT_SCHEMA,
            "ok": False,
            "authority": "read_only_intake_census_no_composition_or_promotion_authority",
            "counts": {},
            "packages": [],
            "queue": [],
            "unroutable_rows": [],
            "errors": [{"code": "ledger_root_not_object"}],
            "warnings": [],
        }
    return census(integration, composition, root)


def main() -> int:
    default_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--integration", type=Path)
    parser.add_argument("--composition", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run(args.root, args.integration, args.composition)
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    else:
        print("OK" if result["ok"] else "FAIL")
        for key, value in sorted(result["counts"].items()):
            print(f"{key}: {value}")
        for item in result["queue"]:
            print(f"QUEUE {item['repair_path']} :: {','.join(item['candidate_entrypoints'])}")
        for item in result["unroutable_rows"]:
            print(f"UNROUTABLE {item['lane']} :: {item['reason']}")
        for kind in ("errors", "warnings"):
            for item in result[kind]:
                print(f"{kind[:-1].upper()} {json.dumps(item, sort_keys=True, allow_nan=False)}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
