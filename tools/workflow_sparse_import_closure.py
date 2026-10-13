#!/usr/bin/env python3
"""Compile Python import closure against GitHub Actions sparse checkouts.

The auditor parses workflow and Python bytes as data. It never imports or executes
repository code. PASS means every mechanically resolved repository-local Python
file for a discovered entrypoint is selected by the literal sparse checkout.
Unsupported workflow selection or dynamic import construction is truth-labelled
UNKNOWN rather than silently accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Sequence

# Make direct ``python tools/...`` and import-by-path use the same sibling modules.
_REPOSITORY = Path(__file__).resolve().parents[1]
if str(_REPOSITORY) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY))

from tools.workflow_sparse_import_closure_common import (
    CONFIG_SCHEMA, SCHEMA, ContractError, _finding_key, _status,
)
from tools.workflow_sparse_import_closure_python import compile_entry_closure
from tools.workflow_sparse_import_closure_workflow import (
    _selected, extract_entries, normalize_patterns, parse_workflow_bytes,
)


def audit_workflow(root: Path, workflow: Path) -> dict[str, object]:
    rel_workflow = workflow.relative_to(root).as_posix()
    try:
        jobs = parse_workflow_bytes(workflow.read_text(encoding="utf-8"), rel_workflow)
    except (OSError, UnicodeError, ContractError) as exc:
        return {
            "path": rel_workflow,
            "jobs": [],
            "findings": [{"code": "WORKFLOW_PARSE_ERROR", "detail": str(exc)}],
            "status": "FAIL",
        }
    job_rows: list[dict[str, object]] = []
    workflow_findings: list[dict[str, object]] = []
    for job in jobs:
        active_patterns: list[str] | None = None
        pattern_findings: list[dict[str, object]] = []
        has_checkout = False
        step_rows: list[dict[str, object]] = []
        for step in job.steps:
            if step.uses and step.uses.lower().startswith("actions/checkout@"):
                has_checkout = True
                if step.sparse_checkout is None:
                    active_patterns = None  # full checkout
                    pattern_findings = []
                elif not step.sparse_literal:
                    active_patterns = []
                    pattern_findings = [{
                        "code": "UNSUPPORTED_SPARSE_VALUE",
                        "value": list(step.sparse_checkout),
                    }]
                else:
                    active_patterns, pattern_findings = normalize_patterns(step.sparse_checkout)
                continue
            if not step.run:
                continue
            entries, command_findings = extract_entries(step.run)
            if not entries and not command_findings:
                continue
            if not has_checkout or active_patterns is None:
                step_rows.append({
                    "number": step.number,
                    "name": step.name,
                    "coverage": "FULL_OR_EXTERNAL",
                    "entries": [],
                    "findings": sorted(command_findings, key=_finding_key),
                    "status": "UNKNOWN" if command_findings else "SKIP",
                })
                continue
            compiled = [compile_entry_closure(root, entry) for entry in entries]
            findings = list(pattern_findings) + list(command_findings)
            if not pattern_findings:
                for entry_row in compiled:
                    for file in entry_row["files"]:
                        if not _selected(root, file, active_patterns):
                            findings.append({
                                "code": "MISSING_FROM_SPARSE_CHECKOUT",
                                "source": file,
                                "target": entry_row["target"],
                                "chain": entry_row["chains"].get(
                                    file, [entry_row["target"], file]
                                ),
                            })
            entry_status = _status(row["status"] for row in compiled) if compiled else "PASS"
            if any(f["code"] == "MISSING_FROM_SPARSE_CHECKOUT" for f in findings):
                step_status = "FAIL"
            elif pattern_findings or command_findings:
                step_status = _status([entry_status, "UNKNOWN"])
            else:
                step_status = entry_status
            step_rows.append({
                "number": step.number,
                "name": step.name,
                "coverage": "SPARSE",
                "patterns": list(active_patterns),
                "entries": compiled,
                "findings": sorted(findings, key=_finding_key),
                "status": step_status,
            })
        job_status = _status(row["status"] for row in step_rows) if step_rows else "SKIP"
        job_rows.append({"id": job.name, "steps": step_rows, "status": job_status})
    workflow_status = _status(row["status"] for row in job_rows) if job_rows else "SKIP"
    return {
        "path": rel_workflow,
        "jobs": sorted(job_rows, key=lambda row: row["id"]),
        "findings": sorted(workflow_findings, key=_finding_key),
        "status": workflow_status,
    }

def _config_workflows(root: Path, config: Path | None) -> list[Path]:
    if config is None:
        directory = root / ".github" / "workflows"
        return sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    try:
        value = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read config: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != CONFIG_SCHEMA:
        raise ContractError("config schema mismatch")
    rows = value.get("workflows")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, str) and row for row in rows):
        raise ContractError("config workflows must be a non-empty string list")
    if len(set(rows)) != len(rows):
        raise ContractError("config workflows contain duplicates")
    result: list[Path] = []
    for row in rows:
        pure = PurePosixPath(row)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ContractError(f"invalid workflow path: {row}")
        path = (root / Path(*pure.parts)).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ContractError(f"workflow path is missing: {row}")
        result.append(path)
    return sorted(result)

def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def audit_repository(root: Path, config: Path | None = None) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise ContractError(f"repository root is not a directory: {root}")
    workflows = [audit_workflow(root, path) for path in _config_workflows(root, config)]
    status = _status(row["status"] for row in workflows) if workflows else "SKIP"
    counts = {key: 0 for key in ("PASS", "FAIL", "UNKNOWN", "SKIP")}
    for row in workflows:
        counts[row["status"]] += 1
    report: dict[str, object] = {
        "schema": SCHEMA,
        "status": status,
        "summary": counts,
        "workflows": sorted(workflows, key=lambda row: row["path"]),
    }
    report["receipt_sha256"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    return report

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--workflow", action="append", default=[])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.workflow and args.config:
            raise ContractError("--workflow and --config are mutually exclusive")
        if args.workflow:
            transient = {
                "schema": CONFIG_SCHEMA,
                "workflows": args.workflow,
            }
            # No temporary repository mutation: execute the same contract directly.
            workflows = []
            for row in transient["workflows"]:
                path = (args.root.resolve() / row).resolve()
                if not path.is_relative_to(args.root.resolve()) or not path.is_file():
                    raise ContractError(f"workflow path is missing: {row}")
                workflows.append(audit_workflow(args.root.resolve(), path))
            status = _status(row["status"] for row in workflows) if workflows else "SKIP"
            counts = {key: 0 for key in ("PASS", "FAIL", "UNKNOWN", "SKIP")}
            for row in workflows:
                counts[row["status"]] += 1
            report = {
                "schema": SCHEMA,
                "status": status,
                "summary": counts,
                "workflows": sorted(workflows, key=lambda row: row["path"]),
            }
            report["receipt_sha256"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
        else:
            report = audit_repository(args.root, args.config)
    except ContractError as exc:
        print(f"workflow-sparse-import-closure: {exc}", file=sys.stderr)
        return 2
    data = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data, encoding="utf-8")
    else:
        sys.stdout.write(data)
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
