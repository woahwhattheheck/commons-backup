#!/usr/bin/env python3
"""Conservatively cancel provably obsolete queued GitHub Actions runs.

Default behavior is read-only. A queued run becomes a candidate only when:
  1. its associated pull request is closed;
  2. its associated open PR has moved to a different head SHA; or
  3. --dedupe-exact is set and a newer queued run exists for the exact same
     repository, workflow, event, branch, and head SHA.

The tool never targets in-progress jobs and never prints the token. Set GH_TOKEN
or GITHUB_TOKEN with repository Actions write access. Pass --execute to cancel.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

API = "https://api.github.com"
UTC = dt.timezone.utc


@dataclass(frozen=True)
class Candidate:
    repository: str
    run_id: int
    workflow_id: int
    workflow_name: str
    event: str
    branch: str
    head_sha: str
    created_at: str
    reason: str
    pr_number: int | None


class GitHub:
    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("GH_TOKEN or GITHUB_TOKEN is required")
        self.token = token

    def request(self, method: str, path: str, body: bytes | None = None) -> Any:
        request = urllib.request.Request(
            API + path,
            method=method,
            data=body,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "actions-queue-storm-remediation/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc

    def queued_runs(self, repository: str) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        page = 1
        while True:
            query = urllib.parse.urlencode(
                {"status": "queued", "per_page": 100, "page": page}
            )
            payload = self.request(
                "GET", f"/repos/{repository}/actions/runs?{query}"
            )
            batch = payload.get("workflow_runs", [])
            runs.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return runs

    def pull_request(self, repository: str, number: int) -> dict[str, Any]:
        return self.request("GET", f"/repos/{repository}/pulls/{number}")

    def cancel(self, repository: str, run_id: int) -> None:
        self.request(
            "POST",
            f"/repos/{repository}/actions/runs/{run_id}/cancel",
            body=b"",
        )


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def old_enough(run: dict[str, Any], minimum_age: dt.timedelta, now: dt.datetime) -> bool:
    return now - parse_time(run["created_at"]) >= minimum_age


def analyze_repository(
    client: GitHub,
    repository: str,
    *,
    minimum_age: dt.timedelta,
    dedupe_exact: bool,
    now: dt.datetime,
) -> tuple[list[dict[str, Any]], list[Candidate]]:
    runs = client.queued_runs(repository)
    candidates: dict[int, Candidate] = {}
    pr_cache: dict[int, dict[str, Any]] = {}

    for run in runs:
        if not old_enough(run, minimum_age, now):
            continue
        prs = run.get("pull_requests") or []
        if not prs:
            continue
        pr_number = int(prs[0]["number"])
        pr = pr_cache.get(pr_number)
        if pr is None:
            pr = client.pull_request(repository, pr_number)
            pr_cache[pr_number] = pr

        if pr.get("state") != "open":
            reason = f"associated PR #{pr_number} is {pr.get('state', 'not-open')}"
        elif pr.get("head", {}).get("sha") != run.get("head_sha"):
            reason = (
                f"PR #{pr_number} current head {pr.get('head', {}).get('sha')} "
                f"differs from queued head {run.get('head_sha')}"
            )
        else:
            continue

        candidates[int(run["id"])] = Candidate(
            repository=repository,
            run_id=int(run["id"]),
            workflow_id=int(run["workflow_id"]),
            workflow_name=str(run["name"]),
            event=str(run["event"]),
            branch=str(run.get("head_branch") or ""),
            head_sha=str(run.get("head_sha") or ""),
            created_at=str(run["created_at"]),
            reason=reason,
            pr_number=pr_number,
        )

    if dedupe_exact:
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(list)
        for run in runs:
            if not old_enough(run, minimum_age, now):
                continue
            key = (
                int(run["workflow_id"]),
                str(run["event"]),
                str(run.get("head_branch") or ""),
                str(run.get("head_sha") or ""),
            )
            groups[key].append(run)

        for group in groups.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda item: (item["created_at"], int(item["id"])), reverse=True)
            keep = group[0]
            for run in group[1:]:
                run_id = int(run["id"])
                if run_id in candidates:
                    continue
                prs = run.get("pull_requests") or []
                candidates[run_id] = Candidate(
                    repository=repository,
                    run_id=run_id,
                    workflow_id=int(run["workflow_id"]),
                    workflow_name=str(run["name"]),
                    event=str(run["event"]),
                    branch=str(run.get("head_branch") or ""),
                    head_sha=str(run.get("head_sha") or ""),
                    created_at=str(run["created_at"]),
                    reason=f"exact duplicate; keeping newer queued run {keep['id']}",
                    pr_number=int(prs[0]["number"]) if prs else None,
                )

    ordered = sorted(candidates.values(), key=lambda item: (item.created_at, item.run_id))
    return runs, ordered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repositories", nargs="+", help="owner/repository")
    parser.add_argument("--execute", action="store_true", help="perform cancellations")
    parser.add_argument(
        "--dedupe-exact",
        action="store_true",
        help="also cancel older exact duplicate queued runs",
    )
    parser.add_argument("--minimum-age-minutes", type=int, default=15)
    parser.add_argument(
        "--max-cancels",
        type=int,
        default=250,
        help="hard safety cap across all repositories",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    parser.add_argument("--json-report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.minimum_age_minutes < 0:
        raise SystemExit("--minimum-age-minutes must be >= 0")
    if args.max_cancels < 1:
        raise SystemExit("--max-cancels must be >= 1")

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("set GH_TOKEN or GITHUB_TOKEN; token value is never printed")

    client = GitHub(token)
    now = dt.datetime.now(UTC)
    minimum_age = dt.timedelta(minutes=args.minimum_age_minutes)
    all_candidates: list[Candidate] = []
    repo_counts: dict[str, int] = {}

    for repository in args.repositories:
        runs, candidates = analyze_repository(
            client,
            repository,
            minimum_age=minimum_age,
            dedupe_exact=args.dedupe_exact,
            now=now,
        )
        repo_counts[repository] = len(runs)
        all_candidates.extend(candidates)

    if len(all_candidates) > args.max_cancels:
        raise SystemExit(
            f"refusing: {len(all_candidates)} candidates exceed --max-cancels "
            f"{args.max_cancels}; inspect report and raise the cap explicitly"
        )

    actions: list[dict[str, Any]] = []
    for candidate in all_candidates:
        status = "dry_run"
        error = None
        if args.execute:
            try:
                client.cancel(candidate.repository, candidate.run_id)
                status = "cancel_requested"
            except Exception as exc:  # report every failure; continue with bounded set
                status = "error"
                error = str(exc)
        actions.append(
            {
                **asdict(candidate),
                "status": status,
                "error": error,
            }
        )
        if args.execute and args.sleep_seconds:
            time.sleep(args.sleep_seconds)

    report = {
        "mode": "execute" if args.execute else "dry_run",
        "generated_at": now.isoformat(),
        "queued_runs_by_repository": repo_counts,
        "candidate_count": len(all_candidates),
        "dedupe_exact": args.dedupe_exact,
        "minimum_age_minutes": args.minimum_age_minutes,
        "actions": actions,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.json_report:
        with open(args.json_report, "w", encoding="utf-8") as handle:
            handle.write(rendered)

    return 1 if any(item["status"] == "error" for item in actions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
