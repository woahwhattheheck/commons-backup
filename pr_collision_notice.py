#!/usr/bin/env python3
"""Post an advisory exact-path collision notice on a pull request.

The listener is intentionally narrow: it compares the triggering PR's files
with other open PRs and with literal path mentions in active ``wake_jobs``.
It never blocks, labels, closes, merges, or executes code from the PR head.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


MARKER = "<!-- commons-pr-collision-notice -->"
TERMINAL_JOB_STATES = {"CANCELLED", "CLOSED", "COMPLETE", "COMPLETED", "DONE", "MERGED"}
RATE_LIMIT_MAX_RETRIES = 6
RATE_LIMIT_MAX_WAIT_SECONDS = 120.0
OPEN_PR_FILES_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: OPEN, first: 50, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        url
        title
        files(first: 100) {
          pageInfo { hasNextPage }
          nodes { path }
        }
      }
    }
  }
}
"""


def is_rate_limit_error(code: int, detail: str) -> bool:
    if code not in (403, 429):
        return False
    lowered = detail.lower()
    return "rate limit" in lowered or "secondary rate" in lowered


def rate_limit_wait_seconds(
    code: int,
    detail: str,
    headers: Mapping[str, str] | None,
    now: float,
    attempt: int,
) -> float | None:
    if not is_rate_limit_error(code, detail):
        return None
    headers = headers or {}
    wait = 0.0
    retry_after = headers.get("Retry-After")
    if retry_after is not None:
        try:
            wait = max(wait, float(str(retry_after).strip()))
        except ValueError:
            pass
    remaining = headers.get("X-RateLimit-Remaining")
    reset = headers.get("X-RateLimit-Reset")
    if remaining == "0" and reset:
        try:
            wait = max(wait, float(reset) - now)
        except ValueError:
            pass
    if wait <= 0:
        wait = float(min(2 ** attempt, 30))
    return min(max(wait, 1.0), RATE_LIMIT_MAX_WAIT_SECONDS)


class GitHubAPI:
    def __init__(
        self,
        token: str,
        api_url: str = "https://api.github.com",
        sleeper: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        max_retries: int = RATE_LIMIT_MAX_RETRIES,
    ) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.sleeper = time.sleep if sleeper is None else sleeper
        self.clock = time.time if clock is None else clock
        self.max_retries = max_retries

    def request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "commons-pr-collision-notice",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        last_error: RuntimeError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                last_error = RuntimeError(f"GitHub API {method} {path} failed ({exc.code}): {detail}")
                wait = rate_limit_wait_seconds(exc.code, detail, exc.headers, self.clock(), attempt)
                if wait is None or attempt >= self.max_retries:
                    raise last_error from exc
                self.sleeper(wait)
                continue
            return json.loads(raw) if raw else None
        assert last_error is not None
        raise last_error

    def paged(self, path: str) -> list[Any]:
        separator = "&" if "?" in path else "?"
        rows: list[Any] = []
        for page in range(1, 101):
            batch = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise RuntimeError(f"expected a list from GitHub API path {path}")
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise RuntimeError(f"pagination limit reached for GitHub API path {path}")

    def list_open_pulls_with_files(self, repository: str) -> tuple[list[Any], dict[int, list[Any]]]:
        try:
            return self._graphql_open_pulls_with_files(repository)
        except RuntimeError as exc:
            if is_rate_limit_error(403, str(exc)) or is_rate_limit_error(429, str(exc)):
                raise
            return self._rest_open_pulls_with_files(repository)

    def _graphql_open_pulls_with_files(self, repository: str) -> tuple[list[Any], dict[int, list[Any]]]:
        owner, _, name = repository.partition("/")
        if not owner or not name:
            raise RuntimeError(f"invalid repository name {repository!r}")
        pulls: list[Any] = []
        files_by_pr: dict[int, list[Any]] = {}
        cursor: str | None = None
        for _ in range(100):
            payload = self.request(
                "POST",
                "/graphql",
                {"query": OPEN_PR_FILES_QUERY, "variables": {"owner": owner, "name": name, "cursor": cursor}},
            )
            if not isinstance(payload, Mapping):
                raise RuntimeError("GraphQL open-pull listing returned a non-object")
            errors = payload.get("errors")
            repo = ((payload.get("data") or {}) if isinstance(payload.get("data"), Mapping) else {}).get("repository")
            if errors and not isinstance(repo, Mapping):
                raise RuntimeError(f"GraphQL open-pull listing failed: {errors}")
            if not isinstance(repo, Mapping):
                raise RuntimeError("GraphQL open-pull listing missing repository data")
            connection = repo.get("pullRequests")
            if not isinstance(connection, Mapping):
                raise RuntimeError("GraphQL open-pull listing missing pullRequests")
            for node in connection.get("nodes") or []:
                if not isinstance(node, Mapping):
                    continue
                number = int(node["number"])
                pulls.append(
                    {
                        "number": number,
                        "html_url": str(node.get("url") or ""),
                        "title": str(node.get("title") or ""),
                    }
                )
                file_conn = node.get("files") if isinstance(node.get("files"), Mapping) else {}
                paths = [
                    {"filename": str(row["path"])}
                    for row in (file_conn.get("nodes") or [])
                    if isinstance(row, Mapping) and row.get("path")
                ]
                page_info = file_conn.get("pageInfo") if isinstance(file_conn.get("pageInfo"), Mapping) else {}
                if page_info.get("hasNextPage"):
                    paths = self.paged(f"/repos/{repository}/pulls/{number}/files")
                files_by_pr[number] = paths
            page = connection.get("pageInfo") if isinstance(connection.get("pageInfo"), Mapping) else {}
            if not page.get("hasNextPage"):
                return pulls, files_by_pr
            cursor = page.get("endCursor")
        raise RuntimeError("pagination limit reached for GraphQL open-pull listing")

    def _rest_open_pulls_with_files(self, repository: str) -> tuple[list[Any], dict[int, list[Any]]]:
        prefix = f"/repos/{repository}"
        open_prs = self.paged(f"{prefix}/pulls?state=open")
        files_by_pr = {int(pull["number"]): self.paged(f"{prefix}/pulls/{int(pull['number'])}/files") for pull in open_prs}
        return open_prs, files_by_pr


def _paths(files: Iterable[Mapping[str, Any]]) -> set[str]:
    return {str(row["filename"]) for row in files if row.get("filename")}


def find_pr_overlaps(
    target_number: int,
    target_paths: set[str],
    open_prs: Sequence[Mapping[str, Any]],
    files_by_pr: Mapping[int, Iterable[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    overlaps: list[dict[str, Any]] = []
    for pull in open_prs:
        number = int(pull["number"])
        if number == target_number:
            continue
        shared = sorted(target_paths & _paths(files_by_pr.get(number, [])))
        if shared:
            overlaps.append(
                {
                    "number": number,
                    "url": str(pull.get("html_url") or ""),
                    "title": str(pull.get("title") or ""),
                    "paths": shared,
                }
            )
    return sorted(overlaps, key=lambda row: row["number"])


def find_wake_job_overlaps(wake_dir: Path, target_paths: set[str]) -> list[dict[str, Any]]:
    overlaps: list[dict[str, Any]] = []
    if not wake_dir.is_dir():
        return overlaps
    for path in sorted(wake_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        state = str(row.get("status") or row.get("state") or "OPEN").upper()
        if state in TERMINAL_JOB_STATES:
            continue
        exact = sorted(candidate for candidate in target_paths if candidate in json.dumps(row, sort_keys=True))
        if exact:
            overlaps.append(
                {
                    "job_id": str(row.get("job_id") or path.stem),
                    "status": state,
                    "paths": exact,
                }
            )
    return overlaps


def _code(value: str) -> str:
    return f"`{value.replace('`', '')}`"


def render_notice(
    target_number: int,
    head_sha: str,
    pr_overlaps: Sequence[Mapping[str, Any]],
    job_overlaps: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        MARKER,
        "### Commons collision notice",
        "",
        "Advisory only — this never gates, closes, labels, or delays the open PR.",
        f"Compared exact changed paths for PR #{target_number} at {_code(head_sha)}.",
    ]
    if pr_overlaps:
        lines.extend(["", "**Open PR overlaps**"])
        for row in pr_overlaps:
            link = f"[#{row['number']}]({row['url']})" if row.get("url") else f"#{row['number']}"
            paths = ", ".join(_code(path) for path in row["paths"])
            lines.append(f"- {link}: {paths}")
    if job_overlaps:
        lines.extend(["", "**Active wake-job path mentions**"])
        for row in job_overlaps:
            paths = ", ".join(_code(path) for path in row["paths"])
            lines.append(f"- {_code(str(row['job_id']))} ({row['status']}): {paths}")
    if not pr_overlaps and not job_overlaps:
        lines.extend(["", "No exact path overlaps detected."])
    lines.extend(["", "Recomputed on each open, reopen, ready-for-review, or synchronize event."])
    return "\n".join(lines)


def run(event_path: Path, repo_root: Path, api: GitHubAPI) -> str:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    pull = event["pull_request"]
    target_number = int(pull["number"])
    head_sha = str(pull["head"]["sha"])
    repository = str(event["repository"]["full_name"])
    prefix = f"/repos/{repository}"

    open_prs, files_by_pr = api.list_open_pulls_with_files(repository)
    target_files = files_by_pr.get(target_number)
    if target_files is None:
        target_files = api.paged(f"{prefix}/pulls/{target_number}/files")
    target_paths = _paths(target_files)

    pr_overlaps = find_pr_overlaps(target_number, target_paths, open_prs, files_by_pr)
    job_overlaps = find_wake_job_overlaps(repo_root / "wake_jobs", target_paths)
    comments = api.paged(f"{prefix}/issues/{target_number}/comments")
    existing = next((row for row in comments if MARKER in str(row.get("body") or "")), None)

    if not pr_overlaps and not job_overlaps and existing is None:
        return "no exact overlaps; no comment needed"

    body = render_notice(target_number, head_sha, pr_overlaps, job_overlaps)
    if existing is None:
        api.request("POST", f"{prefix}/issues/{target_number}/comments", {"body": body})
        return "created collision notice"
    api.request("PATCH", f"{prefix}/issues/comments/{existing['id']}", {"body": body})
    return "updated collision notice"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", "")))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not args.event.is_file():
        parser.error("a pull_request event JSON file is required")
    if not token:
        parser.error("GITHUB_TOKEN is required for the GitHub comment write road")
    print(run(args.event, args.repo_root, GitHubAPI(token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
