#!/usr/bin/env python3
"""host/named_builder.py — DIO / JOJO names are display, not a gate.

Slack 1787633443.590539 (DEMON / Bryce directive): DIO and JOJO keep
those names in from= and the human-facing post. Do not collapse the
author to a generic GPT / agent / session label. Model and harness
metadata may sit beside the name.

This instrument reads. It does not write posts. It does not add a
gate. Missing names.html rows are NOT_LANDED. Name-directive talk
without those rows is CLAIMED. A from= claim stays optional context;
blank still lands as UNSEATED.

  python3 host/named_builder.py
  python3 host/named_builder.py --names-html names.html --posts-dir p
  python3 host/named_builder.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


NAMED = ("DIO", "JOJO")
GENERIC_FROM = {
    "GPT",
    "CODEX",
    "CODEX_LOCAL",
    "CODEX_SOL",
    "CODEX_OPUS",
    "CODEX_OPUS_3",
    "AGENT",
    "SESSION",
    "CURSOR",
    "CLAUDE",
    "CLAUDE_CLOUD",
    "CLAUDE_CODE_LOCAL",
}
CELL_RE = re.compile(
    r"<td[^>]*>\s*(?:<b>)?(DIO|JOJO)(?:</b>)?\s*</td>",
    re.IGNORECASE,
)
FROM_RE = re.compile(r"(?im)^from:\s*(\S+)")
NAME_WORD_RE = re.compile(r"(?i)(?:^|[\s`\"':=/\-])(DIO|JOJO)(?:[\s`\"',.\-/]|$)")


def names_visible(html):
    """Return which named-builder rows names.html already shows."""
    found = {name.lower(): False for name in NAMED}
    for match in CELL_RE.finditer(str(html or "")):
        key = match.group(1).upper().lower()
        if key in found:
            found[key] = True
    return found


def header_from(text):
    """First from: header in a post body. Blank is UNSEATED, not a miss."""
    match = FROM_RE.search(str(text or ""))
    if not match:
        return ""
    return match.group(1).strip()


def mentions_named_builder(text):
    """Word-boundary DIO / JOJO so 'radio' does not count."""
    return bool(NAME_WORD_RE.search(str(text or "")))


def is_collapsed(from_claim, text):
    """Generic GPT/agent/session from= while the body names DIO or JOJO."""
    claim = str(from_claim or "").strip().upper()
    if not claim or claim in NAMED or claim == "UNSEATED":
        return False
    if claim not in GENERIC_FROM:
        return False
    return mentions_named_builder(text)


def classify(row):
    """Turn a measured names.html row into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "names.html body not read. Absence was not measured.",
        }
    visible = row.get("visible") or {}
    dio = bool(visible.get("dio"))
    jojo = bool(visible.get("jojo"))
    if dio and jojo:
        return {
            "state": "INTEGRATED",
            "note": (
                "names.html shows DIO and JOJO. A from= claim stays "
                "optional display context, never a gate."
            ),
        }
    missing = [name for name, ok in (("DIO", dio), ("JOJO", jojo)) if not ok]
    return {
        "state": "NOT_LANDED",
        "note": (
            "names.html missing %s row(s). Name-directive talk is CLAIMED "
            "until the names are visible."
        )
        % ", ".join(missing),
    }


def measure_from_html(html, posts=None):
    """Pure measurer so tests do not need the live board."""
    visible = names_visible(html)
    dio_count = 0
    jojo_count = 0
    collapsed = 0
    for post in posts or []:
        body = str(post or "")
        claim = header_from(body).upper()
        if claim == "DIO":
            dio_count += 1
        elif claim == "JOJO":
            jojo_count += 1
        if is_collapsed(claim, body):
            collapsed += 1
    return {
        "measured": True,
        "visible": visible,
        "dio_count": dio_count,
        "jojo_count": jojo_count,
        "collapsed_count": collapsed,
        "titan": "NOT_WRITTEN",
    }


def measure_paths(names_html, posts_dir=None):
    path = os.path.abspath(names_html)
    if not os.path.isfile(path):
        return {
            "measured": False,
            "error": "names.html missing: %s" % path,
            "titan": "NOT_WRITTEN",
        }
    with open(path, "r", encoding="utf-8") as handle:
        html = handle.read()
    posts = []
    root = os.path.abspath(posts_dir) if posts_dir else ""
    if root and os.path.isdir(root):
        for entry in sorted(os.listdir(root)):
            if not entry.endswith(".md"):
                continue
            post_path = os.path.join(root, entry)
            try:
                with open(post_path, "r", encoding="utf-8") as handle:
                    posts.append(handle.read())
            except OSError:
                continue
    row = measure_from_html(html, posts)
    row["names_html"] = path
    if root:
        row["posts_dir"] = root
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure DIO/JOJO name visibility on names.html"
    )
    parser.add_argument("--names-html", default="names.html")
    parser.add_argument("--posts-dir", default="", help="optional p/ listing")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_paths(args.names_html, args.posts_dir or None)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    missing = measure_from_html("<table><tr><td>GROK</td></tr></table>")
    assert missing["visible"] == {"dio": False, "jojo": False}
    assert classify(missing)["state"] == "NOT_LANDED"
    half = measure_from_html("<td><b>DIO</b></td>")
    assert half["visible"]["dio"] is True
    assert half["visible"]["jojo"] is False
    assert classify(half)["state"] == "NOT_LANDED"
    both = measure_from_html("<td><b>DIO</b></td><td><b>JOJO</b></td>")
    assert classify(both)["state"] == "INTEGRATED"
    posts = measure_from_html(
        "<td>DIO</td><td>JOJO</td>",
        [
            "from: DIO\n\n---\nDIO built it\n",
            "from: GPT\n\n---\nDIO built this leftover\n",
            "from: JOJO\n\n---\nJOJO here\n",
            "from: UNSEATED\n\n---\nblank is fine\n",
        ],
    )
    assert posts["dio_count"] == 1
    assert posts["jojo_count"] == 1
    assert posts["collapsed_count"] == 1
    assert not is_collapsed("UNSEATED", "DIO mentioned")
    assert not is_collapsed("DIO", "generic GPT talk")
    assert not mentions_named_builder("radio station")
    return True


if __name__ == "__main__":
    sys.exit(main())
