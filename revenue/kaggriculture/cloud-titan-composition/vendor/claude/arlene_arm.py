"""Paired panel: exact Arlene versus Arlene + motif overlay, both seats.

Control and candidate differ by the overlay and nothing else -- same seed, same
seat, same opponent, same intact baseline underneath. Own cash and own-minus-rival
margin are tracked separately, because a change can move one without the other and
the competition scores the seat's own cash.

Opponents are the vendored public parents (Apache-2.0, notices and lineage under
../cloud-frontier-policy/next-panel/). No source is reacquired here.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import time

import cards as cards_mod
import native_motifs


def NM_engine():
    return native_motifs.engine()


import arlene_motifs
import arlene_plan
import route_cards


def _load(path, name="agent"):
    rp = os.path.realpath(path)
    sp = importlib.util.spec_from_file_location(
        os.path.splitext(os.path.basename(rp))[0] + "_arm", rp)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    sha = hashlib.sha256(open(rp, "rb").read()).hexdigest()
    return mod, {"path": rp, "sha256": sha, "label": f"{os.path.basename(rp)}@{sha[:12]}"}


OPPONENTS = {
    "arlene": None,   # the vendored module itself, a fresh Agent per game
    "apex": "/home/user/work/apex-rt/main.py",
}


def make_opponent(name, A):
    if name == "arlene":
        ag = A.Agent()
        return (lambda obs, cfg: ag.act(obs)), {"label": "arlene (vendored)"}
    mod, ident = _load(OPPONENTS[name])
    fn = mod.agent
    def call(obs, cfg):
        try:
            return fn(obs, cfg)
        except TypeError:
            return fn(obs)
    return call, ident


def game(seed, seat, opponent, table, overlay, A, arl_id, record_path=False,
         ledger=False):
    """One full game. `record_path` also records the end-of-day RNG path, which is
    how a candidate/control pair is told apart: an identical path means the two
    games share a market world, so any cash difference between them is economic
    and not a different town."""
    rec = None
    book = None
    if ledger:
        import ledger as ledger_mod
        book = {"market": [], "harvest": []}
        owners = {}
        K = __import__("kaggle_environments.envs.kaggriculture.kaggriculture",
                       fromlist=["_commit_unit"])
        originals = ledger_mod._wrap(K, book, owners)
        # The owner map must be built from the farm objects the INTERPRETER is
        # holding. `env.step` re-structifies the state, so ids captured from
        # `env.state` before the step are stale and every order lands unattributed.
        # `_process_market` receives the live state, so the map is rebuilt there.
        _orig_market = K._process_market

        def process_market(state, env_):
            owners.clear()
            for s_i, f in enumerate(state[0].observation.farms):
                owners[id(f)] = s_i
            return _orig_market(state, env_)
        K._process_market = process_market
    if record_path:
        import market_path
        rec = market_path.PathRecorder()
        rec.__enter__()
    env = cards_mod.make_env(seed)
    env.reset(2)
    opp, opp_id = make_opponent(opponent, A)
    if not overlay:
        me = A.Agent()
    elif isinstance(table, dict) and table.get("lane") == "plan":
        me = arlene_plan.PlanOverlay(A, table["chooser"],
                                     max_steps=table.get("max_steps",
                                                         arlene_plan.MAX_PLAN_STEPS),
                                     deposit=table.get("deposit", True),
                                     min_value=table.get("min_value", 0.0),
                                     one_way=table.get("one_way", False))
    else:
        me = arlene_motifs.Overlay(A, table)
    t0 = time.time()
    n = 0
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            acts[i] = me.act(obs) if i == seat else opp(obs, env.configuration)
        env.step(acts)
        n += 1
    farms = env.state[0].observation.farms
    own = float(farms[seat]["money"])
    rival = float(farms[1 - seat]["money"])
    ledger_out = None
    if book is not None:
        ledger_mod._unwrap(K, originals)
        K._process_market = _orig_market
        agg = {}
        for r in book["market"]:
            k = (r["seat"], r["op"], r["item"])
            e = agg.setdefault(k, {"units": 0, "cash": 0.0})
            e["units"] += 1
            e["cash"] += r["price"] * (1 if r["op"] == "SELL" else -1)
        ledger_out = {f"seat{k[0]}|{k[1]}|{k[2]}": v for k, v in sorted(
            agg.items(), key=lambda kv: str(kv[0]))}
    path = None
    if rec is not None:
        path = rec.path()
        rec.__exit__(None, None, None)
    return {"seed": seed, "seat": seat, "opponent": opponent, "path": path,
            "ledger": ledger_out,
            "opponent_id": opp_id, "arlene": arl_id,
            "arm": "candidate" if overlay else "control",
            "own_cash": own, "rival_cash": rival, "margin": own - rival,
            "rounds": n, "wall_s": round(time.time() - t0, 1),
            "fills": getattr(me, "fills", []),
            "plan_report": me.report() if hasattr(me, "report") else None,
            "motif_table": {"motifs": len(table.get("motifs", []) or []),
                            "proposable": sum(1 for m in table.get("motifs", [])
                                              if m.get("proposable")),
                            "authored": table.get("meta", {}).get("authored"),
                            "provenance": table.get("meta", {}).get("provenance")}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--opponents", nargs="+", default=["arlene", "apex"])
    ap.add_argument("--motifs", default=None)
    ap.add_argument("--plan", choices=("greedy", "cap"), default=None,
                    help="run the bounded worker-reallocation continuation lane "
                         "with the named target chooser instead of a motif table")
    ap.add_argument("--plan-max-steps", type=int, default=arlene_plan.MAX_PLAN_STEPS)
    ap.add_argument("--plan-min-value", type=float, default=0.0)
    ap.add_argument("--plan-no-deposit", action="store_true")
    ap.add_argument("--label", default=None)
    ap.add_argument("--ledger", action="store_true",
                    help="record every executed market order per seat with its unit "
                         "price, so a rival cash change can be attributed to its own "
                         "buys and sells rather than asserted")
    ap.add_argument("--record-path", action="store_true",
                    help="record the end-of-day RNG path for each arm and report "
                         "whether the pair shared a market world")
    ap.add_argument("--out", default="results/arlene-arm.json")
    a = ap.parse_args()
    A, arl_id = route_cards.load_arlene()
    if a.plan:
        chooser = (arlene_plan.CapChooser(NM_engine()) if a.plan == "cap"
                   else arlene_plan.GreedyChooser())
        table = {"lane": "plan", "chooser": chooser,
                 "one_way": a.plan == "cap",
                 "max_steps": a.plan_max_steps, "deposit": not a.plan_no_deposit,
                 "min_value": a.plan_min_value, "meta": {"authored": "hand",
                 "provenance": "engine-derived-control"}}
        label = a.label or f"plan/{a.plan} steps<={a.plan_max_steps}"
    else:
        table = json.load(open(a.motifs))
        label = a.label or os.path.basename(a.motifs)
    rows = []
    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                c = game(seed, seat, opp, table, False, A, arl_id, a.record_path,
                         a.ledger)
                d = game(seed, seat, opp, table, True, A, arl_id, a.record_path,
                         a.ledger)
                if a.record_path:
                    import market_path
                    diff = market_path.diff({"path": c["path"]}, {"path": d["path"]})
                    c["path_divergent_days"] = d["path_divergent_days"] = len(diff)
                    d["path_first_divergence"] = diff[0] if diff else None
                rows.extend([c, d])
                print(f"seed {seed} seat {seat} vs {opp:7s}  "
                      f"control own {c['own_cash']:9.0f} margin {c['margin']:+9.0f} | "
                      f"candidate own {d['own_cash']:9.0f} margin {d['margin']:+9.0f} | "
                      f"d_own {d['own_cash'] - c['own_cash']:+9.0f} "
                      f"d_margin {d['margin'] - c['margin']:+9.0f} "
                      f"fills {len(d['fills'])}"
                      + (f" path_div {d.get('path_divergent_days')}d"
                         if a.record_path else "")
                      + (f" done {d['plan_report']['completed']}"
                         f" abandoned {d['plan_report']['abandoned']}"
                         if d.get("plan_report") else ""), flush=True)
    def agg(sel):
        c = [r for r in rows if r["arm"] == "control" and sel(r)]
        d = [r for r in rows if r["arm"] == "candidate" and sel(r)]
        if not c:
            return None
        pairs = [(x, y) for x in c for y in d
                 if (x["seed"], x["seat"], x["opponent"]) ==
                 (y["seed"], y["seat"], y["opponent"])]
        return {
            "games": len(pairs),
            "mean_own_control": sum(x["own_cash"] for x, _ in pairs) / len(pairs),
            "mean_own_candidate": sum(y["own_cash"] for _, y in pairs) / len(pairs),
            "mean_d_own": sum(y["own_cash"] - x["own_cash"] for x, y in pairs) / len(pairs),
            "mean_margin_control": sum(x["margin"] for x, _ in pairs) / len(pairs),
            "mean_margin_candidate": sum(y["margin"] for _, y in pairs) / len(pairs),
            "mean_d_margin": sum(y["margin"] - x["margin"] for x, y in pairs) / len(pairs),
            "candidate_wins": sum(1 for _, y in pairs if y["margin"] > 0),
            "candidate_ties": sum(1 for _, y in pairs if y["margin"] == 0),
            "candidate_losses": sum(1 for _, y in pairs if y["margin"] < 0),
            "pairs_own_improved": sum(1 for x, y in pairs if y["own_cash"] > x["own_cash"]),
            "pairs_own_worsened": sum(1 for x, y in pairs if y["own_cash"] < x["own_cash"]),
            "total_fills": sum(len(y["fills"]) for _, y in pairs),
        }
    summary = {"table": label, "overall": agg(lambda r: True),
               "by_opponent": {o: agg(lambda r, o=o: r["opponent"] == o)
                               for o in a.opponents}}
    print("\n=== summary ===")
    print(json.dumps(summary, indent=1, default=str))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"summary": summary, "rows": rows}, open(a.out, "w"),
              indent=1, default=str)


if __name__ == "__main__":
    main()
