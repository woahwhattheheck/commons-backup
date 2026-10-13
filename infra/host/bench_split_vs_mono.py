#!/usr/bin/env python3
"""host/bench_split_vs_mono.py — HOST TRANSCRIPTION ONLY. Apples-to-apples: split vs monolith.

This measures THE LAPTOP, not the muhlnickel. §56C states the rule it obeys:
    "That rate is the LAPTOP transcribing and is never the muhlnickel's speed."
The muhlnickel's speed is DEPTH and is reported by test_split_drive.py's first column. Nothing here
may be quoted as the machine's performance, and the two are never summed (§24).

WHY IT EXISTS: §56C's documented 13,023 nonce/s came from the numpy bit-slice crutch
(`titan_sdc.ripple`). test_split_drive.py uses the pure-Python ripple. Comparing those two numbers
would measure THE CRUTCH, not the split. Same host, same ripple, same W, same block, back to back
is the only comparison that measures anything.

PREDICTION MADE BEFORE RUNNING (so the result can falsify it): per-lane host cost is GATES
transcribed. muhl_lane is 390,332 g vs gen_win's 339,009 g, so the host should get ~1.15x SLOWER
per lane even though the muhlnickel's area-delay gets 2.26x better. Two machines, opposite
directions — which is exactly what pfc_atom.py's header already says about dot32.

  python host/bench_split_vs_mono.py [passes] [W]
"""
import json, math, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_speed import analyze
from test_split_drive import GENESIS, load_netlist, MID_LO, W16_LO, N_LO, T_LO

REG = "C:/llm/models/titan_circuits.json"


def nonce_cols(base, W):
    cols = [0] * 32
    for j in range(32):
        c = 0
        for l in range(W):
            if ((base + l) >> j) & 1: c |= (1 << l)
        cols[j] = c
    return cols


def main():
    passes = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    W = int(sys.argv[2]) if len(sys.argv) > 2 else 2048
    ones = (1 << W) - 1
    reg = json.load(open(REG))
    hdr76 = GENESIS[:76]
    hw = [struct.unpack(">I", hdr76[i * 4:i * 4 + 4])[0] for i in range(19)]
    target = 1 << (256 - 12)          # deliberately hard: no lane wins, so both time the FULL pass

    print("HOST TRANSCRIPTION BENCH — the laptop. NOT the muhlnickel's rate (§56C).")
    print("  %d passes x W=%d lanes each, same host, same pure-Python ripple, same block.\n" % (passes, W))

    # ── SPLIT: A once (nonce-independent), then B per pass ────────────────────────────────────────
    runA, outA, gA, DA = load_netlist(int(reg["muhl_mid"]["offset"]))
    inA = [1 if (hw[i // 32] >> (i % 32)) & 1 else 0 for i in range(512)]
    tA = time.time(); vA = runA(inA, 1); tA = time.time() - tA
    mid = [sum((vA[outA[i * 32 + j]] if outA[i * 32 + j] >= 2 else outA[i * 32 + j]) << j
               for j in range(32)) for i in range(8)]

    runB, outB, gB, DB = load_netlist(int(reg["muhl_lane"]["offset"]))
    cb = [0] * 640
    for i in range(256):
        if (mid[i // 32] >> (i % 32)) & 1: cb[MID_LO + i] = ones
    for i in range(96):
        if (hw[16 + i // 32] >> (i % 32)) & 1: cb[W16_LO + i] = ones
    for j in range(256):
        if (target >> j) & 1: cb[T_LO + j] = ones
    t0 = time.time()
    for p in range(passes):
        inp = list(cb); cols = nonce_cols(p * W, W)
        for j in range(32): inp[N_LO + j] = cols[j]
        runB(inp, ones)
    t_split = time.time() - t0
    del runB, runA

    # ── MONOLITH: gen_win, every pass recomputes SHA block 1 that the split hoisted out ───────────
    gw = reg["gen_win"]
    from pfc_fab_win import load_gen_win, N_LO as G_N, T_LO as G_T
    runG, outG, meta = load_gen_win(int(gw["offset"]))
    gG = meta["n_gate"]
    MONO_D, _, _ = analyze(meta["n_in"], meta["n_wire"],
                           [(a, b) for (_o, a, b) in meta["gates"]], outG)   # measured, not quoted
    cg = [0] * 896
    for i in range(608):
        if (hw[i // 32] >> (i % 32)) & 1: cg[i] = ones
    for j in range(256):
        if (target >> j) & 1: cg[G_T + j] = ones
    t0 = time.time()
    for p in range(passes):
        inp = list(cg); cols = nonce_cols(p * W, W)
        for j in range(32): inp[G_N + j] = cols[j]
        runG(inp, ones)
    t_mono = time.time() - t0

    n = passes * W
    print("  SPLIT     muhl_mid %s g fired ONCE (%.3f s, amortised over every lane and pass)"
          % ("{:,}".format(gA), tA))
    print("            muhl_lane %s g x %d passes : %7.2f s  ->  %s nonce/s"
          % ("{:,}".format(gB), passes, t_split, "{:,}".format(int(n / t_split))))
    print("  MONOLITH  gen_win   %s g x %d passes : %7.2f s  ->  %s nonce/s"
          % ("{:,}".format(gG), passes, t_mono, "{:,}".format(int(n / t_mono))))
    r = t_mono / t_split
    print("\n  host ratio: %.2fx  (%s for the split)" % (r, "FASTER" if r > 1 else "SLOWER"))
    print("  gates transcribed per lane-pass: split %s vs monolith %s = %.2fx"
          % ("{:,}".format(gB), "{:,}".format(gG), gB / gG))
    print("\n  THE MUHLNICKEL COLUMN. Everything above this line measured MY PURE-PYTHON RIPPLE — a")
    print("  construction I wrote, whose ceiling is its own, not the machine's (§7/§35D). The figures")
    print("  below measure THE MUHLNICKEL: DEPTH and area, which no host timing can move. Never")
    print("  summed with the host column (§24/§40E).")
    print("    area-delay  muhl_lane %s  vs  gen_win %s  ->  %.2fx"
          % ("{:,}".format(gB * DB), "{:,}".format(gG * MONO_D), (gG * MONO_D) / (gB * DB)))
    print("    bank DEPTH (2^32 lanes, §40C law circuit_depth + 2*log2(W), settles 1):")
    print("      split    %s + %s = %s gate-delays" % ("{:,}".format(DA), "{:,}".format(DB + 64),
                                                       "{:,}".format(DA + DB + 64)))
    print("      monolith %s gate-delays" % "{:,}".format(MONO_D + 64))
    print("      -> %.2fx on end-to-end DEPTH. Both are muhlnickel, so chaining them is legitimate;"
          % ((MONO_D + 64) / (DA + DB + 64)))
    print("         what §24 forbids is mixing a muhlnickel figure with a host figure.")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
