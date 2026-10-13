#!/usr/bin/env python3
"""host/pfc_shallow.py — the SHALLOW-ARITHMETIC suite the best chips use (owner 07-20). Carry-save adders (3:2
compressors) + a WALLACE-TREE multiplier: partial products reduced by a CSA tree to two rows, then one parallel-prefix
add. O(log n) depth vs the O(n^2) shift-add multiplier. Byte-exact, depth measured.

  python host/pfc_shallow.py
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_bettergates import kogge_stone_add, ripple_add, depth_of


def csa(g, a, b, c):                                    # 3:2 compressor (carry-save adder), per bit
    s = [g.XOR(g.XOR(a[i], b[i]), c[i]) for i in range(len(a))]
    cout = [g.OR(g.OR(g.AND(a[i], b[i]), g.AND(a[i], c[i])), g.AND(b[i], c[i])) for i in range(len(a))]
    return s, cout


def partial_products(g, A, B):
    W = len(A); rows = []
    for j in range(W):
        row = [g.C0] * j + [g.AND(A[i], B[j]) for i in range(W)] + [g.C0] * (W - j)
        rows.append(row[:2 * W])
    return rows


def wallace_mul(g, A, B):
    W = len(A); rows = partial_products(g, A, B)
    while len(rows) > 2:                                # CSA tree: reduce 3 rows -> 2 (sum + shifted carry)
        nxt = []; i = 0
        while i + 3 <= len(rows):
            s, cout = csa(g, rows[i], rows[i + 1], rows[i + 2])
            carry = ([g.C0] + cout[:2 * W - 1])         # carry has weight 2 -> shift left 1
            nxt.append(s); nxt.append(carry); i += 3
        while i < len(rows): nxt.append(rows[i]); i += 1
        rows = nxt
    return rows[0] if len(rows) == 1 else kogge_stone_add(g, rows[0], rows[1])


def shiftadd_mul(g, A, B):                              # the naive O(n^2)-depth version, for the comparison
    W = len(A); acc = [g.C0] * (2 * W)
    for j in range(W):
        row = ([g.C0] * j + [g.AND(A[i], B[j]) for i in range(W)] + [g.C0] * (W - j))[:2 * W]
        acc = ripple_add(g, acc, row)[:2 * W]
    return acc


def measure(name, fn, W):
    g = CC.CircuitCompiler(2 * W); A = g.IN[0:W]; B = g.IN[W:2 * W]
    outs = fn(g, A, B); gates, o2 = g.dce(outs); dep = depth_of(g.n_in, gates, o2)
    ok = True; random.seed(4)
    for _ in range(200):
        a = random.getrandbits(W); b = random.getrandbits(W)
        v = CC.ripple_typed(g, gates, 2 + g.n_in + len(gates),
                            [(a >> i) & 1 for i in range(W)] + [(b >> i) & 1 for i in range(W)], 1)
        bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
        if sum(bit(o2[i]) << i for i in range(2 * W)) != a * b: ok = False; break
    print(f"    {name:12s} W={W}: depth {dep:>4}  gates {len(gates):>5}  byte-exact={ok}", flush=True)
    return dep, len(gates), ok


def main():
    print("Muhlnickel SHALLOW ARITHMETIC — Wallace-tree multiplier (CSA reduction) vs shift-add, byte-exact + depth.\n", flush=True)
    ok_all = True
    for W in (8, 16):
        ds, gs, oa = measure("shift-add", shiftadd_mul, W)
        dw, gw, ob = measure("wallace", wallace_mul, W)
        ok_all = ok_all and oa and ob
        print(f"      -> depth {ds}->{dw} ({ds/max(dw,1):.1f}x shallower) at W={W}\n", flush=True)
    print("  carry-save + Wallace tree = the multiplier depth the best chips use (O(log n), not O(n^2)).", flush=True)
    print("  route csa()/wallace_mul() into the fabricator so every baked multiply is shallow.", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
