#!/usr/bin/env python3
"""Read-only GitHub Actions workflow fleet auditor and patch generator.

The auditor enumerates `.github/workflows` through GitHub's Contents API,
fetches the exact blob bytes, applies the tested transformation from
`actions_queue_storm_fix.py`, and writes:

* one unified patch per repository;
* one JSON receipt per repository with source blob SHAs and byte hashes; and
* a fleet summary.

It performs GET requests only. It has no GitHub mutation method and cannot
create branches, commits, pull requests, comments, reruns, or cancellations.

Target syntax:
    OWNER/REPOSITORY
    OWNER/REPOSITORY@REF

Examples:
    python github_workflow_fleet_audit.py \
      woahwhattheheck/smb-showcase-inventory \
      woahwhattheheck/pack-market \
      woahwhattheheck/motel-ops-suite \
      --output-dir fleet-audit

Private repositories require GH_TOKEN or GITHUB_TOKEN. The token is never
printed or written to receipts.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import datetime as dt
import difflib
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Protocol, Sequence

API_ROOT = "https://api.github.com"
UTC = dt.timezone.utc
TARGET_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
    r"(?:@(?P<ref>[^\s]+))?$"
)


class AuditError(RuntimeError):
    """Raised for a deterministic audit failure."""


@dataclasses.dataclass(frozen=True)
class Target:
    repository: str
    ref: str


@dataclasses.dataclass(frozen=True)
class WorkflowSource:
    path: str
    blob_sha: str
    api_size: int
    byte_sha256: str
    text: str


@dataclasses.dataclass(frozen=True)
class WorkflowAudit:
    path: str
    blob_sha: str
    api_size: int
    byte_sha256: str
    status: str
    detail: str
    changed: bool


@dataclasses.dataclass(frozen=True)
class RepositoryAudit:
    repository: str
    ref: str
    files_seen: int
    changes_required: int
    unsupported_requiring_review: int
    status_counts: Mapping[str, int]
    patch_filename: str
    patch_sha256: str
    receipt_filename: str
    workflows: Sequence[WorkflowAudit]


class ReadClient(Protocol):
    def get_json(self, path: str) -> Any:
        ...


def parse_target(value: str, default_ref: str) -> Target:
    match = TARGET_RE.fullmatch(value)
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid target {value!r}; expected OWNER/REPOSITORY or "
            "OWNER/REPOSITORY@REF"
        )
    ref = match.group("ref") or default_ref
    if ref.startswith("-"):
        raise argparse.ArgumentTypeError("ref must not start with '-'")
    return Target(
        repository=f"{match.group('owner')}/{match.group('repo')}",
        ref=ref,
    )


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return slug or "audit"


def validate_workflow_path(path: str) -> None:
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise AuditError(f"unsafe workflow path: {path!r}")
    if len(pure.parts) != 3 or pure.parts[:2] != (".github", "workflows"):
        raise AuditError(f"path escapes .github/workflows: {path!r}")
    if pure.suffix.lower() not in {".yml", ".yaml"}:
        raise AuditError(f"unsupported workflow extension: {path!r}")


def load_transform_module(path: Path):
    if not path.is_file():
        raise AuditError(f"transform module not found: {path}")
    spec = importlib.util.spec_from_file_location(
        "actions_queue_storm_fix_for_fleet_audit", path
    )
    if spec is None or spec.loader is None:
        raise AuditError(f"cannot load transform module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "transform_text"):
        raise AuditError(f"{path} does not expose transform_text")
    return module


class GitHubReadClient:
    """Minimal GitHub REST client with an intentionally GET-only surface."""

    def __init__(
        self,
        token: str | None,
        *,
        api_root: str = API_ROOT,
        timeout_seconds: float = 30.0,
        retry_limit: int = 2,
        max_retry_sleep_seconds: float = 15.0,
    ) -> None:
        self._token = token
        self._api_root = api_root.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._retry_limit = retry_limit
        self._max_retry_sleep_seconds = max_retry_sleep_seconds

    def get_json(self, path: str) -> Any:
        if not path.startswith("/"):
            raise AuditError(f"API path must begin with '/': {path!r}")
        url = self._api_root + path

        for attempt in range(self._retry_limit + 1):
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "actions-queue-storm-fleet-audit/1.0",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"

            request = urllib.request.Request(url, method="GET", headers=headers)
            try:
                with urllib.request.urlopen(
                    request, timeout=self._timeout_seconds
                ) as response:
                    payload = response.read()
                    return json.loads(payload) if payload else None
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                retryable = exc.code in {403, 429, 500, 502, 503, 504}
                if attempt >= self._retry_limit or not retryable:
                    raise AuditError(
                        f"GET {path} -> HTTP {exc.code}: {body[:500]}"
                    ) from exc

                retry_after = exc.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    sleep_for = float(retry_after)
                else:
                    reset = exc.headers.get("X-RateLimit-Reset")
                    if reset and reset.isdigit():
                        sleep_for = max(0.0, float(reset) - time.time())
                    else:
                        sleep_for = float(2**attempt)
                time.sleep(min(sleep_for, self._max_retry_sleep_seconds))
            except urllib.error.URLError as exc:
                if attempt >= self._retry_limit:
                    raise AuditError(f"GET {path} failed: {exc}") from exc
                time.sleep(min(float(2**attempt), self._max_retry_sleep_seconds))

        raise AssertionError("unreachable")


def contents_path(repository: str, path: str, ref: str) -> str:
    encoded_path = "/".join(
        urllib.parse.quote(part, safe="") for part in PurePosixPath(path).parts
    )
    query = urllib.parse.urlencode({"ref": ref})
    return f"/repos/{repository}/contents/{encoded_path}?{query}"


def list_workflow_items(
    client: ReadClient,
    target: Target,
    *,
    max_files: int,
) -> list[dict[str, Any]]:
    payload = client.get_json(
        contents_path(target.repository, ".github/workflows", target.ref)
    )
    if not isinstance(payload, list):
        raise AuditError(
            f"{target.repository}@{target.ref}: workflow directory response "
            "was not a list"
        )

    items: list[dict[str, Any]] = []
    for raw in payload:
        if not isinstance(raw, dict):
            raise AuditError(
                f"{target.repository}@{target.ref}: non-object directory entry"
            )
        path = str(raw.get("path", ""))
        entry_type = raw.get("type")
        suffix = PurePosixPath(path).suffix.lower()
        if entry_type != "file" or suffix not in {".yml", ".yaml"}:
            continue
        validate_workflow_path(path)
        items.append(raw)

    items.sort(key=lambda item: str(item["path"]))
    if len(items) > max_files:
        raise AuditError(
            f"{target.repository}@{target.ref}: {len(items)} workflows exceed "
            f"--max-files {max_files}"
        )
    return items


def decode_content_payload(
    payload: Any,
    *,
    expected_path: str,
    expected_sha: str,
    expected_size: int,
) -> WorkflowSource:
    if not isinstance(payload, dict):
        raise AuditError(f"{expected_path}: content response was not an object")
    path = str(payload.get("path", ""))
    validate_workflow_path(path)
    if path != expected_path:
        raise AuditError(
            f"content path mismatch: expected {expected_path!r}, got {path!r}"
        )

    blob_sha = str(payload.get("sha", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
        raise AuditError(f"{path}: invalid blob SHA {blob_sha!r}")
    if blob_sha != expected_sha:
        raise AuditError(
            f"{path}: listing/content blob SHA mismatch "
            f"({expected_sha} != {blob_sha})"
        )

    encoding = payload.get("encoding")
    if encoding != "base64":
        raise AuditError(f"{path}: unsupported content encoding {encoding!r}")
    encoded = payload.get("content")
    if not isinstance(encoded, str):
        raise AuditError(f"{path}: missing base64 content")

    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise AuditError(f"{path}: invalid base64 content") from exc

    declared_size = payload.get("size")
    if not isinstance(declared_size, int) or declared_size < 0:
        raise AuditError(f"{path}: invalid content size")
    if declared_size != expected_size or len(raw) != declared_size:
        raise AuditError(
            f"{path}: size mismatch listing={expected_size}, "
            f"content={declared_size}, decoded={len(raw)}"
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditError(f"{path}: workflow is not UTF-8") from exc

    return WorkflowSource(
        path=path,
        blob_sha=blob_sha,
        api_size=declared_size,
        byte_sha256=hashlib.sha256(raw).hexdigest(),
        text=text,
    )


def fetch_workflow(
    client: ReadClient,
    target: Target,
    item: Mapping[str, Any],
) -> WorkflowSource:
    path = str(item.get("path", ""))
    validate_workflow_path(path)

    blob_sha = str(item.get("sha", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
        raise AuditError(f"{path}: invalid listing blob SHA {blob_sha!r}")
    size = item.get("size")
    if not isinstance(size, int) or size < 0:
        raise AuditError(f"{path}: invalid listing size")

    payload = client.get_json(contents_path(target.repository, path, target.ref))
    return decode_content_payload(
        payload,
        expected_path=path,
        expected_sha=blob_sha,
        expected_size=size,
    )


def unified_patch(path: str, original: str, transformed: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            transformed.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def audit_repository(
    client: ReadClient,
    target: Target,
    transform_module: Any,
    *,
    default_branch: str,
    include_push_only: bool,
    max_files: int,
) -> tuple[RepositoryAudit, str, dict[str, Any]]:
    items = list_workflow_items(client, target, max_files=max_files)
    patch_parts: list[str] = []
    workflow_results: list[WorkflowAudit] = []
    unsupported_statuses = {
        "inline_on_skipped",
        "inline_push_skipped",
        "branches_ignore_skipped",
    }

    for item in items:
        source = fetch_workflow(client, target, item)
        result = transform_module.transform_text(
            source.text,
         default_branch=default_branch,
            include_push_only=include_push_only,
        )
        if result.changed:
            patch_parts.append(
                unified_patch(source.path, source.text, result.text)
            )
        workflow_results.append(
            WorkflowAudit(
                path=source.path,
                blob_sha=source.blob_sha,
                api_size=source.api_size,
                byte_sha256=source.byte_sha256,
                status=result.status,
                detail=result.detail,
                changed=bool(result.changed),
            )
        )

    patch_text = "".join(patch_parts)
    statuses = Counter(result.status for result in workflow_results)
    repository_slug = safe_slug(target.repository.replace("/", "__"))
    ref_slug = safe_slug(target.ref)
    patch_filename = f"{repository_slug}__{ref_slug}.patch"
    receipt_filename = f"{repository_slug}__{ref_slug}.json"
    patch_sha256 = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()

    audit = RepositoryAudit(
        repository=target.repository,
        ref=target.ref,
        files_seen=len(workflow_results),
        changes_required=sum(result.changed for result in workflow_results),
        unsupported_requiring_review=sum(
            result.status in unsupported_statuses for result in workflow_results
        ),
        status_counts=dict(sorted(statuses.items())),
        patch_filename=patch_filename,
        patch_sha256=patch_sha256,
        receipt_filename=receipt_filename,
        workflows=tuple(workflow_results),
    )

    receipt = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(UTC).isoformat(),
        "mode": "read_only_get_and_patch_generation",
        "repository": target.repository,
        "ref": target.ref,
        "default_branch": default_branch,
        "include_push_only": include_push_only,
        "files_seen": audit.files_seen,
        "changes_required": audit.changes_required,
        "unsupported_requiring_review": audit.unsupported_requiring_review,
        "status_counts": audit.status_counts,
        "patch_filename": patch_filename,
        "patch_sha256": patch_sha256,
        "workflows": [dataclasses.asdict(result) for result in workflow_results],
    }
    return audit, patch_text, receipt


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets",
        nargs="+",
        help="OWNER/REPOSITORY or OWNER/REPOSITORY@REF",
    )
    parser.add_argument("--default-ref", default="main")
    parser.add_argument("--default-branch", default="main")
    parser.add_argument(
        "--include-push-only",
        action="store_true",
        help="also scope push-only workflows; off by default",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("fleet-audit"),
    )
    parser.add_argument(
        "--transform-module",
        type=Path,
        default=Path(__file__).with_name("actions_queue_storm_fix.py"),
    )
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 2 when an unsupported trigger form requires manual review",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    client: ReadClient | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if args.max_files < 1:
        raise SystemExit("--max-files must be >= 1")
    if not args.default_branch or any(ch.isspace() for ch in args.default_branch):
        raise SystemExit("--default-branch must be a non-empty branch name")

    targets = [parse_target(value, args.default_ref) for value in args.targets]
    seen = set()
    for target in targets:
        key = (target.repository, target.ref)
        if key in seen:
            raise SystemExit(f"duplicate target: {target.repository}@{target.ref}")
        seen.add(key)

    transform_module = load_transform_module(args.transform_module)
    if client is None:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        client = GitHubReadClient(token)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    audits: list[RepositoryAudit] = []

    for target in targets:
        audit, patch_text, receipt = audit_repository(
            client,
            target,
            transform_module,
            default_branch=args.default_branch,
            include_push_only=args.include_push_only,
            max_files=args.max_files,
        )
        atomic_write(output_dir / audit.patch_filename, patch_text)
        atomic_write(
            output_dir / audit.receipt_filename,
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        )
        audits.append(audit)

    summary = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(UTC).isoformat(),
        "mode": "read_only_get_and_patch_generation",
        "request_methods": ["GET"],
        "targets": [
            {
                "repository": audit.repository,
                "ref": audit.ref,
                "files_seen": audit.files_seen,
                "changes_required": audit.changes_required,
                "unsupported_requiring_review": audit.unsupported_requiring_review,
                "status_counts": audit.status_counts,
                "patch_filename": audit.patch_filename,
                "patch_sha256": audit.patch_sha256,
                "receipt_filename": audit.receipt_filename,
            }
            for audit in audits
        ],
        "totals": {
            "repositories": len(audits),
            "files_seen": sum(audit.files_seen for audit in audits),
            "changes_required": sum(audit.changes_required for audit in audits),
            "unsupported_requiring_review": sum(
                audit.unsupported_requiring_review for audit in audits
            ),
        },
    }
    atomic_write(
        output_dir / "fleet-summary.json",
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.strict and summary["totals"]["unsupported_requiring_review"]:
        return 2
    return 1 if summary["totals"]["changes_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
