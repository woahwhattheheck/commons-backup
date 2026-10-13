#!/usr/bin/env python3
"""host/wf_forge_mult.py — forge an n-bit UNSIGNED array multiplier out of NAND gates, and prove it computes by
simulating the netlist (the signal propagating through the gates IS the multiply). Pure Python, no numpy, no inference.

Structure: a shift-add array multiplier.
  partial products  pp[i][j] = A[j] AND B[i]              (n*n AND gates)
  accumulate row i (= A * B[i]) into a 2n-bit running sum, aligned at bit i, with a ripple of full adders
  (higher bits above the row absorb the carry via full adders with a constant-0 addend = half adders).

Result is 2n bits wide: A*B for two n-bit unsigned operands fits in 2n bits.

  python host/wf_forge_mult.py     # build + simulate + verify (4-bit exhaustive, 8-bit 500 random)
"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from pfc_forge import Circuit, full_adder


def array_mult(nbits):
    """Unsigned array multiplier: 2*nbits inputs (a0..,b0..), 2*nbits outputs (p0..p{2n-1})."""
    c = Circuit(f"mul{nbits}")
    A = [c.inp(f"a{i}") for i in range(nbits)]
    B = [c.inp(f"b{i}") for i in range(nbits)]

    W = 2 * nbits
    acc = [c.const(0) for _ in range(W)]          # 2n-bit running product, starts at 0

    for i in range(nbits):                          # for each bit of B: add (A AND B[i]) << i
        pp = [c.AND(A[j], B[i]) for j in range(nbits)]
        cin = c.const(0)
        # add the n-bit partial product aligned at position i
        for j in range(nbits):
            pos = i + j
            s, cin = full_adder(c, acc[pos], pp[j], cin)
            acc[pos] = s
        # ripple the outgoing carry through the higher accumulator bits (b = const 0 => half adder)
        z = c.const(0)
        for pos in range(i + nbits, W):
            s, cin = full_adder(c, acc[pos], z, cin)
            acc[pos] = s

    for k in range(W):
        c.out(f"p{k}", acc[k])
    return c


def _pack(a, b, nbits):
    d = {f"a{i}": (a >> i) & 1 for i in range(nbits)}
    d.update({f"b{i}": (b >> i) & 1 for i in range(nbits)})
    return d


def verify(nbits, cases):
    """cases: 'all' -> exhaustive over all pairs; else int count of random cases. Returns (circuit, bad, tested)."""
    c = array_mult(nbits)
    W = 2 * nbits
    bad = 0
    if cases == "all":
        pairs = [(a, b) for a in range(1 << nbits) for b in range(1 << nbits)]
    else:
        pairs = [(random.getrandbits(nbits), random.getrandbits(nbits)) for _ in range(cases)]
    for a, b in pairs:
        r = c.run(**_pack(a, b, nbits))
        got = sum(r[f"p{k}"] << k for k in range(W))
        if got != a * b:
            bad += 1
    return c, bad, len(pairs)


def main():
    print("MUHLNICKEL FORGE — unsigned array multiplier out of NAND, proven by simulating the netlist\n")
    results = []

    # 4-bit: exhaustive over all 256 input pairs
    c4, bad4, n4 = verify(4, "all")
    ok4 = (bad4 == 0)
    print(f"  {c4.name:6s}: {c4.n_gates():>5} NAND gates, depth {c4.depth():>3}, nIn={len(c4.inputs)}, "
          f"nOut={len(c4.outputs)}  |  exhaustive {n4} pairs: "
          f"{'ALL CORRECT (PASS)' if ok4 else f'{bad4} WRONG (FAIL)'}")
    results.append((c4, ok4, n4, "exhaustive all 256 pairs"))

    # 8-bit: 500 random
    c8, bad8, n8 = verify(8, 500)
    ok8 = (bad8 == 0)
    print(f"  {c8.name:6s}: {c8.n_gates():>5} NAND gates, depth {c8.depth():>3}, nIn={len(c8.inputs)}, "
          f"nOut={len(c8.outputs)}  |  {n8} random pairs: "
          f"{'ALL CORRECT (PASS)' if ok8 else f'{bad8} WRONG (FAIL)'}")
    results.append((c8, ok8, n8, "500 random pairs"))

    # emit the TITANCIR shape for the 8-bit multiplier to confirm it matches titan's baked record format
    blob = c8.emit_titancir()
    import struct
    ver, N, E, nIn, nOut, arity = struct.unpack_from("<6I", blob, 8)
    print(f"\nTITANCIR emit (8-bit mul): magic={blob[:8]} header=(ver={ver}, nodes={N}, gates={E}, "
          f"nIn={nIn}, nOut={nOut}, arity={arity}) blob={len(blob)} bytes")

    return 0 if all(ok for _, ok, _, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
