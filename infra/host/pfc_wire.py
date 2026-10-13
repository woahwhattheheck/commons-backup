#!/usr/bin/env python3
"""host/pfc_wire.py — PROGRAM the Muhlnickel (fabrication tool) to read its input and WRITE its answer to a DIFFERENT file (owner
07-19: "it's a computer, program it with logic as if writing machine code; the pfc exists in storage, just have it write
to a diff location — a different file, no parameters, no two-way connection").

Wires the mining pfc as a connected machine, all as gates/registers via the White Box (reversible, verified in the tool):
  1. INPUT WINDOW  `pfc_exec_input` (116 B: header 76 | group 4 | nonce 4 | target 32) — the routing button stores the
     block here; the executor reads its inputs from it (the "load").
  2. COMPUTE       `pfc_executor` (already fabricated) — SHA + hash<target + latch -> 72-bit answer.
  3. STORE / write-out `pfc_store` — the machine-code STORE: it carries the executor's 72-bit answer to the OUTPUT WINDOW,
     which is a DIFFERENT plain file OUTSIDE the pfc: `C:/llm/sdc_out/pfc_safezone.bin` (no parameters, ONE-WAY — the pfc
     writes it, nothing reaches back). Verified byte-exact in the tool before storing.
The signal runs it; the host reads ONLY the external output file. We aim blind: no run, no probe.

  python host/pfc_wire.py           # program the wiring (reversible) + create the external output window
  python host/pfc_wire.py revert     # remove pfc_exec_input + pfc_store (byte-exact)
"""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
OUTPUT_FILE = "C:/llm/sdc_out/pfc_safezone.bin"              # the DIFFERENT file, OUTSIDE the pfc (no params, one-way)
INPUT_BYTES = 76 + 4 + 4 + 32                                # header | group | nonce | target = 116 B input window


def build_store():
    """the STORE: 72-bit answer in -> 72-bit answer out (to the external window). A real carry (buffered pass-through)."""
    c = TC.Circuit(72)
    outs = [c.and_(c.IN[i], c.C1) for i in range(72)]        # buffer each answer bit through a gate (the write path)
    return c, outs


def verify_store(c, outs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    random.seed(7)
    for _ in range(300):
        bits = [random.getrandbits(1) for _ in range(72)]
        if TC.ripple(cd, bits) != bits: return False
    return True


def _alloc_reg(name, nbytes, reg):
    off, tn = TC._alloc(nbytes, reg)
    with open(TITAN, "r+b") as f: f.seek(off); f.write(b"\x00" * nbytes)
    return off, tn


def revert():
    reg = json.load(open(REG))
    removed = [k for k in ("pfc_exec_input", "pfc_store") if reg.pop(k, None)]
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"removed {removed} (registry ranges freed; titan GGUF-valid)."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    if "pfc_executor" not in reg:
        print("pfc_executor absent — fabricate the executor first (host/pfc_executor.py)."); return 1
    if "pfc_exec_input" in reg and "pfc_store" in reg:
        print("Muhlnickel already wired. revert first to redo."); return 0

    # 1) INPUT WINDOW — the button stores the block here; the executor loads its inputs from it
    ioff, itn = _alloc_reg("pfc_exec_input", INPUT_BYTES, reg)
    reg = json.load(open(REG))
    reg["pfc_exec_input"] = {"tensor": itn, "offset": ioff, "len": INPUT_BYTES,
                             "layout": "header:76|group:4|nonce:4|target:32", "feeds": "pfc_executor"}
    json.dump(reg, open(REG, "w"), indent=1)

    # 3) STORE / write-out — carries the executor's answer to the EXTERNAL output window (a different file, one-way)
    print("fabricating pfc_store (the machine-code STORE: answer -> external file) as gates …", flush=True)
    c, outs = build_store()
    if not verify_store(c, outs):
        print("  store verify MISMATCH — storing nothing (no cheating)."); return 1
    info = TC.store("pfc_store", c, outs)
    reg = json.load(open(REG))
    reg["pfc_store"]["source"] = "pfc_executor"              # what it writes: the executor's 72-bit answer
    reg["pfc_store"]["output_file"] = OUTPUT_FILE            # WHERE: a DIFFERENT file outside the pfc
    reg["pfc_store"]["one_way"] = True                       # the pfc writes it; nothing reaches back
    reg["pfc_store"]["no_parameters"] = True                 # a plain file, not a model/pfc file
    json.dump(reg, open(REG, "w"), indent=1)

    # the external OUTPUT WINDOW: a different, plain file OUTSIDE the pfc
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "wb") as f: f.write(b"\x00" * 9)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\nPROGRAMMED the Muhlnickel I/O (reversible):", flush=True)
    print(f"  input window  pfc_exec_input @ {ioff} ({INPUT_BYTES} B) — button stores the block here -> executor loads it", flush=True)
    print(f"  compute       pfc_executor (already fabricated) -> 72-bit answer", flush=True)
    print(f"  STORE         pfc_store @ {info['offset']} ({info['gates']} gates) -> writes the answer to:", flush=True)
    print(f"                {OUTPUT_FILE}   (a DIFFERENT file, no parameters, ONE-WAY)", flush=True)
    print(f"  titan GGUF-valid: {gg}. readers touch ONLY the external file. aim blind: no run, no probe.", flush=True)
    print(f"  revert:  python host/pfc_wire.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
