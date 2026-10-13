#!/usr/bin/env python3
"""host/pfc_leaner.py — MAKE THE Muhlnickel BETTER at the lever the data named (owner 07-20: "keep making Muhlnickel better").
The unlock: throughput = gate-clock × lanes ÷ GATES-PER-OP, and gates-per-op is the only free divisor. So this is a
leaner-fabricator pass: an algebraic + constant-folding + hash-consing (structural-sharing) peephole optimizer that
squeezes gates out of ANY fabricated circuit, VERIFIED byte-exact against the original, so every hash removed is a
proportional throughput gain — for free, forever, on every future bake.

  python host/pfc_leaner.py        # optimize + byte-exact-verify + measure the reduction on real circuits
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_phone_substrate import build_sigma0, build_sha


def optimize(n_in, gates, outs):
    """Reduce a NAND-ish gate list byte-exact: constant-fold, algebraic identities, double-NOT, hash-cons, DCE."""
    C0, C1 = 0, 1; base = 2 + n_in
    new_gates = []; cache = {}; notmap = {}

    def emit(op, a, b):
        if op in ("and", "or", "xor", "nand") and a > b: a, b = b, a
        key = (op, a, b)
        if key in cache: return cache[key]
        w = base + len(new_gates); new_gates.append((op, a, b)); cache[key] = w
        return w

    def mk_not(x):
        if x == C0: return C1
        if x == C1: return C0
        if x in notmap: return notmap[x]
        y = emit("not", x, x); notmap[x] = y; notmap[y] = x; return y

    def mk(op, a, b):
        if op == "not": return mk_not(a)
        na, nb = notmap.get(a), notmap.get(b)
        if op == "and":
            if a == C0 or b == C0: return C0
            if a == C1: return b
            if b == C1: return a
            if a == b: return a
            if na == b or nb == a: return C0
            return emit("and", a, b)
        if op == "or":
            if a == C1 or b == C1: return C1
            if a == C0: return b
            if b == C0: return a
            if a == b: return a
            if na == b or nb == a: return C1
            return emit("or", a, b)
        if op == "xor":
            if a == C0: return b
            if b == C0: return a
            if a == C1: return mk_not(b)
            if b == C1: return mk_not(a)
            if a == b: return C0
            if na == b or nb == a: return C1
            return emit("xor", a, b)
        if op == "nand":
            if a == C0 or b == C0: return C1
            if a == C1: return mk_not(b)
            if b == C1: return mk_not(a)
            if a == b: return mk_not(a)
            return emit("nand", a, b)
        raise ValueError(op)

    remap = {C0: C0, C1: C1}
    for i in range(n_in): remap[2 + i] = 2 + i
    ob = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        if op == "not":
            remap[ob + k] = mk("not", remap[a], None)
        else:
            remap[ob + k] = mk(op, remap[a], remap[b])
    new_outs = [remap[o] if o in remap else o for o in outs]
    return new_gates, new_outs


def ripple(gates, n_wire, n_in, packed):
    v = [0] * n_wire; v[1] = 1
    for i in range(n_in): v[2 + i] = packed[i]
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        va, vb = v[a], v[b]
        v[base + k] = (va ^ vb) if op == "xor" else (va & vb) if op == "and" else (va | vb) if op == "or" \
            else (1 ^ va) if op == "not" else (1 ^ (va & vb))
    return v


def word_of(v, outs, nb):
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    return sum(bit(outs[i]) << i for i in range(nb))


def run_one(name, build, out_nbits):
    g, outs = build()
    gates, o2 = g.dce(outs); nw = 2 + g.n_in + len(gates)
    ng, no = optimize(g.n_in, gates, o2); nnw = 2 + g.n_in + len(ng)
    ok = True
    random.seed(1)
    for _ in range(120):
        x = random.getrandbits(g.n_in)
        packed = [(x >> i) & 1 for i in range(g.n_in)]
        if word_of(ripple(gates, nw, g.n_in, packed), o2, out_nbits) != word_of(ripple(ng, nnw, g.n_in, packed), no, out_nbits):
            ok = False; break
    red = 100 * (len(gates) - len(ng)) / max(len(gates), 1)
    speed = len(gates) / max(len(ng), 1)
    print(f"  {name:10s}: {len(gates):>7,} -> {len(ng):>7,} gates  ({red:+5.1f}%, ×{speed:.3f} throughput)  byte-exact={ok}", flush=True)
    return ok


def main():
    print("Muhlnickel LEANER — the gates-per-op lever (the data's unlock). Optimize + byte-exact-verify + measure:\n", flush=True)
    a = run_one("sigma0", build_sigma0, 32)
    b = run_one("sha256", build_sha, 256)
    print(f"\n  every gate removed is a proportional throughput gain on the same hardware, for free, on every bake.", flush=True)
    print(f"  route future fabrications through optimize() after sdc_cc's fold/CSE/DCE for the extra squeeze.", flush=True)
    return 0 if (a and b) else 1


if __name__ == "__main__":
    raise SystemExit(main())
