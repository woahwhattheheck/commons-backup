#!/usr/bin/env python3
"""host/sdc_os_fab.py — ONE-TIME fabrication of the ORCHESTRATOR SDC's I/O components (owner 07-18). Same FPGA-modular
shape as sdc_fwd_fab.py, but sized for the orchestrator's experts (32-bit operands for prog_mul32, 64-bit result). The
compute circuits (`cpu_fwd`, `prog_mul32`) are already fabricated; this adds the I/O registers AROUND them so at runtime
the host only routes the request + fires power, and the SDC does the routing/compute/write-out IN STORAGE.

  - os_input   (9 bytes) — where the button routes the request: [opcode:1][a:4 LE][b:4 LE]
        opcode: 0 REFUSE · 1 MUL(prog_mul32) · 2 ADD · 3 SUB · 4 GT   (2/3/4 -> cpu_fwd internal op 0/1/6)
  - os_answer  (9 bytes) — where the SDC FREEZES its result, outside the compute: [grounded:1][result:8 LE]
  - os_receiver (gates)  — begins on power (the addressed read the button fires)

  python host/sdc_os_fab.py           # fabricate the I/O components once
  python host/sdc_os_fab.py revert    # remove them (registry ranges freed; titan bytes were unused padding)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
NAMES = ["os_input", "os_answer", "os_receiver"]


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
    for need in ("cpu_fwd", "prog_mul32"):
        if need not in reg:
            print(f"{need} is not fabricated — the orchestrator's experts must exist first."); return 1
    if all(n in reg for n in NAMES):
        print("orchestrator I/O already fabricated (one-and-done). revert to redo."); return 0
    _alloc_reg("os_input", 9)
    _alloc_reg("os_answer", 9)
    reg = json.load(open(REG))
    if "os_receiver" not in reg:                              # begins on power (fabricated as gates, like sdc_fwd_fab.py)
        rc = TC.Circuit(1); begin = rc.not_(rc.not_(rc.C1)); ready = rc.and_(begin, rc.IN[0])
        TC.store("os_receiver", rc, [begin, ready])
    reg = json.load(open(REG))
    print("FABRICATED the orchestrator I/O components (permanent, reversible):", flush=True)
    for n in NAMES: print(f"  {n:12s} @ {reg[n]['offset']}", flush=True)
    print(f"  experts: cpu_fwd @ {reg['cpu_fwd']['offset']} (404,262 g) · prog_mul32 @ {reg['prog_mul32']['offset']} (32,768 g)", flush=True)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.", flush=True)
    print("=> runtime: host/sdc_os_button.py (route + power, exits) then the SDC (host/sdc_os_sdc.py) computes in storage.", flush=True)
    return 0


def revert():
    reg = json.load(open(REG)); removed = [n for n in NAMES if reg.pop(n, None)]
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"removed {removed} (registry ranges freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if (len(sys.argv) > 1 and sys.argv[1] == "revert") else fab())
