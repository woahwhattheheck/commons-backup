#!/usr/bin/env python3
"""Materialize a conservative FrozenSelected event-horizon HIRE closure.

The event-horizon simulator sees authored market intent before official engine
execution is known.  The predecessor unconditionally manufactures a hand for
HIRE.  This carrier removes only that unaudited simulation side effect; it does
not alter emitted market orders or canonical files in place.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Final

SOURCE_RELATIVE_PATH: Final = "revenue/kaggriculture/cloud-execution-lab/frozen_selected.py"
SOURCE_GIT_BLOB_SHA1: Final = "fc7baf5c179818a55037f6a61d92984d81d1a21c"
BASE_COMMIT: Final = "c51049d671b55d282e0fed5df37a0be7c513a838"

OLD_HIRE_BRANCH: Final = """        elif order[0]=='HIRE':
            farm['hands'].append(m._spawn_hand(farm,size))
            private['inventories'].append({})
"""

NEW_HIRE_BRANCH: Final = """        elif order[0]=='HIRE':
            # Authored HIRE is intent, not execution evidence.  This simulator
            # has neither the official row-level funding result nor enough
            # market state to prove that a hand was created.  Conservatively
            # leave actor cardinality unchanged; emitted actions are untouched.
            continue
"""

REQUIRED_REACH_FRAGMENTS: Final = (
    "apply_represented_market(f,p,current_market,size)",
    "apply_represented_market(f,p,action.get('market',[]),size)",
    "unit_event=(represented_shed_event(",
    "end=max(end,unit_event)",
)


def git_blob_sha1(data: bytes) -> str:
    """Return Git's SHA-1 identity for one blob."""
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def materialize(source: str) -> str:
    """Apply the one-branch closure, failing closed on source drift."""
    encoded = source.encode("utf-8")
    actual = git_blob_sha1(encoded)
    if actual != SOURCE_GIT_BLOB_SHA1:
        raise ValueError(
            f"source drift: expected git blob {SOURCE_GIT_BLOB_SHA1}, got {actual}"
        )
    if source.count(OLD_HIRE_BRANCH) != 1:
        raise ValueError("expected exactly one predecessor HIRE branch")
    for fragment in REQUIRED_REACH_FRAGMENTS:
        if fragment not in source:
            raise ValueError(f"missing score-path reach fragment: {fragment!r}")
    candidate = source.replace(OLD_HIRE_BRANCH, NEW_HIRE_BRANCH, 1)
    if OLD_HIRE_BRANCH in candidate or candidate.count(NEW_HIRE_BRANCH) != 1:
        raise AssertionError("candidate replacement contract failed")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    source = source_bytes.decode("utf-8")
    candidate = materialize(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(candidate, encoding="utf-8", newline="\n")

    receipt = {
        "admission": "HOLD_FOR_PAIRED_PANEL",
        "base_commit": BASE_COMMIT,
        "source_path": SOURCE_RELATIVE_PATH,
        "source_git_blob_sha1": git_blob_sha1(source_bytes),
        "candidate_git_blob_sha1": git_blob_sha1(candidate.encode("utf-8")),
        "mutation": "represented market HIRE no longer manufactures an unexecuted hand",
        "runtime_emission_changed": False,
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
