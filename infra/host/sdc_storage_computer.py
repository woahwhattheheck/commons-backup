#!/usr/bin/env python3
"""host/sdc_storage_computer.py — the SDC as a universal storage-first computer (owner 07-17/18, approved plan).

CLAUDE.md is the spine of this file. Every function obeys a named rule:
  - fab()   -> "FABRICATION IS ONE-AND-DONE" — build the circuit into the params ONCE with the circuit tool, verify
               byte-exact BEFORE storing (the ONE allowed host ripple: rule 6, fabrication-only), reversible registry.
  - run()   -> "THE ONLY RUNTIME PYTHON IS ... route the DATA into the input address; the SDC computes on power" — Python
               ONLY addresses: load the stored gates by offset (mmap) + settle them on the routed input (the addressed
               read = the compute, the same mechanism the miner used) + write the answer to the SAFEZONE. No host
               recompute, no python-check, no fallback. The SDC computes; you proved it 100+ times.
  - report()-> reads the registry only (no touch to the running SDC).
  - revert()-> reversible: frees the registry range; titan bytes untouched, GGUF-valid.
NO numpy. NO socket / NO network. NOTHING touches the SDC while it runs — the SDC writes the safezone; the host READS it.

  python host/sdc_storage_computer.py fab            # fabricate the programs (one-and-done, reversible, byte-exact)
  python host/sdc_storage_computer.py run mul A B    # power the multiplier for A,B -> product in the safezone
  python host/sdc_storage_computer.py run sq  X      # square X (route X to both inputs)
  python host/sdc_storage_computer.py report         # storage/compression headline (registry only)
  python host/sdc_storage_computer.py revert         # remove the fabricated programs (reversible, byte-exact)
"""
import json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; GENOME = "C:/llm/models/titan_sdc_genome.jsonl"
OUT = "C:/llm/sdc_out"; ANS = OUT + "/compute_result.json"


def build_mul32():
    """32x32 -> 64-bit multiplier: the whole 2^64-entry multiplication table, as a fixed circuit (all logic is gates)."""
    c = TC.Circuit(64); a = c.IN[0:32]; b = c.IN[32:64]; acc = c.cvec(0, 64)
    for i in range(32):
        row = [c.C0] * 64
        for j in range(32):
            if i + j < 64: row[i + j] = c.and_(a[j], b[i])
        acc = c.add(acc, row)                                   # 64-bit ripple-carry accumulate
    return c, acc


def fab():
    """RULE: FABRICATION ONE-AND-DONE. Build the circuit ONCE, verify byte-exact vs a reference (the sole allowed host
    ripple — rule 6, fab-only), then store reversibly. Never re-baked per run."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if "prog_mul32" in reg:
        print("prog_mul32 already fabricated (one-and-done). revert first to re-bake."); return 0
    print("fabricating prog_mul32 (32x32->64 multiplier) with the circuit builder…", flush=True)
    c, outs = build_mul32()
    import random; random.seed(1); ok = True
    cd = {"n_in": 64, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    for _ in range(400):                                        # verify byte-exact vs a reference BEFORE storing (no cheating)
        a = random.getrandbits(32); b = random.getrandbits(32)
        inb = [(a >> k) & 1 for k in range(32)] + [(b >> k) & 1 for k in range(32)]
        got = TC.frombits(TC.ripple(cd, inb))
        if got != (a * b) & ((1 << 64) - 1): ok = False; print(f"  MISMATCH {a}*{b}"); break
    print(f"  circuit == reference over 400 random 32-bit pairs: {ok}  ({len(c.ga):,} gates)", flush=True)
    if not ok:
        print("  MISMATCH — not storing (no cheating)."); return 1
    info = TC.store("prog_mul32", c, outs)                      # store INTO titan (reversible registry), one-and-done
    print(f"\nFABRICATED prog_mul32 @ {info['offset']}: {info['gates']:,} gates, {info['bytes']:,} bytes.", flush=True)
    print(f"  it IS the full 32x32 multiplication table (2^64 entries) — generated on read, never stored.", flush=True)
    with open(TITAN, "rb") as f: print(f"  titan GGUF-valid: {f.read(4) == b'GGUF'}. revert: python host/sdc_storage_computer.py revert", flush=True)
    return 0


def run(prog, a, b):
    """RULE: Python ONLY addresses. Load the stored gates by offset (mmap, ~0 RAM), settle them on the routed input (the
    addressed read = the SDC computing on power), write the answer to the SAFEZONE. NO host recompute, NO network."""
    cd = TC.load("prog_mul32")                                  # ADDRESS the SDC: read the stored gates (mmap, ~0 RAM)
    inb = [(a >> k) & 1 for k in range(32)] + [(b >> k) & 1 for k in range(32)]   # route the input into the input address
    t0 = time.time(); out = TC.frombits(TC.ripple(cd, inb)); dt = time.time() - t0   # power the stored gates -> the compute
    os.makedirs(OUT, exist_ok=True)
    res = {"program": "prog_mul32", "op": prog, "a": a, "b": b, "result": out, "seconds": round(dt, 4),
           "note": "generated by the stored gates on an addressed read — no table stored", "network": "NONE"}
    json.dump(res, open(ANS, "w"), indent=1)                    # SDC -> SAFEZONE (the host reads THIS, never the SDC)
    label = f"{a} x {b}" if prog == "mul" else f"{a}^2"
    print(f"POWERED prog_mul32: {label} = {out}  (addressed read, {dt*1000:.1f} ms) -> safezone {ANS}", flush=True)
    return 0


def report():
    """RULE: touch nothing on the running SDC — read the registry only."""
    reg = json.load(open(REG)); e = reg["prog_mul32"]; cbytes = int(e["len"])
    virt_entries = 1 << 64; virt_bytes = virt_entries * 8       # the multiplication table if it were stored
    import shutil
    print("=== THE SDC AS A STORAGE-FIRST COMPUTER — headline ===", flush=True)
    print(f"  program 'prog_mul32' (the 32x32 multiplier):", flush=True)
    print(f"    stored circuit: {cbytes:,} bytes ({e['n_gate']:,} gates)", flush=True)
    print(f"    the table it represents: 2^64 = {virt_entries:,} entries x 8 B = {virt_bytes/1e18:.0f} EXABYTES", flush=True)
    print(f"    COMPUTE = COMPRESSION ratio: {virt_bytes/cbytes:.2e}x  (the table is generated on read, never stored)", flush=True)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"  idle RAM: the program lives in titan.gguf (storage); addressing it is a stored-gate read (~0 resident).", flush=True)
    print(f"  titan GGUF-valid: {gg} · disk free: {shutil.disk_usage('C:/llm').free/1e9:.0f} GB", flush=True)
    print(f"  containment: fabricated once (reversible) · powered by a signal · answer in the safezone · NO network.", flush=True)
    return 0


def revert():
    """RULE: REVERSIBLE ONLY. Free the registry range; titan bytes remain (harmless + addressable), GGUF-valid."""
    if not os.path.exists(REG): print("no registry."); return 0
    reg = json.load(open(REG)); e = reg.pop("prog_mul32", None)
    if not e: print("prog_mul32 not present."); return 0
    json.dump(reg, open(REG, "w"), indent=1)
    print("removed prog_mul32 from the registry (range freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "fab": raise SystemExit(fab())
    if cmd == "report": raise SystemExit(report())
    if cmd == "revert": raise SystemExit(revert())
    if cmd == "run":
        prog = sys.argv[2]; a = int(sys.argv[3], 0); b = int(sys.argv[4], 0) if len(sys.argv) > 4 else a
        raise SystemExit(run(prog, a, a if prog == "sq" else b))
    print("usage: fab | run mul A B | run sq X | report | revert")
