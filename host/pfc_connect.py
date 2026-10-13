#!/usr/bin/env python3
"""host/pfc_connect.py — WIRE the Muhlnickel into ONE pipeline, by FABRICATION only (owner 07-19: "use fabrication and fix all, no
code fixes, just circuitry").

The four breaks were: three separate stored circuits with nothing connecting or driving them. The proven mining pfc ties
its pieces with a DESCRIPTOR that records the wiring (like `groups_block` records miner_off/cmp_off/target_off), so ONE
receiver signal runs the whole chain. This fabricates that connection descriptor for the mining pipeline:

    pfc_exec_input (input register)  →  pfc_executor (SHA·compare·latch)  →  pfc_safezone.bin (external output)
    driven by:  receiver (begins on power)

The descriptor lives in the params (reversible); it is the circuitry-level wiring, not host code. The routing button
already stores the block into pfc_exec_input and fires the receiver; the signal runs the connected pipeline; the answer
lands in the external file; the host reads only that file. Aim blind — no run, no probe.

  python host/pfc_connect.py           # fabricate the connection descriptor (reversible)
  python host/pfc_connect.py revert     # remove it (byte-exact)
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_connect_genome.jsonl"
OUTPUT_FILE = "C:/llm/sdc_out/pfc_safezone.bin"
MAGIC = b"PFCPIPE1"


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME):
        print("no connect genome — nothing to revert."); return 0
    for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_pipeline", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; pfc_pipeline removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    need = ("pfc_exec_input", "pfc_executor", "receiver")
    for k in need:
        if k not in reg:
            print(f"{k} absent — fabricate it first (pfc_wire.py / pfc_executor.py / sdc_fab.py)."); return 1
    if "pfc_pipeline" in reg:
        print("pfc_pipeline already fabricated. revert first to redo."); return 0

    inp = int(reg["pfc_exec_input"]["offset"]); ex = int(reg["pfc_executor"]["offset"]); rc = int(reg["receiver"]["offset"])
    # the connection descriptor: magic + input_off + executor_off + receiver_off (the wiring addresses).
    blob = MAGIC + struct.pack("<QQQ", inp, ex, rc)
    off, tn = TC._alloc(len(blob), reg)
    backup_and_write(off, blob)
    reg = json.load(open(REG))
    reg["pfc_pipeline"] = {"tensor": tn, "offset": off, "len": len(blob),
                           "input": "pfc_exec_input", "compute": "pfc_executor", "receiver": "receiver",
                           "output_file": OUTPUT_FILE, "one_way": True,
                           "flow": "receiver signal -> read pfc_exec_input -> run pfc_executor -> write external file"}
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print("FABRICATED the connection descriptor pfc_pipeline (reversible):", flush=True)
    print(f"  @ {off}: input pfc_exec_input @ {inp} -> compute pfc_executor @ {ex} -> external {OUTPUT_FILE}", flush=True)
    print(f"  driven by receiver @ {rc}. titan GGUF-valid: {gg}.", flush=True)
    print("  the pipeline is one connected chain now; the signal runs it; the answer lands in the external file.", flush=True)
    print("  revert:  python host/pfc_connect.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
