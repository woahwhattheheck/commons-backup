"""How long is one worker free, consecutively, in a real Arlene game?

The single-slot lane is exhausted: a free slot can only act on the tile beneath the
worker, and the measurements say nothing worth doing is ever there. But a worker
that is free for a RUN of consecutive turns can be walked somewhere it matters and
back, which no single-slot proposal can express.

This measures the runs, per worker, with the pinned engine and Arlene's own `_noop`
predicate deciding what "free" means -- so the budget for any bounded continuation
plan comes from what the route actually leaves open, not from a guess.

Also recorded, because a plan needs a destination worth walking to: at the start of
each run, how far that worker is from the shed, from the nearest empty matching
structure, and from the nearest animal or plant that has something to collect.
"""

import argparse
import json
import os
from collections import Counter

import cards as cards_mod
import route_cards


def _dist(a, b):
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def targets(obs, seat, pos, K, board):
    farm, priv = obs["farms"][seat], obs["private"]
    shed = priv.get("shed") or {}
    empty = {"COOP": [], "PASTURE": []}
    collect, water = [], []
    for y, row in enumerate(farm["tiles"]):
        for x, t in enumerate(row):
            if not isinstance(t, dict):
                continue
            if t.get("kind") in empty and t.get("animal") is None:
                empty[t["kind"]].append((x, y))
            elif t.get("animal") is not None:
                if int(t.get("yield_units", 0)) > 0 or t.get("fertilizer_available"):
                    collect.append((x, y))
            elif t.get("kind") == "PLANT":
                if int(t.get("yield_units", 0)) > 0:
                    collect.append((x, y))
                elif not t.get("watered_today"):
                    water.append((x, y))
    half = board // 2
    depot = [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]
    fillable = []
    for an, d in K.ANIMALS.items():
        if shed.get(an, 0) > 0:
            fillable += empty[d["structure"]]
    def near(pts):
        return min((_dist(pos, p) for p in pts), default=None)

    def round_trip(pts):
        """Exact turns for the whole errand: walk out, act, walk from THAT tile to
        the depot, drop. Adding start->target and start->depot is not the same
        journey and undercounts; this uses the second leg from the target."""
        best = None
        for p in pts:
            d = _dist(pos, p) + 1 + min(_dist(p, q) for q in depot) + 1
            best = d if best is None else min(best, d)
        return best

    return {"to_depot": near(depot), "to_collect": near(collect),
            "to_water": near(water), "to_fillable_structure": near(fillable),
            "collect_and_deposit_turns": round_trip(collect),
            "collect_and_home_turns": (min((2 * _dist(pos, p) + 1 for p in collect),
                                           default=None)),
            "fill_turns": round_trip(fillable) if fillable else None,
            "n_collect": len(collect), "n_fillable": len(fillable)}


def measure(seed, seat, opponent_spec):
    from kaggle_environments.envs.kaggriculture import kaggriculture as K
    A, arl_id = route_cards.load_arlene()
    opp, opp_id = route_cards.load_agent(opponent_spec)
    env = cards_mod.make_env(seed)
    env.reset(2)
    mine, theirs = A.Agent(), A.Agent()
    open_run = {}
    runs = []
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                a = mine.act(obs)
                farm, priv = obs["farms"][seat], obs["private"]
                tiles = farm["tiles"]
                board = len(tiles)
                seeds = priv.get("seeds") or {}
                invs = priv.get("inventories") or []
                pos = [farm["farmer"]] + list(farm.get("hands", []))
                units = [list(a["farmer"])] + [list(h) for h in a["hands"]]
                step = int(obs["day"]) * 24 + int(obs["hour"])
                free_now = set()
                for j, op in enumerate(units):
                    if j >= len(pos):
                        continue
                    x, y = int(pos[j][0]), int(pos[j][1])
                    if not (0 <= x < board and 0 <= y < board):
                        continue
                    inv = invs[j] if j < len(invs) else {}
                    if A._noop(op, tiles[y][x], inv, seeds, x, y, board):
                        free_now.add(j)
                        if j not in open_run:
                            open_run[j] = {"unit": j, "start": step,
                                           "day": int(obs["day"]),
                                           "at": (x, y), "len": 0,
                                           "targets": targets(obs, seat, (x, y),
                                                              K, board)}
                        open_run[j]["len"] += 1
                for j in list(open_run):
                    if j not in free_now:
                        runs.append(open_run.pop(j))
                acts[i] = a
            else:
                acts[i] = (theirs.act(obs) if opponent_spec == "arlene"
                           else route_cards.call(opp, obs, env.configuration))
        env.step(acts)
    runs.extend(open_run.values())
    return runs, {"seed": seed, "seat": seat, "arlene": arl_id, "opponent": opp_id}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--opponent", default="arlene")
    ap.add_argument("--out", default="results/free-runs.json")
    a = ap.parse_args()
    allruns, meta = [], []
    for seed in a.seeds:
        runs, m = measure(seed, a.seat, a.opponent)
        allruns.extend(dict(r, seed=seed) for r in runs)
        meta.append(m)
        hist = Counter(min(r["len"], 12) for r in runs)
        print(f"seed {seed} seat {a.seat}: {len(runs)} free runs; length histogram "
              f"(12+ pooled) " + " ".join(f"{k}:{hist[k]}" for k in sorted(hist)),
              flush=True)
    long_runs = [r for r in allruns if r["len"] >= 4]
    print(f"\nruns of 4+ consecutive free turns: {len(long_runs)} of {len(allruns)}")
    def fits(key):
        return [r for r in long_runs
                if r["targets"].get(key) is not None
                and r["targets"][key] <= r["len"]]
    reach = [r for r in long_runs
             if r["targets"]["to_collect"] is not None
             and r["targets"]["to_collect"] + 1 <= r["len"]]
    print(f"  reach a collectable tile and act within the run:       {len(reach)}")
    print(f"  collect and return to the START tile within the run:   "
          f"{len(fits('collect_and_home_turns'))}")
    print(f"  collect, walk THAT tile to the depot and DROP:         "
          f"{len(fits('collect_and_deposit_turns'))}")
    print(f"  reach a fillable structure, place, and deposit:        "
          f"{len(fits('fill_turns'))}")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"meta": meta, "runs": allruns}, open(a.out, "w"), indent=1,
              default=str)


if __name__ == "__main__":
    main()
