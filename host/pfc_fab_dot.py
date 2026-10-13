#!/usr/bin/env python3
"""host/pfc_fab_dot.py — FABRICATE the depth-optimal block-dot INTO titan.gguf. A byte edit. Seconds.

OWNER, 2026-07-24, verbatim: *"fabrication means edit the binary and save that takes 2 seconds"* and *"fabrication NEVER
USES CACHE OR HOST RESOURCES TO HOLD THE CIRCUIT."*

What fabrication IS: build the gate netlist, verify it byte-exact, then `TC.store()` it — serialize + seek + write into
the params. The circuit then LIVES IN STORAGE, permanently, addressable, reversible via the registry/genome. That is the
whole operation and it costs a file write.

What fabrication IS NOT (the mistake this file replaces): walking the model's 12.6B params through dequant/requantize/
bit-transpose in Python and parking the result in a host-side disk cache. That is host compute holding the circuit in
host resources — forbidden, and unnecessary, because the model's parameter bytes are ALREADY in the binary and already
addressable (`host/pfc_load.py`: "the model's parameter bytes ARE its circuit — never copied").

THE CIRCUIT (measured shallowest, `host/pfc_dot_depth.py`): BLK weights x BLK activations -> int32, built as ONE
carry-save forest over every partial product of every lane, resolved by a SINGLE Kogge-Stone parallel-prefix add.
DEPTH is the pfc's latency, so depth is what this minimizes.

  python host/pfc_fab_dot.py            # build + verify + BYTE-EDIT into titan.gguf
  python host/pfc_fab_dot.py --blk 32   # smaller fabric
"""
import os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC


def _sx(bits, n):
    b = list(bits); return b + [b[-1]] * (n - len(b))


def build_shallow_dot(c, W, X, blk, WB, ow=32):
    """CSA forest over ALL partial products of ALL lanes -> 2 rows -> ONE Kogge-Stone add. Minimum depth."""
    def csa(a, b, d):                                    # 3:2 compressor, per bit
        s = [c.xor(c.xor(a[i], b[i]), d[i]) for i in range(ow)]
        co = [c.or_(c.or_(c.and_(a[i], b[i]), c.and_(a[i], d[i])), c.and_(b[i], d[i])) for i in range(ow)]
        return s, co

    def kogge_stone(A, B):                               # parallel-prefix adder, O(log n) depth
        n = len(A)
        P0 = [c.xor(A[i], B[i]) for i in range(n)]
        G = [c.and_(A[i], B[i]) for i in range(n)]; P = list(P0)
        d = 1
        while d < n:
            nG, nP = list(G), list(P)
            for i in range(d, n):
                nG[i] = c.or_(G[i], c.and_(P[i], G[i - d]))
                nP[i] = c.and_(P[i], P[i - d])
            G, P = nG, nP; d <<= 1
        return [P0[0]] + [c.xor(P0[i], G[i - 1]) for i in range(1, n)]

    rows = []
    for i in range(blk):
        a = _sx(X[i], ow)
        for k in range(WB):
            sh = ([c.C0] * k + a)[:ow]
            if k < WB - 1:
                rows.append([c.and_(t, W[i][k]) for t in sh])
            else:                                        # MSB of a two's-complement weight carries NEGATIVE weight:
                gated = [c.and_(t, W[i][k]) for t in sh] #   gate first, then invert; the +1 is unconditional (~0+1=0)
                rows.append([c.not_(t) for t in gated])
    rows.append([(c.C1 if (blk >> p) & 1 else c.C0) for p in range(ow)])   # all blk two's-complement +1s, folded
    while len(rows) > 2:
        nxt = []; i = 0
        while i + 3 <= len(rows):
            s, co = csa(rows[i], rows[i + 1], rows[i + 2])
            nxt.append(s); nxt.append([c.C0] + co[:ow - 1]); i += 3
        while i < len(rows): nxt.append(rows[i]); i += 1
        rows = nxt
    return (rows[0] if len(rows) == 1 else kogge_stone(rows[0], rows[1]))[:ow]


def depth_of(circ, outs):
    d = {0: 0, 1: 0}
    for i in range(circ.n_in): d[2 + i] = 0
    base = 2 + circ.n_in
    for k in range(len(circ.ga)):
        d[base + k] = 1 + max(d.get(circ.ga[k], 0), d.get(circ.gb[k], 0))
    return max(d.get(o, 0) for o in outs)


def main():
    blk = 32; WB = 8; XB = 8
    if "--blk" in sys.argv: blk = int(sys.argv[sys.argv.index("--blk") + 1])
    name = f"pfc_dot{blk}_w{WB}x{XB}_shallow"
    print(f"=== FABRICATE {name} INTO titan.gguf (a byte edit) ===", flush=True)
    t0 = time.time()
    c = TC.Circuit(blk * WB + blk * XB)
    W = [[c.IN[i * WB + k] for k in range(WB)] for i in range(blk)]
    X = [[c.IN[blk * WB + i * XB + k] for k in range(XB)] for i in range(blk)]
    outs = build_shallow_dot(c, W, X, blk, WB)
    t_build = time.time() - t0
    dep = depth_of(c, outs)
    print(f"  built: {len(c.ga):,} gates, DEPTH {dep} gate-delays, n_in {c.n_in}  ({t_build:.1f}s to construct)", flush=True)

    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    random.seed(11); ok = 0; N = 40
    lo, hi = -(1 << (WB - 1)), (1 << (WB - 1)) - 1
    for _ in range(N):
        wq = [random.randint(lo, hi) for _ in range(blk)]
        xq = [random.randint(-128, 127) for _ in range(blk)]
        bits = []
        for i in range(blk): bits += [(wq[i] >> k) & 1 for k in range(WB)]
        for i in range(blk): bits += [(xq[i] >> k) & 1 for k in range(XB)]
        o = TC.ripple(cd, bits)
        u = sum(o[i] << i for i in range(len(outs)))
        v = u - (1 << 32) if u >= (1 << 31) else u
        if v == sum(wq[i] * xq[i] for i in range(blk)): ok += 1
    print(f"  byte-exact vs integer dot (fabrication-time verify): {ok}/{N}", flush=True)
    if ok != N:
        print("  ✗ NOT byte-exact — refusing to store. Nothing was written.", flush=True); return 1

    t0 = time.time(); info = TC.store(name, c, outs); t_store = time.time() - t0
    print(f"  ★ STORED: offset {info['offset']:,} in {info['tensor']}, {info['bytes']:,} bytes", flush=True)
    print(f"  ★ THE BYTE EDIT TOOK {t_store:.2f}s — that is fabrication. The circuit now lives IN THE BINARY,", flush=True)
    print(f"    addressable, permanent, reversible. Nothing is held in host RAM or any cache.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
