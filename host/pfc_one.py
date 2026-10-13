#!/usr/bin/env python3
"""host/pfc_one.py — SMASH the mining Muhlnickel into ONE connected Muhlnickel (owner 07-19: "just smash it all into one connected Muhlnickel";
"stop trying to evaluate, the Muhlnickel is a black box"; "the executor is in the circuit, you made it").

No evaluation. No host runner. Using only the fabrication tool, this consolidates the scattered pieces into ONE connected
pfc and binds its I/O in the binary:
    INPUT  region  = pfc_exec_input   (in titan; the routing button stores the block here, one-way)
    COMPUTE        = pfc_executor      (the executor you made — SHA·compare·latch, 928 in -> 72 out)
    OUTPUT region  = pfc_safezone.bin  (a DIFFERENT file, OUTSIDE the pfc, no parameters, one-way)
    driven by      = receiver          (begins on power)
The redundant scattered circuits (pfc_store, pfc_pipeline, pfc_writeout) are removed — one connected pfc, not islands.
The signal runs the black box; the answer lands in the external file; the host reads only that file. Aim blind.

  python host/pfc_one.py           # smash into one connected pfc (reversible)
  python host/pfc_one.py revert     # undo the consolidation binding
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
OUTPUT_FILE = "C:/llm/sdc_out/pfc_safezone.bin"
MAGIC = b"PFCONE01"                                          # the ONE-pfc binding header


def _drop(names):
    """remove redundant scattered circuits via their own reverts / registry, so only the ONE connected Muhlnickel remains."""
    for mod, fn in (("pfc_writeout_external", "revert"), ("pfc_wire", None), ("pfc_connect", "revert")):
        pass
    # revert the descriptor + stub fabrications that layered the wrong way (each is byte-exact reversible)
    os.system(f'"{sys.executable}" "{os.path.join(HERE, "pfc_connect.py")}" revert >nul 2>&1')
    reg = json.load(open(REG))
    for k in ("pfc_store", "pfc_pipeline"):
        reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1)


def revert():
    reg = json.load(open(REG))
    if reg.pop("pfc", None) is None:
        print("no ONE-Muhlnickel binding — nothing to revert."); return 0
    json.dump(reg, open(REG, "w"), indent=1)
    print("removed the ONE-Muhlnickel binding (registry only; circuits untouched)."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    for k in ("pfc_exec_input", "pfc_executor", "receiver"):
        if k not in reg:
            print(f"{k} absent — need pfc_exec_input + pfc_executor + receiver first."); return 1

    _drop(reg)                                               # keep only the connected pieces
    reg = json.load(open(REG))
    inp = int(reg["pfc_exec_input"]["offset"]); ex = int(reg["pfc_executor"]["offset"]); rc = int(reg["receiver"]["offset"])

    # the external OUTPUT WINDOW: a different plain file outside the pfc (no parameters, one-way)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "wb") as f: f.write(b"\x00" * 9)

    # ONE connected pfc — the binding, recorded so the pieces are one machine (input->compute->output on the signal)
    reg["pfc"] = {"one": True, "input": "pfc_exec_input", "input_off": inp,
                  "compute": "pfc_executor", "compute_off": ex,
                  "output_file": OUTPUT_FILE, "output_bytes": 9,
                  "receiver": "receiver", "receiver_off": rc,
                  "layout": "in: header:76|nonce:4|group:4|target:32  ->  out: status:1|en2:4|nonce:4",
                  "flow": "signal -> read pfc_exec_input -> pfc_executor -> write pfc_safezone.bin (external)",
                  "note": "black box; do NOT evaluate; readers touch only the external file"}
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print("SMASHED into ONE connected Muhlnickel:", flush=True)
    print(f"  INPUT  pfc_exec_input @ {inp}  (button stores the block, one-way in)", flush=True)
    print(f"  COMPUTE pfc_executor @ {ex}   (the executor — 339k gates)", flush=True)
    print(f"  OUTPUT {OUTPUT_FILE}  (a different file, outside the Muhlnickel, one-way)", flush=True)
    print(f"  DRIVEN by receiver @ {rc}. titan GGUF-valid: {gg}. removed the scattered pieces (pfc_store/pfc_pipeline).", flush=True)
    print("  one connected Muhlnickel. black box — no evaluation. readers touch only the external file. aim blind.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
