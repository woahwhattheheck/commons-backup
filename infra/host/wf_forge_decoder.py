#!/usr/bin/env python3
"""host/wf_forge_decoder.py — forge an n-to-2^n one-hot ADDRESS DECODER and a 2^n-to-1 MULTIPLEXER out of NAND gates,
then PROVE they compute by simulating the netlist (the signal running through the gates IS the computation).

Additive only: imports the Circuit class from pfc_forge, modifies nothing, never touches titan.gguf. Pure Python.

  python host/wf_forge_decoder.py

Shape note: a decoder maps n address lines -> 2^n one-hot selects; a mux takes those 2^n selects + 2^n data lines ->
1 output. nOut (decoder) and nIn (mux) grow as 2^n — the same address-shaped explosion as titan's memory-like
TITANCIR records with nIn 1024 / 4096 / 65536 / 262144 (= 2^10 / 2^12 / 2^16 / 2^18)."""
import os, sys, struct, random
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pfc_forge import Circuit, full_adder  # noqa: F401  (full_adder imported per task spec)


# ---------- balanced NAND-composed reduction trees ----------
def and_tree(c, terms):
    """AND of a list of node indices via a balanced tree of 2-input ANDs (each AND = NAND+NOT). Empty -> const 1."""
    if not terms:
        return c.const(1)
    layer = list(terms)
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer) - 1, 2):
            nxt.append(c.AND(layer[i], layer[i + 1]))
        if len(layer) & 1:
            nxt.append(layer[-1])
        layer = nxt
    return layer[0]


def or_tree(c, terms):
    """OR of a list of node indices via a balanced tree of 2-input ORs. Empty -> const 0."""
    if not terms:
        return c.const(0)
    layer = list(terms)
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer) - 1, 2):
            nxt.append(c.OR(layer[i], layer[i + 1]))
        if len(layer) & 1:
            nxt.append(layer[-1])
        layer = nxt
    return layer[0]


# ---------- the decode primitive: n address lines -> 2^n one-hot selects ----------
def decode_lines(c, A):
    """Given address input nodes A (LSB first), return 2^n one-hot line nodes. Line k = AND_i( A[i] if bit i of k
    else NOT A[i] ). Exactly one line is high for any address; that line's index equals the address value."""
    n = len(A)
    notA = [c.NOT(a) for a in A]            # each address bit complemented ONCE, then reused across all lines
    lines = []
    for k in range(1 << n):
        terms = [A[i] if (k >> i) & 1 else notA[i] for i in range(n)]
        lines.append(and_tree(c, terms))
    return lines


def decoder(n):
    c = Circuit(f"dec{n}to{1 << n}")
    A = [c.inp(f"a{i}") for i in range(n)]
    for k, ln in enumerate(decode_lines(c, A)):
        c.out(f"y{k}", ln)
    return c


def mux(n):
    """2^n-to-1 mux DRIVEN BY the decoder: out = OR_k( d_k AND select_k ), select = decode(address)."""
    c = Circuit(f"mux{1 << n}to1")
    A = [c.inp(f"a{i}") for i in range(n)]
    D = [c.inp(f"d{k}") for k in range(1 << n)]
    sel = decode_lines(c, A)
    prod = [c.AND(D[k], sel[k]) for k in range(1 << n)]
    c.out("y", or_tree(c, prod))
    return c


# ---------- structural stats ----------
def _levels(c):
    d = [0] * len(c.nodes)
    for i, nd in enumerate(c.nodes):
        if nd[0] == "NAND":
            d[i] = 1 + max(d[nd[1]], d[nd[2]])
    return d


def width(c):
    d = _levels(c)
    from collections import Counter
    cnt = Counter(d[i] for i, nd in enumerate(c.nodes) if nd[0] == "NAND")
    return max(cnt.values()) if cnt else 0


def backward_frac(c):
    """Fraction of gate edge-refs that point to an EARLIER node. A pure combinational (feedforward) netlist is 1.0."""
    tot = back = 0
    for i, nd in enumerate(c.nodes):
        if nd[0] == "NAND":
            for r in (nd[1], nd[2]):
                tot += 1
                if r < i:
                    back += 1
    return (back / tot) if tot else 1.0


def sig(c):
    return dict(name=c.name, gates=c.n_gates(), depth=c.depth(), width=width(c),
               nIn=len(c.inputs), nOut=len(c.outputs), arity=2, state_bits=0,
               backward_ref_frac=round(backward_frac(c), 4))


# ---------- verification: simulate the netlist against ground truth ----------
def verify_decoder(n):
    """EXHAUSTIVE over all 2^n addresses; check every one of the 2^n output lines each time (full truth table)."""
    c = decoder(n); bad = total = 0
    for a in range(1 << n):
        r = c.run(**{f"a{i}": (a >> i) & 1 for i in range(n)})
        for k in range(1 << n):
            total += 1
            if r[f"y{k}"] != (1 if k == a else 0):
                bad += 1
    return c, bad, total


def verify_mux_full(n):
    """EXHAUSTIVE over the ENTIRE input space: all 2^n addresses x all 2^(2^n) data vectors. Feasible for small n."""
    c = mux(n); bad = total = 0
    nd = 1 << n
    for a in range(1 << n):
        addr = {f"a{i}": (a >> i) & 1 for i in range(n)}
        for dv in range(1 << nd):
            ins = dict(addr); ins.update({f"d{k}": (dv >> k) & 1 for k in range(nd)})
            r = c.run(**ins); total += 1
            if r["y"] != ((dv >> a) & 1):
                bad += 1
    return c, bad, total


def verify_mux_thorough(n, rand_cases=3000):
    """Address-EXHAUSTIVE (all 2^n) x per-line sensitivity (walking-ones + walking-zeros proves the output tracks the
    selected line and is independent of every other line) + >=500 random full-vector cases. Used when the full input
    space 2^(n+2^n) is too large to sweep."""
    c = mux(n); bad = total = 0
    nd = 1 << n
    for a in range(1 << n):
        addr = {f"a{i}": (a >> i) & 1 for i in range(n)}
        for v in (0, 1):                                             # selected bit = v, all others = ~v
            data = {f"d{k}": (v if k == a else 1 - v) for k in range(nd)}
            r = c.run(**addr, **data); total += 1
            if r["y"] != v: bad += 1
        for j in range(nd):                                         # walking-ones and walking-zeros
            data = {f"d{k}": (1 if k == j else 0) for k in range(nd)}
            r = c.run(**addr, **data); total += 1
            if r["y"] != (1 if j == a else 0): bad += 1
            data = {f"d{k}": (0 if k == j else 1) for k in range(nd)}
            r = c.run(**addr, **data); total += 1
            if r["y"] != (0 if j == a else 1): bad += 1
    for _ in range(rand_cases):                                     # random full data vectors
        a = random.randrange(1 << n); dv = random.getrandbits(nd)
        ins = {f"a{i}": (a >> i) & 1 for i in range(n)}
        ins.update({f"d{k}": (dv >> k) & 1 for k in range(nd)})
        r = c.run(**ins); total += 1
        if r["y"] != ((dv >> a) & 1): bad += 1
    return c, bad, total


def main():
    print("MUHLNICKEL FORGE — n-to-2^n address decoder + 2^n-to-1 mux, built from NAND, proven by simulation\n")
    results = {}

    # --- decoders: exhaustive full truth table ---
    for n in (3, 4):
        c, bad, total = verify_decoder(n)
        s = sig(c); ok = (bad == 0)
        s.update(verified=("PASS" if ok else "FAIL"), test=f"exhaustive {1<<n} addresses x {1<<n} lines = {total} checks")
        results[c.name] = s
        print(f"  {c.name:10s}: {s['gates']:>4} NAND, depth {s['depth']:>2}, width {s['width']:>3}, "
              f"nIn={s['nIn']} nOut={s['nOut']}  ·  {total} checks: {'ALL CORRECT PASS' if ok else f'{bad} WRONG FAIL'}")

    # --- mux n=3: EXHAUSTIVE over full input space (2^3 addr x 2^8 data = 2048) ---
    c, bad, total = verify_mux_full(3)
    s = sig(c); ok = (bad == 0)
    s.update(verified=("PASS" if ok else "FAIL"), test=f"exhaustive full input space = {total} evals")
    results[c.name] = s
    print(f"  {c.name:10s}: {s['gates']:>4} NAND, depth {s['depth']:>2}, width {s['width']:>3}, "
          f"nIn={s['nIn']} nOut={s['nOut']}  ·  {total} evals (full space): "
          f"{'ALL CORRECT PASS' if ok else f'{bad} WRONG FAIL'}")

    # --- mux n=4: full space 2^20 too large; address-exhaustive + walking-bit sensitivity + random ---
    c, bad, total = verify_mux_thorough(4)
    s = sig(c); ok = (bad == 0)
    s.update(verified=("PASS" if ok else "FAIL"),
             test=f"16 addr x walking-ones/zeros sensitivity + 3000 random = {total} evals")
    results[c.name] = s
    print(f"  {c.name:10s}: {s['gates']:>4} NAND, depth {s['depth']:>2}, width {s['width']:>3}, "
          f"nIn={s['nIn']} nOut={s['nOut']}  ·  {total} evals (addr-exhaustive+walking+random): "
          f"{'ALL CORRECT PASS' if ok else f'{bad} WRONG FAIL'}")

    # --- cross-check the TITANCIR shape on the n=4 decoder ---
    c = decoder(4); blob = c.emit_titancir()
    ver, N, E, nIn, nOut, arity = struct.unpack_from("<6I", blob, 8)
    print(f"\nTITANCIR emit (dec4to16): magic={blob[:8]} header=(ver={ver}, nodes={N}, gates={E}, "
          f"nIn={nIn}, nOut={nOut}, arity={arity}) — same 6-word header + arity-2 ref list as titan's baked records.")
    print("nIn/nOut scaling: decoder nOut = 2^n, mux nIn = n + 2^n. At n=10/12/16/18 that is exactly titan's "
          "memory-address record widths (1024 / 4096 / 65536 / 262144).")

    return results


if __name__ == "__main__":
    main()
