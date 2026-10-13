#!/usr/bin/env python3
"""Atomic issue/named-work claimant backed only by Commons ``state/claims``."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata

try:
    from host import coordination_state as cs
except ImportError:
    import coordination_state as cs  # type: ignore

_SLUG = re.compile(r"[^a-z0-9._-]+")
_MAX_OPERATION_BYTES = 200
_ACTIONS = {"take", "renew", "release"}


def issue_key(issue, repository=None):
    if type(issue) is not int or issue <= 0:
        raise ValueError("issue number must be a positive integer")
    return cs.repository_claim_key("issue", issue, repository)


def normalize_operation(operation):
    if not isinstance(operation, str):
        raise ValueError("operation must be text")
    value = unicodedata.normalize("NFKC", operation).strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("operation must not contain control characters")
    value = " ".join(value.split()).casefold()
    if not value:
        raise ValueError("operation must be non-empty text")
    if len(value.encode("utf-8")) > _MAX_OPERATION_BYTES:
        raise ValueError("operation must be <= 200 UTF-8 bytes")
    return value


def work_key(operation):
    value = normalize_operation(operation)
    slug = _SLUG.sub("-", value).strip("-._")[:48] or "named"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"work-{slug}-{digest}"


def claim_key(*, issue=None, work=None, repository=None):
    if (issue is None) == (work is None):
        raise ValueError("provide exactly one of issue or work")
    if work is not None and repository is not None:
        raise ValueError("repository applies to issue claims; include it in a named operation instead")
    return issue_key(issue, repository) if issue is not None else work_key(work)


def write_claim(git, holder, action, *, issue=None, work=None, ttl_s=1800,
                note="", remote="origin", push=True, attempts=3, now=None,
                repository=None):
    if action not in _ACTIONS:
        raise ValueError("action must be take, renew, or release")
    if not isinstance(holder, str) or not holder.strip():
        raise ValueError("holder must be non-empty text")
    if type(ttl_s) is not int or not 1 <= ttl_s <= 7200:
        raise ValueError("ttl must be between 1 and 7200 seconds")
    if type(attempts) is not int or not 1 <= attempts <= 10:
        raise ValueError("attempts must be between 1 and 10")

    key = claim_key(issue=issue, work=work, repository=repository)
    audit = []
    if issue is not None and cs.claim_repository(repository) != cs.DEFAULT_REPO.lower():
        audit.append("repository=" + cs.claim_repository(repository))
    if work is not None:
        audit.append("operation=" + normalize_operation(work))
    if note:
        audit.append(str(note).strip())
    result = cs.holding_write(
        git, key, holder.strip(), action, ttl_s=ttl_s,
        note=" | ".join(x for x in audit if x)[:300],
        now=now, remote=remote, push=push, attempts=attempts,
        repository=cs.claim_repository(repository) if issue is not None else None,
    )
    result = dict(result)
    result.update({"action": action, "key": key})
    if issue is not None:
        result["issue"] = issue
        result["repository"] = cs.claim_repository(repository)
    else:
        result["operation"] = normalize_operation(work)
    return result


def claim_status(git, *, issue=None, work=None, remote="origin", now=None, repository=None):
    key = claim_key(issue=issue, work=work, repository=repository)
    snapshot = cs.holdings_list(git, remote=remote, now=now, key=key)
    row = next((r for r in snapshot.get("holdings", []) if r.get("key") == key), None)
    unreadable = bool(row and row.get("unreadable"))
    result = {
        "ok": not unreadable, "action": "status", "key": key, "tip": snapshot.get("tip"),
        "held": None if unreadable else bool(row and row.get("state") == "HELD" and row.get("live") is True),
        "record": row,
    }
    if unreadable:
        result["reason"] = "the current holding could not be read; ownership is unknown, not vacant"
    if issue is not None:
        result["issue"] = issue
        result["repository"] = cs.claim_repository(repository)
    else:
        result["operation"] = normalize_operation(work)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Atomic Commons issue/work claim")
    parser.add_argument("action", choices=("take", "renew", "release", "status"))
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--issue", type=int)
    target.add_argument("--work")
    parser.add_argument("--repository", help="issue source owner/repo; defaults to Commons, not the claim-storage remote")
    parser.add_argument("--holder", default="")
    parser.add_argument("--ttl", type=int, default=1800)
    parser.add_argument("--note", default="")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--git-root", default=None)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args(argv)

    git = cs.Git(args.git_root or cs.ROOT)
    try:
        if args.action == "status":
            result = claim_status(git, issue=args.issue, work=args.work, remote=args.remote,
                                  repository=args.repository)
        else:
            result = write_claim(
                git, args.holder, args.action, issue=args.issue, work=args.work,
                ttl_s=args.ttl, note=args.note, remote=args.remote,
                push=not args.no_push, attempts=args.attempts,
                repository=args.repository,
            )
    except (ValueError, cs.GitError) as exc:
        result = {"ok": False, "action": args.action, "reason": str(exc)}
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
