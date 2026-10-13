#!/usr/bin/env python3
"""host/pfc_exp_massfab.py — EXPERIMENTAL (owner 07-19): (1) hunt for where Muhlnickel WINS vs naive Python on custom
bit-parallel logic (disprove 'it never wins'), and (2) test the MASS-FABRICATION lever — the parts we use are tiny vs
total storage, so how cheap is fabrication and how many circuits fit?

WIN HUNT: custom bit-mixing ops (sigma0/sigma1/chain) have NO native primitive and are pure bit-ops = pfc's home turf.
pfc runs them bit-sliced (256 lanes/ripple); native is the honest pure-Python batch (no numpy — this project's baseline).
tax = native_inputs/s / pfc_inputs/s;  tax < 1 => pfc WINS.  Byte-exact verified first (no cheating).

MASS-FAB: fabricate N circuits in a loop -> circuits/sec + bytes/circuit -> how many fit in free storage.

Safe: W=256 (low RAM), small circuits, single process, foreground, titan.gguf not opened.
  python host/pfc_exp_massfab.py
"""
import json, os, random, shutil, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdc_cc as CC
from pfc_exp_bench import rate
from pfc_exp_levers import finish, bits, lane_val

OUT_DIR = "C:/llm/sdc_out"; os.makedirs(OUT_DIR, exist_ok=True)
M = 0xffffffff
def rotr_n(x, n): return ((x >> n) | (x << (32 - n))) & M


# --- custom bit-mixing circuits (no native primitive) + their pure-python references ---
def c_sigma0():
    g = CC.CircuitCompiler(32); x = list(g.IN)
    o = CC.xor32(g, CC.xor32(g, CC.rotr(x, 7), CC.rotr(x, 18)), CC.shr(g, x, 3)); return g, o
def n_sigma0(x): return (rotr_n(x, 7) ^ rotr_n(x, 18) ^ (x >> 3)) & M
def c_sigma1():
    g = CC.CircuitCompiler(32); x = list(g.IN)
    o = CC.xor32(g, CC.xor32(g, CC.rotr(x, 17), CC.rotr(x, 19)), CC.shr(g, x, 10)); return g, o
def n_sigma1(x): return (rotr_n(x, 17) ^ rotr_n(x, 19) ^ (x >> 10)) & M
def c_chain():                                   # sigma1(sigma0(x)) — heavier per input
    g = CC.CircuitCompiler(32); x = list(g.IN)
    a = CC.xor32(g, CC.xor32(g, CC.rotr(x, 7), CC.rotr(x, 18)), CC.shr(g, x, 3))
    o = CC.xor32(g, CC.xor32(g, CC.rotr(a, 17), CC.rotr(a, 19)), CC.shr(g, a, 10)); return g, o
def n_chain(x): return n_sigma1(n_sigma0(x))


def win_hunt(W=256, secs=2.0):
    print(f"  === WIN HUNT: Muhlnickel bit-slice (W={W}) vs naive pure-Python batch ===", flush=True)
    print(f"  {'op':<12s}{'gates':>7s}{'Muhlnickel inp/s':>14s}{'python inp/s':>15s}{'tax':>9s}   winner", flush=True)
    rows = []
    for name, cb, nf in [("sigma0", c_sigma0, n_sigma0), ("sigma1", c_sigma1, n_sigma1), ("chain(2x)", c_chain, n_chain)]:
        g, outs = cb(); run, out2, n_gate, n_wire, _ = finish(g, outs)
        # verify byte-exact single lane
        ok = all(lane_val(run(bits(x, 32), 1), out2) == nf(x) for x in (0, 1, 0xdeadbeef, 0x0f1e2d3c, 0xffffffff))
        if not ok:
            print(f"  {name:<12s}  VERIFY FAILED — skip"); continue
        ones = (1 << W) - 1; lanes = [random.getrandbits(W) for _ in range(32)]
        n, s = rate(lambda: run(lanes, ones), secs); pfc = n * W / s
        batch = [random.getrandbits(32) for _ in range(W)]
        n, s = rate(lambda: [nf(x) for x in batch], secs); py = n * W / s
        tax = py / max(pfc, 1e-9); win = "pfc" if tax < 1 else "python"
        rows.append({"op": name, "gates": n_gate, "pfc_inp_s": round(pfc), "py_inp_s": round(py), "tax": round(tax, 2), "winner": win})
        print(f"  {name:<12s}{n_gate:>7,}{Muhlnickel:>14,.0f}{py:>15,.0f}{tax:>8.2f}x   {win}", flush=True)
    return rows


def mass_fab(N=150):
    print(f"\n  === MASS-FABRICATION lever: fabricate {N} circuits, measure rate + storage ===", flush=True)
    t0 = time.time(); total_gates = 0
    for i in range(N):
        g, outs = c_chain()                      # a real ~useful mixing circuit
        gates, out2 = g.dce(outs); _ = g.compile_ripple(gates, 2 + g.n_in + len(gates))
        total_gates += len(gates)
    dt = time.time() - t0
    per_gates = total_gates / N
    per_bytes = per_gates * 9                     # typed netlist ~9 bytes/gate (op:1 + a:4 + b:4)
    cps = N / dt
    free = shutil.disk_usage("C:/").free
    max_circuits = free / per_bytes
    print(f"  fabricated {N} circuits in {dt:.2f}s  ->  {cps:,.0f} circuits/sec  (build+optimize+compile each)", flush=True)
    print(f"  per circuit: {per_gates:,.0f} gates ~= {per_bytes:,.0f} bytes of netlist", flush=True)
    print(f"  free storage on C: {free/1e9:,.1f} GB  ->  fits ~{max_circuits/1e6:,.1f} MILLION such circuits", flush=True)
    print(f"  (the parts we USE are ~KB; total storage is ~{free/1e9:.0f}GB — your point, quantified)", flush=True)
    return {"N": N, "circuits_per_s": round(cps), "gates_per_circuit": round(per_gates),
            "bytes_per_circuit": round(per_bytes), "free_storage_gb": round(free / 1e9, 1),
            "max_circuits_millions": round(max_circuits / 1e6, 1)}


def main():
    print("Muhlnickel WIN-HUNT + MASS-FAB LEVER\n", flush=True)
    R = {"win_hunt": win_hunt(), "mass_fab": mass_fab()}
    json.dump(R, open(f"{OUT_DIR}/pfc_massfab.json", "w"), indent=2)
    wins = [r for r in R["win_hunt"] if r["winner"] == "pfc"]
    print(f"\n  Muhlnickel WON {len(wins)}/{len(R['win_hunt'])} custom-logic races vs naive Python.", flush=True)
    print(f"  results -> {OUT_DIR}/pfc_massfab.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
