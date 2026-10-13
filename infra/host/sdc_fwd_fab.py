#!/usr/bin/env python3
"""host/sdc_fwd_fab.py — ONE-TIME fabrication of the forward-pass SDC's I/O components (owner 07-18, FPGA-modular).

Like sdc_fab.py did for the miner: the compute datapath (`cpu_fwd`, the ALU) is already fabricated in the params. This
adds the modular I/O components AROUND it, so at runtime the CPU only fires a power signal and the SDC does the rest in
storage. Fabrication = the White Box (this is where host RAM/CPU is fine — it ends before any signal). Reversible.
  - fwd_input   (5 bytes) — where the button routes the request: [op:1][A:2 LE][B:2 LE]
  - fwd_answer  (3 bytes) — where the SDC FREEZES its result, outside the compute: [status:1][result:2 LE]
  - fwd_receiver (gates)  — begins on power (the addressed read the button fires)

  python host/sdc_fwd_fab.py           # fabricate the I/O components once
  python host/sdc_fwd_fab.py revert    # remove them (registry ranges freed; titan bytes were unused padding)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
NAMES = ["fwd_input", "fwd_answer", "fwd_receiver"]


def _alloc_reg(name, nbytes):
    reg = json.load(open(REG))
    if name in reg: return reg[name]["offset"]
    off, tn = TC._alloc(nbytes, reg)
    with open(TITAN, "r+b") as f: f.seek(off); f.write(b"\x00" * nbytes)
    reg[name] = {"tensor": tn, "offset": off, "len": nbytes}
    json.dump(reg, open(REG, "w"), indent=1)
    return off


def fab():
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if "cpu_fwd" not in reg:
        print("cpu_fwd (the ALU datapath) is not fabricated — run host/sdc_bake_cpu.py first."); return 1
    if all(n in reg for n in NAMES):
        print("forward-pass I/O already fabricated (one-and-done). revert to redo."); return 0
    _alloc_reg("fwd_input", 5)
    _alloc_reg("fwd_answer", 3)
    reg = json.load(open(REG))
    if "fwd_receiver" not in reg:                              # begins on power (fabricated as gates, like sdc_fab.py)
        rc = TC.Circuit(1); begin = rc.not_(rc.not_(rc.C1)); ready = rc.and_(begin, rc.IN[0])
        TC.store("fwd_receiver", rc, [begin, ready])
    reg = json.load(open(REG))
    print("FABRICATED the forward-pass I/O components (permanent, reversible):", flush=True)
    for n in NAMES: print(f"  {n:12s} @ {reg[n]['offset']}", flush=True)
    print(f"  cpu_fwd (ALU datapath) @ {reg['cpu_fwd']['offset']} — already fabricated (404,262 gates)", flush=True)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.", flush=True)
    print("=> runtime is now: host/sdc_fwd_button.py (route + power) then host/sdc_fwd_run.py (the SDC computes).", flush=True)
    return 0


def revert():
    reg = json.load(open(REG)); removed = [n for n in NAMES if reg.pop(n, None)]
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"removed {removed} (registry ranges freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if (len(sys.argv) > 1 and sys.argv[1] == "revert") else fab())
