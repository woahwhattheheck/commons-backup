#!/usr/bin/env python3
"""Independent adversarial re-check of wf_forge_compare.py. Fresh ground-truth, exhaustive where feasible,
plus edge cases the builder's random sampling may have missed. Additive, read-only reuse."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf_forge_compare import magnitude_comparator, mux_tree, _drive

def check_cmp_exhaustive(nbits):
    c = magnitude_comparator(nbits); bad = 0; total = 0; examples = []
    for a in range(1 << nbits):
        for b in range(1 << nbits):
            r = c.run(**_drive(a, b, nbits)); total += 1
            want = (int(a < b), int(a > b), int(a == b))
            got = (r["lt"], r["gt"], r["eq"])
            if got != want:
                bad += 1
                if len(examples) < 5: examples.append((a, b, got, want))
    return bad, total, examples

def check_cmp_edges(nbits):
    """explicit edge cases: 0/0, 0/max, max/0, max/max, equal-nonzero, adjacent."""
    c = magnitude_comparator(nbits); mx = (1 << nbits) - 1; bad = 0
    cases = [(0,0),(0,mx),(mx,0),(mx,mx),(5,5),(mx-1,mx),(mx,mx-1),(1,0),(0,1)]
    for a,b in cases:
        r = c.run(**_drive(a,b,nbits))
        want = (int(a<b),int(a>b),int(a==b)); got=(r["lt"],r["gt"],r["eq"])
        # exactly one of lt/gt/eq must be 1 (mutual exclusion + totality)
        if got != want or sum(got)!=1:
            bad += 1; print(f"    EDGE FAIL a={a} b={b} got={got} want={want}")
    return bad, len(cases)

def check_cmp16_random(trials=2000):
    """16-bit random, an untested width — fresh ground truth."""
    c = magnitude_comparator(16); bad=0
    for _ in range(trials):
        a=random.getrandbits(16); b=random.getrandbits(16)
        r=c.run(**_drive(a,b,16))
        if (r["lt"],r["gt"],r["eq"])!=(int(a<b),int(a>b),int(a==b)): bad+=1
    # force some equal cases
    for v in (0, 0xFFFF, 0x8000, 0x1234):
        r=c.run(**_drive(v,v,16))
        if (r["lt"],r["gt"],r["eq"])!=(0,0,1): bad+=1
    return bad, trials+4

def check_mux_exhaustive_indep(k):
    """independent mux ground truth: for each single-hot data pattern, y must equal the addressed bit;
    also full exhaustive over all patterns x all selects."""
    c = mux_tree(k); n = 1<<k; bad=0; total=0
    # single-hot addressing test: set only bit `addr`, select `sel`; y==1 iff addr==sel
    for addr in range(n):
        for sel in range(n):
            dvals={f"d{j}":(1 if j==addr else 0) for j in range(n)}
            svals={f"s{j}":(sel>>j)&1 for j in range(k)}
            r=c.run(**dvals,**svals); total+=1
            want = 1 if addr==sel else 0
            if r["y"]!=want: bad+=1
    # full exhaustive
    for pattern in range(1<<n):
        dvals={f"d{j}":(pattern>>j)&1 for j in range(n)}
        for sel in range(n):
            svals={f"s{j}":(sel>>j)&1 for j in range(k)}
            r=c.run(**dvals,**svals); total+=1
            if r["y"]!=((pattern>>sel)&1): bad+=1
    return bad, total

def main():
    random.seed(1234567)
    print("INDEPENDENT ADVERSARIAL CHECK\n")
    b,t,ex = check_cmp_exhaustive(4)
    print(f"  cmp4 exhaustive {t}: {'PASS' if b==0 else f'{b} FAIL {ex}'}")
    b8,t8,ex8 = check_cmp_exhaustive(8)   # builder only did 500 random; do all 65536
    print(f"  cmp8 EXHAUSTIVE {t8} (builder did 500 random): {'PASS' if b8==0 else f'{b8} FAIL {ex8}'}")
    be,te = check_cmp_edges(8)
    print(f"  cmp8 edges {te} (incl mutual-exclusion): {'PASS' if be==0 else f'{be} FAIL'}")
    b16,t16 = check_cmp16_random(2000)
    print(f"  cmp16 random {t16} (untested width): {'PASS' if b16==0 else f'{b16} FAIL'}")
    bm,tm = check_mux_exhaustive_indep(3)
    print(f"  mux3 single-hot + exhaustive {tm}: {'PASS' if bm==0 else f'{bm} FAIL'}")
    allbad = b+b8+be+b16+bm
    print(f"\n{'ALL INDEPENDENT CHECKS PASS' if allbad==0 else f'{allbad} DISCREPANCIES'}")
    return 0 if allbad==0 else 1

if __name__=="__main__":
    raise SystemExit(main())
