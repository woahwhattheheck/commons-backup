"""Cheap scan: what do Arlene's three checkpoint features read, seed by seed?

Pricing a tail choice costs a full extra game per option. Most seeds are not worth
that: a feature far below its threshold is a decision with no tension in it. This
plays ONE game per seed and records what each checkpoint saw and whether the
baseline switched, so the expensive realised-value runs can be aimed at the seeds
where a threshold is actually close to flipping.
"""

import argparse
import json
import os

import cards as cards_mod
import route_cards


def scan(seed, seat, opponent_spec, A):
    opp, _ = route_cards.load_agent(opponent_spec)
    env = cards_mod.make_env(seed)
    env.reset(2)
    mine, theirs = A.Agent(), A.Agent()
    seen = {}
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                step = int(obs["day"]) * 24 + int(obs["hour"])
                for (turn, feat, thr, target) in A.DECISIONS:
                    if step == turn:
                        before = mine.cur
                        val = A._feature(obs, feat)
                        seen[turn] = {"feature": feat, "value": val,
                                      "threshold": thr, "before": before,
                                      "switch_ok": mine._switch_ok(target, turn),
                                      "would_switch": val >= thr}
                acts[i] = mine.act(obs)
                for turn in list(seen):
                    if seen[turn].get("after") is None or "after" not in seen[turn]:
                        if int(obs["day"]) * 24 + int(obs["hour"]) == turn:
                            seen[turn]["after"] = mine.cur
                            seen[turn]["switched"] = mine.cur != seen[turn]["before"]
            else:
                acts[i] = (theirs.act(obs) if opponent_spec == "arlene"
                           else route_cards.call(opp, obs, env.configuration))
        env.step(acts)
    farms = env.state[0].observation.farms
    own = float(farms[seat]["money"])
    rival = float(farms[1 - seat]["money"])
    return {"seed": seed, "seat": seat, "opponent": opponent_spec,
            "own_cash": own, "rival_cash": rival, "margin": own - rival,
            "checkpoints": seen}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--opponent", default="arlene")
    ap.add_argument("--out", default="results/tail-scan.json")
    a = ap.parse_args()
    A, arl_id = route_cards.load_arlene()
    rows = []
    for seed in a.seeds:
        r = scan(seed, a.seat, a.opponent, A)
        rows.append(r)
        parts = []
        for turn, c in sorted(r["checkpoints"].items()):
            gap = c["value"] - c["threshold"]
            parts.append(f"{turn}:{c['feature']}={c['value']} thr{c['threshold']} "
                         f"gap{gap:+g}{' SWITCHED' if c.get('switched') else ''}"
                         f"{'' if c['switch_ok'] else ' [incompatible]'}")
        print(f"seed {seed:8d} own {r['own_cash']:9.0f} margin {r['margin']:+9.0f}  "
              + " | ".join(parts), flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"arlene": arl_id, "rows": rows}, open(a.out, "w"), indent=1,
              default=str)


if __name__ == "__main__":
    main()
