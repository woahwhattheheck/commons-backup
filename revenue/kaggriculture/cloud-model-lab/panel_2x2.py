"""The 2x2 panel: seed recovery x committed producer envelope, paired per game.

Four arms per (seed, seat, opponent), differing only by which of the two additive
switches is on. `baseline` is the control. The end-of-day RNG path is recorded for
every arm, so an arm that differs from the control can be shown to be playing the
SAME market world rather than a different town.

W/T/L against the rival is reported first, because only win/loss/tie changes
ratings; own and rival cash are reported alongside to diagnose why, not as the
result. The interaction term d(combined) - d(seed) - d(committed) is reported per
pair, because two switches that each help do not have to add.

Run: python -B panel_2x2.py --seeds ... --opponents arlene apex lonespear cok
"""

import argparse
import json
import os
import time

import cards as cards_mod
import seed_committed_2x2 as X

ARM_ORDER = ["baseline", "seed", "committed", "combined"]


def game(seed, seat, opponent, arm_name, record_path=True):
    import arlene_arm
    import route_cards
    A, arl_id = route_cards.load_arlene()
    rec = None
    if record_path:
        import market_path
        rec = market_path.PathRecorder()
        rec.__enter__()
    env = cards_mod.make_env(seed)
    env.reset(2)
    opp, opp_id = arlene_arm.make_opponent(opponent, A)
    me = X.make(arm_name)
    t0 = time.time()
    worst, n = 0.0, 0
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                t = time.perf_counter()
                acts[i] = me.act(X.normalise(obs, i), env.configuration)
                worst = max(worst, time.perf_counter() - t)
            else:
                acts[i] = opp(obs, env.configuration)
        env.step(acts)
        n += 1
    farms = env.state[0].observation.farms
    own, rival = float(farms[seat]["money"]), float(farms[1 - seat]["money"])
    path = None
    if rec is not None:
        path = rec.path()
        rec.__exit__(None, None, None)
    rep = me.production.report() if hasattr(me.production, "report") else None
    return {"seed": seed, "seat": seat, "opponent": opponent, "arm": arm_name,
            "own_cash": own, "rival_cash": rival, "margin": own - rival,
            "rounds": n, "wall_s": round(time.time() - t0, 1),
            "worst_action_s": round(worst, 4), "path": path,
            "opponent_id": opp_id, "arlene": arl_id,
            "parent_calls": me.parent_calls,
            "cap_fills": len(getattr(me.production, "fills", []) or []),
            "budget_events": len(getattr(me.budget, "events", []) or [])
                             if me.budget is not None else None,
            "plan_report": rep}


def wtl(margin):
    return "W" if margin > 0 else ("L" if margin < 0 else "T")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--opponents", nargs="+",
                    default=["arlene", "apex", "lonespear", "cok"])
    ap.add_argument("--arms", nargs="+", default=ARM_ORDER)
    ap.add_argument("--control", default="baseline")
    ap.add_argument("--no-path", action="store_true")
    ap.add_argument("--out", default="results/panel-2x2.json")
    a = ap.parse_args()
    rows = []
    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                by = {}
                for arm in a.arms:
                    r = game(seed, seat, opp, arm, not a.no_path)
                    by[arm] = r
                    rows.append(r)
                base = by[a.control]
                import market_path
                line = (f"seed {seed} seat {seat} vs {opp:9s} "
                        f"base own {base['own_cash']:8.0f} rival "
                        f"{base['rival_cash']:8.0f} {wtl(base['margin'])}")
                for arm in a.arms:
                    if arm == a.control:
                        continue
                    r = by[arm]
                    div = (len(market_path.diff({"path": base["path"]},
                                                {"path": r["path"]}))
                           if not a.no_path else None)
                    r["path_divergent_days"] = div
                    line += (f" | {arm} {wtl(r['margin'])} "
                             f"d_own {r['own_cash'] - base['own_cash']:+7.0f} "
                             f"d_riv {r['rival_cash'] - base['rival_cash']:+7.0f}"
                             + (f" pathdiv {div}d" if div is not None else ""))
                if set(ARM_ORDER) <= set(by):
                    inter = ((by["combined"]["own_cash"] - base["own_cash"])
                             - (by["seed"]["own_cash"] - base["own_cash"])
                             - (by["committed"]["own_cash"] - base["own_cash"]))
                    by["combined"]["interaction_d_own"] = inter
                    line += f" | interaction {inter:+7.0f}"
                print(line, flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1, default=str)

    ctrl = {(r["seed"], r["seat"], r["opponent"]): r
            for r in rows if r["arm"] == a.control}
    print("\n=== W/T/L first (only win/loss/tie changes ratings) ===")
    print(f"  {'arm':10s} {'W/T/L':>8s} {'flips':>6s} {'mean d_own':>11s} "
          f"{'mean d_rival':>13s} {'cap fills':>10s} {'budget ev':>10s}")
    for arm in a.arms:
        rs = [r for r in rows if r["arm"] == arm]
        v = [wtl(r["margin"]) for r in rs]
        k = lambda r: (r["seed"], r["seat"], r["opponent"])
        flips = sum(1 for r in rs if wtl(r["margin"]) != wtl(ctrl[k(r)]["margin"]))
        do = [r["own_cash"] - ctrl[k(r)]["own_cash"] for r in rs]
        dr = [r["rival_cash"] - ctrl[k(r)]["rival_cash"] for r in rs]
        print(f"  {arm:10s} {v.count('W')}/{v.count('T')}/{v.count('L'):<4d} "
              f"{flips:6d} {sum(do)/len(do):+11.1f} {sum(dr)/len(dr):+13.1f} "
              f"{sum(r['cap_fills'] for r in rs):10d} "
              f"{sum(r['budget_events'] or 0 for r in rs):10d}")
    seeds = sorted({r["seed"] for r in rows})
    opps = sorted({r["opponent"] for r in rows})
    lineage = {"arlene": "arlene", "apex": "apex",
               "lonespear": "public bank PR9942", "cok": "public bank PR9942"}
    print(f"\n  independent seeds: {len(seeds)} {seeds}")
    print(f"  opponent entries: {len(opps)} {opps}")
    print("  independent opponent lineages: "
          f"{len({lineage.get(o, o) for o in opps})} "
          f"{sorted({lineage.get(o, o) for o in opps})}  "
          "(lonespear and COK are two frozen public source revisions from ONE "
          "bank, not two independent families)")
    if not a.no_path:
        bad = [r for r in rows if r.get("path_divergent_days")]
        print(f"  pairs whose end-of-day RNG path differs from the control: "
              f"{len(bad)}")


if __name__ == "__main__":
    main()
