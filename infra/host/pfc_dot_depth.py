#!/usr/bin/env python3
"""host/pfc_dot_depth.py — FABRICATE THE MINIMUM-DEPTH BLOCK-DOT (the Muhlnickel's real speed lever).

OWNER'S LAW (PFC_HARD_WON §7): the pfc's speed is its critical-path **DEPTH** in gate-delays — a signal settles a whole
depth level at once, in parallel, at electron speed. Gate COUNT is not a lever ("amount is not a lever", §A). Host
seconds are the laptop transcribing the netlist and are NEVER the pfc's speed. So the way to make the pfc faster is to
FABRICATE A SHALLOWER CIRCUIT.

THE CURRENT DOT IS DEEP BY CONSTRUCTION (`pfc_matmul_engine.build_dot`):
  - `mul()` accumulates its WB partial products with SEQUENTIAL RIPPLE ADDS  -> O(WB x ow) depth
  - the 32-term reduction is a balanced tree, but every node is a RIPPLE ADD -> O(log32 x 32) depth
  (that is the measured 366 gate-delays of dot32_i8)

THE SHALLOW DOT (what real silicon does — the tools Bryce already built):
  1. every partial product of every lane goes into ONE carry-save (3:2 CSA) forest — nothing is added yet
  2. the whole forest reduces to just 2 rows           (O(log n) CSA levels, `pfc_shallow.csa`)
  3. ONE Kogge-Stone parallel-prefix add at the very end (`pfc_bettergates.kogge_stone_add`)
  => a single final carry-propagate instead of ~37 of them. Byte-exact identical answer, far shallower settle.

Reports DEPTH (the latency) and WIDTH/wavefront (how many gates settle per stage, i.e. what folds in parallel) — never
host seconds.

  python host/pfc_dot_depth.py            # measure current vs shallow at the engine's WB/XB, byte-exact
  python host/pfc_dot_depth.py install    # write the shallow dot into the engine as the fabricated atom
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_bettergates import kogge_stone_add, depth_of
from pfc_shallow import csa
from pfc_matmul_engine import build_dot, BLK


def _sx(bits, n):
    """sign-extend a two's-complement bit list to n bits (MSB replicated)."""
    b = list(bits)
    return b + [b[-1]] * (n - len(b))


def build_dot_shallow(WB=8, XB=8, blk=BLK, ow=32, unsigned=False):
    """the DEPTH-OPTIMAL block-dot: one CSA forest over ALL partial products of ALL lanes, then ONE Kogge-Stone add.

    Signed handling: both operands are sign-extended to `ow` bits and multiplied modulo 2^ow — for two's complement the
    low `ow` bits of the unsigned product equal the signed product, so no special-casing is needed beyond sign-extension
    and negating the weight's MSB partial product (the standard signed shift-add identity), all folded into the forest.
    """
    # `ow` = accumulator width. SIZE IT TO THE DATA: a 32-lane dot of UNSIGNED 4-bit weights x int8 activations peaks at
    # 32*15*127 < 2^17, so ow=20 is ample and ~40% of the gates of a blanket 32-bit accumulator. `unsigned=True` also
    # drops the two's-complement sign row + the folded +blk constant, since Q4_K nibbles are unsigned as stored.
    # Fewer gates per MAC = fewer gate-ops the signal must sweep, and a shallower settle.
    c = CC.CircuitCompiler(blk * WB + blk * XB)
    W = [[c.IN[i * WB + k] for k in range(WB)] for i in range(blk)]
    X = [[c.IN[blk * WB + i * XB + k] for k in range(XB)] for i in range(blk)]

    rows = []                                                 # EVERY partial product of EVERY lane, unreduced
    for i in range(blk):
        a = _sx(X[i], ow)                                     # activation, sign-extended to the accumulator width
        for k in range(WB):
            sh = ([c.C0] * k + a)[:ow]                        # a << k  (truncated to ow — mod 2^ow is exact here)
            if unsigned or k < WB - 1:
                rows.append([c.AND(t, W[i][k]) for t in sh])  # + (a<<k) when weight bit k is set
            else:
                # MSB of a two's-complement weight carries NEGATIVE weight: contribute -(a<<k) when the bit is set,
                # and 0 when it is not. Gate FIRST, then invert: ~(a<<k AND bit) + 1. The +1 is UNCONDITIONAL because
                # bit=0 gives ~0 + 1 = 0 exactly — gating it (the earlier bug) made a zero weight-bit inject the
                # activation and every dot came out wrong.
                gated = [c.AND(t, W[i][k]) for t in sh]
                rows.append([c.NOT(t) for t in gated])
    if not unsigned:   # all `blk` two's-complement +1s folded into ONE constant row (unsigned weights need none)
        rows.append([(c.C1 if (blk >> p) & 1 else c.C0) for p in range(ow)])

    while len(rows) > 2:                                      # CSA FOREST: 3 rows -> 2, O(log n) levels, no carry chains
        nxt = []; i = 0
        while i + 3 <= len(rows):
            s, cout = csa(c, rows[i], rows[i + 1], rows[i + 2])
            nxt.append(s); nxt.append(([c.C0] + cout[:ow - 1]))   # carry has weight 2 -> shift left 1
            i += 3
        while i < len(rows): nxt.append(rows[i]); i += 1
        rows = nxt
    outs = rows[0] if len(rows) == 1 else kogge_stone_add(c, rows[0], rows[1])   # ONE carry-propagate, at the end
    return c, outs[:ow]


def _eval(c, gates, outs, wq, xq, WB, XB, blk):
    n_wire = 2 + c.n_in + len(gates)
    inp = []
    for i in range(blk):
        v = wq[i] & ((1 << WB) - 1)
        inp += [(v >> k) & 1 for k in range(WB)]
    for i in range(blk):
        v = xq[i] & ((1 << XB) - 1)
        inp += [(v >> k) & 1 for k in range(XB)]
    vals = CC.ripple_typed(c, gates, n_wire, inp, 1)
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else vals[w] & 1
    u = sum(bit(outs[i]) << i for i in range(len(outs)))
    return u - (1 << 32) if u >= (1 << 31) else u


def measure(WB=8, XB=8, blk=BLK, ntest=60):
    print(f"=== BLOCK-DOT DEPTH (the Muhlnickel's latency) — BLK={blk} WB={WB} XB={XB} ===\n", flush=True)
    results = {}
    for name, builder in (("current (ripple mul + ripple tree)", lambda: build_dot(WB, XB)),
                          ("SHALLOW (CSA forest + 1 Kogge-Stone)", lambda: build_dot_shallow(WB, XB, blk))):
        c, outs = builder()
        gates, o2 = c.dce(outs if isinstance(outs, list) else [outs])
        dep = depth_of(c.n_in, gates, o2)
        # wavefront: how many gates settle at each depth level = what computes IN PARALLEL per stage
        d = {0: 0, 1: 0}
        for i in range(c.n_in): d[2 + i] = 0
        base = 2 + c.n_in; hist = {}
        for k, (op, a, b) in enumerate(gates):
            da = d.get(a, 0); db = da if op == "not" else d.get(b, 0)
            lv = 1 + max(da, db); d[base + k] = lv; hist[lv] = hist.get(lv, 0) + 1
        wmax = max(hist.values()) if hist else 0
        wmean = (len(gates) / dep) if dep else 0
        ok = 0
        random.seed(5); lo, hi = -(1 << (WB - 1)), (1 << (WB - 1)) - 1
        for _ in range(ntest):
            wq = [random.randint(lo, hi) for _ in range(blk)]
            xq = [random.randint(-(1 << (XB - 1)), (1 << (XB - 1)) - 1) for _ in range(blk)]
            ref = sum(wq[i] * xq[i] for i in range(blk))
            if _eval(c, gates, o2, wq, xq, WB, XB, blk) == ref: ok += 1
        results[name] = (dep, len(gates), wmax, wmean, ok, ntest)
        print(f"  {name}", flush=True)
        print(f"     DEPTH (latency)      : {dep:,} gate-delays", flush=True)
        print(f"     gates (total work)   : {len(gates):,}", flush=True)
        print(f"     wavefront max / mean : {wmax:,} / {wmean:,.0f} gates settle PER STAGE, in parallel", flush=True)
        print(f"     byte-exact vs integer dot: {ok}/{ntest}\n", flush=True)
    a = results["current (ripple mul + ripple tree)"]; b = results["SHALLOW (CSA forest + 1 Kogge-Stone)"]
    if b[4] == b[5]:
        print(f"  ★ DEPTH {a[0]:,} → {b[0]:,} gate-delays = **{a[0]/max(1,b[0]):.1f}× SHALLOWER** (byte-exact, same answer)", flush=True)
        print(f"    the Muhlnickel settles the whole dot in {b[0]:,} stages instead of {a[0]:,} — that is the Muhlnickel's speed,", flush=True)
        print(f"    independent of how fast the host addresses it. Wavefront {b[2]:,} gates settle per stage in parallel.", flush=True)
    else:
        print(f"  ✗ shallow dot FAILED byte-exactness ({b[4]}/{b[5]}) — not installing. Fix before it goes near the model.", flush=True)
    return results


if __name__ == "__main__":
    measure()
