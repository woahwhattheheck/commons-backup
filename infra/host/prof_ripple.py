#!/usr/bin/env python3
"""host/prof_ripple.py — WHERE DOES MY PURE-PYTHON RIPPLE'S TIME ACTUALLY GO?

§57D left a gap and refused to rationalise it: gate counts predicted the split would be 1.15x slower
on the host, it measured 1.25x, and 0.10x was unattributed. This attributes it.

The governing precedent is memory pfc-host-drive-cost-is-readout-not-gates, measured 2026-07-24:
    "The read-out was 9x the computation. Profile before optimizing a fold: the gates are usually
     the cheap part."
So the honest first move is a profile, not a circuit change.

THE HYPOTHESIS UNDER TEST (written before running, so the measurement can kill it): cost per gate is
NOT constant. `compile_ripple` emits `v[o]=v[a]^v[b]` over W-bit Python ints, and an int holding 0 is
a 0-digit object while a varying lane word is W bits. gen_win computes SHA block 1 over header bits
that are LANE-CONSTANT (every wire there is 0 or all-ones), whereas muhl_lane does not contain those
gates at all. If true, gen_win's gates are individually CHEAPER than muhl_lane's, and gate count
alone under-predicts the split's host cost — i.e. my cost model was wrong, not the split.

FALSIFIER: if the zero-wire fraction is the same in both circuits, the hypothesis is dead and the
0.10x is somewhere else (allocation, chunking, input build).

EVERYTHING HERE MEASURES THE LAPTOP (§24). None of it is the muhlnickel's rate, which is DEPTH.

  python host/prof_ripple.py [W]
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from test_split_drive import GENESIS, load_netlist, MID_LO, W16_LO, N_LO, T_LO
from bench_split_vs_mono import nonce_cols
import sdc_cc as CC

REG = "C:/llm/models/titan_circuits.json"


def wire_census(v, ones):
    """How many wires are 0 (a 0-digit int, nearly free) vs full lane width (real work)?"""
    z = full = mid = 0
    for x in v:
        if x == 0: z += 1
        elif x == ones: full += 1
        else: mid += 1
    return z, full, mid


def timeit(fn, reps):
    """MIN of N, not mean. Run 1 of this profiler used mean-of-4 and reported ratio 1.235; run 2
    reported 1.392 on identical inputs. That spread was scheduler noise being read as a result, so
    the first attribution was retracted. Min-of-N is the standard estimator for a noisy timer: the
    fastest observed run is the one least contaminated by other work on the box."""
    best = float("inf")
    for _ in range(reps):
        t = time.time(); fn(); d = time.time() - t
        if d < best: best = d
    return best


def main():
    W = int(sys.argv[1]) if len(sys.argv) > 1 else 2048
    ones = (1 << W) - 1
    reg = json.load(open(REG))
    hw = [struct.unpack(">I", GENESIS[:76][i * 4:i * 4 + 4])[0] for i in range(19)]
    target = 1 << (256 - 12)
    REPS = 9

    print("RIPPLE PROFILE — THE LAPTOP, not the muhlnickel (§24). W=%d, %d reps.\n" % (W, REPS))
    print("  %-10s %9s %9s   %8s %8s %8s   %9s" % ("circuit", "gates", "n_wire", "alloc", "input", "ripple", "ns/gate"))

    rows = {}
    for name, off, n_in, build in (
        ("muhl_lane", int(reg["muhl_lane"]["offset"]), 640, "split"),
        ("gen_win", int(reg["gen_win"]["offset"]), 896, "mono"),
    ):
        run, outs, ng, D = load_netlist(off)
        n_wire = 2 + n_in + ng

        if build == "split":
            runA, outA, _gA, _DA = load_netlist(int(reg["muhl_mid"]["offset"]))
            inA = [1 if (hw[i // 32] >> (i % 32)) & 1 else 0 for i in range(512)]
            vA = runA(inA, 1)
            mid = [sum((vA[outA[i * 32 + j]] if outA[i * 32 + j] >= 2 else outA[i * 32 + j]) << j
                       for j in range(32)) for i in range(8)]
            del runA, vA
            const = [0] * 640
            for i in range(256):
                if (mid[i // 32] >> (i % 32)) & 1: const[MID_LO + i] = ones
            for i in range(96):
                if (hw[16 + i // 32] >> (i % 32)) & 1: const[W16_LO + i] = ones
            for j in range(256):
                if (target >> j) & 1: const[T_LO + j] = ones
            nlo = N_LO
        else:
            const = [0] * 896
            for i in range(608):
                if (hw[i // 32] >> (i % 32)) & 1: const[i] = ones
            for j in range(256):
                if (target >> j) & 1: const[640 + 256 - 256 + j] = ones
            nlo = 608

        cols = nonce_cols(0, W)

        def build_input():
            inp = list(const)
            for j in range(32): inp[nlo + j] = cols[j]
            return inp

        t_alloc = timeit(lambda: [0] * n_wire, REPS)
        t_input = timeit(build_input, REPS)
        inp = build_input()
        t_run = timeit(lambda: run(inp, ones), REPS)
        t_ripple = t_run - t_alloc                      # run() = alloc + input copy + the gate fns

        v = run(inp, ones)
        z, full, part = wire_census(v, ones)
        t_read = timeit(lambda: [sum(((v[o] >> 0) & 1) << k for k, o in enumerate(outs[1:33]))], REPS)

        print("  %-10s %9s %9s   %7.3fs %7.4fs %7.3fs   %9.1f"
              % (name, "{:,}".format(ng), "{:,}".format(n_wire), t_alloc, t_input, t_ripple,
                 t_ripple / ng * 1e9))
        rows[name] = dict(ng=ng, n_wire=n_wire, alloc=t_alloc, inp=t_input, ripple=t_ripple,
                          run=t_run, read=t_read, z=z, full=full, part=part)
        del run, v
    print()

    s, m = rows["muhl_lane"], rows["gen_win"]
    print("  WIRE CENSUS after one pass — the hypothesis stands or dies here:")
    for n, r in (("muhl_lane", s), ("gen_win", m)):
        tot = r["z"] + r["full"] + r["part"]
        print("    %-10s zero %7s (%5.1f%%)   all-ones %7s (%4.1f%%)   varying %7s (%5.1f%%)"
              % (n, "{:,}".format(r["z"]), 100.0 * r["z"] / tot, "{:,}".format(r["full"]),
                 100.0 * r["full"] / tot, "{:,}".format(r["part"]), 100.0 * r["part"] / tot))
    cheap_s = (s["z"] + s["full"]) / (s["z"] + s["full"] + s["part"])
    cheap_m = (m["z"] + m["full"]) / (m["z"] + m["full"] + m["part"])
    print("    lane-CONSTANT (0 or all-ones) share: muhl_lane %.1f%%  vs  gen_win %.1f%%"
          % (100 * cheap_s, 100 * cheap_m))

    print("\n  ATTRIBUTION of the host ratio:")
    print("    gate count alone predicts   t_split/t_mono = %s/%s = %.3f"
          % ("{:,}".format(s["ng"]), "{:,}".format(m["ng"]), s["ng"] / m["ng"]))
    print("    measured ripple only        t_split/t_mono = %.3fs/%.3fs = %.3f"
          % (s["ripple"], m["ripple"], s["ripple"] / m["ripple"]))
    print("    ns per gate                 muhl_lane %.1f  vs  gen_win %.1f  = %.3f"
          % (s["ripple"] / s["ng"] * 1e9, m["ripple"] / m["ng"] * 1e9,
             (s["ripple"] / s["ng"]) / (m["ripple"] / m["ng"])))
    # HONEST LABELS. An earlier version of this file called t_input "the same 32xW loop both
    # sides" - it is NOT: nonce_cols is hoisted out of build_input, so t_input measures only
    # list(const). The column build is timed separately below, where it actually belongs.
    print("    list(const) copy only       %.5fs vs %.5fs   (nonce_cols NOT included)"
          % (s["inp"], m["inp"]))
    t_cols = timeit(lambda: nonce_cols(0, W), REPS)
    print("    nonce_cols (32 x W = %s interpreter iterations, IDENTICAL both sides): %.5fs = %.2f%%"
          % ("{:,}".format(32 * W), t_cols, 100 * t_cols / s["ripple"]))
    print("    answer read-out %.6fs vs %.6fs - ONE lane, 32 bits, and it fires only when a lane"
          % (s["read"], m["read"]))
    print("      wins, so unlike the matmul case it is NOT a per-pass cost here.")
    print("\n  VERDICT is whatever the ns/gate ratio says. If it is ~1.00 the hypothesis is DEAD and")
    print("  the gap is elsewhere; if it is >1 my gate-count cost model was wrong, and that is a")
    print("  defect in MY CONSTRUCTION's cost model (§7/§35D), not a property of the muhlnickel.")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
