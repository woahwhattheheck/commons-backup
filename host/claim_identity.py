#!/usr/bin/env python3
"""Advisory swarm display-name claims on Commons' existing atomic work rail.

A claimed display name is coordination evidence only. It is never authentication,
posting/admission authority, source ownership, merge authority, provider authority,
or payment authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata

try:
    from host import claim_work as cw
except ImportError:
    import claim_work as cw  # type: ignore

_NAME_PREFIX = "swarm-display-name:"
_MAX_NAME_BYTES = 120
_SESSION_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ACTIONS = {"take", "renew", "release"}

_AUTHORITY_FALSE = {
    "authenticated": False,
    "posting_authority": False,
    "source_authority": False,
    "merge_authority": False,
    "provider_authority": False,
    "payment_authority": False,
}


def normalize_display_name(name):
    if not isinstance(name, str):
        raise ValueError("display name must be text")
    value = unicodedata.normalize("NFKC", name)
    if any(unicodedata.category(ch) in {"Cc", "Cf"} for ch in value):
        raise ValueError("display name must not contain control or format characters")
    value = " ".join(value.strip().split()).casefold()
    if not value:
        raise ValueError("display name must be non-empty text")
    if len(value.encode("utf-8")) > _MAX_NAME_BYTES:
        raise ValueError("display name must be <= 120 UTF-8 bytes after normalization")
    return value


def identity_operation(name):
    return _NAME_PREFIX + normalize_display_name(name)


def normalize_session_tag(session_tag):
    if not isinstance(session_tag, str):
        raise ValueError("session tag must be text")
    if session_tag != session_tag.strip():
        raise ValueError("session tag must not have leading or trailing whitespace")
    value = session_tag
    if not _SESSION_TAG.fullmatch(value):
        raise ValueError(
            "session tag must be 1..128 ASCII letters/digits plus . _ : - and start alphanumeric"
        )
    return value


def session_tag_sha256(session_tag):
    value = normalize_session_tag(session_tag)
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def session_holder(session_tag):
    return "session-" + session_tag_sha256(session_tag)[:32]


def _decorate(result, display_name, *, action, session_tag=None):
    out = dict(result)
    out.update(_AUTHORITY_FALSE)
    out["action"] = action
    out["display_name"] = normalize_display_name(display_name)
    out["coordination_only"] = True
    if session_tag is not None:
        out["session_tag_sha256"] = session_tag_sha256(session_tag)

    ok = out.get("ok") is True
    if action == "take":
        out["verdict"] = (
            "NAME_CLEAR_FOR_COORDINATION" if ok
            else "NAME_COLLISION_RENAME_RECOMMENDED" if out.get("held_by")
            else "NAME_TAKE_RECONCILE"
        )
    elif action == "renew":
        out["verdict"] = "NAME_RENEWED" if ok else "NAME_RENEW_RECONCILE"
    elif action == "release":
        out["verdict"] = "NAME_RELEASED" if ok else "NAME_RELEASE_RECONCILE"
    elif action == "status":
        out["verdict"] = (
            "NAME_STATUS_UNAVAILABLE" if not ok
            else "NAME_LIVE_ADAPTER_CLAIM_OBSERVED" if out.get("held") is True
            else "NO_LIVE_ADAPTER_CLAIM_OBSERVED"
        )
    return out


def write_identity_claim(
    git,
    session_tag,
    action,
    *,
    display_name,
    ttl_s=1800,
    note="",
    remote="origin",
    push=True,
    attempts=3,
    now=None,
):
    if action not in _ACTIONS:
        raise ValueError("action must be take, renew, or release")
    normalized = normalize_display_name(display_name)
    tag = normalize_session_tag(session_tag)
    result = cw.write_claim(
        git,
        session_holder(tag),
        action,
        work=_NAME_PREFIX + normalized,
        ttl_s=ttl_s,
        note=("advisory swarm display-name claim; non-auth" +
              ((" | " + str(note).strip()) if str(note).strip() else "")),
        remote=remote,
        push=push,
        attempts=attempts,
        now=now,
    )
    return _decorate(result, normalized, action=action, session_tag=tag)


def identity_status(git, *, display_name, remote="origin", now=None):
    normalized = normalize_display_name(display_name)
    result = cw.claim_status(
        git, work=_NAME_PREFIX + normalized, remote=remote, now=now
    )
    return _decorate(result, normalized, action="status")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Advisory Commons swarm display-name claim (never authentication)"
    )
    parser.add_argument("action", choices=("take", "renew", "release", "status"))
    parser.add_argument("--identity", required=True, help="self-declared display name")
    parser.add_argument(
        "--session-tag",
        default="",
        help="non-secret per-session ASCII token; required for take/renew/release",
    )
    parser.add_argument("--ttl", type=int, default=1800)
    parser.add_argument("--note", default="")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--git-root", default=None)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args(argv)

    git = cw.cs.Git(args.git_root or cw.cs.ROOT)
    try:
        if args.action == "status":
            result = identity_status(git, display_name=args.identity, remote=args.remote)
        else:
            if not args.session_tag:
                raise ValueError("--session-tag is required for take, renew, and release")
            result = write_identity_claim(
                git,
                args.session_tag,
                args.action,
                display_name=args.identity,
                ttl_s=args.ttl,
                note=args.note,
                remote=args.remote,
                push=not args.no_push,
                attempts=args.attempts,
            )
    except (ValueError, cw.cs.GitError) as exc:
        result = dict(_AUTHORITY_FALSE)
        result.update({
            "ok": False,
            "action": args.action,
            "coordination_only": True,
            "reason": str(exc),
        })
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
