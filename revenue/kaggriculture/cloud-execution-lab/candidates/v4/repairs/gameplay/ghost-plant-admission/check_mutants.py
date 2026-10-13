# SPDX-License-Identifier: Apache-2.0
"""Reject simple semantic regressions without relying on Python assert."""
from __future__ import annotations
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / "ghost_plant_admission.py").read_text()

MUTANTS = {
    "drops_seed_equality": ("0 < live_n <= available < raw_n", "0 < live_n < available < raw_n"),
    "forgets_live_hands": ('live_hands = len(farm["hands"])', 'live_hands = 0'),
    "edits_earliest_ghost": (
        'range(len(result_hands) - 1, live_hands - 1, -1)',
        'range(live_hands, len(result_hands))'),
    "under_repairs_excess": ("repair_counts[crop] = raw_n - available",
                              "repair_counts[crop] = max(0, raw_n - available - 1)"),
}


def load(text, name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    try:
        exec(compile(text, name, "exec"), mod.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return mod


def obs(seeds, live=1):
    return {"player": 0, "farms": [{"hands": [[1, 0] for _ in range(live)]}, {"hands": []}],
            "private": {"seeds": dict(seeds)}}


def act(farmer, hands):
    return {"farmer": farmer, "hands": hands, "market": [["SELL", "WHEAT", 1]]}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def acceptance(mod):
    # Equality boundary: live demand exactly equals available seeds.
    a = act(["PLANT", "CARROT"], [["PLANT", "CARROT"], ["PLANT", "CARROT"]])
    out, r = mod.repair_ghost_plant_poisoning(obs({"CARROT": 2}), a, enabled=True)
    require(r["changed"] and out["hands"] == [["PLANT", "CARROT"], ["PASS"]], "equality")
    # Live hand itself must stay live when farmer passes.
    a = act(["PASS"], [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]])
    out, r = mod.repair_ghost_plant_poisoning(obs({"WHEAT": 1}), a, enabled=True)
    require(r["changed"] and out["hands"] == [["PLANT", "WHEAT"], ["PASS"]], "live-hand")
    # Exactly one of two ghost rows must move, and it must be the latest one.
    a = act(["PLANT", "CARROT"], [["PLANT", "CARROT"], ["PLANT", "CARROT"], ["PLANT", "CARROT"]])
    out, r = mod.repair_ghost_plant_poisoning(obs({"CARROT": 3}), a, enabled=True)
    require(r["replaced_hand_indexes"] == [2], "minimum/latest")
    # Two excess rows require two edits; partial repair must never escape.
    a = act(["PLANT", "CARROT"], [["PLANT", "CARROT"], ["PLANT", "CARROT"], ["PLANT", "CARROT"]])
    out, r = mod.repair_ghost_plant_poisoning(obs({"CARROT": 2}), a, enabled=True)
    require(r["changed"] and r["replaced_hand_indexes"] == [1, 2], "full excess")


def main():
    acceptance(load(SOURCE, "seedghost_baseline"))
    rejected = []
    for name, (old, new) in MUTANTS.items():
        if SOURCE.count(old) != 1:
            raise RuntimeError("mutation anchor drift: " + name)
        text = SOURCE.replace(old, new)
        try:
            acceptance(load(text, "seedghost_mutant_" + name))
        except Exception:
            rejected.append(name)
        else:
            raise RuntimeError("semantic mutant survived: " + name)
    print("rejected", len(rejected), "mutants:", ", ".join(rejected))


if __name__ == "__main__":
    main()
