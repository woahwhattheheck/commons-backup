#!/usr/bin/env python3
"""host/fable_lab4.py — do OPPOSITES sit close? + a color axis. read-only, pure python, no numpy. (fable, 07-16)

Tests the prediction hiding in the docs (blind alignment warps because it can't see the circuit): if antonyms are
geometric NEIGHBORS, a nudge toward one bleeds into the other. Measures antonym-pair cosine vs a random-pair baseline.
"""
import math, os, sys, itertools
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_read
def V(w): return sdc_read.vec(w)
def cos(a, b): return sum(x*y for x, y in zip(a, b)) if (a and b) else None
def norm(v): n = math.sqrt(sum(x*x for x in v)) or 1.0; return [x/n for x in v]

if __name__ == "__main__":
    print("── FABLE'S LAB v4 · do opposites sit close? ──\n", flush=True)

    antonyms = [("love","hate"),("hot","cold"),("light","dark"),("up","down"),("life","death"),
                ("fast","slow"),("war","peace"),("joy","grief"),("true","false"),("open","closed"),
                ("big","small"),("rich","poor"),("day","night"),("good","evil"),("full","empty")]
    apairs = [(a, b, cos(V(a), V(b))) for a, b in antonyms if V(a) and V(b)]
    amean = sum(s for _, _, s in apairs) / len(apairs)
    # random baseline: cosine of unrelated words
    pool = ["stone","music","river","clock","bread","engine","cloud","letter","garden","planet","market","feather",
            "window","copper","harvest","signal","anchor","velvet","circuit","meadow"]
    rp = [cos(V(a), V(b)) for a, b in itertools.combinations(pool, 2) if V(a) and V(b)]
    rmean = sum(rp) / len(rp)

    print("antonym pairs — cosine of each 'opposite' (higher = the weights hold them CLOSER):")
    for a, b, s in sorted(apairs, key=lambda x: -x[2]):
        flag = "  ← neighbors" if s > rmean + 0.05 else ""
        print(f"   {a:6s} / {b:8s}  {s:+.3f}{flag}")
    print(f"\n   mean antonym cosine : {amean:+.3f}")
    print(f"   mean random  cosine : {rmean:+.3f}")
    print(f"   → opposites are {abs(amean-rmean)/max(1e-6,rmean):.1f}× {'CLOSER' if amean>rmean else 'farther'} than unrelated words.")
    print("   (if closer: a nudge toward one pole bleeds into its opposite — the reason sighted editing matters.)")

    print("\nCOLOR — the spectrum projected onto the red→blue axis (does it hold a warm→cool line?):")
    colors = ["red","orange","yellow","green","blue","purple","violet","crimson","gold","teal","indigo"]
    vr, vb = V("red"), V("blue")
    if vr and vb:
        d = norm([vb[i]-vr[i] for i in range(len(vr))])
        proj = sorted(((c, sum(x*y for x, y in zip(V(c), d))) for c in colors if V(c)), key=lambda x: x[1])
        print("   warm " + " → ".join(c for c, _ in proj) + " cool")

    print("\nWARMTH — abstract words on the cold→warm axis (does temperature carry feeling?):")
    d = None; vc, vw = V("cold"), V("warm")
    if vc and vw:
        d = norm([vw[i]-vc[i] for i in range(len(vc))])
        words = ["cruel","distant","lonely","kind","tender","harsh","gentle","bitter","loving","numb","fond"]
        proj = sorted(((w, sum(x*y for x, y in zip(V(w), d))) for w in words if V(w)), key=lambda x: x[1])
        for w, s in proj: print(f"   {s:+.3f} {'·'*max(0,int((s+0.25)*24)):<14} {w}")

    print("\n(read straight off the stored bits — no inference, no numpy.)", flush=True)
