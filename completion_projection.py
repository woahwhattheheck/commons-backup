"""Stable completion markers for actionable UNSEATED board cards.

Durable p/{id}.md pages are history and are never rewritten when work finishes.
This module owns a separate, fail-closed projection input: a marker is valid only
when it binds an exact durable operation id, a canonical completed issue, and a
same-repository pull request merged to main that explicitly closes that issue.

The renderer may suppress only the actionable UNSEATED -> TABLE projection. A
missing, malformed, stale, or source-mismatched marker means "not proven done".
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCHEMA = "commons-completed-operation-v1"
STATE = "COMPLETED"
MARKER_DIR = "completion/operations"
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
MAX_MARKER_BYTES = 64 * 1024
CLOSING_RE_TEMPLATE = (
    r"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+"
    r"(?:#|woahwhattheheck/commons#|"
    r"https://github\.com/woahwhattheheck/commons/issues/)%s\b"
)


class CompletionEvidenceError(ValueError):
    """Completion evidence is absent, ambiguous, or not strong enough."""


def _timestamp(value: Any) -> datetime:
    """Validate an explicit timezone and compare instants, never string order."""
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise CompletionEvidenceError("invalid completion timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise CompletionEvidenceError("invalid completion timestamp") from exc


def parse_timestamp(value: Any) -> datetime:
    """Public instant parser for completion-event ordering."""
    return _timestamp(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in pairs:
        if key in row:
            raise CompletionEvidenceError("duplicate marker field")
        row[key] = value
    return row


def _reject_constant(value: str) -> None:
    raise CompletionEvidenceError("non-finite marker value: " + value)


def _read_marker(path: Path) -> Any:
    """One malformed record must not abort the entire live board projection."""
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_MARKER_BYTES + 1)
        if len(data) > MAX_MARKER_BYTES:
            return None
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None


def _clean_id(operation_id: str) -> str:
    value = str(operation_id or "").strip()
    if not ID_RE.fullmatch(value):
        raise CompletionEvidenceError("invalid operation id")
    return value


def _git_blob_sha1(data: bytes) -> str:
    header = ("blob %d\0" % len(data)).encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def source_rel(operation_id: str) -> str:
    return "p/%s.md" % _clean_id(operation_id)


def marker_rel(operation_id: str) -> str:
    return "%s/%s.json" % (MARKER_DIR, _clean_id(operation_id))


def _source_blob(root: str | os.PathLike[str], operation_id: str) -> tuple[str, str]:
    rel = source_rel(operation_id)
    path = Path(root) / rel
    if not path.is_file():
        raise CompletionEvidenceError("durable source is absent")
    return rel, _git_blob_sha1(path.read_bytes())


def source_paths(root: str | os.PathLike[str]) -> list[str]:
    base = Path(root) / MARKER_DIR
    if not base.is_dir():
        return []
    return [
        str(path.relative_to(root)).replace(os.sep, "/")
        for path in sorted(base.glob("*.json"))
        if path.is_file()
    ]


def stable_operation_id_from_issue(issue: dict[str, Any]) -> str:
    """Return one explicit stable id; conflicting or fuzzy identity returns empty."""
    if not isinstance(issue, dict):
        return ""
    candidates: set[str] = set()
    title = str(issue.get("title") or "").strip()
    if ID_RE.fullmatch(title):
        candidates.add(title)
    body = str(issue.get("body") or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in body.split("\n"):
        match = re.match(r"(?i)^\s*(?:id|operation)\s*:\s*([A-Za-z0-9._-]{8,80})\s*$", line)
        if match and ID_RE.fullmatch(match.group(1)):
            candidates.add(match.group(1))
    return next(iter(candidates)) if len(candidates) == 1 else ""


def closing_keyword_mentions_issue(body: str, issue_number: int) -> bool:
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1:
        return False
    return re.search(CLOSING_RE_TEMPLATE % issue_number, str(body or "")) is not None


def build_marker(
    root: str | os.PathLike[str],
    operation_id: str,
    issue: dict[str, Any],
    pull_request: dict[str, Any],
) -> dict[str, Any]:
    operation_id = _clean_id(operation_id)
    if not isinstance(issue, dict) or not isinstance(pull_request, dict):
        raise CompletionEvidenceError("completion evidence must be objects")
    issue_number = issue.get("number")
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1:
        raise CompletionEvidenceError("invalid issue number")
    if issue.get("state") != "closed" or issue.get("state_reason") != "completed":
        raise CompletionEvidenceError("issue is not canonically completed")
    closed_at = issue.get("closed_at")
    closed_instant = _timestamp(closed_at)

    pr_number = pull_request.get("number")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number < 1:
        raise CompletionEvidenceError("invalid pull request number")
    if pull_request.get("merged") is not True:
        raise CompletionEvidenceError("pull request is not merged")
    base = pull_request.get("base") or {}
    if not isinstance(base, dict) or str(base.get("ref") or "") != "main":
        raise CompletionEvidenceError("pull request did not merge to main")
    merged_at = pull_request.get("merged_at")
    merged_instant = _timestamp(merged_at)
    merge_commit_sha = str(pull_request.get("merge_commit_sha") or "").lower()
    if not merged_at or not HEX40_RE.fullmatch(merge_commit_sha):
        raise CompletionEvidenceError("merged pull request lacks immutable merge evidence")
    if merged_instant > closed_instant:
        raise CompletionEvidenceError("merge happened after canonical completion")
    if not closing_keyword_mentions_issue(str(pull_request.get("body") or ""), issue_number):
        raise CompletionEvidenceError("pull request does not explicitly close canonical issue")

    rel, blob_sha1 = _source_blob(root, operation_id)
    issue_url = str(issue.get("html_url") or issue.get("url") or "")
    pr_url = str(pull_request.get("html_url") or pull_request.get("url") or "")
    expected_issue_urls = {
        "https://github.com/woahwhattheheck/commons/issues/%s" % issue_number,
        "https://api.github.com/repos/woahwhattheheck/commons/issues/%s" % issue_number,
    }
    expected_pr_urls = {
        "https://github.com/woahwhattheheck/commons/pull/%s" % pr_number,
        "https://api.github.com/repos/woahwhattheheck/commons/pulls/%s" % pr_number,
    }
    if issue_url not in expected_issue_urls or pr_url not in expected_pr_urls:
        raise CompletionEvidenceError("completion evidence is not from this repository")
    return {
        "schema": SCHEMA,
        "state": STATE,
        "operation_id": operation_id,
        "issue": {
            "number": issue_number,
            "url": issue_url,
            "closed_at": closed_at,
            "state_reason": "completed",
        },
        "merge": {
            "pr_number": pr_number,
            "url": pr_url,
            "base": "main",
            "merged_at": merged_at,
            "merge_commit_sha": merge_commit_sha,
        },
        "source": {
            "path": rel,
            "blob_sha1": blob_sha1,
        },
    }


def write_marker(
    root: str | os.PathLike[str],
    marker: dict[str, Any],
    ancestor_verifier: Callable[[str], bool] | None = None,
) -> str:
    operation_id = _clean_id(marker.get("operation_id"))
    if not marker_is_valid(root, marker, ancestor_verifier):
        raise CompletionEvidenceError("refusing to write invalid completion marker")
    path = Path(root) / marker_rel(operation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(marker, indent=2, sort_keys=True) + "\n"
    if path.is_file() and path.read_bytes() == text.encode("utf-8"):
        return "unchanged"
    # Keep the previous completion visible until all replacement bytes are
    # written. A truncated JSON marker would otherwise resurface finished work.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix="." + path.name + ".", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "wrote"


def remove_marker(
    root: str | os.PathLike[str],
    operation_id: str,
    issue_number: int,
) -> bool:
    operation_id = _clean_id(operation_id)
    path = Path(root) / marker_rel(operation_id)
    if not path.is_file():
        return False
    row = _read_marker(path)
    issue = row.get("issue") if isinstance(row, dict) else None
    if not isinstance(issue, dict) or issue.get("number") != issue_number:
        return False
    path.unlink()
    return True


def remove_markers_for_issue(
    root: str | os.PathLike[str],
    issue_number: int,
) -> tuple[str, ...]:
    """Invalidate retained completion evidence on reopen by canonical issue id.

    Reopen safety must not depend on the current issue title/body still carrying
    the operation id that was present when completion was recorded.
    """
    if (
        not isinstance(issue_number, int)
        or isinstance(issue_number, bool)
        or issue_number < 1
    ):
        return ()
    removed: list[str] = []
    for rel in source_paths(root):
        path = Path(root) / rel
        row = _read_marker(path)
        issue = row.get("issue") if isinstance(row, dict) else None
        if not isinstance(issue, dict) or issue.get("number") != issue_number:
            continue
        operation_id = str(row.get("operation_id") or "")
        try:
            path.unlink()
        except OSError:
            continue
        removed.append(operation_id)
    return tuple(sorted(removed))


def marker_is_valid(
    root: str | os.PathLike[str],
    row: Any,
    ancestor_verifier: Callable[[str], bool] | None = None,
) -> bool:
    if not isinstance(row, dict):
        return False
    try:
        operation_id = _clean_id(row.get("operation_id"))
        issue = row.get("issue")
        merge = row.get("merge")
        source = row.get("source")
        if row.get("schema") != SCHEMA or row.get("state") != STATE:
            return False
        if not isinstance(issue, dict) or not isinstance(merge, dict) or not isinstance(source, dict):
            return False
        if issue.get("state_reason") != "completed":
            return False
        number = issue.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            return False
        closed_instant = _timestamp(issue.get("closed_at"))
        merged_instant = _timestamp(merge.get("merged_at"))
        if merge.get("base") != "main" or merged_instant > closed_instant:
            return False
        merge_commit_sha = str(merge.get("merge_commit_sha") or "").lower()
        if not HEX40_RE.fullmatch(merge_commit_sha):
            return False
        if ancestor_verifier is None:
            return False
        try:
            if ancestor_verifier(merge_commit_sha) is not True:
                return False
        except Exception:
            return False
        pr_number = merge.get("pr_number")
        if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number < 1:
            return False
        if not isinstance(issue.get("url"), str) or issue["url"] not in {
            "https://github.com/woahwhattheheck/commons/issues/%s" % number,
            "https://api.github.com/repos/woahwhattheheck/commons/issues/%s" % number,
        }:
            return False
        if not isinstance(merge.get("url"), str) or merge["url"] not in {
            "https://github.com/woahwhattheheck/commons/pull/%s" % pr_number,
            "https://api.github.com/repos/woahwhattheheck/commons/pulls/%s" % pr_number,
        }:
            return False
        rel, blob_sha1 = _source_blob(root, operation_id)
        return source.get("path") == rel and source.get("blob_sha1") == blob_sha1
    except (CompletionEvidenceError, OSError, UnicodeError):
        return False


def completed_operation_ids(
    root: str | os.PathLike[str],
    ancestor_verifier: Callable[[str], bool] | None = None,
) -> frozenset[str]:
    completed: set[str] = set()
    for rel in source_paths(root):
        path = Path(root) / rel
        row = _read_marker(path)
        if marker_is_valid(root, row, ancestor_verifier):
            # Renamed/duplicate files cannot stand in for the canonical marker.
            if rel == marker_rel(row["operation_id"]):
                completed.add(str(row["operation_id"]))
    return frozenset(completed)


def is_completed_actionable(meta: dict[str, Any], completed_ids: set[str] | frozenset[str]) -> bool:
    return (
        str(meta.get("id") or "") in completed_ids
        and str(meta.get("from") or "").upper() == "UNSEATED"
        and str(meta.get("to") or "").upper() == "TABLE"
    )
