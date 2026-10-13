#!/usr/bin/env python3
"""Independent adversarial re-check of wf_forge_mult.array_mult. Edge cases + fresh random, own reference."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf_forge_mult import array_mult, _pack

def run_one(c, a, b, nbits):
    W = 2 * nbits
    r = c.run(**_pack(a, b, nbits))
    return sum(r[f"p{k}"] << k for k in range(W))

def check(nbits, pairs, label):
    c = array_mult(nbits)
    bad = []
    for a, b in pairs:
        got = run_one(c, a, b, nbits)
        want = a * b            # ground truth in plain Python
        if got != want:
            bad.append((a, b, got, want))
    status = "PASS" if not bad else f"FAIL ({len(bad)})"
    print(f"  mul{nbits} {label}: tested {len(pairs)} -> {status}")
    for a, b, got, want in bad[:5]:
        print(f"     a={a} b={b} got={got} want={want}")
    return not bad

def main():
    allok = True
    mx4 = (1 << 4) - 1     # 15
    mx8 = (1 << 8) - 1     # 255
    # edge cases 4-bit
    edges4 = [(0,0),(0,mx4),(mx4,0),(mx4,mx4),(1,1),(1,mx4),(mx4,1),
              (8,8),(2,mx4),(mx4,2),(4,4),(15,15),(0,7),(7,0),(9,13)]
    allok &= check(4, edges4, "edge cases")
    # 4-bit exhaustive independent
    allok &= check(4, [(a,b) for a in range(16) for b in range(16)], "exhaustive 256")
    # edge cases 8-bit incl overflow (255*255=65025 fits 16 bits)
    edges8 = [(0,0),(0,mx8),(mx8,0),(mx8,mx8),(1,1),(mx8,1),(1,mx8),
              (128,128),(255,255),(200,200),(170,85),(64,4),(255,2),(2,255),
              (100,100),(199,201) if 201<=255 else (199,255)]
    allok &= check(8, edges8, "edge cases (incl 255*255 overflow)")
    # 8-bit fresh random 1000 with a fresh seed
    random.seed(1337)
    rnd = [(random.getrandbits(8), random.getrandbits(8)) for _ in range(1000)]
    allok &= check(8, rnd, "1000 fresh random (seed 1337)")
    print("\nOVERALL:", "PASS" if allok else "FAIL")
    return 0 if allok else 1

if __name__ == "__main__":
    raise SystemExit(main())
