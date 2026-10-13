#!/usr/bin/env python3
"""Verify the UIOWA-101 component catalog against checkout bytes.

The verifier is deliberately version-sensitive: a changed component blob is a
catalog refresh signal, not something to normalize away.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

VALID_STATUSES = {"working", "static", "template", "incomplete"}
VALID_BASES = {
    "source_contract",
    "checked_in_command_contract",
    "checked_in_fixture_contract",
    "provider_readback",
    "published_validation_receipt",
    "checked_in_readme_result",
    "checked_in_generated_artifact",
    "checked_in_contract",
    "checked_in_worked_example",
    "snapshot_gap",
}

def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()

def check_bound_file(repo_root: Path, spec: dict[str, Any], label: str, errors: list[str]) -> bytes | None:
    path = repo_root / spec["path"]
    if not path.is_file():
        errors.append(f"{label}: missing file {spec['path']}")
        return None
    data = path.read_bytes()
    actual = git_blob_sha(data)
    expected = spec.get("blob_sha")
    if actual != expected:
        errors.append(f"{label}: blob drift for {spec['path']}: expected {expected}, got {actual}")
    return data

def csv_data_rows(data: bytes) -> int:
    text = data.decode("utf-8-sig")
    return max(0, sum(1 for _ in csv.reader(text.splitlines())) - 1)

def verify(catalog: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    counts = {status: 0 for status in sorted(VALID_STATUSES)}
    marker_checks = 0
    bound_files = 0

    if catalog.get("schema") != "uiowa.component-entry-catalog.v1":
        errors.append("unexpected catalog schema")
    revision = str(catalog.get("snapshot", {}).get("revision", ""))
    if len(revision) != 40 or any(ch not in "0123456789abcdef" for ch in revision):
        errors.append("snapshot revision must be a lowercase 40-character SHA")

    entries = catalog.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("catalog must contain entries")
        entries = []

    for entry in entries:
        entry_id = str(entry.get("id", "")).strip()
        if not entry_id:
            errors.append("entry missing id")
            continue
        if entry_id in seen:
            errors.append(f"{entry_id}: duplicate id")
        seen.add(entry_id)

        status = entry.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{entry_id}: invalid status {status!r}")
            continue
        counts[status] += 1

        for required in ("title", "supported_input", "produced_output", "prerequisites", "sample_result"):
            if required not in entry:
                errors.append(f"{entry_id}: missing {required}")

        source = entry.get("source")
        if not isinstance(source, dict):
            errors.append(f"{entry_id}: missing source binding")
            source_data = None
        else:
            source_data = check_bound_file(repo_root, source, f"{entry_id}.source", errors)
            if source_data is not None:
                bound_files += 1

        readme = entry.get("readme")
        if isinstance(readme, dict):
            if check_bound_file(repo_root, readme, f"{entry_id}.readme", errors) is not None:
                bound_files += 1

        sample = entry.get("sample_result")
        if not isinstance(sample, dict):
            errors.append(f"{entry_id}: sample_result must be an object")
        else:
            basis = sample.get("basis")
            if basis not in VALID_BASES:
                errors.append(f"{entry_id}: invalid sample basis {basis!r}")
            if not str(sample.get("summary", "")).strip():
                errors.append(f"{entry_id}: sample result needs a summary")
            evidence_path = sample.get("evidence_path")
            evidence_sha = sample.get("evidence_blob_sha")
            if evidence_path and evidence_sha:
                data = check_bound_file(
                    repo_root,
                    {"path": evidence_path, "blob_sha": evidence_sha},
                    f"{entry_id}.sample",
                    errors,
                )
                if data is not None:
                    bound_files += 1
                    expected_rows = sample.get("expected_data_rows")
                    if expected_rows is not None:
                        try:
                            actual_rows = csv_data_rows(data)
                        except Exception as exc:
                            errors.append(f"{entry_id}: cannot count sample CSV rows: {exc}")
                        else:
                            if actual_rows != expected_rows:
                                errors.append(
                                    f"{entry_id}: expected {expected_rows} sample data rows, got {actual_rows}"
                                )

        command = entry.get("command")
        if status == "working":
            if not isinstance(command, str) or not command.strip():
                errors.append(f"{entry_id}: working entry must advertise a command")
            if source_data is None:
                errors.append(f"{entry_id}: working entry has no readable source")
            else:
                text = source_data.decode("utf-8", errors="replace")
                for marker in entry.get("contract_markers", []):
                    marker_checks += 1
                    if marker not in text:
                        errors.append(f"{entry_id}: source contract marker not found: {marker!r}")
        elif status in {"static", "template"}:
            if command not in (None, ""):
                errors.append(f"{entry_id}: {status} entry must not advertise an executable command")
        elif status == "incomplete":
            expected = entry.get("expected_entrypoint")
            if not expected:
                errors.append(f"{entry_id}: incomplete entry must name expected_entrypoint")
            elif (repo_root / expected).exists():
                errors.append(
                    f"{entry_id}: expected entry point now exists; refresh status instead of leaving incomplete"
                )
            if not str(entry.get("missing_reason", "")).strip():
                errors.append(f"{entry_id}: incomplete entry must explain the gap")

        cwd = entry.get("command_cwd")
        if cwd is not None and not (repo_root / cwd).is_dir():
            errors.append(f"{entry_id}: command_cwd does not exist: {cwd}")

    return {
        "schema": "uiowa.component-entry-catalog.verify.v1",
        "snapshot_revision": revision,
        "entry_count": len(entries),
        "status_counts": counts,
        "bound_files_checked": bound_files,
        "contract_markers_checked": marker_checks,
        "errors": errors,
        "warnings": warnings,
        "status": "PASS" if not errors else "FAIL",
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).with_name("component_catalog.json"))
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    repo_root = args.repo_root or Path(__file__).resolve().parents[2]
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    report = verify(catalog, repo_root.resolve())

    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status']} entries={report['entry_count']} "
            f"working={report['status_counts']['working']} static={report['status_counts']['static']} "
            f"template={report['status_counts']['template']} incomplete={report['status_counts']['incomplete']} "
            f"bound_files={report['bound_files_checked']} markers={report['contract_markers_checked']}"
        )
        for error in report["errors"]:
            print(f"ERROR: {error}")
        for warning in report["warnings"]:
            print(f"WARNING: {warning}")
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
