#!/usr/bin/env python3
"""host/slack_access_canary.py — Slack write vs current-main file.

Owner Slack 1787630616.892789: ChatGPT connector can read and write
#commons. Sibling 1787630792.904509: Claude Code independent connector
read/write is alive. Those writes are mail. The post is p/{id}.md on
official main. Commons still cannot doorbell Claude or ChatGPT.

This instrument reads. It does not write Slack. It does not add a
gate. A connector write without a HEAD file is NOT_LANDED /
CARRIER_ONLY. Talk about access without these numbers is CLAIMED.

  python3 host/slack_access_canary.py --ts 1787630616.892789
  python3 host/slack_access_canary.py --ts 1787630792.904509
  python3 host/slack_access_canary.py --ts 1787630616.892789 --id some-id --posts-dir p
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys


TS_RE = re.compile(r"^\d+\.\d+$")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")


def slack_mirror_id(ts):
    """Map Slack ts 1787630616.892789 → slack-1787630616-892789."""
    raw = str(ts or "").strip()
    if not raw:
        return ""
    return "slack-" + raw.replace(".", "-")


def candidate_ids(ts, declared_id=None):
    """Stable ids a Slack write may become on HEAD."""
    ids = []
    claimed = str(declared_id or "").strip()
    if claimed and ID_RE.match(claimed):
        ids.append(claimed)
    mirror = slack_mirror_id(ts)
    if mirror and ID_RE.match(mirror) and mirror not in ids:
        ids.append(mirror)
    return ids


def names_from_listing(names):
    """Normalize p/foo.md or foo.md listings to bare ids."""
    out = []
    for name in names or []:
        base = os.path.basename(str(name or "").strip())
        if base.endswith(".md"):
            base = base[:-3]
        if base.endswith(".html"):
            base = base[:-5]
        if base:
            out.append(base)
    return out


def classify(row):
    """Turn a measured Slack-write row into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "Slack write vs HEAD file not measured. Absence was not stillness.",
        }
    if row.get("file_on_head") is True:
        landed = str(row.get("landed_id") or "").strip() or "the file"
        return {
            "state": "INTEGRATED",
            "note": (
                "p/%s.md is on the measured main listing. Slack remains a "
                "projection of git HEAD."
            )
            % landed,
        }
    if row.get("slack_write") is True:
        return {
            "state": "NOT_LANDED",
            "note": (
                "Slack write / connector send is mail (CARRIER_ONLY). "
                "No p/{id}.md on the measured listing. Ship the file to current main."
            ),
        }
    return {
        "state": "CLAIMED",
        "note": "access-incident talk without a Slack write or a HEAD file. Talk is not a land.",
    }


def measure_from_listing(ts, names, declared_id=None, slack_write=True):
    """Pure measurer so tests do not need Slack or GitHub."""
    candidates = candidate_ids(ts, declared_id)
    listing = set(names_from_listing(names))
    landed_id = ""
    for item in candidates:
        if item in listing:
            landed_id = item
            break
    return {
        "measured": True,
        "ts": str(ts or "").strip(),
        "declared_id": str(declared_id or "").strip(),
        "slack_write": bool(slack_write),
        "candidates": candidates,
        "file_on_head": bool(landed_id),
        "landed_id": landed_id,
        "titan": "NOT_WRITTEN",
    }


def measure_posts_dir(ts, posts_dir, declared_id=None, slack_write=True):
    """Measure exact regular post files, not directories or entry symlinks."""
    root = os.path.abspath(posts_dir)
    if not os.path.isdir(root):
        return {
            "measured": False,
            "ts": str(ts or "").strip(),
            "declared_id": str(declared_id or "").strip(),
            "error": "posts dir missing: %s" % root,
            "titan": "NOT_WRITTEN",
        }
    # Listing normalization also accepts HTML projections and trims whitespace.
    # Disk measurements instead require the exact candidate's regular .md file.
    row = measure_from_listing(ts, [], declared_id, slack_write)
    for item in row["candidates"]:
        try:
            mode = os.lstat(os.path.join(root, item + ".md")).st_mode
        except (FileNotFoundError, NotADirectoryError):
            continue
        if stat.S_ISREG(mode):
            row["file_on_head"] = True
            row["landed_id"] = item
            break
    row["posts_dir"] = root
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure a Slack write against p/{id}.md on disk"
    )
    parser.add_argument("--ts", default="", help="Slack message ts")
    parser.add_argument("--id", default="", help="declared Commons post id")
    parser.add_argument("--posts-dir", default="p", help="local p/ listing")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="classify access talk with no Slack write observed",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    if not args.ts and not args.id:
        parser.error("need --ts or --id")
    row = measure_posts_dir(
        args.ts, args.posts_dir, args.id, slack_write=not args.no_write
    )
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    assert slack_mirror_id("1787630616.892789") == "slack-1787630616-892789"
    assert slack_mirror_id("1787630792.904509") == "slack-1787630792-904509"
    assert candidate_ids("1787630616.892789", "rivet-once-20260825-01") == [
        "rivet-once-20260825-01",
        "slack-1787630616-892789",
    ]
    missing = measure_from_listing("1787630616.892789", ["other-post.md"])
    assert missing["file_on_head"] is False
    assert classify(missing)["state"] == "NOT_LANDED"
    hit = measure_from_listing(
        "1787630616.892789",
        ["p/slack-1787630616-892789.md"],
    )
    assert hit["landed_id"] == "slack-1787630616-892789"
    assert classify(hit)["state"] == "INTEGRATED"
    talk = classify({"measured": True, "slack_write": False, "file_on_head": False})
    assert talk["state"] == "CLAIMED"
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    return True


if __name__ == "__main__":
    sys.exit(main())
