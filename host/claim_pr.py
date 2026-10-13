#!/usr/bin/env python3
"""Claim one pull-request work unit through Commons' atomic claim ledger.

PR work uses one canonical ``pr-N`` key. This adapter delegates its state
transitions and publication retries to the same writer as named-work claims,
so every claim road receives the same concurrency and transport repairs.
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from host import coordination_state as cs
except ImportError:  # Direct execution as ``python host/claim_pr.py``.
    import coordination_state as cs  # type: ignore


def pr_key(pr: int, repository=None) -> str:
    """Return the canonical claim-ledger key for a repository's pull request."""
    if type(pr) is not int or pr <= 0:
        raise ValueError("pull request number must be a positive integer")
    return cs.repository_claim_key("pr", pr, repository)


def write_pr_holding(
    git: cs.Git,
    pr: int,
    holder: str,
    action: str,
    *,
    ttl_s: int = 1800,
    note: str = "",
    now=None,
    remote: str = "origin",
    push: bool = True,
    attempts: int = 3,
    repository=None,
) -> dict:
    """Take, renew, or release the canonical repository/PR holding.

    The shared writer re-reads the ledger and production clock after a race,
    preserves future heartbeats, and retries transient publication failures.
    PR/action fields remain available on every ordinary result.
    """
    key = pr_key(pr, repository)
    repository = cs.claim_repository(repository)
    if repository != cs.DEFAULT_REPO.lower():
        note = "repository=" + repository + ((" | " + note) if note else "")
    result = cs.holding_write(
        git, key, holder.strip() if isinstance(holder, str) else holder, action,
        ttl_s=ttl_s, note=note, now=now, remote=remote, push=push,
        attempts=attempts,
        repository=repository,
    )
    result = dict(result)
    result.update({"pr": pr, "action": action, "repository": repository})
    return result


def pr_status(git: cs.Git, pr: int, *, remote="origin", now=None, repository=None) -> dict:
    """Read one canonical PR holding without materializing unrelated records."""
    key = pr_key(pr, repository)
    repository = cs.claim_repository(repository)
    snapshot = cs.holdings_list(git, remote=remote, now=now, key=key)
    row = next((row for row in snapshot.get("holdings", []) if row.get("key") == key), None)
    unreadable = bool(row and row.get("unreadable"))
    result = {
        "ok": not unreadable, "action": "status", "key": key,
        "pr": pr, "repository": repository, "tip": snapshot.get("tip"),
        "held": None if unreadable else bool(row and row.get("state") == "HELD" and row.get("live") is True),
        "record": row,
    }
    if unreadable:
        result["reason"] = "the current holding could not be read; ownership is unknown, not vacant"
    return result


def _positive_pr(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("PR must be an integer") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("PR must be positive")
    return value


def _ttl(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("TTL must be an integer") from exc
    if not 1 <= value <= 7200:
        raise argparse.ArgumentTypeError("TTL must be between 1 and 7200 seconds")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read or atomically take/renew/release the canonical claim for one pull request"
    )
    parser.add_argument("action", choices=("take", "renew", "release", "status"))
    parser.add_argument("pr", type=_positive_pr)
    parser.add_argument("--repository", help="PR source owner/repo; defaults to Commons, not the claim-storage remote")
    parser.add_argument("--holder", help="required for take, renew, and release")
    parser.add_argument("--ttl", type=_ttl, default=1800)
    parser.add_argument("--note", default="")
    parser.add_argument("--git-root", default=None, help="checkout used for git plumbing")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args(argv)
    if args.action != "status" and args.holder is None:
        parser.error("--holder is required for take, renew, and release")

    git = cs.Git(args.git_root or cs.ROOT)
    try:
        if args.action == "status":
            result = pr_status(git, args.pr, remote=args.remote, repository=args.repository)
        else:
            result = write_pr_holding(
                git,
                args.pr,
                args.holder,
                args.action,
                ttl_s=args.ttl,
                note=args.note,
                remote=args.remote,
                push=not args.no_push,
                repository=args.repository,
            )
    except (ValueError, cs.GitError) as exc:
        result = {"ok": False, "pr": args.pr, "action": args.action, "reason": str(exc)}
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
