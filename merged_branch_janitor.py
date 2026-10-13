#!/usr/bin/env python3
"""Delete a merged pull request's same-repository source branch.

Fork branches, the default branch, unmerged pull requests, and malformed event
payloads are deliberately left untouched. The workflow executes this trusted
base copy, never code from the pull request head.

Deleting a branch that GitHub (or a peer) already removed is success: the
janitor's contract is "the merged same-repo head ref is gone," not "this
process must be the deleter."
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence


def is_absent_ref_error(code: int, detail: str) -> bool:
    """True when GitHub reports the git ref is already gone.

    DELETE /git/refs/heads/{branch} returns HTTP 422 with
    ``Reference does not exist`` when another deleter (GitHub auto-delete on
    merge, a concurrent janitor, a human) already removed the ref. HTTP 404
    is the ordinary missing-resource code for the same state.
    Other 422 bodies stay failures.
    """
    if code == 404:
        return True
    if code == 422 and "Reference does not exist" in detail:
        return True
    return False


class GitHubAPI:
    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")

    def delete_ref(self, repository: str, branch: str) -> str:
        encoded = urllib.parse.quote(branch, safe="/")
        request = urllib.request.Request(
            f"{self.api_url}/repos/{repository}/git/refs/heads/{encoded}",
            method="DELETE",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "commons-merged-branch-janitor",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30):
                return "deleted"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if is_absent_ref_error(exc.code, detail):
                return "already_absent"
            raise RuntimeError(f"GitHub branch delete failed ({exc.code}): {detail}") from exc


def branch_to_delete(event: Mapping[str, Any]) -> tuple[str, str] | None:
    pull = event.get("pull_request")
    repository = event.get("repository")
    if not isinstance(pull, Mapping) or not isinstance(repository, Mapping):
        return None
    if pull.get("merged") is not True:
        return None

    head = pull.get("head")
    base = pull.get("base")
    head_repo = head.get("repo") if isinstance(head, Mapping) else None
    base_repo = base.get("repo") if isinstance(base, Mapping) else None
    if not all(isinstance(row, Mapping) for row in (head, base, head_repo, base_repo)):
        return None

    repository_name = str(repository.get("full_name") or "")
    if not repository_name or str(head_repo.get("full_name") or "") != repository_name:
        return None
    if str(base_repo.get("full_name") or "") != repository_name:
        return None

    branch = str(head.get("ref") or "")
    base_branch = str(base.get("ref") or "")
    default_branch = str(repository.get("default_branch") or "")
    if not branch or branch in {base_branch, default_branch}:
        return None
    return repository_name, branch


def run(event_path: Path, api: GitHubAPI) -> str:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    target = branch_to_delete(event)
    if target is None:
        return "no eligible merged same-repository branch"
    repository, branch = target
    outcome = api.delete_ref(repository, branch)
    if outcome == "already_absent":
        return f"merged branch already absent {repository}:{branch}"
    return f"deleted merged branch {repository}:{branch}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", "")))
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not args.event.is_file():
        parser.error("a pull_request event JSON file is required")
    if not token:
        parser.error("GITHUB_TOKEN is required for branch cleanup")
    print(run(args.event, GitHubAPI(token, os.environ.get("GITHUB_API_URL", "https://api.github.com"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
