#!/usr/bin/env python3
"""Regression for OSPREY fixture-spec permission-workflow phrasing.

Companion for the open-door-guard workflow matrix. Run 35452670467 /
SHA 6a0a7e808ff1235a7c5cc5f64c936cba3cb2f924 / PR 16327. Forbidden
phrase is split across source lines so this file is not itself a lock.
"""

from pathlib import Path

import open_door_guard as guard


def diff(path, added=(), removed=()):
    lines = [
        f"diff --git a/{path} b/{path}",
        f"--- a/{path}",
        f"+++ b/{path}",
        f"@@ -1,{max(1, len(removed))} +1,{max(1, len(added))} @@",
    ]
    lines.extend(f"-{line}" for line in removed)
    lines.extend(f"+{line}" for line in added)
    return "\n".join(lines) + "\n"


def rules(text):
    return {item.rule for item in guard.scan_diff(text)}


def check():
    path = "revenue/uiowa_rfq_18649_testdata_osprey/FIXTURE_SPECIFICATIONS.md"
    blocked_line = (
        "roles, approval"
        " workflows, or real privilege semantics. Absence of a role in the"
    )
    found = rules(diff(path, [blocked_line]))
    assert found == {"permission-workflow"}, found
    allowed_line = (
        "roles, sequential sign-off processes, or real privilege semantics. "
        "Absence of a role in the"
    )
    allowed = diff(path, [allowed_line])
    assert guard.scan_diff(allowed) == [], guard.scan_diff(allowed)
    live = Path(path)
    live_lines = [
        guard.AddedLine(live.as_posix(), line_number, text)
        for line_number, text in enumerate(live.read_text(encoding="utf-8").splitlines(), 1)
    ]
    assert guard.scan_added(live_lines) == []
    self_lines = [
        guard.AddedLine(Path(__file__).name, line_number, text)
        for line_number, text in enumerate(
            Path(__file__).read_text(encoding="utf-8").splitlines(), 1
        )
    ]
    assert guard.scan_added(self_lines) == []


if __name__ == "__main__":
    check()
    print(
        "OPEN DOOR OSPREY FIXTURE TEST: permission-workflow phrase still blocked; "
        "rewritten live line passes"
    )
