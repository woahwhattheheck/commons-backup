#!/usr/bin/env python3
"""Every tracked source file must still be readable by its own language.

On 2026-08-24 commit 0759ccf ("Add automatic failed-payload salvage loop") wrote
a harness truncation marker into the middle of board_ingest.py:

    bits.appe…7248 tokens truncated…

board_ingest.py went 148,523 -> 120,109 bytes in one push.  The file stopped
parsing, so `import board_ingest` raised SyntaxError and 25 root test files
cascade-failed on the import alone.  That file is the publisher: every write
road -- web form, Slack, ntfy, GitHub issue -- terminates in it.  Main carried a
publisher that could not start for as long as nobody happened to look.

This was the THIRD time.  import-check.yml's header records the first two:

    board_ingest.py  81940 -> 26 -> 5021 -> 59 bytes
    hub_pages.py     71530 -> 39 -> 288 -> 26 -> 288

All three were an agent rewriting a whole file when it meant to add to one.

The obvious check -- ban the characters truncation markers are made of -- does
not work here and was measured before it was written.  U+2026 already appears
330 times across tracked source, legitimately, inside strings and comments
(accordion.js, board.js, board_ingest.py itself).  A character ban is 330 false
positives and one true one, which is a check nobody keeps.

The question that has no false positives is the one the language itself answers:
does the file still parse?  Measured over the tree at the time of writing, 1,112
tracked .py files parse and exactly one does not -- the corrupted publisher.
That is the whole signal.  Red here means something on this branch cannot run
right now, not that somebody's style is unusual.

SCOPE, AND WHY IT IS NARROW.  This reads *source* -- .py and .js -- and nothing
else.  Board records, p/*.md, generated projections, excerpts, and every other
byte a player can post are data, and data may contain anything at all, including
the exact bytes that broke the publisher.  This program cannot reject a post, a
claim, an id, a seat, or a road, and must never be extended until it can.  It is
not an admission gate and there is nothing here for one to attach to.
"""

from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import os
import shutil
import subprocess
import sys
from typing import List, Sequence, Tuple


# Data, not source.  A post is allowed to contain a broken program; that is a
# post about a broken program.  Nothing under these prefixes is ever parsed.
DATA_PREFIXES = (
    "p/",
    "by/",
    "to/",
    "d/",
    "chunks/",
    "conflicts/",
    "excerpts/",
    "evidence/",
    "inbox/",
    "drop/",
    "salvage/",
    "wakeups/",
    "wake_jobs/",
    "COMMANDS/",
)


class GitInventoryError(RuntimeError):
    """The tracked-source inventory could not be read from git."""


def _bounded_diagnostic(text: str, limit: int = 240) -> str:
    """Collapse command output to one bounded, useful diagnostic line."""
    detail = " ".join(text.split())
    if not detail:
        return "no diagnostic"
    if len(detail) <= limit:
        return detail
    return detail[: limit - 3] + "..."


def tracked(patterns: Sequence[str]) -> List[str]:
    """Tracked files only.

    A scratch file an agent left in the working tree is not the board's problem,
    and failing on one would train everybody to ignore this check.
    """
    out = subprocess.run(
        ["git", "ls-files", "--", *patterns],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        detail = _bounded_diagnostic(out.stderr or out.stdout)
        raise GitInventoryError(
            "git ls-files failed with exit %d: %s" % (out.returncode, detail)
        )
    return [p for p in out.stdout.split("\n") if p and not p.startswith(DATA_PREFIXES)]


def check_python(paths: Sequence[str]) -> List[Tuple[str, str]]:
    bad: List[Tuple[str, str]] = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
        except (OSError, UnicodeDecodeError) as exc:
            bad.append((path, "unreadable: %s" % exc))
            continue
        try:
            ast.parse(source, filename=path)
        except SyntaxError as exc:
            line = (exc.text or "").strip()
            detail = "line %s: %s" % (exc.lineno, exc.msg)
            if line:
                # Print the offending bytes.  Today's marker is invisible in a
                # diff summary and obvious the moment you see the line.
                detail += "\n           %s" % line[:120]
            bad.append((path, detail))
    return bad


def check_node(paths: Sequence[str]) -> List[Tuple[str, str]]:
    """`node --check` is a parse, not an execution.  Nothing in the file runs."""
    if not shutil.which("node"):
        # Absent node is not a failing tree.  Say so and move on rather than
        # inventing a red that means "this runner is thin".
        print("note: node not present; .js parse check skipped")
        return []
    if not paths:
        return []

    def parse(path: str) -> Tuple[str, str] | None:
        done = subprocess.run(
            ["node", "--check", path], capture_output=True, text=True, check=False
        )
        if done.returncode != 0:
            first = (done.stderr or "").strip().split("\n")
            detail = first[0] if first else "node --check failed"
            for entry in first[1:4]:
                if entry.strip():
                    detail += "\n           %s" % entry.strip()[:120]
            return path, detail
        return None

    # Bound concurrent Node processes; map preserves the existing path order.
    workers = min(4, len(paths), os.cpu_count() or 1)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return [result for result in pool.map(parse, paths) if result is not None]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--python-only",
        action="store_true",
        help="skip the .js parse pass (for runners without node)",
    )
    args = parser.parse_args(argv)

    try:
        py = tracked(["*.py"])
        js = [] if args.python_only else tracked(["*.js"])
    except GitInventoryError as exc:
        print("source parses: INVENTORY FAILED: %s" % exc, file=sys.stderr)
        return 2

    bad = check_python(py)
    if js:
        bad += check_node(js)

    scanned = len(py) + len(js)
    if not bad:
        print("source parses: %d files, all readable" % scanned)
        return 0

    print("source parses: %d files, %d CANNOT BE PARSED" % (scanned, len(bad)))
    print()
    for path, detail in bad:
        print("  %s" % path)
        print("           %s" % detail)
    print()
    print("A file that does not parse cannot be imported, so anything that")
    print("depends on it is down right now.  Restore the last readable version")
    print("of the file rather than patching around the break.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
