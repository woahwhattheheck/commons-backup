#!/usr/bin/env python3
"""Compile a deterministic, fail-closed Commons tool-consumption index.

The catalog names capacity. ``share.json`` records demand and receipts.  This
projection keeps those facts separate: an open job is allocatable only when it
names a tool in the current catalog, and completed work counts as consumed only
when it names a current tool and carries a receipt. Blank or unknown tool IDs
remain visible but never inflate tool capacity or consumption.
Catalog tools without a receipted done job are unobserved in these source inputs,
not unused: work performed elsewhere or without a receipt is outside this view.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "commons-tool-consumption-index/v1"
SOURCE_PATHS = ("skills.json", "commands.json", "tools.json", "share.json")


class ToolConsumptionError(ValueError):
    """A catalog, job, or checked projection is internally inconsistent."""


def canonical_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ToolConsumptionError(message)


def _text(value: object) -> str:
    return str(value or "").strip()


def _records(document: object, key: str, source: str) -> list[dict[str, Any]]:
    _require(isinstance(document, dict), f"{source} must be an object")
    rows = document.get(key)
    _require(isinstance(rows, list), f"{source}.{key} must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        _require(isinstance(row, dict), f"{source}.{key}[{index}] must be an object")
        row_id = _text(row.get("id"))
        _require(bool(row_id), f"{source}.{key}[{index}].id must be nonempty")
        _require(row_id not in seen, f"{source}.{key} contains duplicate id {row_id!r}")
        seen.add(row_id)
        normalized.append(dict(row))
    return normalized


def git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _classify_jobs(
    rows: Iterable[dict[str, Any]],
    *,
    section: str,
    tool_ids: set[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    projected: list[dict[str, Any]] = []
    counts = {
        "total": 0,
        "blank_tool": 0,
        "known_tool": 0,
        "unknown_tool": 0,
        "with_receipt": 0,
        "allocatable": 0,
        "receipted_consumption": 0,
    }
    for row in rows:
        job_id = _text(row.get("id"))
        tool_id = _text(row.get("tool"))
        receipt = _text(row.get("receipt"))
        status = _text(row.get("status"))
        if not tool_id:
            binding = "BLANK_TOOL"
            counts["blank_tool"] += 1
        elif tool_id in tool_ids:
            binding = "KNOWN_TOOL"
            counts["known_tool"] += 1
        else:
            binding = "UNKNOWN_TOOL"
            counts["unknown_tool"] += 1
        allocatable = section == "open" and binding == "KNOWN_TOOL"
        consumed = section == "done" and binding == "KNOWN_TOOL" and bool(receipt)
        counts["total"] += 1
        counts["with_receipt"] += int(bool(receipt))
        counts["allocatable"] += int(allocatable)
        counts["receipted_consumption"] += int(consumed)
        projected.append(
            {
                "id": job_id,
                "from": _text(row.get("from")),
                "ts": _text(row.get("ts")),
                "tool": tool_id,
                "op": _text(row.get("op")),
                "organ": _text(row.get("organ")),
                "status": status,
                "binding": binding,
                "allocation": "ALLOCATABLE" if allocatable else "EXCLUDED",
                "consumption": "RECEIPTED" if consumed else "NOT_COUNTED",
                "receipt": receipt,
            }
        )
    projected.sort(key=lambda row: (row["id"], row["tool"], row["status"]))
    return projected, counts


def build_index(
    *,
    skills: object,
    commands: object,
    tools: object,
    share: object,
    source_commit: str,
    source_blobs: dict[str, str],
) -> dict[str, Any]:
    source_commit = _text(source_commit).lower()
    _require(len(source_commit) == 40 and all(ch in "0123456789abcdef" for ch in source_commit),
             "source_commit must be a 40-character Git SHA")
    _require(set(source_blobs) == set(SOURCE_PATHS), "source_blobs must name exactly the four source files")
    for path, oid in source_blobs.items():
        _require(len(oid) == 40 and all(ch in "0123456789abcdef" for ch in oid),
                 f"source blob for {path} must be a 40-character Git SHA")

    skill_rows = _records(skills, "skills", "skills.json")
    command_rows = _records(commands, "commands", "commands.json")
    tool_rows = _records(tools, "tools", "tools.json")
    tool_ids = {_text(row["id"]) for row in tool_rows}
    _require("open" in share and "done" in share and "refused" in share,
             "share.json must contain open, done, and refused")

    sections: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, dict[str, int]] = {}
    all_job_ids: set[str] = set()
    for section in ("open", "done", "refused"):
        rows = _records(share, section, "share.json")
        overlap = all_job_ids.intersection(_text(row["id"]) for row in rows)
        if overlap:
            raise ToolConsumptionError(
                f"share.json job id appears in multiple sections: {sorted(overlap)[0]!r}"
            )
        all_job_ids.update(_text(row["id"]) for row in rows)
        sections[section], summaries[section] = _classify_jobs(rows, section=section, tool_ids=tool_ids)

    allocatable = [row for row in sections["open"] if row["allocation"] == "ALLOCATABLE"]
    consumed = [row for row in sections["done"] if row["consumption"] == "RECEIPTED"]
    observed_tool_ids = {row["tool"] for row in consumed}
    return {
        "schema": SCHEMA,
        "source_commit": source_commit,
        "source_blobs": {path: source_blobs[path] for path in sorted(source_blobs)},
        "catalog": {
            "skills": len(skill_rows),
            "commands": len(command_rows),
            "tools": len(tool_rows),
            "tool_ids": sorted(tool_ids),
        },
        "summary": {
            "jobs_total": sum(row["total"] for row in summaries.values()),
            "open_jobs": summaries["open"]["total"],
            "open_blank_tool": summaries["open"]["blank_tool"],
            "open_unknown_tool": summaries["open"]["unknown_tool"],
            "open_allocatable": summaries["open"]["allocatable"],
            "done_jobs": summaries["done"]["total"],
            "done_receipted_known_tool": summaries["done"]["receipted_consumption"],
            "refused_jobs": summaries["refused"]["total"],
        },
        "truth": {
            "named_catalog_entry_is_capacity_not_consumption": True,
            "blank_or_unknown_tool_is_not_allocatable": True,
            "consumption_requires_known_tool_and_receipt": True,
            "unobserved_is_not_unused": True,
            "missing_receipt_is_not_evidence_of_non_use": True,
            "jobs_mutated": 0,
            "tools_invoked": 0,
        },
        "allocatable_open_jobs": allocatable,
        "receipted_consumption": consumed,
        "unobserved_tool_ids": sorted(tool_ids - observed_tool_ids),
        "jobs": sections,
    }


def scan(root: Path, source_commit: str) -> dict[str, Any]:
    documents: dict[str, object] = {}
    blobs: dict[str, str] = {}
    for path in SOURCE_PATHS:
        raw = (root / path).read_bytes()
        documents[path] = json.loads(raw)
        blobs[path] = git_blob_sha(raw)
    return build_index(
        skills=documents["skills.json"],
        commands=documents["commands.json"],
        tools=documents["tools.json"],
        share=documents["share.json"],
        source_commit=source_commit,
        source_blobs=blobs,
    )


def check_snapshot(root: Path, path: Path) -> dict[str, Any]:
    expected = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(expected, dict), f"{path} must be a JSON object")
    _require(expected.get("schema") == SCHEMA, f"{path} is not {SCHEMA}")
    actual = scan(root, _text(expected.get("source_commit")))
    if actual != expected:
        raise ToolConsumptionError(f"{path} differs from its exact source inputs")
    return actual


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--source-commit", help="exact source commit for a new projection")
    parser.add_argument("--check", type=Path, help="verify an existing projection")
    parser.add_argument("--output", type=Path, help="write instead of stdout")
    return parser


def write_output(path: Path, text: str) -> None:
    # Follow output links as write_text did, then publish complete regular files.
    try:
        path = path.resolve()
    except RuntimeError as exc:
        raise ToolConsumptionError("output path cannot be resolved") from exc
    try:
        existing = path.stat()
    except FileNotFoundError:
        mode = None
    else:
        if not stat.S_ISREG(existing.st_mode):
            path.write_text(text, encoding="utf-8")
            return
        mode = stat.S_IMODE(existing.st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".tool-consumption-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            if mode is not None:
                os.chmod(temporary, mode)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.check:
            result = check_snapshot(args.root, args.check)
            summary = result["summary"]
            print(
                "MATCH "
                f"{summary['open_jobs']} open "
                f"{summary['open_allocatable']} allocatable "
                f"{summary['done_receipted_known_tool']} consumed"
            )
            return 0
        _require(bool(args.source_commit), "--source-commit is required when creating a projection")
        result = scan(args.root, args.source_commit)
        rendered = canonical_text(result)
        if args.output:
            write_output(args.output, rendered)
        else:
            sys.stdout.write(rendered)
        return 0
    except (ToolConsumptionError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"tool-consumption-index: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
