# SPDX-License-Identifier: Apache-2.0
"""Offline, source-authenticated FULL-interpreter adapter for F3 experiments.

Private opponent truth is available only to this oracle, never the proposal API.
No reference download or substituted mechanics is permitted by this adapter.
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any
from night_feed_frontier import FeedTail, incumbent_feeds, unit

PINS = {
    "checks/reference/engine/kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "checks/reference/engine/kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "checks/reference/engine/utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
    "checks/reference/evaluator/loader.py": "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5",
}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Engine:
    def __init__(self, native_root: Path):
        self.root = native_root.resolve(strict=True)
        for path, expected in PINS.items():
            actual = git_blob((self.root / path).read_bytes())
            if actual != expected:
                raise ValueError(f"reference identity mismatch: {path}: {actual}")
        self.loader = load_file(self.root / "checks/reference/evaluator/loader.py", "_f3_pinned_loader")
        self.engine, self.hashes = self.loader.get_engine(self.root / "checks/reference/engine")
        self.calls = 0

    def initialize(self, seed=17):
        S = self.loader.Struct
        cfg = S({k: v.get("default") if isinstance(v, dict) else v
                 for k, v in self.engine.specification["configuration"].items()})
        cfg.seed = seed
        env = S(configuration=cfg, done=False, info={})
        state = [S(observation=S(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
        self.engine.interpreter(state, env)
        self.calls += 1
        return state, env

    def transition(self, state, env, step, joint):
        for seat in (0, 1):
            state[seat].observation.step = step
            state[seat].action = copy.deepcopy(joint[seat])
        self.engine.interpreter(state, env)
        self.calls += 1
        return state

    def replay(self, snapshot, start, joint_tape, proposal: FeedTail | None = None):
        """Replay fixed actual actions. This is attribution, not an adaptive rival.

Validate the whole tail BEFORE displacement. Decline stale commitments rather
than cancel half a walk. Neither input snapshot nor tape is ever mutated.
"""
        state, env = copy.deepcopy(snapshot)
        if proposal is not None:
            if proposal.step != start or not start < proposal.end <= 696:
                raise ValueError("proposal boundary mismatch")
            if len(joint_tape) < proposal.end - start:
                raise ValueError("incomplete reset suffix")
            obs = state[proposal.seat].observation
            farm = obs.farms[proposal.seat]
            positions = [tuple(farm["farmer"]), *map(tuple, farm["hands"])]
            if proposal.actor >= len(positions) or positions[proposal.actor] != proposal.start:
                raise ValueError("actor identity/position drift")
            actual = [row[proposal.seat] for row in joint_tape[:proposal.end - start]]
            if any(unit(a, proposal.actor) != ["PASS"] for a in actual):
                raise ValueError("actual returned incumbent is not idle")
            if set(proposal.targets) & incumbent_feeds(positions, actual):
                raise ValueError("actual incumbent already feeds a target")
        feeds = []
        reset_state = None
        for offset, joint in enumerate(joint_tape):
            step = start + offset
            actions = copy.deepcopy(joint)
            if proposal is not None and step < proposal.end:
                own = state[proposal.seat].observation.farms[proposal.seat]
                positions = [tuple(own["farmer"]), *map(tuple, own["hands"])]
                if proposal.actor >= len(positions) or positions[proposal.actor] != proposal.positions[offset]:
                    raise ValueError("replayed actor position diverged")
                command = list(proposal.commands[offset])
                if proposal.actor == 0:
                    actions[proposal.seat]["farmer"] = command
                else:
                    hands = actions[proposal.seat].setdefault("hands", [])
                    while len(hands) < proposal.actor:
                        hands.append(["PASS"])
                    hands[proposal.actor - 1] = command
                if command == ["FEED"]:
                    pos = positions[proposal.actor]
                    tile = own["tiles"][pos[1]][pos[0]]
                    inv = state[proposal.seat].observation.private["inventories"][proposal.actor]
                    if not (isinstance(tile, dict) and tile.get("animal") and not tile["fed_today"]
                            and inv.get("WHEAT", 0) > 0):
                        raise ValueError("replayed feed has no fill")
                    feeds.append({"step": step, "actor": proposal.actor, "target": pos})
            self.transition(state, env, step, actions)
            if proposal is not None and step == proposal.end - 1:
                reset_state = copy.deepcopy(state)
            if any(s.status == "DONE" for s in state):
                break
        return state, env, {"feeds": feeds, "reset_state": reset_state}


def pass_action(hands=0):
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hands)], "market": []}
