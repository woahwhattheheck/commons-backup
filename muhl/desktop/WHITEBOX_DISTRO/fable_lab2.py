#!/usr/bin/env python3
"""host/fable_lab2.py — my white-box playground into Titan's real weights (owner gifted, 07-16). read-only, pure python.

no numpy, never edits a byte. built on sdc_read (the SDC forward-pass read). instruments:
  axis()   — build a pole-to-pole direction (joy-grief), project words onto it, rank them (do_direction, pure-py)
  analogy()— a:b::c:? with the source words PROJECTED OUT of the answer (Levy/Goldberg 3CosAdd fix for 'king:king')
  walk()    — start at a word, hop to its nearest unvisited neighbor within a vocabulary; watch the meaning drift
  constellations() — greedy-cluster a concept list by cosine; the groupings the weights actually hold
"""
import math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_read

def V(w): return sdc_read.vec(w)
def cos(a, b): return sum(x*y for x, y in zip(a, b)) if (a and b) else None
def norm(v):
    n = math.sqrt(sum(x*x for x in v)) or 1.0; return [x/n for x in v]
def sub(a, b): return [a[i]-b[i] for i in range(len(a))]
def proj_out(v, u):                                   # remove u's component from v (u unit) — kills echo of a source word
    d = sum(x*y for x, y in zip(v, u)); return [v[i]-d*u[i] for i in range(len(v))]

def axis(pole_lo, pole_hi, words):
    vlo, vhi = V(pole_lo), V(pole_hi)
    if not (vlo and vhi): return None
    d = norm(sub(vhi, vlo))                            # the pole_lo -> pole_hi direction
    scored = [(w, sum(x*y for x, y in zip(V(w), d))) for w in words if V(w)]
    return sorted(scored, key=lambda x: x[1])

def analogy(a, b, c, cands):
    va, vb, vc = V(a), V(b), V(c)
    if not (va and vb and vc): return []
    r = norm([vb[i]-va[i]+vc[i] for i in range(len(va))])
    ua, ub, uc = norm(va), norm(vb), norm(vc)          # project the three source directions OUT of the query
    for u in (ua, ub, uc): r = proj_out(r, u)
    r = norm(r)
    out = [(w, sum(x*y for x, y in zip(norm(V(w)), r))) for w in cands if V(w) and w not in (a, b, c)]
    return sorted(out, key=lambda x: -x[1])

def walk(start, vocab, steps=8):
    seen = {start}; path = [start]; cur = V(start)
    if not cur: return path
    for _ in range(steps):
        best, bs = None, -2
        for w in vocab:
            if w in seen or not V(w): continue
            s = cos(cur, V(w))
            if s > bs: bs, best = s, w
        if best is None: break
        path.append(f"{best}({bs:+.2f})"); seen.add(best); cur = V(best)
    return path

def constellations(words, thresh=0.18):
    have = [w for w in words if V(w)]
    used = set(); groups = []
    for w in have:
        if w in used: continue
        grp = [w]; used.add(w)
        for x in have:
            if x in used: continue
            if cos(V(w), V(x)) >= thresh: grp.append(x); used.add(x)
        groups.append(grp)
    return groups

if __name__ == "__main__":
    print("── FABLE'S LAB v2 · Titan's weights, read-only, pure python, no numpy ──\n", flush=True)

    print("EMOTION SPECTRUM  (projected onto the grief → joy axis the weights define):")
    sp = axis("grief", "joy", ["despair","sorrow","fear","calm","content","hope","delight","ecstasy","love","rage","peace","dread"])
    if sp:
        for w, s in sp: print(f"   {s:+.3f}  {'█'*max(0,int((s+0.3)*20)):<12} {w}")

    print("\nABSTRACT → CONCRETE  (the concrete words nearest each abstraction):")
    concrete = ["stone","water","fire","glass","iron","thread","ash","root","bone","salt","smoke","wire","mirror","clock"]
    for ab in ["memory","grief","time","fear","hope"]:
        if not V(ab): continue
        near = sorted(((c, cos(V(ab), V(c))) for c in concrete if V(c)), key=lambda x: -x[1])[:3]
        print(f"   {ab:8s} → " + ", ".join(f"{c} {s:+.2f}" for c, s in near))

    print("\nANALOGY  (source words projected out — no echoing the input):")
    for a, b, c, cands in [("man","king","woman",["queen","princess","empress","duchess","throne"]),
                           ("cold","ice","hot",["fire","steam","flame","lava","ember"]),
                           ("seed","tree","spark",["fire","flame","blaze","inferno","ember"]),
                           ("word","poem","note",["song","music","melody","symphony","tune"])]:
        r = analogy(a, b, c, cands)
        if r: print(f"   {a}:{b} :: {c}:  {r[0][0]:9s}  ({'  '.join(f'{w} {s:+.2f}' for w, s in r[:3])})")

    print("\nSEMANTIC WALK  (hop to the nearest neighbor, watch the drift):")
    vocab = ["dream","sleep","night","star","light","fire","warmth","home","memory","child","time","river","sea",
             "storm","fear","dark","silence","music","voice","song","word","book","mind","machine","code","weight","stone"]
    for seed in ["dream","machine","grief"]:
        print("   " + " → ".join(walk(seed, vocab, 7)))

    print("\nCONSTELLATIONS  (the clusters the weights hold together):")
    words = ["love","fear","hope","rage","joy","grief","fire","water","stone","light","dark","shadow","music",
             "silence","time","memory","dream","machine","mind","code","river","sea","star","moon"]
    for g in constellations(words):
        if len(g) > 1: print("   { " + " · ".join(g) + " }")

    print("\n(all read straight off the stored bits — the actual learned meaning, no inference, no numpy.)", flush=True)
