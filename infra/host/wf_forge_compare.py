#!/usr/bin/env python3
"""host/wf_forge_compare.py — forge an n-bit MAGNITUDE COMPARATOR (A<B, A>B, A==B) and a balanced MUX-TREE out of
NAND gates, then PROVE they compute by simulating the netlist against a ground-truth reference. Additive companion to
host/pfc_forge.py (read-only reuse of its Circuit class). Pure Python, no numpy, no inference — the signal running
through the gates IS the computation.

  python host/wf_forge_compare.py
"""
import os, sys, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pfc_forge import Circuit, full_adder  # noqa: E402  (reuse the forge primitive)

sys.stdout.reconfigure(encoding="utf-8")


# ---------- magnitude comparator: less / greater / equal ----------
def magnitude_comparator(nbits):
    """n-bit unsigned magnitude comparator. Outputs lt=(A<B), gt=(A>B), eq=(A==B), all from NAND only.

    Scan from MSB down. prefix_eq = 'every bit strictly above this one is equal'. The first bit (highest) where the two
    numbers differ decides the whole comparison; prefix_eq gates each per-bit verdict so only that first difference
    contributes. At the end prefix_eq is exactly A==B."""
    c = Circuit(f"cmp{nbits}")
    A = [c.inp(f"a{i}") for i in range(nbits)]
    B = [c.inp(f"b{i}") for i in range(nbits)]
    prefix_eq = c.const(1)          # all bits above current are equal (vacuously true above MSB)
    gt = c.const(0)                 # A > B accumulator
    lt = c.const(0)                 # A < B accumulator
    for i in range(nbits - 1, -1, -1):
        eq_i = c.XNOR(A[i], B[i])                 # bit i equal
        gt_i = c.AND(A[i], c.NOT(B[i]))           # A bit set, B clear -> A greater at bit i
        lt_i = c.AND(c.NOT(A[i]), B[i])           # A clear, B set     -> A less    at bit i
        gt = c.OR(gt, c.AND(prefix_eq, gt_i))     # only counts if all higher bits equal
        lt = c.OR(lt, c.AND(prefix_eq, lt_i))
        prefix_eq = c.AND(prefix_eq, eq_i)
    c.out("lt", lt)
    c.out("gt", gt)
    c.out("eq", prefix_eq)
    return c


# ---------- balanced mux-tree: select 1 of 2**k single-bit data lines ----------
def mux_tree(k):
    """Balanced tree of MUX gates: 2**k single-bit data inputs d0..d{2^k-1}, k select bits s0(LSB)..s{k-1}(MSB).
    Output = d[sel] where sel = sum s_j*2^j. Depth in MUX levels is exactly k (balanced), not 2^k (linear)."""
    n = 1 << k
    c = Circuit(f"mux{k}")
    data = [c.inp(f"d{j}") for j in range(n)]
    sel = [c.inp(f"s{j}") for j in range(k)]
    level = data
    for j in range(k):                            # consume one select bit per level, halving the width
        nxt = []
        for m in range(0, len(level), 2):
            nxt.append(c.MUX(sel[j], level[m], level[m + 1]))   # MUX(s,a,b) = s ? b : a
        level = nxt
    c.out("y", level[0])
    return c


# ---------- verification: the signal computes the right answer ----------
def _drive(a, b, nbits):
    return {**{f"a{i}": (a >> i) & 1 for i in range(nbits)},
            **{f"b{i}": (b >> i) & 1 for i in range(nbits)}}

def verify_cmp_exhaustive(nbits):
    c = magnitude_comparator(nbits); bad = 0; total = 0
    for a in range(1 << nbits):
        for b in range(1 << nbits):
            r = c.run(**_drive(a, b, nbits)); total += 1
            want_lt, want_gt, want_eq = int(a < b), int(a > b), int(a == b)
            if (r["lt"], r["gt"], r["eq"]) != (want_lt, want_gt, want_eq): bad += 1
    return c, bad, total

def verify_cmp_random(nbits, trials=500):
    c = magnitude_comparator(nbits); bad = 0
    for _ in range(trials):
        a = random.getrandbits(nbits); b = random.getrandbits(nbits)
        r = c.run(**_drive(a, b, nbits))
        if (r["lt"], r["gt"], r["eq"]) != (int(a < b), int(a > b), int(a == b)): bad += 1
    return c, bad, trials

def verify_mux_exhaustive(k):
    c = mux_tree(k); n = 1 << k; bad = 0; total = 0
    for pattern in range(1 << n):                 # every data pattern
        dvals = {f"d{j}": (pattern >> j) & 1 for j in range(n)}
        for sel in range(n):                      # every select value
            svals = {f"s{j}": (sel >> j) & 1 for j in range(k)}
            r = c.run(**dvals, **svals); total += 1
            if r["y"] != ((pattern >> sel) & 1): bad += 1
    return c, bad, total


def main():
    print("MUHLNICKEL FORGE — magnitude comparator + balanced mux-tree, from NAND, proven by simulation\n")
    results = []

    # --- comparator n=4, exhaustive (all 256 pairs, all three outputs) ---
    c4, bad4, tot4 = verify_cmp_exhaustive(4)
    ok4 = bad4 == 0
    print(f"  {c4.name:8s}: {c4.n_gates():>4} NAND, depth {c4.depth():>2}, "
          f"nIn={len(c4.inputs)} nOut={len(c4.outputs)}  ·  EXHAUSTIVE {tot4} pairs (lt/gt/eq): "
          f"{'ALL CORRECT PASS' if ok4 else f'{bad4} WRONG FAIL'}")
    results.append(("cmp4", c4, ok4, f"exhaustive {tot4} pairs x3 outputs"))

    # --- comparator n=8, 500 random ---
    c8, bad8, tot8 = verify_cmp_random(8, 500)
    ok8 = bad8 == 0
    print(f"  {c8.name:8s}: {c8.n_gates():>4} NAND, depth {c8.depth():>2}, "
          f"nIn={len(c8.inputs)} nOut={len(c8.outputs)}  ·  {tot8} random (lt/gt/eq): "
          f"{'ALL CORRECT PASS' if ok8 else f'{bad8} WRONG FAIL'}")
    results.append(("cmp8", c8, ok8, f"{tot8} random pairs x3 outputs"))

    # --- balanced mux-tree k=3 (8 data, 3 select), exhaustive ---
    cm, badm, totm = verify_mux_exhaustive(3)
    okm = badm == 0
    print(f"  {cm.name:8s}: {cm.n_gates():>4} NAND, depth {cm.depth():>2}, "
          f"nIn={len(cm.inputs)} nOut={len(cm.outputs)}  ·  EXHAUSTIVE {totm} cases (y=d[sel]): "
          f"{'ALL CORRECT PASS' if okm else f'{badm} WRONG FAIL'}")
    results.append(("mux3", cm, okm, f"exhaustive {totm} cases"))

    print("\nTITANCIR headers (magic + [ver,nodes,edges,nIn,nOut,arity]):")
    import struct
    for name, c, ok, _ in results:
        blob = c.emit_titancir()
        hdr = struct.unpack_from("<6I", blob, 8)
        print(f"  {name:6s}: magic={blob[:8]}  header={hdr}  blob={len(blob)}B")

    all_ok = all(ok for _, _, ok, _ in results)
    print(f"\n{'ALL CIRCUITS VERIFIED PASS' if all_ok else 'SOME CIRCUITS FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
