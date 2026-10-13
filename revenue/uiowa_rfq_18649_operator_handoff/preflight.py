#!/usr/bin/env python3
"""Preflight the UIOWA-100 operator handoff against a Commons checkout."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "operator_manifest.json"
ALLOWED_PHASES = {
    "kickoff",
    "evidence_collection",
    "analysis",
    "draft_review",
    "final_delivery",
    "optional_readout",
}
ALLOWED_STATUSES = {
    "working",
    "working_reference",
    "working_interactive",
    "working_optional_dependency",
    "working_synthetic_rehearsal",
    "pending_at_snapshot",
}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def repo_root_from(script: Path = Path(__file__).resolve()) -> Path:
    # .../commons/revenue/uiowa_rfq_18649_operator_handoff/preflight.py
    return script.parent.parent.parent


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return payload


def validate(
    manifest: dict[str, Any], root: Path, selected_assets: set[str] | None = None,
) -> dict[str, Any]:
    """Validate the catalog, checking source availability only within the chosen scope."""
    errors: list[str] = []
    warnings: list[str] = []
    selected = set(selected_assets or [])
    assets = manifest.get("assets")
    phases = manifest.get("phases")

    if manifest.get("schema") != "uiowa.operator-handoff.v1":
        errors.append("unsupported or missing manifest schema")
    if not isinstance(phases, list) or set(phases) != ALLOWED_PHASES:
        errors.append("phases must contain the six expected lifecycle phases exactly once")
    if not SHA40.match(str(manifest.get("snapshot_main_sha", ""))):
        errors.append("snapshot_main_sha must be a 40-character lowercase hex SHA")
    if not isinstance(assets, list) or not assets:
        errors.append("assets must be a non-empty array")
        assets = []

    ids: set[str] = set()
    phase_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    executable_assets = 0
    resolved_paths: list[str] = []

    root = root.resolve()
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            errors.append(f"asset[{index}] must be an object")
            continue
        asset_id = str(asset.get("asset_id", "")).strip()
        if not asset_id:
            errors.append(f"asset[{index}] missing asset_id")
        elif asset_id in ids:
            errors.append(f"duplicate asset_id: {asset_id}")
        else:
            ids.add(asset_id)
        check_files = not selected or asset_id in selected

        phase = str(asset.get("phase", ""))
        status = str(asset.get("status", ""))
        phase_counts[phase] += 1
        status_counts[status] += 1
        if phase not in ALLOWED_PHASES:
            errors.append(f"{asset_id or index}: unsupported phase {phase!r}")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{asset_id or index}: unsupported status {status!r}")

        for field in ("purpose", "operator_action", "authority_ceiling"):
            if not isinstance(asset.get(field), str) or not asset[field].strip():
                errors.append(f"{asset_id or index}: missing {field}")

        rel = str(asset.get("path", "")).strip()
        if status == "pending_at_snapshot":
            if rel and check_files:
                candidate = (root / rel).resolve()
                if candidate.exists():
                    warnings.append(
                        f"{asset_id}: pending-at-snapshot path now exists; refresh manifest before delivery"
                    )
            continue

        if not rel:
            errors.append(f"{asset_id or index}: non-pending asset has no path")
            continue
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"{asset_id}: path escapes repository root: {rel}")
            continue
        if check_files and not candidate.exists():
            errors.append(f"{asset_id}: path missing from checkout: {rel}")
        elif check_files:
            resolved_paths.append(rel)

        commands = asset.get("sample_commands") or []
        if commands:
            executable_assets += 1
            workdir_rel = str(asset.get("working_dir", "")).strip()
            if not workdir_rel:
                errors.append(f"{asset_id}: sample_commands require working_dir")
                continue
            workdir = (root / workdir_rel).resolve()
            try:
                workdir.relative_to(root)
            except ValueError:
                errors.append(f"{asset_id}: working_dir escapes repository root")
                continue
            if check_files and not workdir.is_dir():
                errors.append(f"{asset_id}: working_dir missing: {workdir_rel}")
                continue

            for command_index, command in enumerate(commands):
                if not isinstance(command, list) or not command:
                    errors.append(f"{asset_id}: command[{command_index}] must be a non-empty argv array")
                    continue
                if any(not isinstance(arg, str) or not arg for arg in command):
                    errors.append(f"{asset_id}: command[{command_index}] has an empty/non-string argv item")
                    continue
                script = (workdir / command[0]).resolve()
                try:
                    script.relative_to(root)
                except ValueError:
                    errors.append(f"{asset_id}: command[{command_index}] script escapes root")
                    continue
                if check_files and not script.is_file():
                    errors.append(
                        f"{asset_id}: command[{command_index}] script missing: "
                        f"{workdir_rel}/{command[0]}"
                    )

    unknown = selected - ids
    if unknown:
        errors.append(f"unknown --asset values: {sorted(unknown)}")
    if selected:
        warnings.append("Source availability was checked only for selected assets; this is not a full-catalog preflight.")

    missing_phases = sorted(ALLOWED_PHASES - set(phase_counts))
    if missing_phases:
        errors.append(f"no assets mapped to phases: {missing_phases}")

    required_inputs = manifest.get("required_university_inputs")
    if not isinstance(required_inputs, list) or not required_inputs:
        errors.append("required_university_inputs must be a non-empty array")

    return {
        "ok": not errors,
        "schema": manifest.get("schema"),
        "snapshot_main_sha": manifest.get("snapshot_main_sha"),
        "root": str(root),
        "filesystem_scope": "selected_assets" if selected else "full_catalog",
        "selected_assets": sorted(selected),
        "skipped_assets": sorted(ids - selected) if selected else [],
        "assets": len(assets),
        "executable_assets": executable_assets,
        "phase_counts": dict(sorted(phase_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "resolved_paths": len(resolved_paths),
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--asset", action="append", dest="assets",
                        help="Check source availability only for a named asset; repeat to select multiple.")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    root = (args.root or repo_root_from()).resolve()
    result = validate(manifest, root, set(args.assets or []) or None)
    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"UIOWA-100 preflight: {'PASS' if result['ok'] else 'FAIL'} "
            f"scope={result['filesystem_scope']} "
            f"assets={result['assets']} executable_assets={result['executable_assets']} "
            f"snapshot={result['snapshot_main_sha']}"
        )
        for warning in result["warnings"]:
            print(f"WARN: {warning}")
        for error in result["errors"]:
            print(f"ERROR: {error}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
