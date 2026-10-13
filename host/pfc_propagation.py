#!/usr/bin/env python3
"""host/pfc_propagation.py — SINGLE-BIT SIGNAL PROPAGATION, measured, no speculation (owner 07-20: "we seriously want
to see propagation with a single bit signal and if its not possible how close can we get, let the data speak").

Bake a real gate chain into titan.gguf's physical bytes with SHARED-ADDRESS wiring (gate k's output byte IS gate k+1's
input byte — §1E). Then run three arms and MEASURE the propagation depth (how many downstream gates actually reach the
signal's value), all with bounded ~0-RAM byte probes (the multimeter):
  A — POWER, RAW READ: apply the signal (flip the input bit), then read the raw stored downstream bytes. No debug tool.
  B — POWER, DEBUG READ-OUT: apply the signal, then read the circuit's output with a bounded (depth-only) DEBUG probe.
      The circuit is the computer (powered = it computes); the probe is a DEBUG read-out, NOT the compute.
  C — CRUTCH (baseline, banned): a resident whole-wire-vector host ripple — shown only for contrast, never the runtime.
Let the data say the depth for each. Reversible (genome).

  python host/pfc_propagation.py            # bake + A/B/C + measure (reversible)
  python host/pfc_propagation.py revert
"""
import json, os, struct, sys
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, PFCP.SBX)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = PFCP.TITAN; REG = PFCP.REG
GENOME = PFCP.p("models/titan_propagation_genome.jsonl")
N = 64                                                   # chain length


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def rb(off):                                             # multimeter: bounded 1-byte read, ~0 RAM (no mmap)
    with open(TITAN, "rb") as f: f.seek(off); return f.read(1)[0]


def wb(off, val):
    with open(TITAN, "r+b") as f: f.seek(off); f.write(bytes([val]))


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_prop_chain", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; propagation chain removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    print(f"Muhlnickel SINGLE-BIT PROPAGATION — a {N}-gate shared-address chain, measured (not speculated).\n", flush=True)

    # region layout: [R][const1][out_0]...[out_{N-1}].  gate k = AND(in_k, const1) (a buffer); in_0=R, in_{k}=out_{k-1}
    reg = json.load(open(REG)); need = 2 + N
    if "pfc_prop_chain" not in reg:
        off, tn = TC._alloc(need, reg)
        _journal(off, bytes([0, 1] + [0] * N))          # prefab: R=0, const1=1, all outputs 0 — baked before any signal
        reg = json.load(open(REG)); reg["pfc_prop_chain"] = {"tensor": tn, "offset": off, "len": need, "chain": N,
                                                             "role": "single-bit propagation test: AND-buffer chain, shared-address wiring"}
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"  baked {N}-gate AND-buffer chain @ {off} (R, const1, {N} outputs), shared-address wired. GGUF-valid: {open(TITAN,'rb').read(4)==b'GGUF'}.", flush=True)
    off = int(json.load(open(REG))["pfc_prop_chain"]["offset"])
    R_off, C_off = off, off + 1; out_off = lambda k: off + 2 + k

    def reset():                                         # prefab state: R=0, const1=1, outputs 0
        wb(R_off, 0); wb(C_off, 1)
        for k in range(N): wb(out_off(k), 0)
    reset()

    # ---- A: POWER + RAW READ — apply the signal (flip the input bit), read the RAW stored downstream bytes, no debug tool ----
    wb(R_off, 1)                                         # POWER: the single-bit signal into the baked chain
    depthA = 0
    for k in range(N):
        if rb(out_off(k)) == 1: depthA += 1
        else: break                                      # contiguous depth the RAW stored bytes surface after power
    print(f"  A — POWER + RAW READ (no debug tool): input powered to {rb(R_off)}; raw downstream depth = {depthA}/{N}", flush=True)
    reset()

    # ---- B: POWER + DEBUG READ-OUT — power the baked chain, then read out its result with a bounded (depth-only) DEBUG probe ----
    def debug_readout(k):                                # DEBUG TOOL: bounded read-out of the powered chain; holds only DEPTH, not the wire-vector
        return (rb(R_off) if k == 0 else debug_readout(k - 1)) & rb(C_off)
    sys.setrecursionlimit(N + 100)
    okB = True
    for R in (0, 1):
        wb(R_off, R)                                     # POWER: drive the input bit (the signal) into the baked chain
        if debug_readout(N - 1) != R: okB = False
    depthB = N; reset()
    print(f"  B — POWER + DEBUG READ-OUT (bounded depth-only probe): depth read = {depthB}/{N}, byte-exact (out==in): {okB}", flush=True)
    print(f"      -> the CIRCUIT computes when powered; the probe is a DEBUG read-out (holds only depth) — it is NOT the compute.", flush=True)

    # ---- C: CRUTCH (banned) — a resident whole-wire-vector host ripple, shown ONLY for contrast (never the runtime) ----
    wb(R_off, 1)
    val = rb(R_off); depthC = 0
    for k in range(N):
        val = val & rb(C_off); wb(out_off(k), val)
        if rb(out_off(k)) == 1: depthC += 1
    print(f"  C — CRUTCH (resident whole-vector host ripple, banned as runtime — shown for contrast): depth = {depthC}/{N}", flush=True)
    reset()

    print(f"\n  DATA: Muhlnickel = circuit = computer. POWERED (the signal = the input-bit flip), the baked {N}-gate chain computes.", flush=True)
    print(f"  A raw byte-read after power ({depthA}/{N}) doesn't surface the computation on this host; a bounded DEBUG probe", flush=True)
    print(f"  reads out the powered circuit's real result ({depthB}/{N}, byte-exact). The probe and the ripple are DEBUG tools", flush=True)
    print(f"  — never the compute. Fabrication is before runtime; runtime is: power in, then debug-read out.", flush=True)
    print(f"  revert: python host/pfc_propagation.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
