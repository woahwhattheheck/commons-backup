#!/usr/bin/env python3
"""Read-only GitHub Actions queue triage for Commons-style fast-moving repos.

The tool NEVER cancels workflow runs.  It snapshots queued runs, branch tips,
and open pull-request heads, then labels each queued run with the strongest
source-backed reason it can prove.  Only labels ending in ``_CANDIDATE`` are
reasonable inputs to a separate, privileged canceller, and that canceller must
re-read the run/PR/ref immediately before mutation.

Typical use::

    python host/actions_queue_triage.py --repo woahwhattheheck/commons \
      --out /tmp/actions-queue-triage.json

Authentication is optional for public repositories but strongly recommended to
avoid GitHub's low anonymous rate limit.  ``COMMONS_GITHUB_TOKEN``,
``GITHUB_TOKEN`` and ``GH_TOKEN`` are checked in that order; ``gh auth token``
is used as a final fallback when available.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "commons-actions-queue-triage/v1"
DEFAULT_REPO = "woahwhattheheck/commons"
CANDIDATE_CLASSES = {
    "SUPERSEDED_PR_HEAD_CANDIDATE",
    "CLOSED_PR_HEAD_CANDIDATE",
    "SUPERSEDED_BRANCH_HEAD_CANDIDATE",
    "ORPHANED_PUSH_HEAD_CANDIDATE",
}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _discover_token() -> str:
    for name in ("COMMONS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    try:
        done = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


class GitHubError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None,
                 rate_limited: bool = False, retry_after: str | None = None):
        super().__init__(message)
        self.status = status
        self.rate_limited = rate_limited
        self.retry_after = retry_after


def _http_error(method: str, path: str, exc: urllib.error.HTTPError) -> GitHubError:
    detail = exc.read().decode("utf-8", "replace")[:300]
    headers = exc.headers or {}
    retry_after = headers.get("Retry-After")
    limited = exc.code == 429 or (exc.code == 403 and (
        headers.get("X-RateLimit-Remaining") == "0"
        or retry_after is not None or "rate limit" in detail.lower()
    ))
    return GitHubError(f"{method} {path} -> HTTP {exc.code}: {detail}",
                       status=exc.code, rate_limited=limited, retry_after=retry_after)


class GitHub:
    """Tiny read-only REST client; ``transport`` is injectable for tests."""

    def __init__(self, repo: str, token: str = "", transport=None):
        if repo.count("/") != 1:
            raise ValueError("repo must be OWNER/NAME")
        self.repo = repo
        self.token = token
        self.transport = transport

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub path must be absolute")
        if params:
            path += ("&" if "?" in path else "?") + urllib.parse.urlencode(params)
        if self.transport is not None:
            return self.transport(path)
        request = urllib.request.Request("https://api.github.com" + path)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", "commons-actions-queue-triage")
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _http_error("GET", path, exc) from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"GET {path} -> {exc}") from exc

    def paged(self, path: str, *, cap: int | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while cap is None or len(rows) < cap:
            payload = self.get(path, {"per_page": 100, "page": page})
            if not isinstance(payload, list):
                raise GitHubError(f"GET {path}: expected list page")
            batch = [row for row in payload if isinstance(row, dict)]
            if cap is not None:
                batch = batch[: max(0, cap - len(rows))]
            rows.extend(batch)
            if len(payload) < 100 or (cap is not None and len(rows) >= cap):
                break
            page += 1
        return rows

    def queued_runs(self, cap: int = 1000) -> tuple[list[dict[str, Any]], int | None]:
        rows: list[dict[str, Any]] = []
        page = 1
        total: int | None = None
        while len(rows) < cap:
            payload = self.get(
                f"/repos/{self.repo}/actions/runs",
                {"status": "queued", "per_page": 100, "page": page},
            )
            if not isinstance(payload, dict):
                raise GitHubError("actions/runs: expected object")
            if total is None and isinstance(payload.get("total_count"), int):
                total = payload["total_count"]
            raw = payload.get("workflow_runs") or []
            if not isinstance(raw, list):
                raise GitHubError("actions/runs: workflow_runs must be a list")
            batch = [row for row in raw if isinstance(row, dict)]
            batch = batch[: max(0, cap - len(rows))]
            rows.extend(batch)
            if len(raw) < 100 or len(rows) >= cap:
                break
            page += 1
        return rows, total


@dataclass(frozen=True)
class Snapshot:
    branch_tips: dict[str, str]
    open_pr_heads: dict[int, str]
    open_pr_head_shas: frozenset[str]
    complete_branches: bool
    complete_open_prs: bool


def _valid_sha(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 40:
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in value)


def _run_pr_numbers(run: dict[str, Any]) -> list[int]:
    out: list[int] = []
    for row in run.get("pull_requests") or []:
        if not isinstance(row, dict):
            continue
        number = row.get("number")
        if type(number) is int and number > 0:
            out.append(number)
    return sorted(set(out))


def classify_run(run: dict[str, Any], snapshot: Snapshot, repo: str) -> dict[str, Any]:
    """Classify one queued run without mutating anything.

    Fail closed: if branch/PR inventories are incomplete, any conclusion that
    depends on absence is downgraded to ``UNKNOWN_KEEP``.
    """
    run_id = run.get("id")
    sha = run.get("head_sha")
    branch = run.get("head_branch")
    event = run.get("event")
    prs = _run_pr_numbers(run)
    head_repo = ((run.get("head_repository") or {}).get("full_name"))

    base = {
        "run_id": run_id if type(run_id) is int else None,
        "name": run.get("name") if isinstance(run.get("name"), str) else None,
        "event": event if isinstance(event, str) else None,
        "head_sha": sha if isinstance(sha, str) else None,
        "head_branch": branch if isinstance(branch, str) else None,
        "head_repository": head_repo if isinstance(head_repo, str) else None,
        "pr_numbers": prs,
        "html_url": run.get("html_url") if isinstance(run.get("html_url"), str) else None,
    }

    def finish(label: str, reason: str, *, candidate: bool = False) -> dict[str, Any]:
        return {
            **base,
            "classification": label,
            "cancel_candidate": candidate,
            "reason": reason,
        }

    if not _valid_sha(sha):
        return finish("UNKNOWN_KEEP", "missing or invalid 40-hex head_sha")
    sha_norm = sha.lower()

    # Strongest keep proof: the exact SHA is the current head of any open PR.
    if sha_norm in snapshot.open_pr_head_shas:
        nums = [number for number, head in snapshot.open_pr_heads.items() if head == sha_norm]
        return finish("LIVE_PR_HEAD_KEEP", f"exact SHA is current head of open PR(s) {sorted(nums)}")

    # Exact branch tip is also a keep proof. For fork PRs, base-repo branch
    # inventory does not establish absence, so only compare positively identified
    # same-repo branches. Missing repository provenance must fail closed.
    same_repo = head_repo == repo
    if same_repo and isinstance(branch, str) and snapshot.branch_tips.get(branch) == sha_norm:
        return finish("LIVE_BRANCH_HEAD_KEEP", f"exact SHA is current tip of branch {branch}")

    # Every cancel-candidate below depends on the exact SHA not being a live
    # open-PR head. With an incomplete PR inventory, that absence is unproven.
    if not snapshot.complete_open_prs:
        return finish("UNKNOWN_KEEP", "open-PR inventory incomplete; cannot prove queued head is stale")

    # Same-repo stale proofs also depend on the exact SHA not being the current
    # branch tip. Fork branches are not represented by the base-repo inventory.
    if same_repo and isinstance(branch, str) and not snapshot.complete_branches:
        return finish("UNKNOWN_KEEP", "branch inventory incomplete; cannot prove queued head is stale")

    open_referenced = [number for number in prs if number in snapshot.open_pr_heads]
    if open_referenced:
        current = {number: snapshot.open_pr_heads[number] for number in open_referenced}
        return finish(
            "SUPERSEDED_PR_HEAD_CANDIDATE",
            f"referenced open PR head moved: {current}",
            candidate=True,
        )

    # Absence from the open-PR inventory proves closure only when the inventory
    # was fully enumerated. A run may have multiple historical PR refs; if none
    # remain open, it is stale unless a live branch tip already kept it above.
    if prs:
        return finish(
            "CLOSED_PR_HEAD_CANDIDATE",
            f"run references PR(s) {prs}, none present in complete open-PR inventory",
            candidate=True,
        )

    if isinstance(branch, str) and same_repo:
        current = snapshot.branch_tips.get(branch)
        if current:
            return finish(
                "SUPERSEDED_BRANCH_HEAD_CANDIDATE",
                f"branch {branch} moved to {current}",
                candidate=True,
            )
        if event == "push":
            return finish(
                "ORPHANED_PUSH_HEAD_CANDIDATE",
                f"push branch {branch} no longer exists in complete branch inventory",
                candidate=True,
            )

    return finish(
        "UNKNOWN_KEEP",
        "no source-backed proof that queued head is closed or superseded",
    )


def make_snapshot(branches: Iterable[dict[str, Any]], open_prs: Iterable[dict[str, Any]], *,
                  complete_branches: bool = True, complete_open_prs: bool = True) -> Snapshot:
    branch_tips: dict[str, str] = {}
    for row in branches:
        name = row.get("name")
        sha = ((row.get("commit") or {}).get("sha"))
        if isinstance(name, str) and _valid_sha(sha):
            branch_tips[name] = sha.lower()

    open_pr_heads: dict[int, str] = {}
    for row in open_prs:
        number = row.get("number")
        sha = ((row.get("head") or {}).get("sha"))
        if type(number) is int and number > 0 and _valid_sha(sha):
            open_pr_heads[number] = sha.lower()
    return Snapshot(
        branch_tips=branch_tips,
        open_pr_heads=open_pr_heads,
        open_pr_head_shas=frozenset(open_pr_heads.values()),
        complete_branches=complete_branches,
        complete_open_prs=complete_open_prs,
    )


def build_report(repo: str, runs: list[dict[str, Any]], total_queued: int | None,
                 snapshot: Snapshot, *, cap: int) -> dict[str, Any]:
    rows = [classify_run(run, snapshot, repo) for run in runs]
    rows.sort(key=lambda row: (row["cancel_candidate"], row["classification"], row["run_id"] or 0))
    counts = Counter(row["classification"] for row in rows)
    observed = len(rows)
    complete_runs = isinstance(total_queued, int) and total_queued <= observed
    return {
        "schema": SCHEMA,
        "observed_at": _now_iso(),
        "repo": repo,
        "queued_total_reported": total_queued,
        "queued_runs_observed": observed,
        "queued_inventory_complete": complete_runs,
        "cap": cap,
        "branch_inventory_complete": snapshot.complete_branches,
        "open_pr_inventory_complete": snapshot.complete_open_prs,
        "counts": dict(sorted(counts.items())),
        "cancel_candidates": sum(1 for row in rows if row["cancel_candidate"]),
        "safety": {
            "mutates_github": False,
            "cancels_runs": False,
            "required_before_cancel": "re-read run, PR state, branch tip, and active-lane hold immediately before mutation",
        },
        "runs": rows,
    }


def _write_report(report: dict[str, Any], out: Path | None) -> None:
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if out is None:
        sys.stdout.write(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    # Evidence tooling should not silently overwrite an earlier snapshot.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(out, flags, 0o644)
    try:
        body = text.encode("utf-8")
        view = memoryview(body)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise OSError("short write")
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--cap", type=int, default=1000,
                        help="maximum queued runs to inspect (default: 1000)")
    parser.add_argument("--out", type=Path, help="create-exclusive JSON output path")
    args = parser.parse_args(argv)
    if args.cap <= 0:
        parser.error("--cap must be positive")

    github = GitHub(args.repo, _discover_token())
    runs, total = github.queued_runs(args.cap)
    branches = github.paged(f"/repos/{args.repo}/branches")
    open_prs = github.paged(f"/repos/{args.repo}/pulls?state=open")
    snapshot = make_snapshot(branches, open_prs)
    report = build_report(args.repo, runs, total, snapshot, cap=args.cap)
    _write_report(report, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
