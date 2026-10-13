# SPDX-License-Identifier: Apache-2.0
"""Compose one joint-unit admission repair into the current native seller.

This is not the legacy V4 materializer. It changes only unit replay; market
prefix, admission, objectives, clocks, deadlines and feature defaults stay put.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

SCHEDULER_BLOB = "a483b24dd72b580d7d8811636b54d2d44f391575"
FROZEN_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"

HELPER = '''def apply_projected_units(farm, private, action, board_size, day,
                          turns_per_day, shed_capacity):
    """Replay one unit phase, including the interpreter's joint seed gate.

    Caller owns the detached projection. Count every raw list PLANT request,
    including requests from nonexistent hands and impossible planting tiles.
    Do not normalize, truncate or mutate the authored action vector.
    """
    action = action if isinstance(action, dict) else {}
    farmer = action.get("farmer", ["PASS"])
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        hands = []
    actions = [farmer, *hands]
    seeds = private.get("seeds", {}) if hasattr(private, "get") else {}
    demand = {}
    for command in actions:
        if isinstance(command, list) and len(command) >= 2 and command[0] == "PLANT":
            crop = command[1]
            demand[crop] = demand.get(crop, 0) + 1
    blocked = {crop for crop, count in demand.items() if count > seeds.get(crop, 0)}
    for index, command in enumerate(actions):
        if (isinstance(command, list) and len(command) >= 2
                and command[0] == "PLANT" and command[1] in blocked):
            command = ["PASS"]
        m._apply_unit_action(farm, private, index, command, board_size, day,
                             turns_per_day, shed_capacity)


'''

POST_OLD = '''    acts = [action.get('farmer',['PASS']), *action.get('hands',[])]
    demand = {}
    for a in acts:
        if a and a[0]=='PLANT' and len(a)>1:
            demand[a[1]]=demand.get(a[1],0)+1
    blocked={p for p,n in demand.items() if n>private['seeds'].get(p,0)}
    capacity=int(config.get('shedCapacity',100)) if shed_capacity is None else int(shed_capacity)
    for i,a in enumerate(acts):
        if a and a[0]=='PLANT' and a[1] in blocked:a=['PASS']
        m._apply_unit_action(farm,private,i,a,len(farm['tiles']),int(obs['step'])//int(config.get('turnsPerDay',24)),int(config.get('turnsPerDay',24)),capacity)
'''
POST_NEW = '''    capacity=int(config.get('shedCapacity',100)) if shed_capacity is None else int(shed_capacity)
    apply_projected_units(farm,private,action,len(farm['tiles']),
                          int(obs['step'])//int(config.get('turnsPerDay',24)),
                          int(config.get('turnsPerDay',24)),capacity)
'''
RECEIPT_OLD = '''                acts=[act.get('farmer',['PASS']),*act.get('hands',[])]
                for i,a in enumerate(acts):
                    m._apply_unit_action(f,p,i,a,len(f['tiles']),t//24,24,10**6)
'''
RECEIPT_NEW = '''                apply_projected_units(f,p,act,len(f['tiles']),t//24,24,10**6)
'''
FUNDING_OLD = '''            acts = [action.get('farmer', ['PASS']), *action.get('hands', [])]
            for i, a in enumerate(acts):
                m._apply_unit_action(f, p, i, a, len(f['tiles']), t // 24, 24, 10**6)
'''
FUNDING_NEW = '''            apply_projected_units(f, p, action, len(f['tiles']), t // 24, 24, 10**6)
'''
EVENT_OLD = '''        acts=[action.get('farmer',['PASS']),*action.get('hands',[])]
        for i,a in enumerate(acts):
            m._apply_unit_action(
                f,p,i,a,size,t//turns_per_day,turns_per_day,10**6)
'''
EVENT_NEW = '''        apply_projected_units(f,p,action,size,t//turns_per_day,turns_per_day,10**6)
'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Unit-replay source anchor is missing or ambiguous")
    return source.replace(old, new, 1)


def compose_sources(scheduler: str, frozen: str) -> tuple[str, str]:
    """Preserve all bytes outside four known seams and one new helper.

    Other repairs may compose first when these exact seams remain unchanged.
    Partial/repeated application fails rather than silently mixing versions.
    """
    ast.parse(scheduler)
    ast.parse(frozen)
    if "apply_projected_units" in scheduler or "apply_projected_units" in frozen:
        raise ValueError("Joint-unit repair already present or partly composed")
    if frozen.count("from scheduler import *") != 1:
        raise ValueError("Native frozen seller no longer imports scheduler helpers")
    scheduler = _replace_once(scheduler, POST_OLD, POST_NEW)
    scheduler = _replace_once(scheduler, RECEIPT_OLD, RECEIPT_NEW)
    scheduler = _replace_once(scheduler, "def post_units(", HELPER + "def post_units(")
    frozen = _replace_once(frozen, FUNDING_OLD, FUNDING_NEW)
    frozen = _replace_once(frozen, EVENT_OLD, EVENT_NEW)
    compile(scheduler, "scheduler.py", "exec")
    compile(frozen, "frozen_selected.py", "exec")
    return scheduler, frozen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="New directory for two composed source files; not a release")
    parser.add_argument("--scheduler-blob", default=SCHEDULER_BLOB)
    parser.add_argument("--frozen-blob", default=FROZEN_BLOB)
    args = parser.parse_args()
    names = ("scheduler.py", "frozen_selected.py")
    inputs = [(args.package / name).read_bytes() for name in names]
    expected = (args.scheduler_blob, args.frozen_blob)
    for name, data, pin in zip(names, inputs, expected):
        if git_blob(data) != pin:
            raise SystemExit(f"{name}: input blob does not match explicit pin {pin}")
    outputs = compose_sources(*(data.decode("utf-8") for data in inputs))
    # Never overwrite a runtime or earlier output. All checks precede creation.
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"scope": "native-unit-replay-only", "release_authorized": False, "files": {}}
    for name, before, text in zip(names, inputs, outputs):
        data = text.encode("utf-8")
        (args.output / name).write_bytes(data)
        receipt["files"][name] = {"before": git_blob(before), "after": git_blob(data),
                                  "sha256": hashlib.sha256(data).hexdigest()}
    (args.output / "UNIT-PROJECTION.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
