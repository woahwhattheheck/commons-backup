#!/usr/bin/env python3
"""Compose the existing two-seat fail-close repair with LABORFLOW multi-detour admission.

This is an exact-source composer for the canonical TITAN V4 redundant-hire helper.
It does not modify runtime/defaults itself.  The input is pinned by the existing
`repair_redundant_hire_two_seat` transformer; this composer then lifts only the
one-productive-detour ceiling while reserving every previously certified job's
capacity, marginal market units, target and deposit tick.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
BASE_REPAIR_PATH = HERE / "repair_redundant_hire_two_seat.py"
INPUT_GIT = "9ded2a9b636793df0511103da802bd3f26dbbb94"
TWO_SEAT_GIT = "a58ba3403d89f0d9a17e56225f891f1aa81a4c8f"


def _load_base_repair():
    spec = importlib.util.spec_from_file_location("redundant_hire_two_seat_repair", BASE_REPAIR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load sibling two-seat repair")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


SIGNATURE_OLD = '''    step: int, end: int, board: int, cap: int, limit: int, reserved: set[tuple[int, int]],\n) -> dict | None:\n'''
SIGNATURE_NEW = '''    step: int, end: int, board: int, cap: int, limit: int, reserved: set[tuple[int, int]],\n    reserved_capacity: int, reserved_market_units: Mapping[str, int],\n    reserved_drop_steps: set[int],\n) -> dict | None:\n'''

CAPACITY_OLD = '''            if stock + quantity > cap or item not in inventory:\n                continue\n'''
CAPACITY_NEW = '''            if stock + reserved_capacity + quantity > cap or item not in inventory:\n                continue\n'''

DROP_OLD = '''                drop_step = step + 1 + drop_offset\n                conflict = False\n'''
DROP_NEW = '''                drop_step = step + 1 + drop_offset\n                if drop_step in reserved_drop_steps:\n                    continue\n                conflict = False\n'''

VALUE_OLD = '''                value = sum(mechanics.market_price(item, inventory[item] + q, params)\n                            for q in range(quantity))\n'''
VALUE_NEW = '''                base_inventory = inventory[item] + int(reserved_market_units.get(item, 0))\n                value = sum(mechanics.market_price(item, base_inventory + q, params)\n                            for q in range(quantity))\n'''

LOOP_OLD = '''    protected = 0; reserved: set[tuple[int, int]] = set(); detours = []\n    first_removed = 1 + existing + len(hires) - best\n    cost_start = len(hires) - best\n    for offset in range(best):\n        worker = first_removed + offset\n        witness = _productive_detour(mechanics, observation, farm, private, route, events, positions,\n                                      worker, costs[cost_start + offset], step, end,\n                                      board, cap, limit, reserved)\n        if witness is None:\n            break\n        detours.append(witness); reserved.add(tuple(witness["target"])); protected += 1\n        break\n'''
LOOP_NEW = '''    protected = 0; reserved: set[tuple[int, int]] = set(); detours = []\n    reserved_capacity = 0; reserved_market_units = Counter(); reserved_drop_steps: set[int] = set()\n    first_removed = 1 + existing + len(hires) - best\n    cost_start = len(hires) - best\n    for offset in range(best):\n        worker = first_removed + offset\n        witness = _productive_detour(mechanics, observation, farm, private, route, events, positions,\n                                      worker, costs[cost_start + offset], step, end,\n                                      board, cap, limit, reserved, reserved_capacity,\n                                      reserved_market_units, reserved_drop_steps)\n        if witness is None:\n            break\n        detours.append(witness); reserved.add(tuple(witness["target"])); protected += 1\n        reserved_capacity += int(witness["quantity"])\n        reserved_market_units[witness["item"]] += int(witness["quantity"])
        reserved_drop_steps.add(int(witness["deposit_step"]))\n'''

REPORT_OLD = '''        productive_detours=detours,\n        useful_worker_actions=sum(w["useful_worker_actions"] for w in detours),\n'''
REPORT_NEW = '''        productive_detours=detours,\n        productive_hires=protected,\n        reserved_capacity_units=reserved_capacity,\n        reserved_market_units=dict(reserved_market_units),\n        useful_worker_actions=sum(w["useful_worker_actions"] for w in detours),\n'''

_PATCHES = (
    ("productive-detour signature", SIGNATURE_OLD, SIGNATURE_NEW),
    ("cumulative capacity reservation", CAPACITY_OLD, CAPACITY_NEW),
    ("deposit-tick reservation", DROP_OLD, DROP_NEW),
    ("marginal quote reservation", VALUE_OLD, VALUE_NEW),
    ("multi-detour contiguous-prefix loop", LOOP_OLD, LOOP_NEW),
    ("reservation telemetry", REPORT_OLD, REPORT_NEW),
)


def rewrite_postimage_text(text: str) -> str:
    """Apply LABORFLOW to the exact two-seat postimage text, failing on drift."""
    out = text
    for name, old, new in _PATCHES:
        count = out.count(old)
        if count != 1:
            raise RuntimeError(f"{name}: expected exactly one anchor, found {count}")
        out = out.replace(old, new, 1)
    return out


def transform(data: bytes) -> bytes:
    actual = git_blob(data)
    if actual != INPUT_GIT:
        raise RuntimeError(f"wrong input blob: {actual}")
    base = _load_base_repair()
    if base.INPUT_GIT != INPUT_GIT or base.OUTPUT_GIT != TWO_SEAT_GIT:
        raise RuntimeError("sibling two-seat repair identity drift")
    two_seat = base.transform(data)
    if git_blob(two_seat) != TWO_SEAT_GIT:
        raise RuntimeError(f"unexpected two-seat postimage blob: {git_blob(two_seat)}")
    return rewrite_postimage_text(two_seat.decode("utf-8")).encode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=pathlib.Path)
    ap.add_argument("--output", type=pathlib.Path)
    ns = ap.parse_args()
    out = transform(ns.source.read_bytes())
    if ns.output:
        if ns.output.exists():
            raise RuntimeError(f"refusing to overwrite {ns.output}")
        ns.output.write_bytes(out)
    print(git_blob(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
