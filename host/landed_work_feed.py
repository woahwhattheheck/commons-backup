#!/usr/bin/env python3
"""Per-merge landed-work feed. One line. Not per day. Not a digest.

Ride named leftover commons-ship-enforcer (Claude is taking headless on
the owner PC). This helper formats the merge line the enforcer already
knows. --send/--go REFUSED: no new Slack secret in this repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "ground/LANDED_WORK_FEED.json"
REPO = "woahwhattheheck/commons"
UNKNOWN_REPO = "UNKNOWN"
CHANNEL = "C0BTVA3C0G3"
BAKE_SUBJECT = "llms.txt+fresh.md"
BAKE_PATHS = {
    "llms.txt",
    "fresh.md",
    "pulse.json",
    "head.json",
    "peers.md",
    "change.md",
    "challenge.json",
}
PR_RE = re.compile(r"#(\d+)")
REFUSE = ("--send", "--apply", "--go", "--autopilot")


def git(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=str(cwd or ROOT),
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
    ).strip()


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CATALOG).read_text(encoding="utf-8"))


def _repository_name(value: str) -> str | None:
    name = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
        if all(part not in {".", ".."} for part in name.split("/")):
            return name
    return None


def repository_of(cwd: Path | None = None, repository: str | None = None) -> str:
    """Return a repository label without exposing origin URLs or userinfo."""
    if repository is not None:
        return _repository_name(repository) or UNKNOWN_REPO
    try:
        origin = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(cwd or ROOT), stderr=subprocess.PIPE,
        ).decode("utf-8").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        return UNKNOWN_REPO
    scp = re.fullmatch(r"(?:[^/@:\s]+@)?github\.com:(.+)", origin, re.IGNORECASE)
    if scp:
        path = scp.group(1)
    else:
        try:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"https", "http", "ssh", "git"} or parsed.hostname != "github.com":
                return UNKNOWN_REPO
            if parsed.query or parsed.fragment:
                return UNKNOWN_REPO
            path = parsed.path
        except ValueError:
            return UNKNOWN_REPO
    return _repository_name(path.strip("/").removesuffix(".git")) or UNKNOWN_REPO


def harness_of(author: str) -> str:
    name = author.strip()
    if name == "Cursor Agent":
        return "cursor"
    if name == "commons-llms":
        return "bake"
    if name in {"GitHub", "woahwhattheheck"}:
        return "github"
    return name.replace(" ", "-").lower() or "UNSEATED"


class ChangedPathsUnavailable(RuntimeError):
    """A commit's first parent is absent from the local object database."""

    def __init__(self, first_parent: str):
        self.first_parent = first_parent
        super().__init__(f"first parent {first_parent} is unavailable locally")


def paths_of(sha: str, cwd: Path | None = None) -> list[str]:
    """Compare the real first parent; a shallow boundary is not a root."""
    root = str(cwd or ROOT)
    env = os.environ.copy()
    env["GIT_NO_LAZY_FETCH"] = "1"
    raw_commit = subprocess.check_output(
        ["git", "cat-file", "commit", sha], cwd=root, env=env,
    )
    headers = raw_commit.split(b"\n\n", 1)[0].splitlines()
    first_parent = next(
        (line[7:].decode("ascii") for line in headers if line.startswith(b"parent ")),
        None,
    )
    revisions = [first_parent, sha] if first_parent else ["--root", sha]
    # NUL-delimited bytes preserve Git filenames, including whitespace/Unicode.
    try:
        out = subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r",
             "--diff-merges=first-parent", "-z", *revisions, "--"],
            cwd=root, env=env, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as error:
        if first_parent:
            parent = subprocess.run(
                ["git", "cat-file", "-e", first_parent + "^{commit}"],
                cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if parent.returncode:
                raise ChangedPathsUnavailable(first_parent) from error
        raise
    return [os.fsdecode(path) for path in out.split(b"\0") if path]


def parse_commit(
    sha: str, author: str, subject: str, cwd: Path | None = None,
    *, repository: str | None = None,
) -> dict[str, Any] | None:
    if subject.startswith(BAKE_SUBJECT):
        return None
    unavailable_parent = None
    try:
        paths = paths_of(sha, cwd)
    except ChangedPathsUnavailable as error:
        paths = []
        unavailable_parent = error.first_parent
    if paths and set(paths) <= BAKE_PATHS:
        return None
    pr_match = PR_RE.search(subject)
    row = {
        "repo": repository_of(cwd, repository),
        "pr": int(pr_match.group(1)) if pr_match else None,
        "sha": sha,
        "title": subject,
        "harness": harness_of(author),
        "paths": paths,
        "author": author,
    }
    if unavailable_parent:
        row["paths_coverage"] = {
            "state": "UNAVAILABLE",
            "reason": "FIRST_PARENT_UNAVAILABLE",
            "first_parent_sha": unavailable_parent,
        }
    return row


def _line_label(text: str, delimiters: str = "") -> str:
    if any(
        ord(c) < 32
        or 0xD800 <= ord(c) <= 0xDFFF
        or c in "\x85\u2028\u2029" + delimiters
        for c in text
    ):
        return json.dumps(text, ensure_ascii=True)
    return text


def format_line(row: dict[str, Any]) -> str:
    pr = f"#{row['pr']}" if row.get("pr") else "PR=FINDER-FAILED"
    path_labels = [_line_label(path, '\\",') for path in row.get("paths") or []]
    paths = ",".join(path_labels) or "paths=FINDER-FAILED"
    return (
        f"{row['repo']} {pr} {row['sha'][:9]} {_line_label(row['title'])} "
        f"harness={_line_label(row['harness'])} paths={paths}"
    )


def recent_merges(
    limit: int = 8, cwd: Path | None = None, *, repository: str | None = None,
) -> list[dict[str, Any]]:
    """Return up to limit non-bake entries from one first-parent history.

    Page by the last examined commit's first parent, not a fixed overscan or
    offsets against moving HEAD. Long bake runs must not hide landed work.
    """
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    if limit == 0:
        return []
    resolved_repository = repository_of(cwd, repository)
    tip = git(["rev-parse", "--verify", "HEAD^{commit}"], cwd=cwd)
    rows: list[dict[str, Any]] = []
    while True:
        raw = git(
            ["log", "--first-parent", "-64", "-z", "--format=%H%x00%an%x00%s", tip, "--"],
            cwd=cwd,
        )
        # Fixed-width NUL fields retain empty/control-bearing subjects.
        fields = raw.split("\0")[:-1]
        records = [fields[i:i + 3] for i in range(0, len(fields), 3)]
        if not records:
            break
        for sha, author, subject in records:
            parsed = parse_commit(sha, author, subject, cwd, repository=resolved_repository)
            if parsed is not None:
                rows.append(parsed)
                if len(rows) >= limit:
                    return rows
        # Continue from the first parent, never rediscover HEAD between pages.
        last_sha = records[-1][0]
        parents = git(["rev-list", "--parents", "-n", "1", last_sha], cwd=cwd).split()
        if len(parents) < 2:
            break
        tip = parents[1]
    return rows


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "LANDED_WORK_FEED",
        "id": "cursor-landed-work-feed-20260902-01",
        "gate": False,
        "refused": flag,
        "verdict": "FINDER-FAILED",
        "sent": 0,
        "cash": 0,
        "note": f"{flag} REFUSED. No new Slack secret. Use the harness that already has Slack.",
    }


def measure(
    limit: int = 8, cwd: Path | None = None, *, repository: str | None = None,
) -> dict[str, Any]:
    catalog = load_catalog()
    resolved_repository = repository_of(cwd, repository)
    rows = recent_merges(limit, cwd, repository=resolved_repository)
    return {
        "kind": "LANDED_WORK_FEED",
        "id": catalog["id"],
        "gate": False,
        "commons_admission": False,
        "cadence": "per-merge",
        "not_per_day": True,
        "channel": CHANNEL,
        "thread_per": "repo",
        "ride": catalog["ride"],
        "headless_enforcer": catalog["headless_enforcer"],
        "invented_stripe_urls": False,
        "sends": 0,
        "cash_usd": 0,
        "repos_named_here": catalog["repos_named_here"],
        "twelve_named_here": False,
        "unnamed_remainder": "FINDER-FAILED",
        "count": len(rows),
        "repo": resolved_repository,
        "lines": [format_line(row) for row in rows],
        "merges": rows,
        "verdict": "RENDER",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--root", type=Path, help="checkout to read; defaults to this helper's repository")
    parser.add_argument("--repo", help="explicit owner/name; otherwise infer the configured GitHub origin")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "LANDED_WORK_FEED",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                    },
                    sort_keys=True,
                )
            )
            return 1
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    packet = measure(args.limit, args.root, repository=args.repo)
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
