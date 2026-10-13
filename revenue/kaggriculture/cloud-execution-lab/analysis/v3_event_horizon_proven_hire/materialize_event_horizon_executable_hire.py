#!/usr/bin/env python3
"""Materialize a sound lower-bound HIRE simulation for SELL event horizons.

The represented-horizon simulator sees authored market intent, not official
execution receipts.  The predecessor unconditionally manufactures a hand for
every HIRE.  This source-bound carrier spawns a represented hand only when the
copied farm's conservative cash lower bound proves that the HIRE must execute.
It does not alter emitted orders or canonical files in place.
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

OLD_SIGNATURE: Final = "def apply_represented_market(farm, private, orders, size):"
NEW_SIGNATURE: Final = "def apply_represented_market(farm, private, orders, size, config):"

OLD_BUY_BRANCH: Final = """        elif order[0] in ('BUY_PRODUCT','BUY_ANIMAL') and len(order)>2:
            private['shed'][order[1]]=private['shed'].get(order[1],0)+max(0,int(order[2]))
"""

NEW_BUY_BRANCH: Final = """        elif order[0] in ('BUY_PRODUCT','BUY_ANIMAL') and len(order)>2:
            quantity=max(0,int(order[2]))
            private['shed'][order[1]]=private['shed'].get(order[1],0)+quantity
            if quantity>0:
                # This helper has no fill/price receipt for represented buys.
                # Zero is a sound lower bound on cash left for a later HIRE.
                farm['money']=0
        elif order[0] in ('BUY_SEED','BUY_LAND'):
            # These rows can consume cash without changing represented shed.
            # Preserve a sound lower bound for any later HIRE in the tape.
            farm['money']=0
"""

OLD_HIRE_BRANCH: Final = """        elif order[0]=='HIRE':
            farm['hands'].append(m._spawn_hand(farm,size))
            private['inventories'].append({})
"""

NEW_HIRE_BRANCH: Final = """        elif order[0]=='HIRE':
            hires=max(0,int(farm.get('hires_today',0)))
            cost=m._hire_cost(hires,int(config.get('farmHandCostMult',1)))
            money=max(0,int(farm.get('money',0)))
            if money>=cost:
                farm['money']=money-cost
                farm['hires_today']=hires+1
                farm['hands'].append(m._spawn_hand(farm,size))
                private['inventories'].append({})
"""

OLD_CURRENT_CALL: Final = "apply_represented_market(f,p,current_market,size)"
NEW_CURRENT_CALL: Final = "apply_represented_market(f,p,current_market,size,config)"
OLD_FUTURE_CALL: Final = "apply_represented_market(f,p,action.get('market',[]),size)"
NEW_FUTURE_CALL: Final = "apply_represented_market(f,p,action.get('market',[]),size,config)"

REQUIRED_REACH_FRAGMENTS: Final = (
    "unit_event=(represented_shed_event(",
    "end=max(end,unit_event)",
    "price = m._hire_cost(hires, int(config.get('farmHandCostMult', 1)))",
)


def git_blob_sha1(data: bytes) -> str:
    """Return Git's SHA-1 identity for one blob."""
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"expected exactly one {label}; found {source.count(old)}")
    return source.replace(old, new, 1)


def materialize(source: str) -> str:
    """Apply the bounded closure, failing closed on source or reach drift."""
    encoded = source.encode("utf-8")
    actual = git_blob_sha1(encoded)
    if actual != SOURCE_GIT_BLOB_SHA1:
        raise ValueError(
            f"source drift: expected git blob {SOURCE_GIT_BLOB_SHA1}, got {actual}"
        )
    for fragment in REQUIRED_REACH_FRAGMENTS:
        if fragment not in source:
            raise ValueError(f"missing score-path/native-oracle fragment: {fragment!r}")

    candidate = source
    candidate = _replace_once(candidate, OLD_SIGNATURE, NEW_SIGNATURE, "helper signature")
    candidate = _replace_once(candidate, OLD_BUY_BRANCH, NEW_BUY_BRANCH, "buy branch")
    candidate = _replace_once(candidate, OLD_HIRE_BRANCH, NEW_HIRE_BRANCH, "HIRE branch")
    candidate = _replace_once(candidate, OLD_CURRENT_CALL, NEW_CURRENT_CALL, "current call")
    candidate = _replace_once(candidate, OLD_FUTURE_CALL, NEW_FUTURE_CALL, "future call")

    for old in (OLD_SIGNATURE, OLD_BUY_BRANCH, OLD_HIRE_BRANCH,
                OLD_CURRENT_CALL, OLD_FUTURE_CALL):
        if old in candidate:
            raise AssertionError("candidate retained a predecessor anchor")
    for new in (NEW_SIGNATURE, NEW_BUY_BRANCH, NEW_HIRE_BRANCH,
                NEW_CURRENT_CALL, NEW_FUTURE_CALL):
        if candidate.count(new) != 1:
            raise AssertionError("candidate replacement postcondition failed")
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
        "mutation": "represented HIRE spawns only when a conservative cash lower bound proves execution",
        "runtime_emission_changed": False,
        "soundness_boundary": "SELL credit ignored; any represented buy zeros later-HIRE cash lower bound",
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
