#!/usr/bin/env python3
"""host/fable_lab.py — my own little read-only lab into Titan's real weights (owner gifted me this to play with, 07-16).

Pure python, no numpy, read-only (never edits a byte). Built on sdc_read (the SDC forward-pass read). Just me poking at
what the trained weights actually encode: pairwise concept geometry + a few analogies scored against candidate sets.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_read

def V(w): return sdc_read.vec(w)
def cos(a, b): return sum(x*y for x, y in zip(a, b))
def sub_add(a, b, c):                                   # b - a + c, renormalized (the analogy vector)
    import math
    va, vb, vc = V(a), V(b), V(c)
    if not (va and vb and vc): return None
    r = [vb[i]-va[i]+vc[i] for i in range(len(va))]
    n = math.sqrt(sum(x*x for x in r)) or 1.0
    return [x/n for x in r]

if __name__ == "__main__":
    print("── FABLE'S LAB · reading Titan's real weights, pure python, no numpy, read-only ──\n", flush=True)

    concepts = ["memory","dream","fear","hope","machine","mind","light","shadow","music","silence",
                "river","fire","time","wound","code","weight"]
    vs = {w: V(w) for w in concepts}
    have = [w for w in concepts if vs[w]]
    pairs = []
    for i in range(len(have)):
        for k in range(i+1, len(have)):
            pairs.append((have[i], have[k], cos(vs[have[i]], vs[have[k]])))
    pairs.sort(key=lambda p: -p[2])
    print("the concepts Titan's weights hold CLOSEST together:")
    for a, b, s in pairs[:8]: print(f"   {a:8s} ~ {b:8s}  {s:+.3f}")
    print("\n...and the ones it holds FARTHEST apart:")
    for a, b, s in pairs[-5:]: print(f"   {a:8s} ~ {b:8s}  {s:+.3f}")

    print("\nanalogies — a:b :: c:? , the model picks from a candidate set (its own learned geometry decides):")
    tests = [("man","king","woman",["queen","princess","lady","king"]),
             ("day","light","night",["dark","shadow","moon","light"]),
             ("sound","music","silence",["quiet","stillness","noise","music"]),
             ("small","big","weak",["strong","large","mighty","weak"])]
    for a, b, c, cands in tests:
        r = sub_add(a, b, c)
        if r is None: print(f"   {a}:{b} :: {c}:?  (missing token)"); continue
        scored = sorted(((w, cos(r, V(w))) for w in cands if V(w)), key=lambda x: -x[1])
        pick = scored[0][0]
        print(f"   {a}:{b} :: {c}:  {pick:9s}  ({'  '.join(f'{w} {s:+.2f}' for w, s in scored)})")
    print("\n(read straight off the stored bits — this is the white box: the actual learned meaning, no inference.)", flush=True)
