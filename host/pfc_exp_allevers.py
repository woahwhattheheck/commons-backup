#!/usr/bin/env python3
"""host/pfc_exp_allevers.py — EXPERIMENTAL (owner 07-19): PUSH ALL LEVERS AT ONCE.

Two lever families (from SDC_SWARM.md + this session's measurements) — they are DIFFERENT AXES:
  THROUGHPUT (evaluation rate): bit-slicing · circuit minimization (fold/CSE/DCE) · type/locality · no-native-primitive.
  CAPACITY   (addressable lanes, ~0 storage): files × receivers × shared-vector fold × bit-address(1 bit/lane) ×
             winner-only × device-federation × MLC × pipelining.

Stack THROUGHPUT levers on the best-case op and sweep bit-width to its real PEAK (RAM-guarded). Stack CAPACITY levers as a
calculation on this box's free storage. Then state the honest combined picture: capacity is astronomical & ~free;
throughput is fixed & CPU-bound; they CONVERGE only on parallel hardware (FPGA evaluates all addressed lanes at once).

Safe: tiny circuit => wide bit-slice is still low RAM; live RAM guard; single process; titan.gguf not opened.
  python host/pfc_exp_allevers.py
"""
import json, os, random, shutil, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdc_cc as CC
from pfc_exp_bench import rate, rss, free_mb
from pfc_exp_levers import finish, bits, lane_val
OUT_DIR = "C:/llm/sdc_out"; os.makedirs(OUT_DIR, exist_ok=True)
M = 0xffffffff
def rotr_n(x, n): return ((x >> n) | (x << (32 - n))) & M


def build_sigma0():   # minimized custom bit-op = the throughput best-case (fold/CSE/DCE applied by finish())
    g = CC.CircuitCompiler(32); x = list(g.IN)
    o = CC.xor32(g, CC.xor32(g, CC.rotr(x, 7), CC.rotr(x, 18)), CC.shr(g, x, 3)); return g, o
def nat_sigma0(x): return (rotr_n(x, 7) ^ rotr_n(x, 18) ^ (x >> 3)) & M


def throughput_stack():
    print("  === THROUGHPUT stack: minimized custom op, bit-slice swept to PEAK ===", flush=True)
    g, outs = build_sigma0(); run, out2, n_gate, n_wire, _ = finish(g, outs)
    ok = all(lane_val(run(bits(x, 32), 1), out2) == nat_sigma0(x) for x in (0, 1, 0xdeadbeef, M))
    print(f"    circuit: {n_gate} gates (minimized), {n_wire} wires, byte-exact={ok}", flush=True)
    print(f"     W          RSSMB      inp/s", flush=True)
    best = (0, 0)
    for W in (64, 256, 1024, 4096, 16384, 65536, 262144):
        proj = n_wire * (W / 8 + 40) * 1.5 / 1e6
        if free_mb() - proj < 600:
            print(f"     W={W}: RAM-guard stop"); break
        ones = (1 << W) - 1; lanes = [random.getrandbits(W) for _ in range(32)]
        n, s = rate(lambda: run(lanes, ones), 2.0); ips = n * W / s
        r, _ = rss()
        print(f"     {W:<8d}   {r:7.1f}   {ips:14,.0f}", flush=True)
        if ips > best[1]: best = (W, ips)
    # native pure-python baseline for the same op
    batch = [random.getrandbits(32) for _ in range(4096)]
    n, s = rate(lambda: [nat_sigma0(x) for x in batch], 1.5); py = n * 4096 / s
    print(f"    PEAK throughput: {best[1]:,.0f} inp/s at W={best[0]}  ·  naive python {py:,.0f} inp/s  ·  win {py and best[1]/py:,.0f}x", flush=True)
    return {"peak_inp_s": round(best[1]), "peak_W": best[0], "python_inp_s": round(py),
            "win_x": round(best[1] / max(py, 1e-9), 1), "n_gate": n_gate}


def capacity_stack():
    print("\n  === CAPACITY stack: all folds, on this box's free storage ===", flush=True)
    free = shutil.disk_usage("C:/").free
    # per-lane storage cost under each fold (from SDC_SWARM.md, measured)
    tiers = [("copy-vector (5 MB/lane grp)", 19100.0), ("shared-vector fold (~13 B/lane)", 13.0),
             ("bit-address fold (1 bit/lane)", 1 / 8.0), ("winner-only (store only winners)", None)]
    rows = []
    print(f"    free storage on C: {free/1e9:,.1f} GB", flush=True)
    for name, bpl in tiers:
        if bpl is None:
            lanes = float("inf"); s = "~unbounded by storage (bounded by #circuits) — the 10^15 tier"
        else:
            lanes = free / bpl; s = f"{lanes:,.3e} addressable lanes"
        rows.append({"fold": name, "bytes_per_lane": bpl, "lanes": None if bpl is None else round(lanes)})
        print(f"    {name:<34s} -> {s}", flush=True)
    return {"free_gb": round(free / 1e9, 1), "tiers": rows}


def main():
    print("Muhlnickel — PUSH ALL LEVERS AT ONCE\n", flush=True)
    t = throughput_stack(); c = capacity_stack()
    # the honest combined picture
    peak = t["peak_inp_s"]
    dense_lanes = c["tiers"][2]["lanes"]     # bit-address fold
    yrs = dense_lanes / max(peak, 1e-9) / 31557600 if peak else float("inf")
    print("\n  === COMBINED (honest) ===", flush=True)
    print(f"  THROUGHPUT peak (all throughput levers stacked, 1 CPU core): {peak:,.0f} lane-evals/sec.", flush=True)
    print(f"  CAPACITY   ceiling (bit-address fold, this box): {dense_lanes:,.3e} addressable lanes.", flush=True)
    print(f"  -> the capacity is astronomical and ~free; the CPU throughput is FIXED. To EVALUATE the addressed", flush=True)
    print(f"     lanes at this peak would take ~{yrs:,.3e} years. Addressing a lane != computing it.", flush=True)
    print(f"  -> the two axes are ORTHOGONAL on a CPU. They CONVERGE only on parallel hardware (SIMD/GPU/FPGA),", flush=True)
    print(f"     where all addressed lanes evaluate at once — there, capacity BECOMES throughput.", flush=True)
    json.dump({"throughput": t, "capacity": c, "eval_years_for_capacity": yrs},
              open(f"{OUT_DIR}/pfc_allevers.json", "w"), indent=2)
    print(f"\n  results -> {OUT_DIR}/pfc_allevers.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
