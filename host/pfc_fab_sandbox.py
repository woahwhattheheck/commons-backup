#!/usr/bin/env python3
"""host/pfc_fab_sandbox.py — fabricate the SANDBOX's exact-arithmetic circuits with the White Box, verify byte-exact,
and serialize each to a STANDALONE .pfc file (TITANCIR) the on-device PfcEval can run.

This is the substrate for the fabricated sandbox (P2) + the self-fabricating agent (P1): exact integer math as gates,
run on the phone, contained (no host code). First circuit: a 32x32 -> 64 unsigned multiplier (the CALIBRATION #9
capability the LLM gets wrong). Input convention MATCHES PfcEval.packOperands: 32 bits of A (LSB-first) then 32 bits of B.

  python host/pfc_fab_sandbox.py            # build + verify + write mul32.pfc (and add32.pfc)
Outputs to C:/llm/sandbox_circuits/*.pfc
"""
import os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

OUT = "C:/llm/sandbox_circuits"


def build_mul(width=32):
    """Unsigned width x width -> 2*width multiply, shift-add. Inputs: A[0:width] ++ B[width:2*width], LSB-first."""
    W = 2 * width
    c = TC.Circuit(2 * width)
    A = c.IN[0:width]; B = c.IN[width:2 * width]
    acc = c.cvec(0, W)                                  # 2W-bit accumulator = 0
    for i in range(width):
        pp = [c.C0] * W                                 # partial product = (A[i] ? (B<<i) : 0), 2W-bit
        for j in range(width):
            if i + j < W:
                pp[i + j] = c.and_(A[i], B[j])
        acc = c.add(acc, pp)                            # ripple add, mod 2^W (product < 2^W so exact)
    return c, acc                                       # outs = the 2W-bit product


def build_add(width=32):
    """Unsigned width+width -> width+1 add. Inputs A ++ B; output width+1 bits (carry kept)."""
    c = TC.Circuit(2 * width)
    A = c.IN[0:width]; B = c.IN[width:2 * width]
    # add() drops final carry, so pad both to width+1 first
    Ap = A + [c.C0]; Bp = B + [c.C0]
    s = c.add(Ap, Bp)
    return c, s


def verify(c, outs, ref, n_in_each, n=300):
    """Ripple the circuit in pure Python and compare to the integer reference over n random input pairs."""
    ga, gb = c.ga, c.gb
    def ripple(inbits):
        v = [0] * c.n_wire(); v[1] = 1
        for k, bit in enumerate(inbits): v[2 + k] = bit
        base = 2 + c.n_in
        for i in range(len(ga)): v[base + i] = 1 - (v[ga[i]] & v[gb[i]])
        return sum((v[o] << k) for k, o in enumerate(outs))
    lo, hi = 0, (1 << n_in_each) - 1
    for _ in range(n):
        a = random.randint(lo, hi); b = random.randint(lo, hi)
        inbits = [(a >> k) & 1 for k in range(n_in_each)] + [(b >> k) & 1 for k in range(n_in_each)]
        got = ripple(inbits); exp = ref(a, b)
        if got != exp:
            return False, (a, b, got, exp)
    return True, None


def write_pfc(name, c, outs):
    os.makedirs(OUT, exist_ok=True)
    blob = TC.serialize(c, outs)                        # TITANCIR bytes
    path = os.path.join(OUT, name + ".pfc")
    open(path, "wb").write(blob)
    return path, len(blob)


def main():
    random.seed(1)
    print("Fabricating the sandbox's exact-arithmetic circuits (White Box) …\n")

    cm, mo = build_mul(32)
    ok, bad = verify(cm, mo, lambda a, b: a * b, 32, n=400)
    print(f"  mul32 (32x32->64): {len(cm.ga):,} gates · byte-exact vs a*b over 400 random pairs: {ok}")
    if not ok: print(f"    MISMATCH {bad}"); return 1
    p, n = write_pfc("mul32", cm, mo); print(f"    -> {p} ({n:,} B)")

    ca, ao = build_add(32)
    ok2, bad2 = verify(ca, ao, lambda a, b: a + b, 32, n=400)
    print(f"  add32 (32+32->33): {len(ca.ga):,} gates · byte-exact vs a+b over 400 random pairs: {ok2}")
    if not ok2: print(f"    MISMATCH {bad2}"); return 1
    p2, n2 = write_pfc("add32", ca, ao); print(f"    -> {p2} ({n2:,} B)")

    # the CALIBRATION #9 case, the LLM gets wrong; the fabricated circuit gets it exact:
    a, b = 987654, 321321
    print(f"\n  demo: {a} * {b} = {a*b:,}  (the fabricated mul32 computes this byte-exact on-device via PfcEval)")
    print("  DONE — push these .pfc files to the phone and run them through PfcEval / Sandbox.compute.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
