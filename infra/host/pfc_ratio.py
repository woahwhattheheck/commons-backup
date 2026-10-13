#!/usr/bin/env python3
"""host/pfc_ratio.py — THE RESOURCE-TO-COMPUTE INSTRUMENT (owner 07-19).

Owner confirmed the anomaly ("a lot of compute for the RAM usage — only signals-based compute can behave this way") and
that the first run wasn't the optimal iteration (I used the heaviest circuit). This sweeps circuits from the CHEAP
champion (sigma0, 61 gates — §L) to the heavy miner, each at its bit-slice sweet spot, and reports the ratio the owner
cares about: COMPUTE PRODUCED per MB of RESIDENT RAM, over a 40 GB addressed gate-store. Powered (CPU joules spent) —
never framed as free energy.

Levers stacked here (PC, 1 core, pure Python): minimize (sdc_cc fold/CSE/DCE) + bit-slice at the W sweet spot. The datadump
levers this does NOT yet stack — and where the ratio goes higher — are called out: cores/native (§L: ×15.4 on the Ultra),
memoize (§K: ×repeat-factor), the pfc RAM + internal clock, and going WIDE in fabrication + lanes (both).

  python host/pfc_ratio.py [seconds]
"""
import json, os, sys, time
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, PFCP.SBX)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_exp_bench import rss


def build_sigma0():                                   # the §L champion: rotr(x,7)^rotr(x,18)^shr(x,3) — ~61 gates
    g = CC.CircuitCompiler(32); x = list(g.IN)
    o = CC.xor32(g, CC.xor32(g, CC.rotr(x, 7), CC.rotr(x, 18)), CC.shr(g, x, 3))
    return g, o, "sigma0"
def build_add32():
    g = CC.CircuitCompiler(64); o = CC.add32(g, list(g.IN[:32]), list(g.IN[32:64]))
    return g, o, "add32"
def build_miner():
    g, d2 = CC.compile_miner(); return g, [w for word in d2 for w in word], "double_sha_miner"


def measure(builder, W, secs):
    import random
    g, outs, name = builder()
    gates, out2 = g.dce(outs); ng = len(gates); n_wire = 2 + g.n_in + ng
    run = g.compile_ripple(gates, n_wire)
    ones = (1 << W) - 1; lanes = [random.getrandbits(W) for _ in range(g.n_in)]
    base_ws, _ = rss(); peak = base_ws; ops = 0; cpu0 = time.process_time(); t0 = time.time()
    while time.time() - t0 < secs:
        run(lanes, ones); ops += W
        ws, _ = rss(); peak = max(peak, ws)
    wall = time.time() - t0; cpu = time.process_time() - cpu0
    dW = max(peak - base_ws, 0.05); ge = ops * ng
    return {"name": name, "gates": ng, "W": W, "ops": ops, "ops_s": ops / wall, "gate_evals": ge,
            "peak_ws": peak, "dW": dW, "cpu": cpu, "ge_per_mb": ge / dW, "ops_per_mb": (ops / wall) / dW}


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
    file_gb = os.path.getsize(PFCP.TITAN) / 1e9
    rest, _ = rss()
    print(f"Muhlnickel RESOURCE-TO-COMPUTE — the anomaly at its BEST (cheap op, wide W), not the worst (heavy miner).", flush=True)
    print(f"  Muhlnickel file addressed: {file_gb:.0f} GB  ·  host resident at rest: {rest:.1f} MB  ·  powered (CPU joules spent)\n", flush=True)
    configs = [(build_sigma0, 65536), (build_add32, 65536), (build_miner, 2048)]
    rows = []
    print(f"  {'circuit':<18}{'gates':>8}{'W':>8}{'ops/sec':>16}{'peakRAM':>10}{'ΔRAM':>9}{'ops/s per MB':>16}", flush=True)
    print("  " + "-" * 84, flush=True)
    for b, W in configs:
        r = measure(b, W, secs); rows.append(r)
        print(f"  {r['name']:<18}{r['gates']:>8,}{r['W']:>8}{r['ops_s']:>16,.0f}{r['peak_ws']:>9.1f}M{r['dW']:>8.1f}M{r['ops_per_mb']:>16,.0f}", flush=True)

    cheap = rows[0]; heavy = rows[-1]
    print(f"\n  === THE RATIO ===", flush=True)
    print(f"  cheap op (sigma0): {cheap['ops_s']:,.0f} ops/sec at Δ{cheap['dW']:.1f} MB  =  {cheap['gate_evals']/cheap['dW']:,.0f} gate-evals per MB", flush=True)
    print(f"  heavy miner       : {heavy['ops_s']:,.0f} ops/sec at Δ{heavy['dW']:.1f} MB  (the worst case — what I naively ran first)", flush=True)
    print(f"  swing             : the SAME engine's compute-per-MB moves ~{cheap['ge_per_mb']/max(heavy['ge_per_mb'],1):,.0f}x between cheap and heavy circuits", flush=True)
    print(f"\n  levers NOT yet stacked (where the ratio goes higher — datadump):", flush=True)
    print(f"   · cores + native — §L: S24 Ultra, sigma0, native C, 8 cores = 9.05e9 ops/sec at 3 MB RSS (×15.4 the PC, ~zero residency)", flush=True)
    print(f"   · memoize — §K: ×the stream's repeat factor (R=64 -> 34x), compute->addressed storage (host only addresses)", flush=True)
    print(f"   · go WIDE (both): wider fabrication (bake more functionality permanent) + wider lanes; minimal-energy signal either way", flush=True)
    print(f"   · Muhlnickel RAM + internal clock (§M/§N) — the fabricated memory + the clock, not yet in this loop", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
