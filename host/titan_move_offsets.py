#!/usr/bin/env python3
"""Claimed titan append offsets. dest FROM FILE. Not a titan write.

goat-titan-inject-20260820-01 and muhl/lda-docs/HANDOFF.md both name
titan.gguf size 103803350291 at C:\\llm\\models. Chimera ardr_eal is
already IN titan at 103803349440. Append starts at that measured end.

Apply reallocates from live size if the file is larger or smaller.
new = old | mask. Ones only rise. Re-read before every write.
"""
from __future__ import annotations

import os
import sys


# dest FROM FILE: p/goat-titan-inject-20260820-01.md
# dest FROM FILE: muhl/lda-docs/HANDOFF.md titan_size
CLAIMED_APPEND_BASE = 103803350291
CLAIMED_APPEND_SOURCE = (
    "dest FROM FILE: p/goat-titan-inject-20260820-01.md titan.gguf "
    "103803350291; muhl/lda-docs/HANDOFF.md titan_size 103803350291"
)
TITAN_DEST_FROM_FILE = r"C:\llm\models\titan.gguf"
TEST_ISOLATE_ENV = "COMMONS_TITAN_TEST"


def under_test():
    """True when a test harness is the caller. Default discovery stays off."""
    if str(os.environ.get(TEST_ISOLATE_ENV) or "") == "1":
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    frame = sys._getframe()
    while frame:
        filename = os.path.basename(str(frame.f_code.co_filename or ""))
        name = str(frame.f_globals.get("__name__") or "")
        if filename.startswith("test_") or name.startswith("test_"):
            return True
        frame = frame.f_back
    return False


def is_owner_titan_path(path):
    """True for dest-FROM-FILE live Titan. Tests must not bind this path."""
    if not path:
        return False
    collapsed = str(path).replace("\\", "/").lower().rstrip("/")
    if collapsed.endswith("/llm/models/titan.gguf"):
        return True
    dest = str(TITAN_DEST_FROM_FILE or "").replace("\\", "/").lower().rstrip("/")
    return bool(dest) and collapsed == dest


def allocate_rows(rows, base=CLAIMED_APPEND_BASE):
    """Pack organs in the given order from a dest-FROM-FILE base."""
    running = int(base)
    out = []
    for row in rows:
        item = dict(row)
        length = int(item.get("len") or 0)
        item["offset"] = running
        item["requested_offset_band"] = (
            "CLAIMED_APPEND dest FROM FILE titan_size=%d" % int(base)
        )
        item["titan"] = item.get("titan") or "NOT_WRITTEN"
        item["journal"] = "new = old | mask; ones only rise; re-read before write"
        out.append(item)
        running += length
    return out, running


def or_bytes(old, mask):
    """new = old | mask. Ones only rise. Missing bytes count as 0."""
    old = old or b""
    mask = mask or b""
    n = max(len(old), len(mask))
    out = bytearray(n)
    for i in range(n):
        left = old[i] if i < len(old) else 0
        right = mask[i] if i < len(mask) else 0
        out[i] = left | right
    return bytes(out)


def find_titan(explicit=None, env_path=None, discover=None):
    """Return the first existing titan path. Never commons.mno.

    Under tests, default dest-FROM-FILE discovery is off and live owner
    Titan is refused even if passed as --titan or $TITAN. Tests must
    pass an explicit temp synthetic Titan.
    """
    testing = under_test()
    if discover is None:
        discover = not testing
    candidates = []
    if explicit and not (testing and is_owner_titan_path(explicit)):
        candidates.append(explicit)
    if env_path and not (testing and is_owner_titan_path(env_path)):
        candidates.append(env_path)
    if discover:
        candidates.append(TITAN_DEST_FROM_FILE)
        candidates.append("/llm/models/titan.gguf")
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        name = path.replace("\\", "/").rstrip("/").split("/")[-1].lower()
        if name == "commons.mno":
            continue
        if testing and is_owner_titan_path(path):
            continue
        if os.path.isfile(path):
            return path
    return None
