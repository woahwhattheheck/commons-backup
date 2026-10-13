"""Merge the 2x2 panel shards and report what actually decides a rating.

Reports W/T/L first. Own and rival cash diagnose why; they are not the result.
Counts are reported as TRUE independent observations, not as game counts: two
seats that return byte-identical cash are one observation, and an opponent that
finishes on zero cash discriminates nothing.
"""

import argparse
import json
from collections import defaultdict

LINEAGE = {"arlene": "arlene", "apex": "apex",
           "lonespear": "public bank PR9942", "cok": "public bank PR9942"}


def wtl(m):
    return "W" if m > 0 else ("L" if m < 0 else "T")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--control", default="baseline")
    ap.add_argument("--out", default="results/2x2-summary.json")
    a = ap.parse_args()
    rows = []
    for p in a.inputs:
        rows += json.load(open(p))
    key = lambda r: (r["seed"], r["seat"], r["opponent"])
    ctrl = {key(r): r for r in rows if r["arm"] == a.control}
    arms = []
    for r in rows:
        if r["arm"] not in arms:
            arms.append(r["arm"])

    # true independent observations: collapse seats that return identical cash
    cells = defaultdict(list)
    for r in rows:
        if r["arm"] == a.control:
            cells[(r["seed"], r["opponent"])].append((r["seat"], r["own_cash"],
                                                      r["rival_cash"]))
    dup_seats, indep_cells, degenerate = 0, 0, 0
    for (seed, opp), v in sorted(cells.items()):
        vals = {(o, rv) for _, o, rv in v}
        if len(v) > 1 and len(vals) == 1:
            dup_seats += 1
        indep_cells += len(vals)
        if any(rv == 0 for _, _, rv in v):
            degenerate += 1

    print("=== W/T/L first (only win/loss/tie changes ratings) ===")
    print(f"  {'arm':11s} {'W/T/L':>9s} {'flips':>6s} {'T->W':>5s} {'->L':>4s} "
          f"{'mean d_own':>11s} {'mean d_rival':>13s} {'mean d_margin':>14s}")
    summary = {}
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm and key(r) in ctrl]
        v = [wtl(r["margin"]) for r in rs]
        flips = [(r, wtl(ctrl[key(r)]["margin"]), wtl(r["margin"])) for r in rs
                 if wtl(r["margin"]) != wtl(ctrl[key(r)]["margin"])]
        do = [r["own_cash"] - ctrl[key(r)]["own_cash"] for r in rs]
        dr = [r["rival_cash"] - ctrl[key(r)]["rival_cash"] for r in rs]
        dm = [r["margin"] - ctrl[key(r)]["margin"] for r in rs]
        tw = sum(1 for _, b, c in flips if b == "T" and c == "W")
        tol = sum(1 for _, b, c in flips if c == "L")
        print(f"  {arm:11s} {v.count('W')}/{v.count('T')}/{v.count('L'):<5d}"
              f"{len(flips):6d} {tw:5d} {tol:4d} {sum(do)/len(do):+11.1f} "
              f"{sum(dr)/len(dr):+13.1f} {sum(dm)/len(dm):+14.1f}")
        summary[arm] = dict(W=v.count("W"), T=v.count("T"), L=v.count("L"),
                            flips=len(flips), tie_to_win=tw, to_loss=tol,
                            mean_d_own=round(sum(do)/len(do), 1),
                            mean_d_rival=round(sum(dr)/len(dr), 1),
                            mean_d_margin=round(sum(dm)/len(dm), 1),
                            games=len(rs),
                            flip_detail=[(key(r), b, c) for r, b, c in flips])

    inter = [r["interaction_d_own"] for r in rows if "interaction_d_own" in r]
    if inter:
        print(f"\n  interaction d(combined)-d(seed)-d(committed), own cash: "
              f"n={len(inter)} min {min(inter):+.0f} max {max(inter):+.0f} "
              f"nonzero {sum(1 for x in inter if x)}")
    div = [r for r in rows if r.get("path_divergent_days")]
    print(f"  pairs whose end-of-day RNG path differs from the control: {len(div)}")
    worst = max((r.get("worst_action_s") or 0) for r in rows)
    print(f"  worst single action across every arm and game: {worst*1000:.0f} ms")

    seeds = sorted({r["seed"] for r in rows})
    opps = sorted({r["opponent"] for r in rows})
    print(f"\n  games {len([r for r in rows if r['arm'] == a.control])} control + "
          f"{len(rows) - len([r for r in rows if r['arm'] == a.control])} arm")
    print(f"  seeds {len(seeds)} {seeds}")
    print(f"  opponent entries {len(opps)}; independent opponent LINEAGES "
          f"{len({LINEAGE.get(o, o) for o in opps})} "
          f"{sorted({LINEAGE.get(o, o) for o in opps})}")
    print(f"  (seed,opponent) cells where both seats returned identical cash: "
          f"{dup_seats} of {len(cells)} -- those seats are ONE observation, not two")
    print(f"  independent control outcomes after collapsing identical seats: "
          f"{indep_cells}")
    print(f"  cells whose rival finished on 0 cash (non-discriminating): "
          f"{degenerate}")
    json.dump({"summary": summary, "seeds": seeds, "opponents": opps,
               "identical_seat_cells": dup_seats, "cells": len(cells),
               "independent_control_outcomes": indep_cells,
               "zero_rival_cells": degenerate,
               "interaction": inter, "worst_action_s": worst},
              open(a.out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
