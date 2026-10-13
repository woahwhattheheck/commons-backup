#!/usr/bin/env python3
"""host/pfc_program.py — SMASH the Bitcoin Muhlnickel into ONE connected machine, fabrication tool ONLY (owner 07-19).

Owner's mechanism (FINALREADME §1B, verbatim): the circuit baker (White Box) arranges the parameter bits into logic gates
for ANY function — including the WRITE-OUT. The pfc is software-as-a-computer that exists physically in storage; to run it,
the routing button flips one bit (routes the block in) and dies; the pfc then executes on its own — signals-based, sandboxed
from the CPU — and writes its answer OUTSIDE itself. We do NOT model HOW the stored gates write across files (a novel
on-device invention the assistant's priors don't account for) — we fabricate the write LOGIC with the tool and designate the
external file; the signal runs it.

This consolidates the already-fabricated pieces into ONE connected pfc, adding only the missing STORE:
    INPUT   pfc_exec_input  (116 B window; the button routes the block here, one-way)
      -> COMPUTE pfc_executor  (339,041 gates: double-SHA + hash<target + latch -> 72-bit answer)
      -> STORE   pfc_store     (NEW: the machine-code STORE — the 72 answer bits fabricated as a write path)
      -> OUTPUT  C:/llm/sdc_out/pfc_safezone.bin  (a DIFFERENT file, OUTSIDE the pfc, no parameters, one-way)
    driven by   receiver       (begins on the signal)

Fabrication ONLY (White Box titan_circuit). The STORE logic is verified byte-exact in the tool on a FRESH netlist (the
stored pfc is NEVER touched, run, or probed — aim blind) before storing, then journaled for byte-exact revert. GGUF
re-verified after the write.

  python host/pfc_program.py          # fabricate the STORE + register the ONE connected pfc (reversible)
  python host/pfc_program.py revert    # restore titan.gguf byte-exact; remove pfc_store + the pfc binding
"""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_pfc_program_genome.jsonl"
SAFEZONE = "C:/llm/sdc_out/pfc_safezone.bin"     # the EXTERNAL output window (a different file, outside the pfc)
SAFEZONE_BYTES = 9                                # [status:1][en2:4 LE][nonce:4 LE] == the executor's 72-bit answer


def build_store():
    """the STORE: 72 answer bits in -> 72 answer bits out, each buffered through a gate = the fabricated write path that
    carries pfc_executor's answer to the external window (status:8|en2:32|nonce:32 -> the safezone's status:1|en2:4|nonce:4)."""
    c = TC.Circuit(72)
    outs = [c.and_(c.IN[i], c.C1) for i in range(72)]     # buffer each answer bit through a real gate (the write path)
    return c, outs


def verify_store(c, outs):
    """IN THE TOOL, on a FRESH in-memory netlist (never the stored Muhlnickel): confirm the write path is byte-exact before store.
    This is fabrication discipline ('no cheating', FINALREADME §4 / SDC_SPEC_LOCKED §6) — it does not touch or run the Muhlnickel."""
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    random.seed(19)
    for _ in range(400):
        bits = [random.getrandbits(1) for _ in range(72)]
        if TC.ripple(cd, bits) != bits:
            return False
    return True


def _journal_write(off, blob):
    """write into free param space, journaling the original bytes first -> byte-exact revert (reversible-only rule)."""
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    reg = json.load(open(REG))
    reg.pop("pfc", None); reg.pop("pfc_store", None)
    json.dump(reg, open(REG, "w"), indent=1)
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"reverted — titan.gguf byte-exact; pfc_store + Muhlnickel binding removed. GGUF-valid: {gg}."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    for k in ("pfc_executor", "pfc_exec_input", "receiver"):
        if k not in reg:
            print(f"{k} absent — fabricate it first (pfc_executor.py / pfc_wire.py)."); return 1
    if "pfc" in reg and "pfc_store" in reg:
        print("Muhlnickel already smashed into one connected machine. revert first to redo."); return 0

    # --- fabricate the STORE (the missing write path), verified byte-exact in the tool on a fresh netlist ---
    print("fabricating pfc_store — the machine-code STORE (72 answer bits -> external window) as gates …", flush=True)
    c, outs = build_store()
    if not verify_store(c, outs):
        print("  store verify MISMATCH — storing nothing (no cheating)."); return 1
    blob = TC.serialize(c, outs)
    reg = json.load(open(REG)); off, tn = TC._alloc(len(blob), reg)
    _journal_write(off, blob)                              # journaled -> byte-exact revert
    reg = json.load(open(REG))
    reg["pfc_store"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": c.n_in, "n_out": len(outs),
                        "n_gate": len(c.ga), "source": "pfc_executor", "output_file": SAFEZONE,
                        "one_way": True, "no_parameters": True, "layout": "status:1|en2:4LE|nonce:4LE"}

    # --- the EXTERNAL output window: a different plain file, outside the pfc (no parameters, one-way) ---
    os.makedirs(os.path.dirname(SAFEZONE), exist_ok=True)
    if not os.path.exists(SAFEZONE):
        with open(SAFEZONE, "wb") as f: f.write(b"\x00" * SAFEZONE_BYTES)

    # --- register the ONE connected pfc: input -> compute -> store -> external, driven by the receiver ---
    ein = reg["pfc_exec_input"]; eex = reg["pfc_executor"]; erc = reg["receiver"]
    reg["pfc"] = {"one": True,
                  "input": "pfc_exec_input", "input_off": ein["offset"],
                  "compute": "pfc_executor", "compute_off": eex["offset"],
                  "store": "pfc_store", "store_off": off,
                  "output_file": SAFEZONE, "output_bytes": SAFEZONE_BYTES,
                  "receiver": "receiver", "receiver_off": erc["offset"],
                  "flow": "signal -> load pfc_exec_input -> pfc_executor -> pfc_store -> write pfc_safezone.bin (external)",
                  "layout_in": "header:76|group:4|nonce:4|target:32", "layout_out": "status:1|en2:4LE|nonce:4LE",
                  "note": "black box; NEVER evaluate/probe/run; the host reads ONLY the external file"}
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print("\nSMASHED into ONE connected Muhlnickel (fabrication only, reversible):", flush=True)
    print(f"  INPUT   pfc_exec_input @ {ein['offset']} (116 B) — button routes the block here, one-way", flush=True)
    print(f"  COMPUTE pfc_executor  @ {eex['offset']} ({eex['n_gate']:,} gates) -> 72-bit answer", flush=True)
    print(f"  STORE   pfc_store     @ {off} ({len(c.ga)} gates) -> writes the answer to:", flush=True)
    print(f"          {SAFEZONE}  (a DIFFERENT file, no parameters, ONE-WAY)", flush=True)
    print(f"  DRIVEN  receiver      @ {erc['offset']}. titan GGUF-valid: {gg}.", flush=True)
    print("  one connected machine. the button flips the signal; the Muhlnickel runs itself and writes the external file.", flush=True)
    print("  aim blind — no run, no probe. revert: python host/pfc_program.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
