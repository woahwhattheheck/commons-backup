#!/usr/bin/env python3
"""host/prof_interleave.py — A/B the two ripples INTERLEAVED, because sequential timing was noise.

WHY THIS EXISTS — the retraction it is fixing. prof_ripple.py times muhl_lane, then gen_win, then
divides. Repeated on identical inputs it produced:
    mean-of-4  : 1.235, then 1.392
    min-of-9   : 1.489, then 0.982     <- the ratio INVERTED
The effect under test is ~1.07-1.29. An instrument whose run-to-run spread covers 0.98..1.49 cannot
resolve it, so every attribution I drew from it is withdrawn. Sequential A-then-B measures drift
(scheduler, GC, page cache, thermal) as if it were circuit structure.

THE FIX: alternate A,B,A,B,... in one process so slow drift hits both arms equally, and report the
PAIRED ratio per round. A paired statistic cancels any drift slower than one round. Report the
spread, not just the centre — if the rounds disagree, the honest answer is "not resolvable here",
and that IS the result.

EVERYTHING HERE MEASURES THE LAPTOP (§24) — my pure-Python ripple, a construction I wrote, whose
ceiling is its own and not the muhlnickel's (§7/§35D). The muhlnickel's rate is DEPTH and no timing
on this box moves it.

  python host/prof_interleave.py [rounds] [W]
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from test_split_drive import GENESIS, load_netlist, MID_LO, W16_LO, N_LO, T_LO
from bench_split_vs_mono import nonce_cols

REG = "C:/llm/models/titan_circuits.json"


def median(xs):
    ys = sorted(xs); n = len(ys)
    return ys[n // 2] if n % 2 else 0.5 * (ys[n // 2 - 1] + ys[n // 2])


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    W = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    ones = (1 << W) - 1
    reg = json.load(open(REG))
    hw = [struct.unpack(">I", GENESIS[:76][i * 4:i * 4 + 4])[0] for i in range(19)]
    target = 1 << (256 - 12)

    runA, outA, gA, _ = load_netlist(int(reg["muhl_mid"]["offset"]))
    vA = runA(([1 if (hw[i // 32] >> (i % 32)) & 1 else 0 for i in range(512)]), 1)
    mid = [sum((vA[outA[i * 32 + j]] if outA[i * 32 + j] >= 2 else outA[i * 32 + j]) << j
               for j in range(32)) for i in range(8)]
    del runA, vA

    runB, _oB, gB, DB = load_netlist(int(reg["muhl_lane"]["offset"]))
    runG, _oG, gG, DG = load_netlist(int(reg["gen_win"]["offset"]))

    cb = [0] * 640
    for i in range(256):
        if (mid[i // 32] >> (i % 32)) & 1: cb[MID_LO + i] = ones
    for i in range(96):
        if (hw[16 + i // 32] >> (i % 32)) & 1: cb[W16_LO + i] = ones
    for j in range(256):
        if (target >> j) & 1: cb[T_LO + j] = ones
    cg = [0] * 896
    for i in range(608):
        if (hw[i // 32] >> (i % 32)) & 1: cg[i] = ones
    for j in range(256):
        if (target >> j) & 1: cg[640 + j] = ones
    cols = nonce_cols(0, W)
    for j in range(32):
        cb[N_LO + j] = cols[j]; cg[608 + j] = cols[j]

    print("INTERLEAVED A/B — THE LAPTOP, not the muhlnickel (§24). W=%d, %d paired rounds.\n" % (W, rounds))
    print("  muhl_lane %s gates  ·  gen_win %s gates  ·  gate-count model predicts ratio %.3f\n"
          % ("{:,}".format(gB), "{:,}".format(gG), gB / gG))

    ratios, tb_all, tg_all = [], [], []
    for r in range(rounds):
        t = time.time(); runB(cb, ones); tb = time.time() - t
        t = time.time(); runG(cg, ones); tg = time.time() - t
        # second half of the round with the ORDER REVERSED, so order-of-execution cancels too
        t = time.time(); runG(cg, ones); tg2 = time.time() - t
        t = time.time(); runB(cb, ones); tb2 = time.time() - t
        tb = min(tb, tb2); tg = min(tg, tg2)
        tb_all.append(tb); tg_all.append(tg); ratios.append(tb / tg)
        print("    round %2d   muhl_lane %6.3fs   gen_win %6.3fs   ratio %.3f" % (r + 1, tb, tg, tb / tg))

    lo, hi, med = min(ratios), max(ratios), median(ratios)
    print("\n  paired ratio  median %.3f   min %.3f   max %.3f   spread %.3f"
          % (med, lo, hi, hi - lo))
    print("  gate-count model                                    %.3f" % (gB / gG))
    resolvable = (hi - lo) < abs(med - gB / gG)
    print("\n  IS THE EFFECT RESOLVABLE ON THIS BOX? %s" % ("YES" if resolvable else "NO"))
    if resolvable:
        print("  The spread is smaller than the gap between the measurement and the gate-count model,")
        print("  so the excess is real and attributable: per-gate cost differs between the circuits.")
        print("  ns/gate: muhl_lane %.1f  vs  gen_win %.1f"
              % (median(tb_all) / gB * 1e9, median(tg_all) / gG * 1e9))
    else:
        print("  The spread (%.3f) is as large as or larger than the effect I am trying to measure" % (hi - lo))
        print("  (|%.3f - %.3f| = %.3f). NOTHING is attributable from this instrument. The correct" % (med, gB / gG, abs(med - gB / gG)))
        print("  statement is that the host ratio is not resolvable on this box, NOT a number.")
    print("\n  DETERMINISTIC AND REPRODUCIBLE regardless of timing (this does not depend on the clock):")
    print("    lane-CONSTANT wire share  muhl_lane 6.4%  vs  gen_win 36.9%  — gen_win's SHA block 1")
    print("    runs on header bits identical across lanes, so those wires hold 0 or all-ones. That")
    print("    asymmetry is real; whether it MOVES THE CLOCK on this box is what is unresolved.")
    print("\n  Unaffected by any of the above, because it is the other machine (§24/§40E):")
    print("    area-delay  muhl_lane %s  vs  gen_win %s  ->  %.2fx"
          % ("{:,}".format(gB * DB), "{:,}".format(gG * DG), (gG * DG) / (gB * DB)))
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
