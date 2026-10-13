# SPDX-License-Identifier: Apache-2.0
"""Property-based differential fuzzer: pinned official interpreter vs mechanics adapter.

The fuzzer exists to find the NEXT bug of the #11690 class: a divergence
between ``mechanics_adapter.mechanics_transition`` (the incremental,
interpreter-faithful worker-prefix transition used by the cloud anytime joint
beam) and the pinned official Kaggriculture interpreter's worker phase.

Oracle design (no re-implementation, no drift):
  * The official worker phase is the atomic-PLANT-prepass block of
    ``interpreter()`` in ``reference/engine/kaggriculture.py``. It is extracted
    verbatim from the pinned file at load time and its sha256 must match
    ``ENGINE_BLOCK_SHA256``; any drift fails loudly instead of silently
    comparing against a stale copy.
  * The block is executed with the preserved ``_apply_unit_action`` primitive
    from the pinned ``mechanics.py`` (``run_contracts.EXPECTED_MECHANICS_BLOB``).
    The engine's own copy of that primitive is asserted byte-identical at load.
  * ``kaggle_environments`` is not importable here, so the oracle drives the
    extracted block with lightweight namespace stand-ins instead of full
    episode state. The block only touches ``obs0.farms[i]`` and
    ``s.observation.private``, which are the exact (farm, private) structures
    the adapter operates on.

What is compared per generated case:
  * Final (farm, private) equality after the full worker tuple. The adapter's
    internal ``_TRANSITION_META_KEY`` is stripped before comparison.
  * Prune correctness: whenever the adapter returns ``None`` (prune this
    candidate), the official per-step recording must show the action was a
    silent no-op. A pruned-but-officially-effective action is a mismatch.
    (The reverse -- adapter retains a no-op -- is by contract: syntactic PLANT
    requests and rollback-sensitive BUILD no-ops are always retained.)

What is NOT covered: market actions (SELL/BUY_PRODUCT), hire/buyLand, and
end-of-day effects (decay, weed spawn, inventory drop). The adapter explicitly
does not own market emission; those phases are out of scope for this oracle.

Usage:
    python3 diff_fuzz.py --cases 500 --seeds 5 --output /tmp/diff_fuzz.json
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import random
import re
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from joint_action_beam import Action
from mechanics_adapter import (
    _TRANSITION_META_KEY,
    MechanicsContext,
    mechanics_transition,
)
from test_mechanics_adapter import MECHANICS_PATH, fixture as base_fixture, load_mechanics

HERE = Path(__file__).resolve().parent
ENGINE_PATH = HERE.parent / "cloud-execution-lab" / "reference" / "engine" / "kaggriculture.py"

# Pinned sha256 of the extracted worker-phase block of the pinned reference
# engine's interpreter(): the atomic PLANT prepass plus the sequential
# per-worker _apply_unit_action dispatch, through the blank line preceding
# the `_process_market` call.
ENGINE_BLOCK_SHA256 = "46fc69d80b692fe25091dd5eda84c289c5b657c80c0d82053794c6eb479bf4b8"
EXPECTED_MECHANICS_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"


def _extract_engine_block() -> str:
    """Extract the interpreter's worker-phase block verbatim from the pinned engine."""
    lines = ENGINE_PATH.read_text().split("\n")
    marker = "        # Atomic PLANT validation: if total PLANT requests for a crop this turn"
    start = next(i for i, line in enumerate(lines) if line == marker)
    end = next(
        i for i, line in enumerate(lines)
        if line == "    _process_market(state, env)"
    )
    block = "\n".join(lines[start:end])
    digest = hashlib.sha256(block.encode()).hexdigest()
    if digest != ENGINE_BLOCK_SHA256:
        raise SystemExit(
            f"official interpreter worker-phase drift: got {digest}, "
            f"pinned {ENGINE_BLOCK_SHA256} ({ENGINE_PATH})"
        )
    # The block sits inside `for i, s in enumerate(state):`; dedent it so it can
    # execute with caller-supplied namespace bindings.
    return textwrap.dedent(block)


def _func_source(path: Path, name: str) -> str:
    src = path.read_text()
    match = re.search(rf"^def {name}\(.*?\n(?=^def |\Z)", src, re.S | re.M)
    if not match:
        raise SystemExit(f"could not extract {name} from {path}")
    return match.group(0)


def check_pins() -> dict[str, str]:
    """Verify every pin the oracle depends on; fail loudly on drift."""
    data = Path(MECHANICS_PATH).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if blob != EXPECTED_MECHANICS_BLOB:
        raise SystemExit(f"mechanics blob drift: {blob}")
    block = _extract_engine_block()
    engine_apply = _func_source(ENGINE_PATH, "_apply_unit_action")
    mechanics_apply = _func_source(Path(MECHANICS_PATH), "_apply_unit_action")
    if engine_apply != mechanics_apply:
        raise SystemExit(
            "engine _apply_unit_action diverged from pinned mechanics.py primitive; "
            "the oracle would no longer be faithful"
        )
    return {
        "mechanics_git_blob": blob,
        "engine_block_sha256": ENGINE_BLOCK_SHA256,
    }


ENGINE_BLOCK = _extract_engine_block()


def official_worker_phase(
    mechanics: Any,
    farm: dict,
    private: dict,
    turns: list[list[Action]],
    board_size: int,
    day: int,
    turns_per_day: int = 24,
    shed_capacity: int = 100,
) -> tuple[dict, dict, list[list[dict]], list[set[str]]]:
    """Run the pinned official worker phase over one or more worker tuples.

    Each turn gets its own atomic PLANT prepass, exactly like the interpreter.
    Returns (farm, private, steps_per_turn, blocked_per_turn) where each step
    records the effective action the interpreter applied and whether it
    changed any state.
    """
    farm = copy.deepcopy(farm)
    private = copy.deepcopy(private)
    all_steps: list[list[dict]] = []
    all_blocked: list[set[str]] = []

    for actions in turns:
        steps: list[dict] = []

        def recording_apply(farm_arg, private_arg, idx, action,
                            bs, d, tpd, sc=shed_capacity):
            before = (copy.deepcopy(farm_arg), copy.deepcopy(private_arg))
            mechanics._apply_unit_action(farm_arg, private_arg, idx, action,
                                         bs, d, tpd, sc)
            changed = (farm_arg != before[0]) or (private_arg != before[1])
            steps.append({
                "idx": idx,
                "effective_action": copy.deepcopy(action),
                "changed": changed,
            })

        namespace: dict[str, Any] = {
            "farmer_action": copy.deepcopy(actions[0]) if actions else ["PASS"],
            "hands_actions": [copy.deepcopy(a) for a in actions[1:]],
            "s": SimpleNamespace(observation=SimpleNamespace(private=private)),
            "obs0": SimpleNamespace(farms=[farm]),
            "i": 0,
            "_apply_unit_action": recording_apply,
            "board_size": board_size,
            "day": day,
            "turns_per_day": turns_per_day,
            "shed_capacity": shed_capacity,
        }
        exec(ENGINE_BLOCK, namespace)  # noqa: S102 - pinned official code by design
        all_steps.append(steps)
        all_blocked.append(set(namespace["blocked"]))
    return farm, private, all_steps, all_blocked


def _strip_meta(state: dict) -> dict:
    state = copy.deepcopy(state)
    state.pop(_TRANSITION_META_KEY, None)
    return state


def adapter_run(
    mechanics: Any,
    initial: dict,
    turns: list[list[Action]],
    board_size: int,
    day: int,
    turns_per_day: int = 24,
    shed_capacity: int = 100,
) -> tuple[dict, dict, list[list[int]]]:
    """Walk the adapter transition over one or more worker tuples.

    A ``None`` step (beam prune hint) keeps the prior state so the walk stays
    defined; prune correctness is checked separately against the official
    per-step recording. ``idx == 0`` starts each turn with fresh prefix
    metadata, exactly like the beam's per-turn use. Returns
    (farm, private, pruned_indices_per_turn).
    """
    transition = mechanics_transition(
        mechanics,
        MechanicsContext(board_size=board_size, day=day,
                         turns_per_day=turns_per_day,
                         shed_capacity=shed_capacity),
    )
    # NOTE: the transition's _TRANSITION_META_KEY must survive across steps of
    # one walk: it is the adapter's internal per-search prefix bookkeeping.
    # It is stripped only from the final state before comparison.
    state = copy.deepcopy(initial)
    pruned_per_turn: list[list[int]] = []
    for actions in turns:
        pruned: list[int] = []
        for idx, action in enumerate(actions):
            nxt = transition(state, idx, action)
            if nxt is None:
                pruned.append(idx)
                continue
            state = nxt
        pruned_per_turn.append(pruned)
    final = _strip_meta(state)
    return final["farm"], final["private"], pruned_per_turn


def _is_syntactic_plant(action: Action) -> bool:
    return isinstance(action, list) and len(action) >= 2 and action[0] == "PLANT"


def diff_states(official: Any, adapted: Any, path: str = "$") -> list[str]:
    """Recursive structural diff; returns human-readable difference paths."""
    diffs: list[str] = []
    if type(official) is not type(adapted):
        return [f"{path}: type {type(official).__name__} != {type(adapted).__name__}"]
    if isinstance(official, dict):
        for key in sorted(set(official) | set(adapted), key=repr):
            if key not in official:
                diffs.append(f"{path}.{key}: missing in official")
            elif key not in adapted:
                diffs.append(f"{path}.{key}: missing in adapter")
            else:
                diffs.extend(diff_states(official[key], adapted[key], f"{path}.{key}"))
    elif isinstance(official, (list, tuple)):
        if len(official) != len(adapted):
            diffs.append(f"{path}: len {len(official)} != {len(adapted)}")
        for i, (a, b) in enumerate(zip(official, adapted)):
            diffs.extend(diff_states(a, b, f"{path}[{i}]"))
    elif official != adapted:
        diffs.append(f"{path}: {official!r} != {adapted!r}")
    return diffs


class Mismatch(Exception):
    """Raised when the adapter diverges from the official interpreter."""

    def __init__(self, kind: str, detail: dict):
        super().__init__(kind)
        self.kind = kind
        self.detail = detail


def check_case(
    mechanics: Any,
    initial: dict,
    turns: list[list[Action]],
    board_size: int,
    day: int,
    turns_per_day: int = 24,
    shed_capacity: int = 100,
) -> dict:
    """Run one differential case; raise Mismatch on divergence, else return stats."""
    o_farm, o_private, o_steps, blocked = official_worker_phase(
        mechanics, initial["farm"], initial["private"], turns,
        board_size, day, turns_per_day, shed_capacity,
    )
    a_farm, a_private, pruned_per_turn = adapter_run(
        mechanics, initial, turns, board_size, day, turns_per_day, shed_capacity,
    )

    # Prune correctness: a pruned action must be a silent no-op officially, and
    # the adapter must never prune a syntactic PLANT request.
    for t, (actions, pruned, steps) in enumerate(zip(turns, pruned_per_turn, o_steps)):
        for idx in pruned:
            if _is_syntactic_plant(actions[idx]):
                raise Mismatch("pruned-plant", {
                    "turn": t, "idx": idx, "action": actions[idx],
                    "official_steps": steps,
                })
            if steps[idx]["changed"]:
                raise Mismatch("wrongful-prune", {
                    "turn": t,
                    "idx": idx,
                    "action": actions[idx],
                    "official_effective": steps[idx]["effective_action"],
                    "blocked": sorted(blocked[t]),
                })

    farm_diffs = diff_states(o_farm, a_farm, "$.farm")
    private_diffs = diff_states(o_private, a_private, "$.private")
    diffs = farm_diffs + private_diffs
    if diffs:
        raise Mismatch("state-divergence", {
            "diffs": diffs[:40],
            "diff_count": len(diffs),
            "blocked": [sorted(b) for b in blocked],
            "pruned": pruned_per_turn,
        })
    return {"pruned": pruned_per_turn,
            "blocked": [sorted(b) for b in blocked],
            "official_changed_steps": sum(
                1 for steps in o_steps for s in steps if s["changed"])}


# ---------------------------------------------------------------------------
# Adversarial generator
# ---------------------------------------------------------------------------

def _scarce_seed_count(rng: random.Random) -> int:
    roll = rng.random()
    if roll < 0.45:
        return rng.randint(0, 1)
    if roll < 0.8:
        return 2
    return rng.randint(3, 4)


def _gen_tile(rng: random.Random, mechanics: Any, board: int, day: int,
              tpd: int) -> Any:
    roll = rng.random()
    if roll < 0.40:
        return None
    if roll < 0.45:
        return "LOCKED"
    if roll < 0.70:
        crop = rng.choice(sorted(mechanics.CROPS))
        cd = mechanics.CROPS[crop]
        planted_day = max(0, day - rng.randint(0, 3))
        return {
            "kind": "PLANT",
            "crop": crop,
            "planted_day": planted_day,
            "watered_today": rng.random() < 0.5,
            "consecutive_unwatered": rng.randint(0, 3),
            "yield_units": rng.randint(0, 3) if cd["ongoing"] else rng.randint(0, 2),
            "max_lifespan_step": (
                -1 if cd["ongoing"]
                else (planted_day + cd["max_yield_day"] + 1) * tpd
            ),
            "fertilized_until_day": day + 2 if rng.random() < 0.2 else -1,
        }
    if roll < 0.80:
        structure = rng.choice(["COOP", "PASTURE"])
        return {"kind": structure}
    if roll < 0.90:
        structure = rng.choice(["COOP", "PASTURE"])
        animal = rng.choice([
            name for name, spec in mechanics.ANIMALS.items()
            if spec["structure"] == structure
        ])
        return {
            "kind": structure,
            "animal": animal,
            "placed_day": max(0, day - rng.randint(0, 2)),
            "yield_units": rng.randint(0, 2),
            "consecutive_unfed": rng.randint(0, 2),
            "fed_today": rng.random() < 0.5,
            "cared_today": rng.random() < 0.5,
            "fertilizer_available": rng.random() < 0.4,
            "pending_care_bonus": 0,
        }
    return None


def _gen_inventory(rng: random.Random, mechanics: Any) -> dict:
    inv: dict[str, int] = {}
    if rng.random() < 0.35:
        inv["FERTILIZER"] = rng.randint(1, 2)
    if rng.random() < 0.25:
        inv["WHEAT"] = rng.randint(1, 3)
    if rng.random() < 0.20:
        inv[rng.choice(sorted(mechanics.ANIMALS))] = rng.randint(1, 2)
    if rng.random() < 0.15:
        inv[rng.choice(sorted(mechanics.CROPS))] = rng.randint(1, 2)
    return inv


def gen_initial(rng: random.Random, mechanics: Any) -> tuple[dict, dict]:
    """Generate an adversarial initial worker state.

    Returns (state, params) where params carries board_size/day/turns_per_day.
    """
    board = rng.choice([4, 5, 6])
    nworkers = rng.randint(2, 4)
    day = rng.randint(0, 4)
    tpd = 24
    tiles = [[_gen_tile(rng, mechanics, board, day, tpd) for _ in range(board)]
             for _ in range(board)]
    crops = sorted(mechanics.CROPS)
    seeds = {crop: _scarce_seed_count(rng) for crop in crops}

    shed_tiles = set(mechanics._shed_access_tiles(board))
    place_mode = rng.random()
    positions: list[list[int]] = []
    if place_mode < 0.35:
        # Contested: every worker starts on the same tile.
        spot = [rng.randrange(board), rng.randrange(board)]
        positions = [list(spot) for _ in range(nworkers)]
        if tiles[spot[1]][spot[0]] == "LOCKED":
            tiles[spot[1]][spot[0]] = None
    elif place_mode < 0.60:
        # Shed-adjacent: unlock shed ops (PICKUP/DROP/PLACE).
        spots = list(shed_tiles)
        for _ in range(nworkers):
            x, y = rng.choice(spots)
            positions.append([x, y])
            if tiles[y][x] == "LOCKED":
                tiles[y][x] = None
    else:
        for _ in range(nworkers):
            positions.append([rng.randrange(board), rng.randrange(board)])

    shed: dict[str, int] = {}
    for _ in range(rng.randint(0, 3)):
        item = rng.choice(crops + ["EGG", "MILK", "WOOL", "FERTILIZER"])
        shed[item] = shed.get(item, 0) + rng.randint(1, 4)

    state = {
        "farm": {
            "farmer": positions[0],
            "hands": [p for p in positions[1:]],
            "tiles": tiles,
            "money": rng.randint(0, 2000),
        },
        "private": {
            "shed": shed,
            "seeds": seeds,
            "inventories": [_gen_inventory(rng, mechanics) for _ in range(nworkers)],
        },
        "market": {"inventory": {}},
    }
    params = {"board_size": board, "day": day, "turns_per_day": tpd,
              "shed_capacity": 100}
    return state, params


def _tile_at(farm: dict, pos: Any) -> Any:
    try:
        x, y = int(pos[0]), int(pos[1])
    except (TypeError, IndexError):
        return None
    tiles = farm.get("tiles", [])
    if 0 <= y < len(tiles) and 0 <= x < len(tiles[y]):
        return tiles[y][x]
    return None


def gen_action(rng: random.Random, mechanics: Any, state: dict, idx: int) -> Action:
    """Generate one adversarial worker action, biased by the worker's tile."""
    farm, private = state["farm"], state["private"]
    board = len(farm.get("tiles", []))
    pos = mechanics._farmer_position(farm, idx)
    tile = _tile_at(farm, pos)
    shed_adj = (
        pos is not None and mechanics._is_shed_adjacent((int(pos[0]), int(pos[1])), board)
    )
    crops = sorted(mechanics.CROPS)
    seeds = private.get("seeds", {})
    scarce = [c for c in crops if int(seeds.get(c, 0)) <= 2] or crops
    inv = private.get("inventories", [])
    inv = inv[idx] if idx < len(inv) and isinstance(inv[idx], dict) else {}

    roll = rng.random()
    if roll < 0.02:
        # Malformed actions: the official interpreter treats them as silent
        # no-ops; the adapter must prune or no-op identically.
        return rng.choice([[], ["PLANT"], ["PLANT", "BOGUS_CROP"], "PASS",
                           ["JUMP"], ["PICKUP"], ["PLACE", "WHEAT", 0]])
    if roll < 0.32:
        # PLANT oversubscription pressure: scarce-seed crops, every worker.
        return ["PLANT", rng.choice(scarce)]
    if roll < 0.42:
        # BUILD on contested tiles.
        return [rng.choice(["BUILD_COOP", "BUILD_PASTURE"])]
    if roll < 0.52:
        return [rng.choice(["NORTH", "SOUTH", "EAST", "WEST"])]
    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        menu: list[Action] = [["WATER"], ["HARVEST"], ["DIG"]]
        if int(inv.get("FERTILIZER", 0)) > 0:
            menu.append(["FERTILIZE"])
        if roll < 0.62:
            return rng.choice(menu)
    if isinstance(tile, dict) and "animal" in tile:
        menu = [["HARVEST"], ["CARE"], ["COLLECT_FERTILIZER"]]
        if int(inv.get("WHEAT", 0)) > 0:
            menu.append(["FEED"])
        if roll < 0.68:
            return rng.choice(menu)
    if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE"):
        if roll < 0.72:
            animals = [a for a, spec in mechanics.ANIMALS.items()
                       if spec["structure"] == tile["kind"]
                       and int(inv.get(a, 0)) > 0]
            if animals and rng.random() < 0.7:
                return ["PLACE", rng.choice(animals)]
            return ["DIG"]
    if shed_adj and roll < 0.80:
        shed = private.get("shed", {})
        options: list[Action] = []
        stocked = [item for item, n in shed.items() if int(n) > 0]
        if stocked:
            item = rng.choice(sorted(stocked))
            options.append(["PICKUP", item, rng.randint(1, max(1, int(shed[item])))])
        held = [item for item, n in inv.items() if int(n) > 0]
        if held:
            item = rng.choice(sorted(held))
            options.append(["PLACE", item, rng.randint(1, int(inv[item]))])
        if held:
            options.append(["DROP"])
        if options:
            return rng.choice(options)
    if roll < 0.86:
        return ["PASS"]
    # Mixed fallback: anything, including cross-cutting races.
    return rng.choice([
        ["PLANT", rng.choice(crops)],
        [rng.choice(["BUILD_COOP", "BUILD_PASTURE"])],
        [rng.choice(["NORTH", "SOUTH", "EAST", "WEST"])],
        ["WATER"], ["HARVEST"], ["DIG"], ["FERTILIZE"], ["CARE"], ["FEED"],
        ["COLLECT_FERTILIZER"], ["DROP"], ["PASS"],
    ])


def gen_case(rng: random.Random, mechanics: Any
             ) -> tuple[dict, list[list[Action]], dict]:
    """Generate one full differential case: (initial_state, turns, params).

    One in four cases chains a second turn off the first turn's workers, which
    exercises the adapter's idx==0 prefix-metadata reset against the
    interpreter's per-turn prepass.
    """
    state, params = gen_initial(rng, mechanics)
    nworkers = 1 + len(state["farm"]["hands"])
    turns = [[gen_action(rng, mechanics, state, idx) for idx in range(nworkers)]]
    if rng.random() < 0.25:
        # Second turn: fresh worker tuple on the same opening state shape.
        # (Positions are regenerated; the differential comparison chains the
        # real first-turn output, so this stays faithful.)
        turns.append([gen_action(rng, mechanics, state, idx)
                      for idx in range(nworkers)])
    return state, turns, params


# ---------------------------------------------------------------------------
# Directed adversarial templates (regression + known-sensitive shapes)
# ---------------------------------------------------------------------------

def _directed_state(mechanics: Any, workers: int = 3, board: int = 4,
                    seeds: dict | None = None, day: int = 1) -> tuple[dict, dict]:
    state = base_fixture(workers)
    state["farm"]["tiles"] = [[None for _ in range(board)] for _ in range(board)]
    state["farm"]["farmer"] = [1, 1]
    state["farm"]["hands"] = [[1, 1] for _ in range(workers - 1)]
    state["private"]["seeds"] = dict(seeds) if seeds else {"WHEAT": 1}
    state["private"]["inventories"] = [{} for _ in range(workers)]
    params = {"board_size": board, "day": day, "turns_per_day": 24,
              "shed_capacity": 100}
    return state, params


def directed_cases(mechanics: Any) -> list[tuple[str, dict, list[Action], dict]]:
    """Hand-built adversarial templates around the #11690 bug class."""
    cases: list[tuple[str, dict, list[Action], dict]] = []

    state, params = _directed_state(mechanics, 3, seeds={"WHEAT": 1})
    cases.append(("plant-build-plant-oversubscription (#11690 witness)",
                  state, [["PLANT", "WHEAT"], ["BUILD_COOP"], ["PLANT", "WHEAT"]],
                  params))

    state, params = _directed_state(mechanics, 4,
                                    seeds={"WHEAT": 1, "CARROT": 1})
    cases.append(("multi-crop-oversubscription",
                  state,
                  [["PLANT", "WHEAT"], ["PLANT", "CARROT"],
                   ["PLANT", "WHEAT"], ["PLANT", "CARROT"]],
                  params))

    state, params = _directed_state(mechanics, 2, seeds={"WHEAT": 1})
    state["farm"]["tiles"][1][1] = {"kind": "COOP"}  # worker 0 cannot plant here
    state["farm"]["hands"][0] = [2, 1]               # worker 1 on empty tile
    cases.append(("illegal-plant-counts-toward-demand",
                  state, [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]], params))

    state, params = _directed_state(mechanics, 3, seeds={"WHEAT": 1})
    cases.append(("water-after-tentative-plant-rollback",
                  state, [["PLANT", "WHEAT"], ["WATER"], ["PLANT", "WHEAT"]],
                  params))

    state, params = _directed_state(mechanics, 3, seeds={"WHEAT": 1})
    cases.append(("build-race-then-plant",
                  state,
                  [["BUILD_COOP"], ["BUILD_COOP"], ["PLANT", "WHEAT"]],
                  params))

    state, params = _directed_state(mechanics, 3, seeds={"WHEAT": 1})
    cases.append(("dig-vs-tentative-plant",
                  state, [["PLANT", "WHEAT"], ["DIG"], ["PLANT", "WHEAT"]],
                  params))

    state, params = _directed_state(mechanics, 3,
                                    seeds={"WHEAT": 0, "CARROT": 0})
    cases.append(("zero-seed-all-blocked",
                  state,
                  [["PLANT", "WHEAT"], ["PLANT", "CARROT"], ["PLANT", "WHEAT"]],
                  params))

    state, params = _directed_state(mechanics, 2, seeds={"WHEAT": 2})
    state["farm"]["farmer"] = [0, 0]
    state["farm"]["hands"][0] = [0, 0]
    cases.append(("move-then-plant-exact-seeds",
                  state,
                  [["EAST"], ["PLANT", "WHEAT"]], params))

    state, params = _directed_state(mechanics, 4, board=6,
                                    seeds={"WHEAT": 2, "MELON": 1})
    half = 3
    shed_spots = [(half - 1, half - 1), (half, half - 1),
                  (half - 1, half), (half, half)]
    state["farm"]["farmer"] = list(shed_spots[0])
    state["farm"]["hands"] = [list(p) for p in shed_spots[1:]]
    state["private"]["shed"] = {"WHEAT": 5, "FERTILIZER": 2}
    state["private"]["inventories"] = [
        {"WHEAT": 2}, {"FERTILIZER": 1}, {}, {"MELON": 1}]
    cases.append(("shed-ops-interleaved-with-plant-pressure",
                  state,
                  [["PICKUP", "WHEAT", 2], ["PLANT", "WHEAT"],
                   ["DROP"], ["PLANT", "MELON"]],
                  params))

    state, params = _directed_state(mechanics, 3, seeds={"WHEAT": 1})
    cases.append(("malformed-actions-are-silent-noops",
                  state, [["PLANT"], ["JUMP"], ["PLANT", "WHEAT"]], params))

    # Two-turn chaining: the second turn's prepass must be independent, and the
    # adapter's idx==0 metadata reset must reproduce it.
    state, params = _directed_state(mechanics, 3, seeds={"WHEAT": 1})
    cases.append(("two-turn-plant-pressure",
                  state,
                  [[["PLANT", "WHEAT"], ["EAST"], ["PLANT", "WHEAT"]],
                   [["PLANT", "WHEAT"], ["BUILD_COOP"], ["WATER"]]],
                  params))

    wrapped: list[tuple[str, dict, list[list[Action]], dict]] = []
    for name, state, actions_or_turns, params in cases:
        # A single turn is a flat list of actions (each action's first element
        # is the op string); multiple turns nest one level deeper.
        first = actions_or_turns[0]
        is_turn_list = (isinstance(first, list) and len(first) > 0
                        and isinstance(first[0], list))
        turns = actions_or_turns if is_turn_list else [actions_or_turns]
        wrapped.append((name, state, turns, params))
    return wrapped


# ---------------------------------------------------------------------------
# Shrinker
# ---------------------------------------------------------------------------

def _case_fingerprint(mechanics: Any, initial: dict, turns: list[list[Action]],
                      params: dict) -> tuple[str, tuple]:
    """Reproduce a case; return (kind, signature) or ("ok", ()) when clean."""
    try:
        check_case(mechanics, initial, turns, **params)
        return ("ok", ())
    except Mismatch as m:
        if m.kind == "state-divergence":
            return (m.kind, tuple(sorted(m.detail["diffs"])))
        return (m.kind, (m.detail.get("turn"), m.detail.get("idx")))


def _shrink_turns(mechanics: Any, initial: dict, turns: list[list[Action]],
                 params: dict, target_kind: str) -> list[list[Action]] | None:
    """One greedy minimization pass over the turn-structured sequence."""
    # Try dropping each single action.
    for t, turn in enumerate(turns):
        for i in range(len(turn)):
            candidate = [list(x) for x in turns]
            candidate[t] = turn[:i] + turn[i + 1:]
            if not candidate[t]:
                continue
            kind, _ = _case_fingerprint(mechanics, initial, candidate, params)
            if kind == target_kind:
                return candidate
    # Try replacing each action with PASS (keeps worker count/shape).
    for t, turn in enumerate(turns):
        for i in range(len(turn)):
            if turn[i] == ["PASS"]:
                continue
            candidate = [list(x) for x in turns]
            candidate[t][i] = ["PASS"]
            kind, _ = _case_fingerprint(mechanics, initial, candidate, params)
            if kind == target_kind:
                return candidate
    # Try dropping whole turns (keep at least one).
    if len(turns) > 1:
        for t in range(len(turns)):
            candidate = [turns[i] for i in range(len(turns)) if i != t]
            kind, _ = _case_fingerprint(mechanics, initial, candidate, params)
            if kind == target_kind:
                return candidate
    return None


def shrink(mechanics: Any, initial: dict, turns: list[list[Action]], params: dict,
           max_rounds: int = 25) -> tuple[list[list[Action]], tuple[str, tuple]]:
    """Greedily minimize the turn-structured sequence while the mismatch reproduces."""
    target_kind, _ = _case_fingerprint(mechanics, initial, turns, params)
    if target_kind == "ok":
        raise ValueError("shrink called on a non-reproducing case")
    current = [list(t) for t in turns]
    for _ in range(max_rounds):
        shrunk = _shrink_turns(mechanics, initial, current, params, target_kind)
        if shrunk is None:
            break
        current = shrunk
    return current, _case_fingerprint(mechanics, initial, current, params)


def _summarize_state(state: dict) -> dict:
    farm, private = state["farm"], state["private"]
    tiles = farm.get("tiles", [])
    counts: dict[str, int] = {}
    for row in tiles:
        for tile in row:
            key = (
                "empty" if tile is None
                else tile if isinstance(tile, str)
                else tile.get("kind", "?") + ":" + str(tile.get("crop", tile.get("animal", "")))
            )
            counts[key] = counts.get(key, 0) + 1
    return {
        "positions": [farm.get("farmer")] + list(farm.get("hands", [])),
        "tiles": counts,
        "seeds": dict(private.get("seeds", {})),
        "inventories": list(private.get("inventories", [])),
        "shed": dict(private.get("shed", {})),
        "money": farm.get("money"),
    }


def format_witness(name: str, initial: dict, turns: list[list[Action]],
                   params: dict, detail: dict) -> str:
    lines = [
        f"mismatch: {name}",
        f"params: {params}",
        f"initial: {json.dumps(_summarize_state(initial), sort_keys=True)}",
        f"turns: {json.dumps(turns)}",
    ]
    for key, value in detail.items():
        rendered = json.dumps(value, sort_keys=True, default=str)
        lines.append(f"{key}: {rendered[:2000]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_fuzz(mechanics: Any, cases: int, seeds: int,
             run_directed: bool = True, seed_base: int = 1000) -> dict:
    """Run directed templates then seeded random cases; return a JSON report."""
    pins = check_pins()
    report: dict[str, Any] = {
        "pins": pins,
        "directed": [],
        "mismatches": [],
        "cases": 0,
        "mismatches_found": 0,
    }
    t0 = time.perf_counter()

    def run_one(name: str, initial: dict, turns: list[list[Action]], params: dict):
        try:
            stats = check_case(mechanics, initial, turns, **params)
            return {"name": name, "status": "pass", **stats}
        except Mismatch as m:
            shrunk_turns, (kind, _sig) = shrink(
                mechanics, initial, turns, params)
            witness = format_witness(name, initial, shrunk_turns, params,
                                     {"kind": kind, **m.detail})
            entry = {"name": name, "status": "mismatch", "kind": m.kind,
                     "turns": turns, "shrunk_turns": shrunk_turns,
                     "witness": witness}
            report["mismatches"].append(entry)
            report["mismatches_found"] += 1
            return entry

    if run_directed:
        for name, initial, turns, params in directed_cases(mechanics):
            report["directed"].append(run_one(f"directed:{name}", initial,
                                              turns, params))
            report["cases"] += 1

    per_seed_ms: list[float] = []
    for seed in range(seeds):
        rng = random.Random(seed_base + seed)
        s0 = time.perf_counter()
        for n in range(cases):
            initial, turns, params = gen_case(rng, mechanics)
            result = run_one(f"seed={seed} case={n}", initial, turns, params)
            report["cases"] += 1
            if result["status"] == "mismatch":
                result["seed"] = seed
        per_seed_ms.append((time.perf_counter() - s0) * 1000)

    total_s = time.perf_counter() - t0
    report["elapsed_s"] = round(total_s, 3)
    report["cases_per_second"] = (
        round(report["cases"] / total_s, 1) if total_s > 0 else 0)
    report["seed_ms"] = {
        "min": round(min(per_seed_ms), 1) if per_seed_ms else 0,
        "max": round(max(per_seed_ms), 1) if per_seed_ms else 0,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Differential fuzzer: official interpreter vs mechanics_adapter")
    parser.add_argument("--cases", type=int, default=500,
                        help="random cases per seed")
    parser.add_argument("--seeds", type=int, default=5, help="number of seeds")
    parser.add_argument("--seed-base", type=int, default=1000,
                        help="PRNG seed offset (seeds are base..base+seeds-1)")
    parser.add_argument("--no-directed", action="store_true",
                        help="skip hand-built adversarial templates")
    parser.add_argument("--output", default="",
                        help="write JSON report to this path")
    args = parser.parse_args(argv)

    mechanics = load_mechanics()
    report = run_fuzz(mechanics, cases=args.cases, seeds=args.seeds,
                      run_directed=not args.no_directed,
                      seed_base=args.seed_base)
    text = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        Path(args.output).write_text(text + "\n")
    print(text)
    return 1 if report["mismatches_found"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
