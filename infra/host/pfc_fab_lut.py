#!/usr/bin/env python3
"""host/pfc_fab_lut.py — the self-fabricating agent's FABRICATE step for FINITE MAPS.

Take a set of (input -> output) pairs the agent OBSERVED from its own behavior, and fabricate a LUT-as-gates ROM
(decoder + OR-tree, the pfc_addr precedent) that reproduces them byte-exact — then serialize a standalone .pfc the
on-device PfcEval addresses. This is "learn a function from your own logged I/O, bake it as dedicated hardware":
the core of P1 (the self-fabricating agent). The White Box verifies it byte-exact BEFORE it is ever baked.

  python host/pfc_fab_lut.py                 # demo: fabricate x -> x*x (8-bit) as a LUT, verify, write squares.pfc
  # or import fab_lut(pairs, n_in, n_out) from your self-fab driver.
Outputs to C:/llm/sandbox_circuits/*.pfc  (same place the sandbox circuits live)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

OUT = "C:/llm/sandbox_circuits"


def build_lut(n_in, n_out, pairs):
    """ROM: out[j] = OR over keys k whose output has bit j set, of (input == k). Absent inputs -> 0.
    pairs: dict {input_int -> output_int}. Returns (circuit, out_wires)."""
    c = TC.Circuit(n_in)
    IN = c.IN
    eqs = {k: c.eq_const(IN, k) for k in pairs}          # eq_const(input, k) = 1 iff input == k
    outs = []
    for j in range(n_out):
        term = c.C0
        for k, v in pairs.items():
            if (v >> j) & 1:
                term = c.or_(term, eqs[k])
        outs.append(term)
    return c, outs


def verify(c, outs, pairs, n_in):
    """Ripple in pure Python; every observed key must reproduce its output, and a few non-keys must give 0."""
    ga, gb = c.ga, c.gb
    def ripple(x):
        v = [0] * c.n_wire(); v[1] = 1
        for k in range(n_in): v[2 + k] = (x >> k) & 1
        base = 2 + c.n_in
        for i in range(len(ga)): v[base + i] = 1 - (v[ga[i]] & v[gb[i]])
        return sum((v[o] << j) for j, o in enumerate(outs))
    for k, v in pairs.items():
        if ripple(k) != v: return False, ("key", k, ripple(k), v)
    for x in range(min(1 << n_in, 64)):                  # sample non-keys -> must be 0
        if x not in pairs and ripple(x) != 0: return False, ("nonkey", x, ripple(x), 0)
    return True, None


def fab_lut(pairs, n_in, n_out, name):
    """Fabricate + verify + serialize a LUT for observed pairs. Returns (path, gates) or raises on mismatch."""
    c, outs = build_lut(n_in, n_out, pairs)
    ok, bad = verify(c, outs, pairs, n_in)
    if not ok:
        raise RuntimeError(f"LUT verify FAILED {bad} — not baking (a 0 is a wiring bug)")
    os.makedirs(OUT, exist_ok=True)
    blob = TC.serialize(c, outs)
    path = os.path.join(OUT, name + ".pfc")
    open(path, "wb").write(blob)
    return path, len(c.ga)


def main():
    # DEMO: pretend the agent kept computing x*x for 8-bit x (a recurring deterministic need it OBSERVED).
    # It fabricates a LUT that reproduces the observed map exactly, then addresses it instead of re-deriving.
    n_in, n_out = 8, 16
    pairs = {x: x * x for x in range(256)}
    print("Self-fab FABRICATE step — turning observed (input->output) pairs into a gate circuit …\n")
    path, gates = fab_lut(pairs, n_in, n_out, "squares")
    print(f"  observed function: x -> x*x, x in 0..255  ({len(pairs)} pairs)")
    print(f"  fabricated LUT: {gates:,} gates · byte-exact vs all 256 observed pairs: True")
    print(f"    -> {path}")
    print(f"  demo: the agent addresses squares[201] = {pairs[201]} (byte-exact, on-device via PfcEval)")
    print("  This is P1's FABRICATE step: any finite function the agent observes becomes dedicated hardware.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
