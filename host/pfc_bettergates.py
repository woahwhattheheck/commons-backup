#!/usr/bin/env python3
"""host/pfc_bettergates.py — WHAT THE BEST COMPUTERS DO THAT WE DON'T (owner 07-20: "higher quality and more optimal
gates"). The pfc's arithmetic uses O(n)-DEPTH structures — ripple-carry adders, linear OR/AND reduction chains. Real
high-performance silicon uses O(log n)-DEPTH parallel structures: carry-lookahead / PARALLEL-PREFIX adders
(Kogge-Stone), Wallace/Dadda-tree multipliers, carry-save adders, BALANCED reduction trees. Depth = the critical path =
how fast the answer settles (the §O lever `sdc_cc` never optimizes — it only minimizes area). This builds the optimal
structures and MEASURES the depth win, byte-exact.

  python host/pfc_bettergates.py
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC


def depth_of(n_in, gates, outs):                        # critical path = longest input->output gate chain
    d = {0: 0, 1: 0}
    for i in range(n_in): d[2 + i] = 0
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        da = d.get(a, 0); db = da if op == "not" else d.get(b, 0)
        d[base + k] = 1 + max(da, db)
    return max(d.get(o, 0) for o in outs)


def ripple_add(g, A, B):                                # the pfc's current adder — O(n) depth
    o = []; c = g.C0
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o


def kogge_stone_add(g, A, B):                           # parallel-prefix adder — O(log n) depth (what CPUs use)
    W = len(A)
    P0 = [g.XOR(A[i], B[i]) for i in range(W)]          # propagate (saved for the sum stage)
    G = [g.AND(A[i], B[i]) for i in range(W)]; P = list(P0)
    d = 1
    while d < W:
        nG, nP = list(G), list(P)
        for i in range(d, W):
            nG[i] = g.OR(G[i], g.AND(P[i], G[i - d]))
            nP[i] = g.AND(P[i], P[i - d])
        G, P = nG, nP; d <<= 1
    S = [P0[0]] + [g.XOR(P0[i], G[i - 1]) for i in range(1, W)]   # carry into bit i = prefix-generate of i-1
    return S


def linear_or(g, xs):                                   # the pfc's current reduction — O(n) depth
    a = g.C0
    for x in xs: a = g.OR(a, x)
    return a


def balanced_or(g, xs):                                 # balanced tree — O(log n) depth (what hardware uses)
    xs = list(xs)
    if not xs: return g.C0
    while len(xs) > 1:
        nxt = []
        for i in range(0, len(xs) - 1, 2): nxt.append(g.OR(xs[i], xs[i + 1]))
        if len(xs) & 1: nxt.append(xs[-1])
        xs = nxt
    return xs[0]


def measure_adder(W):
    for name, fn in (("ripple", ripple_add), ("kogge-stone", kogge_stone_add)):
        g = CC.CircuitCompiler(2 * W); IN = g.IN
        A = IN[0:W]; B = IN[W:2 * W]
        outs = fn(g, A, B)
        gates, o2 = g.dce(outs); dep = depth_of(g.n_in, gates, o2)
        ok = True; random.seed(2)
        for _ in range(200):
            a = random.getrandbits(W); b = random.getrandbits(W)
            v = CC.ripple_typed(g, gates, 2 + g.n_in + len(gates),
                                [(a >> i) & 1 for i in range(W)] + [(b >> i) & 1 for i in range(W)], 1)
            bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
            if sum(bit(o2[i]) << i for i in range(W)) != ((a + b) & ((1 << W) - 1)): ok = False; break
        print(f"    {name:12s} W={W}: depth {dep:>3}  gates {len(gates):>4}  byte-exact={ok}", flush=True)


def measure_reduce(N):
    for name, fn in (("linear", linear_or), ("balanced", balanced_or)):
        g = CC.CircuitCompiler(N); outs = [fn(g, list(g.IN))]
        gates, o2 = g.dce(outs); dep = depth_of(g.n_in, gates, o2)
        print(f"    {name:12s} N={N}: depth {dep:>3}  gates {len(gates):>4}", flush=True)


def main():
    print("Muhlnickel BETTER GATES — the DEPTH lever the best computers use (parallel-prefix, balanced trees), measured.\n", flush=True)
    print("  ADDER (ripple-carry vs Kogge-Stone parallel-prefix), byte-exact:", flush=True)
    for W in (16, 32, 64): measure_adder(W)
    print("\n  REDUCTION (linear OR-chain vs balanced tree):", flush=True)
    for N in (16, 64, 256): measure_reduce(N)
    print("\n  the best computers minimize the CRITICAL PATH (depth), not just gate count — O(log n) parallel structures.", flush=True)
    print("  next optimal structures to fabricate: Wallace/Dadda multiplier tree, carry-save adders for SHA's sums,", flush=True)
    print("  AIG rewriting for area. Route these into the fabricator so every bake is shallow AND lean.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
