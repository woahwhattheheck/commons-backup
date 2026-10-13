"""Does stacking change T13's own behaviour?

T13's contract says its bound is derived from the intact Arlene/SELL route tape.
This runs the seed switch twice on the same game -- once over the BARE intact
parent (T13's own parent) and once over this lab's cap-production parent -- and
diffs the budget's own event log. Identical event logs mean the composition did
not disturb the component; a difference is the interaction, reported rather than
smoothed over.

Run: python -B compat_seed.py --seeds 9890040 --seats 0 --opponents arlene
"""

import argparse
import json
import os

import cards as cards_mod
import seed_committed_2x2 as X


def run(seed, seat, opponent, arm_name):
    import arlene_arm
    import route_cards
    A, _ = route_cards.load_arlene()
    opp, _ = arlene_arm.make_opponent(opponent, A)
    me = X.make(arm_name)
    env = cards_mod.make_env(seed)
    env.reset(2)
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            acts[i] = (me.act(X.normalise(obs, i), env.configuration)
                       if i == seat else opp(obs, env.configuration))
        env.step(acts)
    farms = env.state[0].observation.farms
    return {"arm": arm_name, "seed": seed, "seat": seat, "opponent": opponent,
            "own_cash": float(farms[seat]["money"]),
            "rival_cash": float(farms[1 - seat]["money"]),
            "events": list(getattr(me.budget, "events", []) or [])
                      if me.budget is not None else [],
            "cap_fills": len(getattr(me.production, "fills", []) or [])
                         if me.production is not None else 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0])
    ap.add_argument("--opponents", nargs="+", default=["arlene"])
    ap.add_argument("--out", default="results/compat-seed.json")
    a = ap.parse_args()
    rows = []
    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                bare = run(seed, seat, opp, "bare_seed")
                over = run(seed, seat, opp, "seed")
                same = bare["events"] == over["events"]
                rows.append({"seed": seed, "seat": seat, "opponent": opp,
                             "bare": bare, "over_production": over,
                             "budget_events_identical": same})
                print(f"seed {seed} seat {seat} vs {opp:9s} "
                      f"bare budget events {len(bare['events'])} "
                      f"over-production {len(over['events'])} "
                      f"cap fills {over['cap_fills']} "
                      f"identical {same}", flush=True)
                if not same:
                    print("   bare:", json.dumps(bare["events"]))
                    print("   over:", json.dumps(over["events"]))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1, default=str)
    n = sum(1 for r in rows if r["budget_events_identical"])
    print(f"\n{n}/{len(rows)} games: the seed budget behaves identically over this "
          f"lab's production parent and over T13's bare parent")


if __name__ == "__main__":
    main()
