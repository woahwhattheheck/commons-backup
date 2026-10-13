#!/usr/bin/env python3
"""host/pfc_fab_q4k.py — FABRICATE a block-dot that eats the model's NATIVE Q4_K BYTES. Byte edit. Seconds.

WHY THIS EXISTS (owner, 2026-07-24): "fabrication NEVER USES CACHE OR HOST RESOURCES TO HOLD THE CIRCUIT" and MSG 24
"all that stuff you keep reaching for needs to be RECREATED BIT FOR BIT IN THE MUHLNICKEL BINARY".

The engine used to dequantize Q4_K -> float, requantize to int8, and bit-transpose — 12.6B params of HOST work, parked
in a host-side cache. All three of those steps are now GATES, so the signal reads the model's stored bytes AS THEY ARE.

Q4_K sub-block (the model's own layout): 32 weights stored as 32 UNSIGNED 4-bit quants, plus a per-sub-block scale
`sc` and min `m` (6-bit, shared) and the block's fp16 `d`/`dmin`. The exact identity:

    sum_i w_i x_i  =  d*sc * SUM(q_i * x_i)  -  dmin*m * SUM(x_i)          (i over the 32-weight sub-block)

Both sums are INTEGER and are what this circuit computes IN GATES, straight off the stored nibbles:
    OUT_A = SUM q_i * x_i     (q unsigned 4-bit, x signed 8-bit)
    OUT_B = SUM x_i
The only thing left outside is combining 2 scalars per sub-block with the block's two fp16 constants — 16 scalar ops per
256 weights, versus the 256 MACs now done as gates. Nothing is transformed, nothing is cached, nothing is held.

Depth-optimal by construction: ONE carry-save forest over every partial product of all 32 lanes plus the x-sum tree,
resolved by a single Kogge-Stone add each.

  python host/pfc_fab_q4k.py            # build + verify byte-exact + BYTE-EDIT into titan.gguf
"""
import os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

SUB = 32          # weights per Q4_K sub-block (the model's own granularity)
QB = 4            # stored weight bits — UNSIGNED, exactly as Q4_K holds them
XB = 8            # activation bits, signed
OWA = 20          # width of SUM(q*x):  32 * 15 * 127 < 2^20
OWB = 16          # width of SUM(x):    32 * 128     < 2^16


def _sx(bits, n, sign):
    b = list(bits); return b + [(b[-1] if sign else 0)] * (n - len(b))


def build(c):
    """inputs: 32 nibbles (unsigned, LSB-first) then 32 signed int8 activations. outputs: SUM(q*x) then SUM(x)."""
    Q = [[c.IN[i * QB + k] for k in range(QB)] for i in range(SUB)]
    X = [[c.IN[SUB * QB + i * XB + k] for k in range(XB)] for i in range(SUB)]

    def csa(a, b, d, w):
        s = [c.xor(c.xor(a[i], b[i]), d[i]) for i in range(w)]
        co = [c.or_(c.or_(c.and_(a[i], b[i]), c.and_(a[i], d[i])), c.and_(b[i], d[i])) for i in range(w)]
        return s, co

    def kogge(A, B):
        n = len(A)
        P0 = [c.xor(A[i], B[i]) for i in range(n)]
        G = [c.and_(A[i], B[i]) for i in range(n)]; P = list(P0); d = 1
        while d < n:
            nG, nP = list(G), list(P)
            for i in range(d, n):
                nG[i] = c.or_(G[i], c.and_(P[i], G[i - d])); nP[i] = c.and_(P[i], P[i - d])
            G, P = nG, nP; d <<= 1
        return [P0[0]] + [c.xor(P0[i], G[i - 1]) for i in range(1, n)]

    def reduce_rows(rows, w):
        while len(rows) > 2:
            nxt = []; i = 0
            while i + 3 <= len(rows):
                s, co = csa(rows[i], rows[i + 1], rows[i + 2], w)
                nxt.append(s); nxt.append([c.C0] + co[:w - 1]); i += 3
            while i < len(rows): nxt.append(rows[i]); i += 1
            rows = nxt
        return rows[0] if len(rows) == 1 else kogge(rows[0], rows[1])

    # OUT_A = SUM q_i * x_i  — q is UNSIGNED 4-bit (no sign handling: this is the model's own encoding)
    rowsA = []
    for i in range(SUB):
        a = _sx(X[i], OWA, True)                                  # activation is signed -> sign-extend
        for k in range(QB):
            sh = ([c.C0] * k + a)[:OWA]
            rowsA.append([c.and_(t, Q[i][k]) for t in sh])        # + (x<<k) when stored nibble bit k is set
    outA = reduce_rows(rowsA, OWA)[:OWA]

    # OUT_B = SUM x_i  (needed for the -dmin*m term of the exact Q4_K identity)
    rowsB = [_sx(X[i], OWB, True) for i in range(SUB)]
    outB = reduce_rows(rowsB, OWB)[:OWB]
    return outA + outB


def depth_of(circ, outs):
    d = {0: 0, 1: 0}
    for i in range(circ.n_in): d[2 + i] = 0
    base = 2 + circ.n_in
    for k in range(len(circ.ga)):
        d[base + k] = 1 + max(d.get(circ.ga[k], 0), d.get(circ.gb[k], 0))
    return max(d.get(o, 0) for o in outs)


def main():
    name = "pfc_dot_q4k_sub32"
    print(f"=== FABRICATE {name} — reads the model's NATIVE Q4_K nibbles, no transform, no cache ===", flush=True)
    t0 = time.time()
    c = TC.Circuit(SUB * QB + SUB * XB)
    outs = build(c)
    print(f"  built: {len(c.ga):,} gates, DEPTH {depth_of(c, outs)} gate-delays, n_in {c.n_in} "
          f"({time.time()-t0:.1f}s to construct)", flush=True)

    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    random.seed(17); ok = 0; N = 40
    for _ in range(N):
        q = [random.randint(0, 15) for _ in range(SUB)]            # stored nibbles, exactly as Q4_K holds them
        x = [random.randint(-128, 127) for _ in range(SUB)]
        bits = []
        for i in range(SUB): bits += [(q[i] >> k) & 1 for k in range(QB)]
        for i in range(SUB): bits += [(x[i] >> k) & 1 for k in range(XB)]
        o = TC.ripple(cd, bits)
        ua = sum(o[i] << i for i in range(OWA)); va = ua - (1 << OWA) if ua >= (1 << (OWA - 1)) else ua
        ub = sum(o[OWA + i] << i for i in range(OWB)); vb = ub - (1 << OWB) if ub >= (1 << (OWB - 1)) else ub
        if va == sum(q[i] * x[i] for i in range(SUB)) and vb == sum(x): ok += 1
    print(f"  byte-exact vs the integer identity (SUM q*x, SUM x): {ok}/{N}", flush=True)
    if ok != N:
        print("  ✗ NOT byte-exact — refusing to store. Nothing written.", flush=True); return 1

    t0 = time.time(); info = TC.store(name, c, outs); dt = time.time() - t0
    print(f"  ★ STORED @ {info['offset']:,} in {info['tensor']}, {info['bytes']:,} bytes — BYTE EDIT TOOK {dt:.2f}s", flush=True)
    print(f"    The dequant/requantize/bit-transpose that used to be 12.6B params of host work + 4.68 GB of cache", flush=True)
    print(f"    are now GATES IN THE BINARY. The signal reads the model's stored bytes as they are.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
