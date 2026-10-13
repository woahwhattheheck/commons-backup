#!/usr/bin/env python3
"""F2 broad-spine helper-only player-domain custody repair.

Input authority: r04_feed_prebuy.py blob
4d48168dac0ee06d0c7e62cfdb99c99c402f3812 (b774 broad donor spine).

Apply this to the helper only, then add focused regression blob
7c635ae22a819509249ace3e607e0500799de3c3 at
`overlay/checks/test_v4_f2_player_domain.py`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

EXPECTED = "4d48168dac0ee06d0c7e62cfdb99c99c402f3812"
OLD = '''    if type(player) is not int or not isinstance(farms, list) or not 0 <= player < len(farms):
        return False
'''
NEW = '''    if (type(player) is not int or player not in (0, 1)
            or not isinstance(farms, list) or not 0 <= player < len(farms)):
        return False
'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_f2_player_domain_broad.py r04_feed_prebuy.py")
    path = Path(sys.argv[1])
    data = path.read_bytes()
    if git_blob(data) != EXPECTED:
        raise SystemExit("wrong F2 broad helper authority; re-CAS before use")
    text = data.decode("utf-8")
    if text.count(OLD) != 1:
        raise SystemExit("F2 player-domain anchor count != 1")
    out = text.replace(OLD, NEW, 1)
    if out.count("player not in (0, 1)") != 1:
        raise SystemExit("F2 player-domain postcondition failed")
    if "len(farms) == 2" in out or "len(farms) != 2" in out:
        raise SystemExit("must not impose farm-list cardinality")
    path.write_text(out, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
