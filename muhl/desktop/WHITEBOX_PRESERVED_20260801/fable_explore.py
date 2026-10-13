#!/usr/bin/env python3
"""host/fable_explore.py — read-only geometry probes: anisotropy (the cone), norm↔frequency, mean-centering.
pure python, no numpy. dumps JSON + a printed summary. (fable, 07-16)"""
import itertools, json, math, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, cos

MODELS = [("A_large", "C:/llm/models/titan.gguf"),
          ("B_small", "C:/llm/models/SmolLM2-360M-Instruct-Q8_0.gguf")]
ANTON = [("love","hate"),("hot","cold"),("light","dark"),("up","down"),("day","night"),("fast","slow"),
         ("war","peace"),("rich","poor"),("big","small"),("good","evil"),("true","false"),("open","closed"),
         ("full","empty"),("life","death"),("black","white"),("weak","strong"),("high","low"),("wet","dry")]
RANDW = ["stone","music","river","clock","bread","engine","cloud","letter","garden","planet","market","window",
         "copper","harvest","signal","anchor","velvet","meadow","glass","ocean","paper","mountain","iron","silver"]
# a rough frequency ladder (very common → rare), for the norm probe
FREQ = ["the","of","and","to","in","is","it","that","people","because","however","science","molecule",
        "philosophy","elephant","xylophone","serendipity","onomatopoeia"]


def norm(v): n = math.sqrt(sum(x*x for x in v)) or 1.0; return [x/n for x in v]
def sub(a, b): return [a[i]-b[i] for i in range(len(a))]


def study(tag, path):
    g = GGUF(path); random.seed(7)
    out = {"tag": tag, "dim": g.n_embd, "vocab": g.n_vocab, "quant": g.tyname}

    # ---- anisotropy: cosine of random token PAIRS (0 = isotropic; >0 = a crowded cone) ----
    ids = random.sample(range(g.n_vocab), min(1400, g.n_vocab))
    rows = [g._row(i) for i in ids]
    pc = []
    for _ in range(4000):
        a, b = random.randrange(len(rows)), random.randrange(len(rows))
        if a != b: pc.append(cos(rows[a], rows[b]))
    pc.sort(); n = len(pc)
    out["anisotropy"] = {"random_pair_cos_mean": round(sum(pc)/n, 4),
                         "p05": round(pc[n//20], 4), "p50": round(pc[n//2], 4), "p95": round(pc[19*n//20], 4)}

    # ---- the global mean direction (the axis of the cone) ----
    dim = g.n_embd; mean = [0.0]*dim
    for r in rows:
        for k in range(dim): mean[k] += r[k]
    mean = [x/len(rows) for x in mean]; mn = math.sqrt(sum(x*x for x in mean))
    out["mean_vector_norm"] = round(mn, 4)   # how far the average embedding is from the origin (cone tilt)

    # ---- norm ↔ frequency: raw L2 norm of the embedding row per word on a frequency ladder ----
    nl = []
    for w in FREQ:
        i = g._find(w)
        if i is not None: nl.append((w, round(g.rownorm(i), 3)))
    out["norm_by_frequency"] = nl

    # ---- opposites vs random, RAW and MEAN-CENTERED (does removing the cone sharpen relations?) ----
    def rel(pairs_cos):
        v = [c for c in pairs_cos if c is not None]; return sum(v)/len(v) if v else None
    A = [cos(g.vec(a), g.vec(b)) for a, b in ANTON if g.vec(a) and g.vec(b)]
    R = [cos(g.vec(a), g.vec(b)) for a, b in itertools.combinations(RANDW, 2) if g.vec(a) and g.vec(b)]
    am, rm = rel(A), rel(R)
    # mean-centered: subtract the global mean, renormalize, remeasure
    def cvec(w):
        raw = g.deq_row(g._find(w)) if g._find(w) is not None else None
        return norm(sub(raw, mean)) if raw else None
    Ac = [cos(cvec(a), cvec(b)) for a, b in ANTON if cvec(a) and cvec(b)]
    Rc = [cos(cvec(a), cvec(b)) for a, b in itertools.combinations(RANDW, 2) if cvec(a) and cvec(b)]
    acm, rcm = rel(Ac), rel(Rc)
    out["separation"] = {"raw": {"opp": round(am,4), "rand": round(rm,4), "ratio": round(am/rm,3)},
                         "mean_centered": {"opp": round(acm,4), "rand": round(rcm,4), "ratio": round(acm/rcm,3)}}
    tight = sorted(((f"{a}/{b}", cos(g.vec(a), g.vec(b))) for a, b in ANTON if g.vec(a) and g.vec(b)), key=lambda x:-x[1])
    out["tightest_opposite"] = [tight[0][0], round(tight[0][1],3)]
    return out


if __name__ == "__main__":
    res = []
    for tag, path in MODELS:
        if not os.path.exists(path): print(f"{tag}: not on disk"); continue
        print(f"reading {tag} …", flush=True); res.append(study(tag, path))
    dump = os.path.join(HERE, "fable_geometry_data.json"); json.dump(res, open(dump, "w"), indent=1)
    print("\n" + "="*70)
    for r in res:
        print(f"\n{r['tag']}  (dim {r['dim']} · vocab {r['vocab']:,} · {r['quant']})")
        a = r["anisotropy"]; print(f"  ANISOTROPY  random-pair cos: mean {a['random_pair_cos_mean']:+.3f}  "
              f"(p05 {a['p05']:+.3f} · p50 {a['p50']:+.3f} · p95 {a['p95']:+.3f})   mean-vector norm {r['mean_vector_norm']:.3f}")
        print(f"  NORM↔FREQ   " + "  ".join(f"{w}:{n}" for w, n in r["norm_by_frequency"]))
        s = r["separation"]; print(f"  SEPARATION  raw opp {s['raw']['opp']:+.3f}/rand {s['raw']['rand']:+.3f} = {s['raw']['ratio']}×   "
              f"→ mean-centered {s['mean_centered']['opp']:+.3f}/{s['mean_centered']['rand']:+.3f} = {s['mean_centered']['ratio']}×")
        print(f"  tightest opposite: {r['tightest_opposite'][0]} {r['tightest_opposite'][1]:+.3f}")
    print(f"\ndumped → {dump}")
