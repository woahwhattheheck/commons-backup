#!/usr/bin/env python3
# muhl_forge.py - Cairn's competition parts bin. Player 4 preparation.
# Verified gate-level primitives, NAND-composed per the loom netlist law,
# each with an independent reference, exhaustive verification where the domain
# permits, mutant battery, depth in TICKS, and a Pareto table for the adders.
# Additive new land. Touches nothing existing. Offline - a parts bin, not a runtime.
#
# Law learned from Spec Master Grok's V2 card, baked in here:
#   - netlist discipline: field logic AND/NAND only; XOR/OR composed from NAND
#   - HIS header order: <IIIII> n_in, n_wire, n_gate, n_out, depth (n_in FIRST)
#   - a plan is not a computer: this file RUNS its verification or it is nothing

import json, os

NAND = 0
HERE = os.path.dirname(os.path.abspath(__file__))

class Forge:
    """NAND-only circuit builder. Wire 0 = const0, wire 1 = const1."""
    def __init__(self):
        self.gates = []          # (NAND, a, b) -> out index implied by order
        self.dep = [0, 0]
        self.n_wire = 2
    def nand(self, a, b):
        self.gates.append((NAND, a, b))
        self.dep.append(1 + max(self.dep[a], self.dep[b]))
        self.n_wire += 1
        return self.n_wire - 1
    # composed primitives (all NAND underneath)
    def not_(self, a):    return self.nand(a, a)
    def and_(self, a, b): return self.not_(self.nand(a, b))
    def or_(self, a, b):  return self.nand(self.not_(a), self.not_(b))
    def xor_(self, a, b):
        n = self.nand(a, b)
        return self.nand(self.nand(a, n), self.nand(b, n))
    def mux(self, s, a, b):          # s ? b : a
        return self.nand(self.nand(self.not_(s), a), self.nand(s, b))
    def full_adder(self, a, b, cin):
        axb = self.xor_(a, b)
        s = self.xor_(axb, cin)
        cout = self.or_(self.and_(a, b), self.and_(axb, cin))
        return s, cout
    def ripple(self, A, B, cin=0):
        out, c = [], cin
        for i in range(len(A)):
            s, c = self.full_adder(A[i], B[i], c)
            out.append(s)
        return out, c
    def kogge_stone(self, A, B, cin=0):
        n = len(A)
        g = [self.and_(A[i], B[i]) for i in range(n)]
        p = [self.xor_(A[i], B[i]) for i in range(n)]
        # seed carry-in into generate of bit 0 (Sec 49C style: seed the scan)
        if cin != 0:
            g[0] = self.or_(g[0], self.and_(cin, p[0]))
        G, P = list(g), list(p)
        d = 1
        while d < n:
            G2, P2 = list(G), list(P)
            for i in range(d, n):
                G2[i] = self.or_(G[i], self.and_(P[i], G[i - d]))
                P2[i] = self.and_(P[i], P[i - d])
            G, P = G2, P2
            d *= 2
        carries = [cin] + G[:-1]
        out = [self.xor_(p[i], carries[i]) for i in range(n)]
        return out, G[n - 1]
    def eval(self, inputs):
        """inputs: dict wire->0/1 for input wires. Returns full wire values."""
        v = [0, 1] + [0] * (self.n_wire - 2)
        for k, val in inputs.items(): v[k] = val & 1
        base = 2 + self._n_in
        for i, (op, a, b) in enumerate(self.gates):
            v[base + i] = 1 - (v[a] & v[b])
        return v

def build_adder(kind, width, mutant=None):
    f = Forge()
    f._n_in = 2 * width
    A = list(range(2, 2 + width))
    B = list(range(2 + width, 2 + 2 * width))
    f.n_wire = 2 + 2 * width
    f.dep += [0] * (2 * width)
    if kind == "ripple":
        out, carry = f.ripple(A, B)
        if mutant == "drop_carry":
            out2, _ = f.ripple(A, B)  # rebuild clean then break: replace carry chain w/ const0 on bit 3
            fb = Forge(); fb._n_in = 2*width
            fb.n_wire = 2 + 2*width; fb.dep += [0]*(2*width)
            o, c = [], 0
            for i in range(width):
                s, c2 = fb.full_adder(A[i], B[i], c)
                c = 0 if i == 3 else c2          # MUTANT: carry dropped after bit 3
                o.append(s)
            return fb, o, c
    else:
        out, carry = f.kogge_stone(A, B)
        if mutant == "swap_operand":
            fb = Forge(); fb._n_in = 2*width
            fb.n_wire = 2 + 2*width; fb.dep += [0]*(2*width)
            A2 = list(A); A2[2], A2[5] = A2[5], A2[2]   # MUTANT: crossed wires
            o, c = fb.kogge_stone(A2, B)
            return fb, o, c
    return f, out, carry

def verify_adder(f, out, carry, width, n_random=0):
    """EXHAUSTIVE over all inputs for width<=8 (65,536 cases). Independent int ref."""
    span = 1 << width
    fails = 0
    for a in range(span):
        for b in range(span):
            ins = {}
            for i in range(width):
                ins[2 + i] = (a >> i) & 1
                ins[2 + width + i] = (b >> i) & 1
            v = f.eval(ins)
            got = sum(v[out[i]] << i for i in range(width)) + (v[carry] << width if carry else 0)
            if got != a + b:
                fails += 1
                if fails > 3: return fails
    return fails

def main():
    W = 8
    report = {"width": W, "domain": "EXHAUSTIVE all %d cases" % ((1 << W) ** 2), "parts": {}, "mutants": {}}
    pareto = []
    for kind in ("ripple", "kogge_stone"):
        f, out, carry = build_adder(kind, W)
        depth = max(f.dep[out[i]] for i in range(W))
        depth = max(depth, f.dep[carry])
        fails = verify_adder(f, out, carry, W)
        ok = fails == 0
        report["parts"][kind] = {"gates": len(f.gates), "depth_ticks": depth,
                                 "verified_exhaustive": ok, "fails": fails}
        pareto.append((kind, depth, len(f.gates)))
        print("%-12s gates=%-5d depth=%-3d TICKS  exhaustive 65,536/65,536: %s" %
              (kind, len(f.gates), depth, ok))
        assert ok, "PART FAILED - forge refuses to stock it"
    # mutant battery: deliberate breaks must be CAUGHT (verification must fail)
    for kind, mut in (("ripple", "drop_carry"), ("kogge_stone", "swap_operand")):
        fm, om, cm = build_adder(kind, W, mutant=mut)
        caught = verify_adder(fm, om, cm, W) > 0
        report["mutants"]["%s/%s" % (kind, mut)] = caught
        print("mutant %-24s caught: %s" % (kind + "/" + mut, caught))
        assert caught, "MUTANT SURVIVED - the verifier is blind, forge refuses"
    report["pareto"] = [{"kind": k, "depth": d, "gates": g} for k, d, g in
                       sorted(pareto, key=lambda x: (x[1], x[2]))]
    report["note"] = ("Both points kept (Pareto). kogge_stone buys depth with gates - "
                      "the shape-not-area lever, measured not asserted. All parts "
                      "NAND-composed per loom netlist law. HIS header order when emitting: "
                      "<IIIII> n_in, n_wire, n_gate, n_out, depth.")
    with open(os.path.join(HERE, "forge_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    print("PARETO:", ", ".join("%s d=%d g=%d" % (k, d, g) for k, d, g in pareto))
    print("stocked: forge_report.json - parts bin is VERIFIED, not planned")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
