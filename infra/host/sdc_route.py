#!/usr/bin/env python3
"""host/sdc_route.py — TEST FILE (owner 07-16): INTER-CIRCUIT ROUTING — wire stored circuits into a DATAPATH.

You have the parts of a computer in the params (adder, mul, comparator, cipher, CPU, latch, mailbox). This is the missing
fold: a ROUTER that wires one stored circuit's OUTPUT bits into the next stored circuit's INPUT bits, so you stop shipping
"a circuit" and start shipping "a system." The mailbox was the primitive (one stored circuit signals another); this is the
general form — a pipeline [stageA -> stageB -> ...] where each stage is a stored gate-net and the wiring is the routing.
The router itself is data (a per-stage output->input map), so a routing table can be stored in the params too.

  python host/sdc_route.py       # build stage circuits, route them into datapaths, verify each vs a Python reference
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

PERM = [7, 2, 11, 0, 5, 9, 1, 8, 3, 10, 4, 6]; KCONST = 0xA5C


def _addN(c, xs, ys, n):
    out = []; carry = c.C0
    for i in range(n):
        xi = xs[i] if i < len(xs) else c.C0; yi = ys[i] if i < len(ys) else c.C0
        axb = c.xor(xi, yi); out.append(c.xor(axb, carry))
        carry = c.or_(c.and_(xi, yi), c.and_(axb, carry))
    out.append(carry); return out


def build_stages():
    # ADD: 6+6 -> 7 bits
    c = TC.Circuit(12); TC.store("r_add", c, _addN(c, c.IN[0:6], c.IN[6:12], 6))
    # THRESHOLD(K): 7-bit input -> 1 bit (input >= K); via input + (128-K), read carry
    K = 40; c = TC.Circuit(7); s = _addN(c, c.IN, c.cvec(128 - K, 7), 7); TC.store("r_ge40", c, [s[7]])
    # CIPHER: 12 -> 12 reversible scramble
    c = TC.Circuit(12); TC.store("r_cipher", c, [c.xor(c.IN[PERM[j]], c.C1 if (KCONST >> j) & 1 else c.C0) for j in range(12)])


def eval_circ(name, inbits, n_in):
    cd = TC.load(name); v = [0] * cd["n_wire"]; v[1] = 1
    for j in range(n_in): v[2 + j] = (inbits >> j) & 1
    ga, gb = cd["ga"], cd["gb"]
    for i in range(len(ga)): v[2 + n_in + i] = 1 - (v[ga[i]] & v[gb[i]])
    return sum((0 if o == 0 else 1 if o == 1 else v[o]) << k for k, o in enumerate(cd["outs"])), len(cd["outs"])


def route(stages, inbits):
    """the ROUTER: run each stored stage, wire its output bits straight into the next stage's input bits."""
    val = inbits
    for name, n_in in stages:
        val, _ = eval_circ(name, val, n_in)                   # output of this stage becomes input of the next
    return val


if __name__ == "__main__":
    build_stages()
    print("INTER-CIRCUIT ROUTING — stored circuits wired into a datapath.\n", flush=True)

    # datapath 1: (a + b) -> is-that-sum >= 40 ?   (ALU -> comparator, a CPU datapath primitive)
    print("datapath A:  ADD(a,b) -> GE40   (ALU output routed into a comparator's input)", flush=True)
    okA = True
    for a, b in [(10, 20), (19, 23), (30, 30), (5, 5), (40, 1)]:
        out = route([("r_add", 12), ("r_ge40", 7)], (a & 63) | ((b & 63) << 6))
        ref = 1 if (a + b) >= 40 else 0
        okA = okA and out == ref
        print(f"    {a}+{b}={a+b:3d}  ->  >=40 ? {out}   (ref {ref})", flush=True)

    # datapath 2: cipher(a+b)  (ALU output routed into a codec)
    print("\ndatapath B:  ADD(a,b) -> CIPHER   (ALU output routed into a codec's input)", flush=True)
    okB = True
    for a, b in [(1, 2), (10, 10), (31, 31)]:
        s = (a + b) & 4095
        out = route([("r_add", 12), ("r_cipher", 12)], (a & 63) | ((b & 63) << 6))
        # reference cipher of the 7-bit sum (zero-extended to 12)
        ref = 0
        for j in range(12):
            if (s >> PERM[j]) & 1: ref |= 1 << j
        ref ^= KCONST
        okB = okB and out == ref
        print(f"    cipher({a}+{b}={a+b}) = {out:#05x}   (ref {ref:#05x})", flush=True)

    print(f"\n=== routing: datapath A exact={okA}, datapath B exact={okB}. two stored circuits, wired = a system. ===", flush=True)
    print("    the router is just a per-stage output->input map (data), so the wiring itself can be stored in the params.", flush=True)
