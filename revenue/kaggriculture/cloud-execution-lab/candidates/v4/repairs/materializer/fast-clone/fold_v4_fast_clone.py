#!/usr/bin/env python3
"""Donor-only fold recipe: port the reviewed V3.1 R04 fast-clone into V4 apply_v4.py.

Authority / scope
-----------------
Input apply_v4.py must be exact Git blob f67f8ce7d5f5779c1fad9b1e51e3b736b02b513d
(the detached V4 chronology authority 15b2b5d2025a7c6976557b5ec3e458a3f09f412b).
The production mechanism is the reviewed #12414/#12431 patch, whose proof compared all
13 * 719 = 9,347 frozen tape actions to copy.deepcopy, checked alias detachment and
future-schema fallback, and required >=1.50x clone speedup.

This script does not touch a repo/ref. It rewrites a supplied apply_v4.py file in place
so the V4 declarative materializer installs the helper in r04_full_router.py. The active
single-tree serializer must rebase/re-CAS this recipe onto its current direct parent and
rerun the existing V4 materialization/checker gates before any ref movement.
"""
from pathlib import Path
import subprocess
import sys

EXPECTED_APPLY_V4_BLOB = "f67f8ce7d5f5779c1fad9b1e51e3b736b02b513d"

HELPER = '''_R04_JSON_SCALAR_TYPES = frozenset((str, int, float, bool, type(None)))


def _r04_is_fast_tape_action(template):
    """Return whether template is exactly the shallow-clone-safe R04 JSON action shape."""
    if (type(template) is not dict or len(template) != 3
            or "farmer" not in template or "hands" not in template or "market" not in template):
        return False
    farmer, hands, market = template["farmer"], template["hands"], template["market"]
    if type(farmer) is not list or type(hands) is not list or type(market) is not list:
        return False
    for value in farmer:
        if type(value) not in _R04_JSON_SCALAR_TYPES:
            return False
    for rows in (hands, market):
        for row in rows:
            if type(row) is not list:
                return False
            for value in row:
                if type(value) not in _R04_JSON_SCALAR_TYPES:
                    return False
    return True


def _r04_clone_tape_action(template):
    """Clone the frozen tape schema; fail closed to deepcopy for any future schema."""
    if not _r04_is_fast_tape_action(template):
        return copy.deepcopy(template)
    return {
        "farmer": list(template["farmer"]),
        "hands": [list(row) for row in template["hands"]],
        "market": [list(row) for row in template["market"]],
    }
'''


def one(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected exactly 1 anchor, found {n}")
    return text.replace(old, new)


def git_blob(path):
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: fold_v4_fast_clone.py path/to/apply_v4.py")
    path = Path(sys.argv[1])
    if git_blob(path) != EXPECTED_APPLY_V4_BLOB:
        raise SystemExit("wrong apply_v4.py authority; re-CAS recipe before use")
    text = path.read_text(encoding="utf-8")

    anchor = '    router = read("r04_full_router.py")\n'
    injected = anchor + '''    router = _replace_once(\n        router,\n        "ANIMALS = {\\\"GOOSE\\\", \\\"COW\\\", \\\"SHEEP\\\"}\\n\\n# Keys are the first two shops in their observed order; values index actions.json.\\n",\n        "ANIMALS = {\\\"GOOSE\\\", \\\"COW\\\", \\\"SHEEP\\\"}\\n\\n"\n        + ''' + repr(HELPER) + ''' +\n        "\\n# Keys are the first two shops in their observed order; values index actions.json.\\n",\n        "R04 V4 reviewed fast tape clone helper",\n    )\n    router = _replace_once(\n        router,\n        "        action = copy.deepcopy(tape[step])\\n",\n        "        action = _r04_clone_tape_action(tape[step])\\n",\n        "R04 V4 fast tape clone hot path",\n    )\n'''
    text = one(text, anchor, injected, "apply_v4 router-read seam")
    path.write_text(text, encoding="utf-8", newline="")


if __name__ == "__main__":
    main()
