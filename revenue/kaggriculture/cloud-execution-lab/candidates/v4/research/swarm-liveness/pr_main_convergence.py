#!/usr/bin/env python3
"""Deterministic, read-only PR-to-main convergence classifier for TITAN V4.

Consumes normalized evidence exported by a live connector. It has no GitHub
credentials and never authorizes merge/close actions.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
CLASS_EXACT = "EXACT_ALREADY_ON_MAIN"
CLASS_PARTIAL = "PARTIAL_OVERLAP_REVIEW"
CLASS_UNIQUE = "UNIQUE_DELTA"
CLASS_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
_BLOB_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class EvidenceError(ValueError):
    pass


def _require_dict(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{where} must be an object")
    return value


def _canonical_path(path: Any, where: str) -> str:
    if not isinstance(path, str) or not path:
        raise EvidenceError(f"{where} path must be a non-empty string")
    if "\\" in path or path.startswith("/"):
        raise EvidenceError(f"{where} path must be repository-relative POSIX")
    pure = PurePosixPath(path)
    if any(part in ("", ".", "..") for part in pure.parts):
        raise EvidenceError(f"{where} path is not canonical: {path!r}")
    normalized = posixpath.normpath(path)
    if normalized != path or normalized == "." or normalized.startswith("../"):
        raise EvidenceError(f"{where} path is not canonical: {path!r}")
    return path


def _blob(value: Any, where: str, *, allow_absent: bool) -> str | None:
    if value is None and allow_absent:
        return None
    if not isinstance(value, str) or not _BLOB_RE.fullmatch(value):
        suffix = " or null" if allow_absent else ""
        raise EvidenceError(f"{where} blob must be lowercase 40/64 hex{suffix}")
    return value


def _file_map(value: Any, where: str, *, allow_absent: bool) -> dict[str, str | None]:
    raw = _require_dict(value, where)
    out: dict[str, str | None] = {}
    for raw_path, raw_blob in raw.items():
        path = _canonical_path(raw_path, where)
        if path in out:
            raise EvidenceError(f"duplicate {where} path: {path}")
        out[path] = _blob(raw_blob, f"{where}[{path}]", allow_absent=allow_absent)
    return out


def _exact_signature(files: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(files.items()))


def _classify(files: dict[str, str], main_files: dict[str, str | None]) -> tuple[str, str, dict[str, int]]:
    if not files:
        return CLASS_INSUFFICIENT, "PR_FILE_MAP_EMPTY", {"same": 0, "different": 0, "absent": 0, "uncovered": 0}
    same = different = absent = uncovered = 0
    for path, blob in files.items():
        if path not in main_files:
            uncovered += 1
        elif main_files[path] is None:
            absent += 1
        elif main_files[path] == blob:
            same += 1
        else:
            different += 1
    counts = {"same": same, "different": different, "absent": absent, "uncovered": uncovered}
    if uncovered:
        return CLASS_INSUFFICIENT, "MAIN_COVERAGE_INCOMPLETE", counts
    if same == len(files):
        return CLASS_EXACT, "ALL_PR_POSTIMAGE_BLOBS_MATCH_MAIN", counts
    if absent == len(files):
        return CLASS_UNIQUE, "ALL_PR_PATHS_VERIFIED_ABSENT_ON_MAIN", counts
    return CLASS_PARTIAL, "MIXED_OR_CONFLICTING_MAIN_POSTIMAGE", counts


def audit(document: dict[str, Any]) -> dict[str, Any]:
    doc = _require_dict(document, "document")
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError(f"schema_version must be {SCHEMA_VERSION}")
    canonical_base = doc.get("canonical_base", "main")
    if not isinstance(canonical_base, str) or not canonical_base:
        raise EvidenceError("canonical_base must be a non-empty string")

    main = _require_dict(doc.get("main"), "main")
    main_ref = main.get("ref")
    if not isinstance(main_ref, str) or not main_ref:
        raise EvidenceError("main.ref must be a non-empty string")
    main_files = _file_map(main.get("files"), "main.files", allow_absent=True)

    raw_prs = doc.get("prs")
    if not isinstance(raw_prs, list):
        raise EvidenceError("prs must be an array")

    seen_numbers: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for idx, raw_pr in enumerate(raw_prs):
        pr = _require_dict(raw_pr, f"prs[{idx}]")
        number = pr.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise EvidenceError(f"prs[{idx}].number must be a positive integer")
        if number in seen_numbers:
            raise EvidenceError(f"duplicate PR number: {number}")
        seen_numbers.add(number)
        state = pr.get("state")
        if state not in ("open", "closed"):
            raise EvidenceError(f"prs[{idx}].state must be open or closed")
        base = pr.get("base")
        if not isinstance(base, str) or not base:
            raise EvidenceError(f"prs[{idx}].base must be a non-empty string")
        head = pr.get("head")
        if not isinstance(head, str) or not head:
            raise EvidenceError(f"prs[{idx}].head must be a non-empty string")
        files_raw = _file_map(pr.get("files"), f"prs[{idx}].files", allow_absent=False)
        files = {path: blob for path, blob in files_raw.items() if blob is not None}
        intent = pr.get("intent")
        if intent is not None and (not isinstance(intent, str) or not intent.strip()):
            raise EvidenceError(f"prs[{idx}].intent must be a non-empty string when supplied")
        classification, reason, counts = _classify(files, main_files)
        if base != canonical_base:
            classification = CLASS_INSUFFICIENT
            reason = "NONCANONICAL_BASE"
        normalized.append({
            "number": number,
            "state": state,
            "base": base,
            "head": head,
            "intent": intent.strip() if isinstance(intent, str) else None,
            "files": files,
            "classification": classification,
            "reason": reason,
            "counts": counts,
        })

    duplicate_buckets: dict[tuple[tuple[str, str], ...], list[int]] = defaultdict(list)
    intent_buckets: dict[str, list[int]] = defaultdict(list)
    sig_by_number: dict[int, tuple[tuple[str, str], ...]] = {}
    for pr in normalized:
        if pr["state"] != "open" or pr["base"] != canonical_base or not pr["files"]:
            continue
        sig = _exact_signature(pr["files"])
        sig_by_number[pr["number"]] = sig
        duplicate_buckets[sig].append(pr["number"])
        if pr["intent"]:
            intent_buckets[pr["intent"]].append(pr["number"])

    exact_duplicate_groups = [
        {"prs": sorted(numbers), "basis": "IDENTICAL_PATH_BLOB_POSTIMAGE"}
        for _, numbers in sorted(duplicate_buckets.items(), key=lambda item: min(item[1]))
        if len(numbers) > 1
    ]

    intent_overlap_reviews = []
    for intent, numbers in sorted(intent_buckets.items()):
        if len(numbers) < 2:
            continue
        signatures = {sig_by_number[n] for n in numbers}
        if len(signatures) > 1:
            intent_overlap_reviews.append({
                "intent": intent,
                "prs": sorted(numbers),
                "basis": "SAME_DECLARED_INTENT_DIFFERENT_POSTIMAGE",
            })

    rows = []
    for pr in sorted(normalized, key=lambda row: row["number"]):
        rows.append({
            "number": pr["number"],
            "state": pr["state"],
            "base": pr["base"],
            "head": pr["head"],
            "intent": pr["intent"],
            "classification": pr["classification"],
            "reason": pr["reason"],
            "counts": pr["counts"],
        })

    summary = {key: 0 for key in (CLASS_EXACT, CLASS_PARTIAL, CLASS_UNIQUE, CLASS_INSUFFICIENT)}
    for row in rows:
        summary[row["classification"]] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "canonical_base": canonical_base,
        "main_ref": main_ref,
        "policy": {
            "read_only": True,
            "decision_authority": False,
            "auto_close": False,
            "auto_merge": False,
            "requires_live_reverification_before_write": True,
        },
        "prs": rows,
        "exact_duplicate_groups": exact_duplicate_groups,
        "intent_overlap_reviews": intent_overlap_reviews,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", default="-", help="JSON evidence file, or - for stdin")
    args = parser.parse_args(argv)
    try:
        if args.evidence == "-":
            document = json.load(sys.stdin)
        else:
            with open(args.evidence, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        result = audit(document)
    except (OSError, json.JSONDecodeError, EvidenceError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
