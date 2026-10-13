"""Does the intact route leave production capacity unused for the rest of the game?

The open-slot lane can only add value through what a worker can do on the tile it
already stands on. Upkeep fills measure in the tens of dollars and are swamped by
how the shared price curve reorders. The one lever in this lane with a large,
compounding payoff is PRODUCTION CAPACITY: an animal sitting in the shed while a
matching empty structure exists, or a structure standing empty for days.

This measures that on a real game, per turn, with the pinned engine:

  idle_animals      animals in the seat's shed with a matching empty structure
  empty_structures  COOP/PASTURE tiles with no animal
  never_filled      structures still empty at the end of the episode
  shed_dead         animals still in the shed at the end

An honest zero here means the lane has no capacity headroom and the direction is
wrong, not that the measurement failed.
"""

import argparse
import json
import os

import cards as cards_mod
import native_motifs as NM
import route_cards


def audit(seed, seat, opponent_spec):
    from kaggle_environments.envs.kaggriculture import kaggriculture as K
    A, arl_id = route_cards.load_arlene()
    opp, opp_id = route_cards.load_agent(opponent_spec)
    env = cards_mod.make_env(seed)
    env.reset(2)
    mine, theirs = A.Agent(), A.Agent()
    per_turn, n = [], 0
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                a = mine.act(obs)
                farm, priv = obs["farms"][seat], obs["private"]
                shed = priv.get("shed") or {}
                carried = {}
                for inv in (priv.get("inventories") or []):
                    for it, c in inv.items():
                        carried[it] = carried.get(it, 0) + c
                empty = {"COOP": [], "PASTURE": []}
                for y, row in enumerate(farm["tiles"]):
                    for x, t in enumerate(row):
                        if isinstance(t, dict) and t.get("kind") in empty \
                                and t.get("animal") is None:
                            empty[t["kind"]].append((x, y))
                fillable = 0
                for an, d in K.ANIMALS.items():
                    have = shed.get(an, 0) + carried.get(an, 0)
                    fillable += min(have, len(empty[d["structure"]]))
                # Slots the ENGINE ignores, split by whether Arlene's own
                # predicate saw it. The second group is headroom its repair logic
                # does not currently reach.
                units = [list(a["farmer"])] + [list(h) for h in a["hands"]]
                pos = [farm["farmer"]] + list(farm.get("hands", []))
                sim = NM.simulate(NM.engine(),
                                  {"farms": obs["farms"], "private": priv,
                                   "day": int(obs["day"])},
                                  {"boardSize": len(farm["tiles"]),
                                   "turnsPerDay": 24,
                                   "shedCapacity": A.SHED_CAP},
                                  seat, units)
                seen_free = unseen_free = 0
                for j, op in enumerate(units):
                    if j >= len(pos) or sim["slots"][j]["kind"] != "none":
                        continue
                    x, y = int(pos[j][0]), int(pos[j][1])
                    inv = (priv.get("inventories") or [{}])[j] \
                        if j < len(priv.get("inventories") or []) else {}
                    if A._noop(op, farm["tiles"][y][x], inv,
                               priv.get("seeds") or {}, x, y, len(farm["tiles"])):
                        seen_free += 1
                    else:
                        unseen_free += 1
                per_turn.append({
                    "engine_idle_seen_by_noop": seen_free,
                    "engine_idle_missed_by_noop": unseen_free,
                    "step": int(obs["day"]) * 24 + int(obs["hour"]),
                    "day": int(obs["day"]),
                    "empty_coop": len(empty["COOP"]),
                    "empty_pasture": len(empty["PASTURE"]),
                    "shed_animals": {a: shed.get(a, 0) for a in K.ANIMALS
                                     if shed.get(a, 0)},
                    "carried_animals": {a: carried.get(a, 0) for a in K.ANIMALS
                                        if carried.get(a, 0)},
                    "fillable_now": fillable,
                })
                acts[i] = a
            else:
                acts[i] = (theirs.act(obs) if opponent_spec == "arlene"
                           else route_cards.call(opp, obs, env.configuration))
        env.step(acts)
        n += 1
    last = per_turn[-1]
    turns_with_fillable = sum(1 for r in per_turn if r["fillable_now"] > 0)
    seen = sum(r["engine_idle_seen_by_noop"] for r in per_turn)
    missed = sum(r["engine_idle_missed_by_noop"] for r in per_turn)
    peak = max((r["fillable_now"] for r in per_turn), default=0)
    return {"seed": seed, "seat": seat, "opponent": opp_id, "arlene": arl_id,
            "turns": n,
            "turns_with_fillable_capacity": turns_with_fillable,
            "peak_fillable": peak,
            "engine_idle_slots_seen_by_noop": seen,
            "engine_idle_slots_missed_by_noop": missed,
            "final_empty_structures": last["empty_coop"] + last["empty_pasture"],
            "final_shed_animals": last["shed_animals"],
            "final_carried_animals": last["carried_animals"],
            "per_turn": per_turn}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0])
    ap.add_argument("--opponent", default="arlene")
    ap.add_argument("--out", default="results/capacity-audit.json")
    a = ap.parse_args()
    rows = []
    for seed in a.seeds:
        for seat in a.seats:
            r = audit(seed, seat, a.opponent)
            rows.append(r)
            print(f"seed {seed} seat {seat}: {r['turns_with_fillable_capacity']} of "
                  f"{r['turns']} turns had an animal in stock AND a matching empty "
                  f"structure (peak {r['peak_fillable']}); at the end "
                  f"{r['final_empty_structures']} structure(s) stood empty, shed "
                  f"{r['final_shed_animals']}, carried {r['final_carried_animals']}",
                  flush=True)
            print(f"    engine-ignored slots: {r['engine_idle_slots_seen_by_noop']} "
                  f"caught by Arlene's own _noop, "
                  f"{r['engine_idle_slots_missed_by_noop']} missed by it", flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
