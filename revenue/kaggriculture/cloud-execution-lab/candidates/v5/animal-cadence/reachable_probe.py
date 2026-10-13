#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evaluation-only observation of current FEED/CARE action opportunities."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
LAB = HERE.parents[2]
OUTPUT = HERE / ".reachable-probe" / f"{os.getpid()}.jsonl"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))
CURRENT = _load("_cadence_reachable_current", LAB / "main.py")


def _units(action):
    return [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]


def _tile(tiles, position):
    try:
        x, y = position
        return tiles[y][x]
    except (TypeError, IndexError, KeyError):
        return None


def agent(observation, configuration=None):
    output = CURRENT.agent(observation, configuration)
    units = _units(output)
    if any(row and row[0] in ("FEED", "CARE") for row in units):
        player = observation["player"]
        farm = observation["farms"][player]
        positions = [farm["farmer"], *farm.get("hands", [])]
        relevant = []
        for actor, action in enumerate(units):
            if action and action[0] in ("FEED", "CARE"):
                position = list(positions[actor]) if actor < len(positions) else None
                relevant.append({
                    "actor": actor,
                    "action": action,
                    "position": position,
                    "tile": _tile(farm["tiles"], position),
                    "inventory": observation["private"]["inventories"][actor]
                    if actor < len(observation["private"].get("inventories", [])) else None,
                })
        instance = CURRENT._INSTANCE
        event = {
            "schema": "titan-v5/animal-cadence/reachable-probe/v1",
            "step": observation["step"],
            "player": player,
            "route_id": getattr(getattr(instance, "controller", None), "cur", None),
            "runtime_status": getattr(instance, "diagnostics", {}).get("status"),
            "parent_calls": getattr(instance, "diagnostics", {}).get("parent_calls"),
            "relevant": relevant,
            "action_sha256": hashlib.sha256(json.dumps(
                output, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()).hexdigest(),
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
    return output
