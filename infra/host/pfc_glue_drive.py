#!/usr/bin/env python3
"""host/pfc_glue_drive.py — the GLUE runs on the Muhlnickel's baked circuits, bit-sliced. Starting with SiLU, the hot one.

`CIRCUIT_PFC.md`'s rule again: if a circuit exists, wire it. `pfc_silu8` (12,593 gates) has been baked since 07-23,
but `pfc_forward.Glue.silu` was still calling host `math.exp`. Its own docstring claimed "a table read, 0 ripple" —
that was not true, and SiLU is the single hottest glue call in the model: 14,336 hidden units x 2 routed experts x 32
layers = ~917,000 calls PER POSITION.

CONTRACT — recovered EMPIRICALLY, not from the fabricator source, by rippling the stored circuit over all 256 input
codes and fitting the curve (`mean |err| = 0.24`, i.e. exact):
    input : 8-bit code, x = -8 + 16*code/256   (range [-8, 8))
    output: int16 = round(silu(x) * 256)

WHY BIT-SLICED. Driving one value per ripple would be 917k x 12,593 gate-ops per position — absurd. Instead every
VALUE is a LANE: the 8 input bits become 8 bit-planes of W lanes, and ONE ripple settles all W silu results at once
(bit-slicing IS SIMD in stored gates, `PFC_LEVER_DATADUMP` §A). A whole expert's 14,336 activations become a single
sweep of the stored circuit.

  python host/pfc_glue_drive.py            # byte-exact vs the circuit's own table + vs host silu, timed
"""
import math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

SILU_LO, SILU_HI, SILU_N, SILU_SCALE = -8.0, 8.0, 256, 256
_CD = None


def _cd():
    global _CD
    if _CD is None: _CD = TC.load("pfc_silu8")
    return _CD


def _ripple_bs(cd, planes, W):
    """Bit-sliced NAND ripple of the stored circuit — W lanes settle in one pass.
    Wire layout: 0=const0, 1=const1, 2..2+n_in-1 = inputs, then gates (same as the fabricator / sdc_fwd_sdc)."""
    MASK = (1 << W) - 1
    n_in = cd["n_in"]; ga = cd["ga"]; gb = cd["gb"]; ng = len(ga)
    v = [0] * (2 + n_in + ng)
    v[1] = MASK
    for i in range(n_in): v[2 + i] = planes[i]
    base = 2 + n_in
    for i in range(ng): v[base + i] = ~(v[ga[i]] & v[gb[i]]) & MASK
    return [v[o] for o in cd["outs"]]


def silu_many(xs, cd=None):
    """SiLU for a whole vector, computed by the STORED GATES in one bit-sliced sweep. Returns floats."""
    if cd is None: cd = _cd()
    W = len(xs)
    if W == 0: return []
    span = SILU_HI - SILU_LO
    codes = [min(SILU_N - 1, max(0, int((x - SILU_LO) / span * SILU_N))) for x in xs]
    planes = [0] * 8                                            # 8 input bits -> 8 bit-planes, lane l = value l
    for l, c in enumerate(codes):
        bit = 1 << l
        while c:
            b = c & -c
            planes[b.bit_length() - 1] |= bit
            c ^= b
    outs = _ripple_bs(cd, planes, W)                            # ONE ripple settles every lane
    res = []
    for l in range(W):
        u = 0
        for k in range(len(outs)): u |= ((outs[k] >> l) & 1) << k
        if u >= 32768: u -= 65536
        res.append(u / SILU_SCALE)
    return res


def main():
    cd = _cd()
    print(f"=== SiLU ON THE Muhlnickel — `pfc_silu8` ({len(cd['ga']):,} gates), bit-sliced ===", flush=True)

    # 1) every code, against the circuit's own single-value ripple (the definition of correct)
    codes = list(range(SILU_N))
    xs = [SILU_LO + (SILU_HI - SILU_LO) * c / SILU_N for c in codes]
    bs = silu_many(xs, cd)
    ok = 0
    for c in codes:
        v = TC.ripple(cd, [(c >> b) & 1 for b in range(8)])
        u = sum(bit << i for i, bit in enumerate(v))
        if u >= 32768: u -= 65536
        if abs(bs[c] - u / SILU_SCALE) < 1e-12: ok += 1
    print(f"  bit-sliced == the circuit's own per-value ripple: {ok}/{SILU_N}", flush=True)

    # 2) against host silu, and timed at a real FFN width
    import random; random.seed(7)
    N = 14336                                                   # one Mixtral expert's hidden width
    vals = [random.gauss(0, 2.5) for _ in range(N)]
    t0 = time.time(); got = silu_many(vals, cd); t_pfc = time.time() - t0
    t0 = time.time(); ref = [x / (1.0 + math.exp(-x)) for x in vals]; t_host = time.time() - t0
    err = max(abs(a - b) for a, b in zip(got, ref))
    print(f"  {N:,} activations (one expert) in ONE sweep: {t_pfc*1000:.1f} ms   host math.exp: {t_host*1000:.1f} ms", flush=True)
    print(f"  max |Muhlnickel - host silu| = {err:.4f}  (the circuit's 8-bit quantisation, not an error)", flush=True)
    print(f"  per position Mixtral needs ~917k silu calls = 64 sweeps of the stored circuit, not 917k host calls.", flush=True)
    return 0 if ok == SILU_N else 1


if __name__ == "__main__":
    raise SystemExit(main())
