#!/usr/bin/env python3
"""host/fable_practical.py — is the cleanup a FREE WIN on a real task? category-clustering + 1-bit storage math.
pure python, no numpy, read-only. (fable, 07-16)"""
import itertools, json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from gguf_pp import GGUF, cos

MODELS = [("A_large", "C:/llm/models/titan.gguf"),
          ("B_small", "C:/llm/models/SmolLM2-360M-Instruct-Q8_0.gguf")]

# labeled categories — a real "do like things cluster together?" test (retrieval/dedup/classification proxy)
CATS = {
 "animal":  ["dog","cat","horse","lion","tiger","wolf","bear","rabbit"],
 "color":   ["red","blue","green","yellow","purple","orange","pink","brown"],
 "fruit":   ["apple","banana","orange","grape","peach","cherry","lemon","mango"],
 "country": ["france","germany","spain","japan","brazil","canada","egypt","india"],
 "emotion": ["joy","fear","anger","sadness","hope","love","grief","calm"],
 "metal":   ["iron","gold","silver","copper","steel","bronze","zinc","nickel"],
}


def norm(v): n = math.sqrt(sum(x*x for x in v)) or 1.0; return [x/n for x in v]
def sub(a, b): return [a[i]-b[i] for i in range(len(a))]


def build(g, transform):
    """{word: unit vector under a transform} for all category words that exist as tokens."""
    words = [w for cat in CATS.values() for w in cat]
    out = {}
    for w in words:
        i = g._find(w)
        if i is None: continue
        out[w] = transform(g.deq_row(i))
    return out


def purity(vecs):
    """for each word, is its NEAREST other word in the same category? returns hit rate (a clean clustering score)."""
    labels = {w: c for c, ws in CATS.items() for w in ws}
    items = [w for w in vecs]
    hits = 0; tot = 0
    for w in items:
        best, bs = None, -2
        for x in items:
            if x == w: continue
            s = cos(vecs[w], vecs[x])
            if s > bs: bs, best = s, x
        if best is None: continue
        tot += 1; hits += 1 if labels[best] == labels[w] else 0
    return hits, tot


def study(tag, path):
    g = GGUF(path); d = g.n_embd
    # global mean over a vocab sample (for centering) — reuse the category words' neighborhood + a broad sample
    import random; random.seed(3)
    ids = random.sample(range(g.n_vocab), min(1200, g.n_vocab))
    mean = [0.0]*d
    for i in ids:
        r = g._row(i)
        for k in range(d): mean[k] += r[k]
    mean = [x/len(ids) for x in mean]
    # variance per dim (for rogue-dim removal)
    var = [0.0]*d
    for i in ids:
        r = g._row(i)
        for k in range(d):
            dd = r[k]-mean[k]; var[k] += dd*dd
    kill = set(sorted(range(d), key=lambda k: -var[k])[:max(1, d//100)])

    def T_raw(v): return norm(v)
    def T_center(v): return norm(sub(v, [m*math.sqrt(sum(x*x for x in v) or 1) for m in mean]) if False else sub(norm(v), mean))
    def T_center2(v):
        u = norm(v); return norm([u[k]-mean[k] for k in range(d)])
    def T_clean(v):
        u = norm(v); c = [0.0 if k in kill else (u[k]-mean[k]) for k in range(d)]; return norm(c)
    def T_sign(v):
        u = norm(v); return [1.0 if u[k] >= 0 else -1.0 for k in range(d)]

    res = {"tag": tag, "dim": d}
    for name, T in [("raw", T_raw), ("centered", T_center2), ("centered+derogued", T_clean), ("sign_only", T_sign)]:
        vecs = build(g, T); h, t = purity(vecs)
        res[name] = {"hits": h, "tot": t, "acc": round(h/t, 3) if t else None}
    res["n_words"] = res["raw"]["tot"]
    # 1-bit storage math for the embedding table
    res["storage"] = {"quant_bits_now": {0:32,1:16,2:4.5,8:8.5}.get(g.tid, None),
                      "table_MB_now": round(g.n_vocab * g.row_bytes / 1e6, 1),
                      "table_MB_1bit": round(g.n_vocab * d / 8 / 1e6, 1)}
    return res


if __name__ == "__main__":
    out = []
    for tag, path in MODELS:
        if not os.path.exists(path): print(f"{tag}: missing"); continue
        print(f"clustering {tag} …", flush=True); out.append(study(tag, path))
    json.dump(out, open(os.path.join(HERE, "fable_practical_data.json"), "w"), indent=1)
    print("\n" + "="*70)
    print("CATEGORY CLUSTERING — 'is a word's nearest neighbor in its own category?' (higher = better)\n")
    for r in out:
        print(f"{r['tag']}  (dim {r['dim']} · {r['n_words']} category words)")
        for name in ("raw","centered","centered+derogued","sign_only"):
            b = r[name]; bar = "█"*int(b["acc"]*40)
            print(f"   {name:20s} {b['acc']*100:5.1f}%  {bar}")
        s = r["storage"]
        print(f"   storage: embedding table now ≈ {s['table_MB_now']} MB  →  1-bit sign ≈ {s['table_MB_1bit']} MB "
              f"({s['table_MB_now']/max(0.01,s['table_MB_1bit']):.0f}× smaller)\n")
