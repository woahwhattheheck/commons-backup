#!/usr/bin/env python3
"""host/fable_clean.py — is the anisotropy cleanup a FREE WIN on REAL TASKS? measured raw vs cleaned. (fable, 07-22)

The other fable tools found: (a) meaning survives at ~1 bit, (b) cosine is mostly sign overlap, (c) a few "rogue"
high-variance dims + a global mean-offset (the "cone") distort every cosine. This tool closes the loop: it takes the
standard cheap fix — subtract the global mean, zero the top-1% rogue dims — and asks whether it makes the model
measurably BETTER at tasks read straight off the weights (analogies + antonym separation). If cleaned > raw, the
cleanup isn't cosmetic; it's a functional upgrade you can bake in. pure python, no numpy, read-only.

Design philosophy (owner): pull the data fast, don't disturb the file. Everything here is bounded reads off mmap.

  python host/fable_clean.py
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, cos

MODELS = [("Titan (dim2816)", "C:/llm/models/titan.gguf"),
          ("SmolLM2-360M", "C:/llm/models/SmolLM2-360M-Instruct-Q8_0.gguf")]
SAMPLE = 2500                                              # random token rows to estimate mean + per-dim variance
ROGUE_FRAC = 0.01                                          # zero the top 1% highest-variance dims (the "rogue" dims)

# analogy batteries: a:b :: c:?  candidate pool = every 2nd element in the category
CATS = {
  "capitals":   [("france","paris"),("japan","tokyo"),("italy","rome"),("egypt","cairo"),("russia","moscow"),
                 ("spain","madrid"),("germany","berlin"),("greece","athens"),("england","london")],
  "past_tense": [("walk","walked"),("play","played"),("jump","jumped"),("talk","talked"),("open","opened"),
                 ("cook","cooked"),("work","worked"),("call","called")],
  "plural":     [("cat","cats"),("dog","dogs"),("car","cars"),("book","books"),("tree","trees"),
                 ("hand","hands"),("king","kings"),("day","days")],
  "comparative":[("big","bigger"),("small","smaller"),("fast","faster"),("slow","slower"),
                 ("strong","stronger"),("weak","weaker"),("high","higher"),("low","lower")],
  "gender":     [("king","queen"),("man","woman"),("boy","girl"),("father","mother"),
                 ("son","daughter"),("brother","sister"),("uncle","aunt"),("prince","princess")],
}
ANTONYMS = [("love","hate"),("hot","cold"),("light","dark"),("up","down"),("day","night"),("fast","slow"),
            ("war","peace"),("rich","poor"),("big","small"),("good","evil"),("true","false"),("open","closed"),
            ("full","empty"),("life","death"),("black","white"),("weak","strong"),("high","low"),("wet","dry")]
RAND_WORDS = ["table","river","music","seven","glass","paper","engine","garden","yellow","planet","reason",
              "market","window","letter","forest","bridge","coffee","silver","doctor","summer","pencil","camera"]


def vec(g, w):
    i = g._find(w)
    return g.deq_row(i) if i is not None else None


def estimate(g, n):
    """sample n token rows -> (mean[d], rogue_dim_set). one pass, running sum + sumsq. deterministic stride, no rng."""
    D = g.n_embd; V = g.n_vocab
    step = max(1, V // n)
    ids = list(range(0, V, step))[:n]
    s = [0.0] * D; ss = [0.0] * D; cnt = 0
    for i in ids:
        r = g.deq_row(i)
        if not r or len(r) != D: continue
        cnt += 1
        for d in range(D):
            x = r[d]; s[d] += x; ss[d] += x * x
    mean = [s[d] / cnt for d in range(D)]
    var = [ss[d] / cnt - mean[d] * mean[d] for d in range(D)]
    k = max(1, int(D * ROGUE_FRAC))
    rogue = set(sorted(range(D), key=lambda d: -var[d])[:k])
    top_share = sum(sorted(var, reverse=True)[:k]) / (sum(var) or 1.0)
    return mean, rogue, k, top_share, cnt


def make_T(mean, rogue):
    def T(v):
        w = [v[i] - mean[i] for i in range(len(v))]
        for d in rogue: w[d] = 0.0
        return w
    return T


def antonym_ratio(g, T):
    def c(a, b):
        va, vb = vec(g, a), vec(g, b)
        if not (va and vb): return None
        return cos(T(va), T(vb))
    opp = [c(a, b) for a, b in ANTONYMS]; opp = [x for x in opp if x is not None]
    rnd = []
    for i in range(len(RAND_WORDS)):
        for j in range(i + 1, len(RAND_WORDS)):
            x = c(RAND_WORDS[i], RAND_WORDS[j])
            if x is not None: rnd.append(x)
    mo = sum(opp) / len(opp); mr = sum(rnd) / len(rnd)
    return mo, mr, (mo / mr if mr else 0.0)


def norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def analogy_acc(g, T):
    per = {}; hit = 0; tot = 0
    for cat, pairs in CATS.items():
        pool = [b for _, b in pairs]
        h = 0; t = 0
        for i, (a, b) in enumerate(pairs):
            sa, sb = pairs[(i + 1) % len(pairs)]           # a DIFFERENT known pair as the source direction
            va, vb, vc = vec(g, sa), vec(g, sb), vec(g, a)
            if not (va and vb and vc): continue
            Ta, Tb, Tc = T(va), T(vb), T(vc)
            r = norm([Tb[k] - Ta[k] + Tc[k] for k in range(len(Ta))])
            best = None; bs = -9
            for cand in pool:
                if cand == b and False: pass
                vcand = vec(g, cand)
                if not vcand or cand in (sa, sb, a): continue
                sco = cos(r, T(vcand))
                if sco > bs: bs = sco; best = cand
            if best is None: continue
            t += 1; ok = (best == b); h += ok
        if t: per[cat] = (h, t); hit += h; tot += t
    return per, hit, tot


def run(tag, path):
    g = GGUF(path)
    print(f"\n=== {tag}  (dim {g.n_embd} · vocab {g.n_vocab:,} · {g.tyname}) ===", flush=True)
    mean, rogue, k, top_share, cnt = estimate(g, SAMPLE)
    mag = math.sqrt(sum(x * x for x in mean))
    print(f"  sampled {cnt} rows · mean-offset |μ| = {mag:.4f} (the cone) · top-1% dims ({k}) hold {top_share*100:.1f}% of variance", flush=True)

    Iden = lambda v: v                                     # RAW (no cleanup)
    Tclean = make_T(mean, rogue)                           # mean-center + zero rogue dims

    ar_raw = antonym_ratio(g, Iden); ar_cln = antonym_ratio(g, Tclean)
    aa_raw = analogy_acc(g, Iden);   aa_cln = analogy_acc(g, Tclean)

    print(f"\n  ANTONYM SEPARATION (opposites / random cosine; higher = cleaner geometry):", flush=True)
    print(f"    raw     : opp {ar_raw[0]:+.3f}  rand {ar_raw[1]:+.3f}  ratio {ar_raw[2]:.2f}x", flush=True)
    print(f"    cleaned : opp {ar_cln[0]:+.3f}  rand {ar_cln[1]:+.3f}  ratio {ar_cln[2]:.2f}x   ->  {(ar_cln[2]-ar_raw[2]):+.2f}x", flush=True)

    print(f"\n  ANALOGY ACCURACY (a:b :: c:? by embedding arithmetic, per category):", flush=True)
    per_raw, hr, tr = aa_raw; per_cln, hc, tc = aa_cln
    for cat in CATS:
        r = per_raw.get(cat, (0, 0)); c = per_cln.get(cat, (0, 0))
        ra = r[0] / r[1] if r[1] else 0; ca = c[0] / c[1] if c[1] else 0
        print(f"    {cat:12s} raw {r[0]}/{r[1]} ({ra:.2f})   ->   cleaned {c[0]}/{c[1]} ({ca:.2f})   {'▲' if ca>ra else '▼' if ca<ra else '='}", flush=True)
    ra = hr / tr if tr else 0; ca = hc / tc if tc else 0
    print(f"    {'OVERALL':12s} raw {hr}/{tr} ({ra:.3f})   ->   cleaned {hc}/{tc} ({ca:.3f})   {(ca-ra)*100:+.1f} pts", flush=True)
    return {"tag": tag, "dim": g.n_embd, "mean_mag": mag, "top_share": top_share,
            "antonym_raw": ar_raw, "antonym_clean": ar_cln,
            "analogy_raw": [hr, tr], "analogy_clean": [hc, tc], "per_raw": per_raw, "per_clean": per_cln}


def _resolve(path):
    if os.path.exists(path): return path
    alt = os.path.join(os.path.dirname(path), "_removed", os.path.basename(path))
    return alt if os.path.exists(alt) else None


if __name__ == "__main__":
    print("FABLE CLEAN — does anisotropy cleanup (mean-center + rogue-dim removal) make the model measurably better?", flush=True)
    out = {}
    for tag, path in MODELS:
        p = _resolve(path)
        if not p: print(f"\n{tag}: not on disk (skipped)"); continue
        try:
            out[tag] = run(tag, p)
        except Exception as e:
            print(f"\n{tag}: error — {e}")
    json.dump(out, open(os.path.join(HERE, "fable_clean_data.json"), "w"), indent=1, default=str)
    print(f"\ndumped -> fable_clean_data.json", flush=True)
