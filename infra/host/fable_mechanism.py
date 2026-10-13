#!/usr/bin/env python3
"""host/fable_mechanism.py — WHY is 1 bit enough? sign-agreement vs cosine + outlier ('rogue') dimensions.
pure python, no numpy, read-only. (fable, 07-16)"""
import itertools, json, math, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, cos

MODELS = [("A_large", "C:/llm/models/titan.gguf"),
          ("B_small", "C:/llm/models/SmolLM2-360M-Instruct-Q8_0.gguf")]
ANTON = [("love","hate"),("hot","cold"),("light","dark"),("up","down"),("day","night"),("true","false"),
         ("big","small"),("good","evil"),("life","death"),("open","closed"),("rich","poor"),("fast","slow")]
RANDW = ["stone","music","river","clock","bread","engine","cloud","letter","garden","planet","window","glass",
         "ocean","paper","mountain","iron","silver","copper","harvest","signal"]


def sign_agree(a, b):
    d = len(a); m = sum(1 for k in range(d) if (a[k] >= 0) == (b[k] >= 0)); return m / d


def study(tag, path):
    g = GGUF(path); random.seed(11); d = g.n_embd
    out = {"tag": tag, "dim": d, "vocab": g.n_vocab}

    # ---- sign-agreement vs cosine across many random pairs: is cos a function of sign overlap? ----
    ids = random.sample(range(g.n_vocab), min(700, g.n_vocab))
    rows = [g._row(i) for i in ids]
    xs, ys = [], []
    for _ in range(2500):
        a, b = random.randrange(len(rows)), random.randrange(len(rows))
        if a == b: continue
        xs.append(sign_agree(rows[a], rows[b])); ys.append(cos(rows[a], rows[b]))
    n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
    sx = math.sqrt(sum((x-mx)**2 for x in xs)/n); sy = math.sqrt(sum((y-my)**2 for y in ys)/n)
    r = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))/n / (sx*sy + 1e-12)
    out["sign_vs_cos_pearson_r"] = round(r, 4)

    # ---- sign-only reconstruction: replace every weight by ±1, remeasure opposites/random ----
    def sgn(v): return [1.0 if x >= 0 else -1.0 for x in v]
    def C_full(a, b): return cos(g.vec(a), g.vec(b)) if (g.vec(a) and g.vec(b)) else None
    def C_sign(a, b):
        va, vb = g.vec(a), g.vec(b)
        if not (va and vb): return None
        sa, sb = sgn(va), sgn(vb); return sum(x*y for x, y in zip(sa, sb)) / d
    Af = [C_full(a,b) for a,b in ANTON if C_full(a,b) is not None]
    Rf = [C_full(a,b) for a,b in itertools.combinations(RANDW,2) if C_full(a,b) is not None]
    As = [C_sign(a,b) for a,b in ANTON if C_sign(a,b) is not None]
    Rs = [C_sign(a,b) for a,b in itertools.combinations(RANDW,2) if C_sign(a,b) is not None]
    out["full_ratio"] = round((sum(Af)/len(Af))/(sum(Rf)/len(Rf)), 3)
    out["signonly_ratio"] = round((sum(As)/len(As))/(sum(Rs)/len(Rs)), 3)

    # ---- rogue dimensions: which dims carry the most variance across the vocab sample? ----
    dmean = [0.0]*d
    for rr in rows:
        for k in range(d): dmean[k] += rr[k]
    dmean = [x/len(rows) for x in dmean]
    dvar = [0.0]*d
    for rr in rows:
        for k in range(d):
            dd = rr[k]-dmean[k]; dvar[k] += dd*dd
    dvar = [x/len(rows) for x in dvar]
    tot = sum(dvar) + 1e-12
    order = sorted(range(d), key=lambda k: -dvar[k])
    top1 = dvar[order[0]]/tot; top5 = sum(dvar[order[k]] for k in range(5))/tot
    top1pct = sum(dvar[order[k]] for k in range(max(1, d//100)))/tot
    out["rogue_dims"] = {"top1_frac_of_var": round(top1,4), "top5_frac": round(top5,4),
                         "top1pct_dims_frac": round(top1pct,4), "top_dim_ids": order[:5],
                         "expected_uniform_top5": round(5/d,4)}

    # ---- separation after ABLATING the top rogue dims (zero them, renormalize) ----
    kill = set(order[:max(1, d//100)])                        # drop the top 1% highest-variance dims
    def ablate(w):
        v = g.vec(w)
        if not v: return None
        z = [0.0 if k in kill else v[k] for k in range(d)]
        n = math.sqrt(sum(x*x for x in z)) or 1.0; return [x/n for x in z]
    def Ca(a, b): return cos(ablate(a), ablate(b)) if (ablate(a) and ablate(b)) else None
    Aa = [Ca(a,b) for a,b in ANTON if Ca(a,b) is not None]
    Ra = [Ca(a,b) for a,b in itertools.combinations(RANDW,2) if Ca(a,b) is not None]
    out["ablated_top1pct_ratio"] = round((sum(Aa)/len(Aa))/(sum(Ra)/len(Ra)), 3)
    return out


if __name__ == "__main__":
    res = []
    for tag, path in MODELS:
        if not os.path.exists(path): print(f"{tag}: not on disk"); continue
        print(f"digging {tag} …", flush=True); res.append(study(tag, path))
    json.dump(res, open(os.path.join(HERE, "fable_mechanism_data.json"), "w"), indent=1)
    print("\n" + "="*72)
    for r in res:
        print(f"\n{r['tag']}  (dim {r['dim']} · vocab {r['vocab']:,})")
        print(f"  sign-agreement ↔ cosine   Pearson r = {r['sign_vs_cos_pearson_r']:+.3f}   "
              f"(→ cosine is {'almost fully' if abs(r['sign_vs_cos_pearson_r'])>0.9 else 'partly'} determined by sign overlap)")
        print(f"  opposites/random ratio    full weights {r['full_ratio']}×   →   SIGN-ONLY (±1) {r['signonly_ratio']}×")
        rd = r["rogue_dims"]
        print(f"  rogue dims   top-1 dim = {rd['top1_frac_of_var']*100:.1f}% of all variance · top-5 = {rd['top5_frac']*100:.1f}% "
              f"· top-1% of dims = {rd['top1pct_dims_frac']*100:.1f}%  (uniform would be top-5 = {rd['expected_uniform_top5']*100:.2f}%)")
        print(f"  separation AFTER killing the top-1% rogue dims: {r['ablated_top1pct_ratio']}×  (vs {r['full_ratio']}× raw)")
    print(f"\ndumped → fable_mechanism_data.json")
