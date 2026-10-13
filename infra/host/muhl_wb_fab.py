#!/usr/bin/env python3
"""host/muhl_wb_fab.py — ONE-TIME fabrication of the White Box forward-pass I/O components.

Same FPGA-modular shape as sdc_os_fab.py / sdc_fwd_fab.py, but sized for wb_fwd (the aimed-training
forward block: K=3, OUT=2, VB=3, YB=8 → 27 input bits, 16 output bits, 2,448 gates, depth 66).
The compute circuit (`wb_fwd`) is already fabricated; this adds the I/O registers AROUND it so at
runtime the training loop writes input + fires power, and the circuit does the forward pass IN
STORAGE — no TC.ripple.

  - wb_input    (9 bytes) — where the training loop places its request: [x0:1][x1:1][x2:1][w0:1]...[w5:1]
        each value is 3-bit (VB=3, range 0..7), stored in the low 3 bits of its byte
  - wb_answer   (3 bytes) — where the circuit freezes its result: [status:1][y0:1][y1:1]
        each y is 8-bit (YB=8, range 0..255)
  - wb_receiver (gates)   — begins on power (the addressed read the training loop fires)

  python host/muhl_wb_fab.py           # fabricate the I/O components once
  python host/muhl_wb_fab.py revert    # remove them (registry ranges freed; titan bytes were unused padding)

Owner justification (07-16): "the SDC can RUN a model (a forward pass is arithmetic, arithmetic is gates)"
Pattern: sdc_os_fab.py (owner 07-18) — "adds the I/O registers AROUND [the compute], so at runtime
the host only routes the request + fires power, and the SDC does the routing/compute/write-out IN STORAGE"
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
NAMES = ["wb_input", "wb_answer", "wb_receiver"]


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
    if "wb_fwd" not in reg:
        print("wb_fwd (the forward-pass circuit) is not fabricated — run sdc_whitebox_train.py first."); return 1
    if all(n in reg for n in NAMES):
        print("wb_fwd I/O already fabricated (one-and-done). revert to redo."); return 0
    _alloc_reg("wb_input", 9)
    _alloc_reg("wb_answer", 3)
    reg = json.load(open(REG))
    if "wb_receiver" not in reg:
        rc = TC.Circuit(1); begin = rc.not_(rc.not_(rc.C1)); ready = rc.and_(begin, rc.IN[0])
        TC.store("wb_receiver", rc, [begin, ready])
    reg = json.load(open(REG))
    print("FABRICATED the White Box forward-pass I/O components (permanent, reversible):", flush=True)
    for n in NAMES: print(f"  {n:12s} @ {reg[n]['offset']}", flush=True)
    e = reg["wb_fwd"]
    print(f"  wb_fwd (forward block) @ {e['offset']} — already fabricated ({e.get('n_gate', '?')} gates, depth {e.get('depth', '?')})", flush=True)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.", flush=True)
    print("=> next: bake the composed circuit (receiver + input-read + wb_fwd + answer-write),", flush=True)
    print("   then replace TC.ripple in sdc_whitebox_train.py:run() with write-fire-read.", flush=True)
    return 0


def revert():
    reg = json.load(open(REG)); removed = [n for n in NAMES if reg.pop(n, None)]
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"removed {removed} (registry ranges freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if (len(sys.argv) > 1 and sys.argv[1] == "revert") else fab())
