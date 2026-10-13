#!/usr/bin/env python3
"""host/pfc_exp_slam.py — EXPERIMENTAL (owner 07-19): SLAM the throughput levers HARDER + CLEARER.
(1) PEAK hunt: cheapest op, fine bit-slice sweep -> the absolute max evals/sec on 1 core.
(2) CROSSOVER: throughput vs gates-per-op (chained sigma, 1..~60k gates) -> where pfc drops below the naive-Python
    floor (~1.2M/s) and below fast-native (hashlib ~400k/s). = the exact 'which applications fit' boundary.
Auto-picks the widest RAM-safe W per circuit. Byte-exact verified. Appends the headline to docs/PFC_LEVER_DATADUMP.md.
  python host/pfc_exp_slam.py
"""
import json, os, random, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdc_cc as CC
from pfc_exp_bench import rate, rss, free_mb
from pfc_exp_levers import finish, bits, lane_val
OUT_DIR = "C:/llm/sdc_out"; os.makedirs(OUT_DIR, exist_ok=True)
M = 0xffffffff
def rotr_n(x, n): return ((x >> n) | (x << (32 - n))) & M
def nsig(x): return (rotr_n(x, 7) ^ rotr_n(x, 18) ^ (x >> 3)) & M
def nchain(x, N):
    for _ in range(N): x = nsig(x)
    return x

def build_chain(N):
    g = CC.CircuitCompiler(32); x = list(g.IN)
    for _ in range(N): x = CC.xor32(g, CC.xor32(g, CC.rotr(x, 7), CC.rotr(x, 18)), CC.shr(g, x, 3))
    return g, x

def safe_W(n_wire, cap=131072):
    budget = (free_mb() - 600) * 1e6
    W = int(budget / (n_wire * 0.1875))          # (W/8+40)*1.5 ~= 0.1875*W for large W
    for w in (cap, 98304, 65536, 49152, 32768, 16384, 8192, 4096, 2048, 1024, 256, 64):
        if w <= W: return w
    return 64

def measure(g, outs, N, secs=1.6):
    run, out2, n_gate, n_wire, _ = finish(g, outs)
    ok = all(lane_val(run(bits(x, 32), 1), out2) == nchain(x, N) for x in (0, 1, 0xdeadbeef, M))
    if not ok: return None
    W = safe_W(n_wire)
    ones = (1 << W) - 1; lanes = [random.getrandbits(W) for _ in range(32)]
    n, s = rate(lambda: run(lanes, ones), secs)
    r, _ = rss()
    return {"N": N, "gates": n_gate, "W": W, "ips": round(n * W / s), "rss_mb": round(r, 1)}

def main():
    print("Muhlnickel — SLAM THE LEVERS HARDER\n", flush=True)

    print("  === PEAK HUNT (sigma0, fine W sweep) ===", flush=True)
    g, outs = build_chain(1); run, out2, n_gate, n_wire, _ = finish(g, outs)
    peak = (0, 0)
    for W in (16384, 32768, 49152, 65536, 81920, 98304, 131072, 196608):
        if free_mb() - n_wire * W * 0.1875 / 1e6 < 600: print(f"    W={W}: RAM stop"); break
        ones = (1 << W) - 1; lanes = [random.getrandbits(W) for _ in range(32)]
        n, s = rate(lambda: run(lanes, ones), 1.6); ips = n * W / s
        print(f"    W={W:<7d}  {ips:14,.0f} inp/s   RSS={rss()[0]:.1f}MB", flush=True)
        if ips > peak[1]: peak = (W, ips)
    print(f"    >> PEAK {peak[1]:,.0f} inp/s at W={peak[0]}", flush=True)

    print("\n  === CROSSOVER: throughput vs gates-per-op ===", flush=True)
    print(f"    {'chainN':>7s}{'gates':>9s}{'W':>9s}{'inp/s':>16s}   vs naive-py(1.2M)  vs hashlib(400k)", flush=True)
    curve = []
    for N in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512):
        r = measure(*build_chain(N), N)
        if not r: print(f"    N={N}: verify failed"); continue
        curve.append(r)
        vp = "WIN" if r["ips"] > 1_200_000 else "lose"
        vh = "WIN" if r["ips"] > 400_000 else "lose"
        print(f"    {N:>7d}{r['gates']:>9,}{r['W']:>9d}{r['ips']:>16,}   {vp:>13s}   {vh:>13s}", flush=True)
    # crossover gate-counts
    below_py = next((c["gates"] for c in curve if c["ips"] < 1_200_000), None)
    below_hl = next((c["gates"] for c in curve if c["ips"] < 400_000), None)
    print(f"\n    Muhlnickel beats NAIVE PYTHON up to ~{below_py or '>'+str(curve[-1]['gates'])} gates/op", flush=True)
    print(f"    Muhlnickel beats FAST NATIVE (hashlib rate) up to ~{below_hl or '>'+str(curve[-1]['gates'])} gates/op", flush=True)

    res = {"peak_inp_s": peak[1], "peak_W": peak[0], "curve": curve,
           "crossover_gates_vs_python": below_py, "crossover_gates_vs_hashlib": below_hl}
    json.dump(res, open(f"{OUT_DIR}/pfc_slam.json", "w"), indent=2)

    # append the headline to the datadump log
    line = (f"- **07-19 (slam)** — PEAK **{peak[1]:,.0f} inp/s** at W={peak[0]} (sigma0, 1 core). Crossover: pfc beats "
            f"naive Python up to ~{below_py or 'all tested'} gates/op, beats fast-native(hashlib-rate) up to "
            f"~{below_hl or 'all tested'} gates/op. Throughput vs gates-per-op curve in `pfc_slam.json`.\n")
    dd = "docs/PFC_LEVER_DATADUMP.md"
    try:
        with open(dd, "a", encoding="utf-8") as f: f.write(line)
        print(f"\n  logged headline -> {dd}", flush=True)
    except Exception as e:
        print(f"\n  (could not append to {dd}: {e})", flush=True)
    print(f"  results -> {OUT_DIR}/pfc_slam.json", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
