#!/usr/bin/env python3
"""Independent adversarial re-check of wf_forge_decoder. Ground truth computed here from first principles,
not reusing the forge's verify_* helpers. Edge cases: addr 0, max addr, one-hot property, mux full space at
n=3 recomputed, mux n=4 full random with fresh RNG, plus a size the builder never tested: dec5to32 exhaustive
and mux32to1 (n=5) address-exhaustive + heavy random."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf_forge_decoder import decoder, mux

def gt_decoder(a, n):
    # ground truth: one-hot, exactly bit `a` set
    return [1 if k == a else 0 for k in range(1 << n)]

fails = []

# --- decoders exhaustive incl n=5 (untested by builder) ---
for n in (3, 4, 5):
    c = decoder(n)
    for a in range(1 << n):
        r = c.run(**{f"a{i}": (a >> i) & 1 for i in range(n)})
        got = [r[f"y{k}"] for k in range(1 << n)]
        want = gt_decoder(a, n)
        # one-hot check + index check
        if got != want:
            fails.append(("dec", n, a, got, want))
        if sum(got) != 1:
            fails.append(("dec-onehot", n, a, sum(got)))
print(f"decoders n=3,4,5 exhaustive: {'PASS' if not fails else 'FAIL'} ({len(fails)} fails)")

# --- mux n=3 full space, recomputed ground truth ---
def mux_gt(a, dv):
    return (dv >> a) & 1
c3 = mux(3); bad3 = 0; tot3 = 0
for a in range(8):
    for dv in range(256):
        ins = {f"a{i}": (a >> i) & 1 for i in range(3)}
        ins.update({f"d{k}": (dv >> k) & 1 for k in range(8)})
        if c3.run(**ins)["y"] != mux_gt(a, dv): bad3 += 1
        tot3 += 1
print(f"mux8to1 full space {tot3} evals: {'PASS' if bad3==0 else f'FAIL {bad3}'}")

# --- mux n=4 fresh random 5000 + edge vectors ---
c4 = mux(4); bad4 = 0; tot4 = 0
random.seed(12345)
edge_dvs = [0, (1<<16)-1, 0xAAAA, 0x5555, 1, 1<<15]
cases = [(random.randrange(16), random.getrandbits(16)) for _ in range(5000)]
for a in range(16):
    for dv in edge_dvs: cases.append((a, dv))
for a, dv in cases:
    ins = {f"a{i}": (a >> i) & 1 for i in range(4)}
    ins.update({f"d{k}": (dv >> k) & 1 for k in range(16)})
    if c4.run(**ins)["y"] != mux_gt(a, dv): bad4 += 1
    tot4 += 1
print(f"mux16to1 {tot4} evals (5000 rand + edges): {'PASS' if bad4==0 else f'FAIL {bad4}'}")

# --- mux n=5 (untested) address-exhaustive + 4000 random ---
c5 = mux(5); bad5 = 0; tot5 = 0
random.seed(999)
cases5 = [(random.randrange(32), random.getrandbits(32)) for _ in range(4000)]
# walking-ones: only line j high -> out == (j==a)
for a in range(32):
    for j in range(32):
        cases5.append((a, 1 << j))
for a, dv in cases5:
    ins = {f"a{i}": (a >> i) & 1 for i in range(5)}
    ins.update({f"d{k}": (dv >> k) & 1 for k in range(32)})
    if c5.run(**ins)["y"] != mux_gt(a, dv): bad5 += 1
    tot5 += 1
print(f"mux32to1 n=5 {tot5} evals (walking + 4000 rand): {'PASS' if bad5==0 else f'FAIL {bad5}'}")

print("\nOVERALL:", "ALL PASS" if (not fails and bad3==0 and bad4==0 and bad5==0) else "DISCREPANCY FOUND")
