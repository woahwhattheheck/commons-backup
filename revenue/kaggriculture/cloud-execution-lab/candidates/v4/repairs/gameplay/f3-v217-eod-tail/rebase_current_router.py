#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebase #12613 V217 EOD-tail semantics onto the current canonical donor.

This transformer is intentionally source-pinned and activation-inert.  It adds
an ``eod_tail_enabled`` parameter to the current V217 planner, but the live
caller inserted by this transform passes ``False``.  A later, separately
validated feature-wiring change is required before gameplay can use the lane.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from pathlib import Path

SOURCE_GIT_BLOB = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"

HELPER_ANCHOR = """\
def _v217_farmer(tape, step):
    return list(tape[step].get('farmer') or ['PASS'])

def _v217_plan(view, st, step, action, pending):
"""

HELPER_REPLACEMENT = """\
def _v217_farmer(tape, step):
    return list(tape[step].get('farmer') or ['PASS'])

def _v217_standard_configuration(configuration):
    def read(name):
        if isinstance(configuration, dict):
            return configuration.get(name)
        return getattr(configuration, name, None) if configuration is not None else None
    for name, expected in (('episodeSteps',720),('turnsPerDay',24),('boardSize',10),
                           ('shedCapacity',100),('maxMarketOrdersPerTurn',10)):
        value=read(name)
        if type(value) is not int or value!=expected:
            return False
    return True

def _v217_plan(view, st, step, action, pending, configuration=None, eod_tail_enabled=False):
"""

PLAN_OLD = """\
        opposite = {'EAST':'WEST','WEST':'EAST','NORTH':'SOUTH','SOUTH':'NORTH'}
        commands = ([['PICKUP','WHEAT']] if need_pickup else []) + [[m] for m in moves] + [['FEED']] + [[opposite[m]] for m in reversed(moves)]
        if len(commands) > end-step or any(_v217_farmer(tape, step+i) != ['PASS'] for i in range(len(commands))):
            continue
        positions = []
        pos = start
        for cmd in commands:
            positions.append(pos)
            if cmd[0] in _V217_MOVES:
                dx, dy = _V217_MOVES[cmd[0]]
                pos = (pos[0]+dx, pos[1]+dy)
        assert pos == start
        return {'step':step, 'route':st.get('plan'), 'commands':commands,
                'positions':positions, 'target':(x,y)}
"""

PLAN_NEW = """\
        opposite = {'EAST':'WEST','WEST':'EAST','NORTH':'SOUTH','SOUTH':'NORTH'}
        forward = ([['PICKUP','WHEAT']] if need_pickup else []) + [[m] for m in moves] + [['FEED']]
        roundtrip = forward + [[opposite[m]] for m in reversed(moves)]
        # The official engine resets the farmer at the nightly boundary.  Take
        # reset credit only when FEED itself occupies the final pre-reset
        # callback; otherwise a later callback can observe the displaced farmer.
        # Existing round trips are never shortened and day 29 has no reset
        # credit.  The caller remains hard-OFF until a later activation gate.
        eod_tail = (eod_tail_enabled and _v217_standard_configuration(configuration)
                    and len(targets) == 1 and end < 719
                    and len(forward) == end-step < len(roundtrip)
                    and all(_v217_farmer(tape, future_step) == ['PASS']
                            for future_step in range(step, end)))
        commands = forward if eod_tail else roundtrip
        if len(commands) > end-step or any(_v217_farmer(tape, step+i) != ['PASS'] for i in range(len(commands))):
            continue
        positions = []
        pos = start
        for cmd in commands:
            positions.append(pos)
            if cmd[0] in _V217_MOVES:
                dx, dy = _V217_MOVES[cmd[0]]
                pos = (pos[0]+dx, pos[1]+dy)
        if eod_tail:
            assert pos == (x, y)
        else:
            assert pos == start
        return {'step':step, 'route':st.get('plan'), 'commands':commands,
                'positions':positions, 'target':(x,y), 'eod_tail':eod_tail}
"""

CALL_OLD = "        task=_v217_plan(view,st,step,action,pending)\n"
CALL_NEW = "        task=_v217_plan(view,st,step,action,pending,configuration,False)\n"


class RebaseError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RebaseError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def transform(source: str) -> str:
    if "def _v217_standard_configuration(" in source or "eod_tail_enabled" in source:
        raise RebaseError("V217 EOD-tail seam already present")
    out = _replace_once(source, HELPER_ANCHOR, HELPER_REPLACEMENT, "planner signature/helper")
    out = _replace_once(out, PLAN_OLD, PLAN_NEW, "planner command block")
    out = _replace_once(out, CALL_OLD, CALL_NEW, "live caller")
    if out.count("eod_tail_enabled and _v217_standard_configuration(configuration)") != 1:
        raise RebaseError("EOD-tail theorem cardinality drift")
    if out.count("_v217_plan(view,st,step,action,pending,configuration,False)") != 1:
        raise RebaseError("live caller is not hard-OFF exactly once")
    ast.parse(out, filename="<v217-eod-tail-current-router>")
    return out


def materialize(source_bytes: bytes) -> bytes:
    if git_blob_sha(source_bytes) != SOURCE_GIT_BLOB:
        raise RebaseError("current donor router Git blob mismatch")
    return transform(source_bytes.decode("utf-8")).encode("utf-8")


def self_test() -> None:
    fixture = (
        "_V217_MOVES={'EAST':(1,0),'WEST':(-1,0),'NORTH':(0,-1),'SOUTH':(0,1)}\n"
        + HELPER_ANCHOR
        + "    targets=[]\n"
          "    start=(0,0)\n"
          "    need_pickup=False\n"
          "    tape=[]\n"
          "    end=0\n"
          "    for distance, y, x in []:\n"
        + PLAN_OLD
        + "    return None\n\n"
          "def caller(view,st,step,action,pending,configuration):\n"
          "    if True:\n"
        + CALL_OLD
        + "    return task\n"
    )
    post = transform(fixture)
    compile(post, "<v217-eod-tail-self-test>", "exec")
    if post.count("configuration,False") != 1:
        raise AssertionError("self-test: live call is not uniquely hard-OFF")
    try:
        transform(post)
    except RebaseError:
        pass
    else:
        raise AssertionError("self-test: double apply must fail closed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("output", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.source is None or args.output is None:
        parser.error("source and output are required unless --self-test is used")
    before = args.source.read_bytes()
    candidate = materialize(before)
    if args.source.resolve(strict=False) == args.output.resolve(strict=False):
        raise RebaseError("output must not alias source")
    args.output.write_bytes(candidate)
    if args.source.read_bytes() != before:
        args.output.unlink(missing_ok=True)
        raise RebaseError("source mutated during materialization")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
