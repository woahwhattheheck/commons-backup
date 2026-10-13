#!/usr/bin/env python3
"""Check exact PR root-tree metadata without checking out or executing PR code.

This produces a failing workflow step for catastrophic root loss; it is not
branch protection, a complete recursive diff, or authority to merge a PR.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Sequence

MAX_BYTES = 8 * 1024 * 1024
MAX_ROOTS = 100_000
SHA = re.compile(r"[0-9a-f]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
MODE_TYPE = {"040000": "tree", "100644": "blob", "100755": "blob",
             "120000": "blob", "160000": "commit"}


class EvidenceError(ValueError):
    """Missing, incomplete, malformed, or mismatched provider evidence."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{label}: expected object")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or not SHA.fullmatch(value):
        raise EvidenceError(f"{label}: expected lowercase 40-hex SHA")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("JSON: duplicate object key")
        result[key] = value
    return result


def _constant(_: str) -> Any:
    raise EvidenceError("JSON: nonfinite number")


def decode_json(raw: bytes) -> Any:
    if len(raw) > MAX_BYTES:
        raise EvidenceError("JSON: byte limit exceeded")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceError("JSON: malformed UTF-8 document") from exc


def _repository(value: Any) -> str:
    if (type(value) is not str or len(value) > 200 or not REPO.fullmatch(value)
            or any(part in {".", ".."} for part in value.split("/"))):
        raise EvidenceError("repository: expected owner/name")
    return value


def event_identity(event: Any, expected_repository: str | None = None
                   ) -> tuple[str, int, str, str]:
    row = _object(event, "event")
    repository = _repository(_object(row.get("repository"), "repository").get("full_name"))
    if expected_repository is not None and repository != _repository(expected_repository):
        raise EvidenceError("event: repository differs from workflow repository")
    pull = _object(row.get("pull_request"), "pull_request")
    number = pull.get("number")
    if type(number) is not int or not 1 <= number <= 2**53 - 1:
        raise EvidenceError("pull_request: invalid number")
    base = _sha(_object(pull.get("base"), "base").get("sha"), "base SHA")
    head = _sha(_object(pull.get("head"), "head").get("sha"), "head SHA")
    return repository, number, base, head


def commit_tree(payload: Any, expected_commit: str) -> str:
    row = _object(payload, "commit")
    if _sha(row.get("sha"), "commit SHA") != _sha(expected_commit, "requested commit"):
        raise EvidenceError("commit: response identity mismatch")
    return _sha(_object(row.get("tree"), "commit tree").get("sha"), "commit tree SHA")


def root_entries(payload: Any, expected_tree: str) -> dict[str, tuple[str, str, str]]:
    row = _object(payload, "tree")
    if _sha(row.get("sha"), "tree SHA") != _sha(expected_tree, "requested tree"):
        raise EvidenceError("tree: response identity mismatch")
    if row.get("truncated") is not False:
        raise EvidenceError("tree: complete nontruncated response required")
    entries = row.get("tree")
    if type(entries) is not list or len(entries) > MAX_ROOTS:
        raise EvidenceError("tree: invalid or oversized entry list")
    result: dict[str, tuple[str, str, str]] = {}
    for item in entries:
        entry = _object(item, "tree entry")
        path = entry.get("path")
        if (type(path) is not str or not path or path in {".", ".."}
                or "/" in path or "\x00" in path
                or any(0xD800 <= ord(char) <= 0xDFFF for char in path)):
            raise EvidenceError("tree: expected literal root component")
        if path in result:
            raise EvidenceError("tree: duplicate root component")
        mode, kind = entry.get("mode"), entry.get("type")
        if type(mode) is not str or type(kind) is not str or MODE_TYPE.get(mode) != kind:
            raise EvidenceError("tree: incompatible mode/type")
        result[path] = (mode, kind, _sha(entry.get("sha"), "entry SHA"))
    return result


def compare_roots(base_payload: Any, head_payload: Any,
                  base_tree: str, head_tree: str) -> dict[str, Any]:
    base = root_entries(base_payload, base_tree)
    head = root_entries(head_payload, head_tree)
    removed = sorted(base.keys() - head.keys())
    added = sorted(head.keys() - base.keys())
    replaced = sorted(path for path in base.keys() & head.keys()
                      if base[path][1] == "tree" and head[path][1] != "tree")
    reasons = []
    # Strictly greater than both thresholds; integer arithmetic avoids rounding.
    if len(base) >= 100 and len(removed) > 25 and len(removed) * 10 > len(base):
        reasons.append("CATASTROPHIC_ROOT_LOSS")
    if replaced:
        reasons.append("ROOT_DIRECTORY_REPLACED")
    return {
        "schema": "commons.pr-root-retention.v1",
        "status": "FAIL" if reasons else "PASS",
        "reasons": reasons,
        "base_tree_sha": base_tree, "head_tree_sha": head_tree,
        "base_root_count": len(base), "head_root_count": len(head),
        "removed_count": len(removed), "added_count": len(added),
        "directory_replacement_count": len(replaced),
        "removed_sample": removed[:25], "added_sample": added[:25],
        "directory_replacement_sample": replaced[:25],
        "merge_authorized": False, "branch_protection_modified": False,
        "scope": "EXACT_EVENT_NONRECURSIVE_ROOTS_ONLY",
    }


def evaluate(event: Any, get_json: Callable[[str], Any],
             expected_repository: str | None = None) -> dict[str, Any]:
    repository, number, base, head = event_identity(event, expected_repository)
    prefix = f"/repos/{repository}/git"
    # These are the only four provider reads. Never use mutable ref aliases,
    # PR-file truncation, recursive trees, content downloads, or head execution.
    base_tree = commit_tree(get_json(f"{prefix}/commits/{base}"), base)
    head_tree = commit_tree(get_json(f"{prefix}/commits/{head}"), head)
    base_payload = get_json(f"{prefix}/trees/{base_tree}")
    head_payload = get_json(f"{prefix}/trees/{head_tree}")
    report = compare_roots(base_payload, head_payload, base_tree, head_tree)
    report.update(repository=repository, pull_request=number,
                  base_commit_sha=base, head_commit_sha=head)
    return report


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        raise EvidenceError("provider: redirect refused")


class MetadataReader:
    """Bounded, GET-only public-GitHub metadata reader; no automatic retries."""
    def __init__(self, token: str = "") -> None:
        self._token = token
        self._opener = urllib.request.build_opener(_NoRedirect())

    def __call__(self, path: str) -> Any:
        if not re.fullmatch(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/git/"
                            r"(?:commits|trees)/[0-9a-f]{40}", path):
            raise EvidenceError("provider: invalid metadata path")
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "commons-pr-root-retention"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            request = urllib.request.Request("https://api.github.com" + path,
                                             method="GET", headers=headers)
            with self._opener.open(request, timeout=30) as response:
                if response.status != 200:
                    raise EvidenceError("provider: expected HTTP 200")
                raw = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise EvidenceError(f"provider: HTTP {exc.code}; retry in a later run") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if isinstance(exc, EvidenceError):
                raise
            raise EvidenceError("provider: metadata request failed") from None
        return decode_json(raw)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"))
    args = parser.parse_args(argv)
    try:
        if not args.event:
            raise EvidenceError("event: --event or GITHUB_EVENT_PATH is required")
        with Path(args.event).open("rb") as source:
            event = decode_json(source.read(MAX_BYTES + 1))
        report = evaluate(event, MetadataReader(os.environ.get("GITHUB_TOKEN", "")),
                          os.environ.get("GITHUB_REPOSITORY") or None)
    except (EvidenceError, OSError) as exc:
        # Never print the event, credentials, HTTP body, or arbitrary OS details.
        detail = str(exc) if isinstance(exc, EvidenceError) else "event: read failed"
        report = {"schema": "commons.pr-root-retention.v1", "status": "ERROR",
                  "reasons": ["EVIDENCE_UNAVAILABLE"], "detail": detail,
                  "merge_authorized": False, "branch_protection_modified": False}
    print(json.dumps(report, sort_keys=True, ensure_ascii=True, separators=(",", ":")))
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
