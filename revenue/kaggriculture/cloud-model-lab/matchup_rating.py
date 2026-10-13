"""An EMPIRICAL matchup rating estimate from head-to-head W/T/L. Not a Kaggle score.

Why this exists, and what it is not. Kaggle's simulation leaderboard updates a
Gaussian skill from win/loss/tie outcomes, and Kaggriculture's final standing is
Bradley-Terry. Neither reads coin margin. So a panel that is cash-positive while
every arm wins carries NO rating information, and this tool is built to say so
rather than to manufacture a number.

Model, stated so it can be disagreed with:

  Bradley-Terry on log-strength. P(A beats B) = sigma(s_A - s_B), a tie counts as
  half a win to each side (the standard Davidson-free reduction; it does not model
  tie propensity, and where ties dominate that is a real limitation, reported).
  Fitted by regularised MM iteration with an L2 prior of sd 2.0 on log-strength,
  so a pairing with no losses returns a finite, honestly-bounded estimate instead
  of +infinity.

Anchor, stated: one named entrant is pinned at 0 log-strength and every other
estimate is RELATIVE to it. There is no absolute scale here and no mapping to a
public score.

Uncertainty, grouped: a nonparametric CLUSTER bootstrap over SEEDS, not over
games. Cells inside one seed share a board and are not independent; seats that
return byte-identical cash are collapsed to a single observation first. The
interval is therefore wide and honest rather than narrow and wrong.

  python -B matchup_rating.py --inputs results/*.json --anchor arlene
"""

import argparse
import glob
import json
import math
import random
from collections import defaultdict


def wtl(margin):
    return "W" if margin > 0 else ("L" if margin < 0 else "T")


def load(paths):
    """Every row becomes one head-to-head observation: arm label vs opponent."""
    obs = []
    for p in paths:
        raw = json.load(open(p))
        rows = raw["rows"] if isinstance(raw, dict) and "rows" in raw else raw
        label = None
        if isinstance(raw, dict):
            label = {k: raw[k]["label"] for k in ("candidate", "control")
                     if isinstance(raw.get(k), dict) and "label" in raw[k]}
        for r in rows:
            if r.get("margin") is None or r.get("error"):
                continue
            name = r["arm"]
            if label and name in label:
                name = label[name].split("@")[0]
            obs.append({"seed": r["seed"], "seat": r["seat"], "a": name,
                        "b": r["opponent"], "res": wtl(r["margin"]),
                        "own": r["own_cash"], "rival": r["rival_cash"]})
    return obs


def collapse_identical_seats(obs):
    """Two seats that return byte-identical cash are ONE observation."""
    seen, out, dropped = {}, [], 0
    for o in obs:
        k = (o["seed"], o["a"], o["b"], o["own"], o["rival"])
        if k in seen:
            dropped += 1
            continue
        seen[k] = True
        out.append(o)
    return out, dropped


def fit(obs, anchor, prior_sd=2.0, iters=4000, lr=0.15):
    """Penalised Bradley-Terry MLE by gradient ascent.

    Maximises sum y*log sigma(s_a - s_b) + (1-y)*log sigma(s_b - s_a) minus an
    L2 penalty, with y = 1 for a win, 0 for a loss and 0.5 for a tie. The penalty
    is what keeps an unbeaten entrant finite; without it the likelihood pushes its
    strength to infinity and the number would be meaningless rather than large.
    """
    names = sorted({o["a"] for o in obs} | {o["b"] for o in obs})
    idx = {n: i for i, n in enumerate(names)}
    data = [(idx[o["a"]], idx[o["b"]],
             1.0 if o["res"] == "W" else (0.0 if o["res"] == "L" else 0.5))
            for o in obs]
    s = [0.0] * len(names)
    lam = 1.0 / (prior_sd ** 2)
    n = max(1, len(data))
    for _ in range(iters):
        g = [-lam * v for v in s]
        for a, b, y in data:
            d = s[a] - s[b]
            p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, d))))
            r = y - p
            g[a] += r
            g[b] -= r
        for i in range(len(s)):
            s[i] += lr * g[i] / n
    base = s[idx[anchor]] if anchor in idx else 0.0
    return {nm: s[idx[nm]] - base for nm in names}


def bootstrap(obs, anchor, draws=400, seed=12345):
    rng = random.Random(seed)
    by_seed = defaultdict(list)
    for o in obs:
        by_seed[o["seed"]].append(o)
    seeds = list(by_seed)
    out = defaultdict(list)
    for _ in range(draws):
        pick = [rng.choice(seeds) for _ in seeds]     # cluster bootstrap
        sample = [o for s in pick for o in by_seed[s]]
        try:
            f = fit(sample, anchor)
        except Exception:
            continue
        for n, v in f.items():
            out[n].append(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--anchor", default="arlene")
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--out", default="results/matchup-rating.json")
    a = ap.parse_args()
    paths = [p for g in a.inputs for p in glob.glob(g)]
    obs = load(paths)
    obs, dropped = collapse_identical_seats(obs)
    print(f"observations {len(obs)} after collapsing {dropped} duplicate-seat rows; "
          f"seed clusters {len({o['seed'] for o in obs})}")

    tab = defaultdict(lambda: [0, 0, 0])
    for o in obs:
        t = tab[(o["a"], o["b"])]
        t[{"W": 0, "T": 1, "L": 2}[o["res"]]] += 1
    print("\n=== head-to-head, W/T/L (the only thing a rating reads) ===")
    for (x, y), t in sorted(tab.items()):
        print(f"  {x:34s} vs {y:12s}  {t[0]}/{t[1]}/{t[2]}")

    decisive = sum(t[0] + t[2] for t in tab.values())
    ties = sum(t[1] for t in tab.values())
    if decisive == 0:
        print("\n  every observation is a tie: Bradley-Terry is unidentified here "
              "and NO rating estimate is reported.")
        return
    fitted = fit(obs, a.anchor)
    boot = bootstrap(obs, a.anchor, a.draws)
    print(f"\n=== Bradley-Terry log-strength, anchored at {a.anchor} = 0 ===")
    print("  (relative only; this is NOT a Kaggle public score)")
    res = {}
    for n, v in sorted(fitted.items(), key=lambda kv: -kv[1]):
        b = sorted(boot.get(n, []))
        lo = b[int(0.025 * len(b))] if b else float("nan")
        hi = b[int(0.975 * len(b)) - 1] if b else float("nan")
        p = 1 / (1 + math.exp(-v))
        print(f"  {n:34s} {v:+7.3f}   95% cluster-bootstrap [{lo:+7.3f}, {hi:+7.3f}]"
              f"   implied P(beat {a.anchor}) {p:.3f}")
        res[n] = {"log_strength": round(v, 4), "ci95": [round(lo, 4), round(hi, 4)],
                  "p_beats_anchor": round(p, 4)}
    print(f"\n  decisive results {decisive}, ties {ties} "
          f"({100.0 * ties / (decisive + ties):.0f}% of observations)")
    if ties > decisive:
        print("  MOST results are ties: this reduction treats a tie as half a win "
              "and does not model tie propensity, so read the estimate as weak.")
    json.dump({"anchor": a.anchor, "model": "Bradley-Terry, ties=half-win, "
               "L2 prior sd 2.0, cluster bootstrap over seeds",
               "observations": len(obs), "duplicate_seat_rows_dropped": dropped,
               "seed_clusters": len({o["seed"] for o in obs}),
               "head_to_head": {f"{x} vs {y}": t for (x, y), t in tab.items()},
               "estimates": res, "decisive": decisive, "ties": ties},
              open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
