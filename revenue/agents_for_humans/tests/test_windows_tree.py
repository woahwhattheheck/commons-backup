"""Windows checkout contract: the git tree must not contain NTFS-illegal paths.

autopsy-agent runs on windows-latest. Git rejects checkout when any tracked
path contains a character Windows cannot name, so the contracts never run.
This scan uses ls-tree (object names, not the working copy) so the same
check is valid after a successful checkout.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ILLEGAL_COMPONENT = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_STEM = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\$|CONOUT\$|CLOCK\$)(\.|$)',
    re.I,
)


def git_root() -> Path:
    out = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
    )
    return Path(out.strip())


def windows_illegal_paths(names: list[str]) -> list[str]:
    bad = []
    for path in names:
        for part in path.split("/"):
            if (
                not part
                or ILLEGAL_COMPONENT.search(part)
                or part.endswith((".", " "))
                or RESERVED_STEM.match(part)
            ):
                bad.append(path)
                break
    return bad


class WindowsTreeTests(unittest.TestCase):
    def test_quoted_truncated_day_key_is_illegal(self):
        self.assertEqual(
            windows_illegal_paths(['d/"2026-09-0.html']),
            ['d/"2026-09-0.html'],
        )
        self.assertEqual(windows_illegal_paths(["d/2026-09-07.html"]), [])

    def test_git_tree_has_no_windows_illegal_paths(self):
        root = git_root()
        raw = subprocess.check_output(
            ["git", "-C", str(root), "ls-tree", "-r", "--name-only", "-z", "HEAD"],
        )
        names = [item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item]
        self.assertEqual(windows_illegal_paths(names), [])


if __name__ == "__main__":
    unittest.main()
