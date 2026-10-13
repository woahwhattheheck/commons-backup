#!/usr/bin/env python3
"""host/pfc_fab_miner_physical.py — fabricate the Bitcoin miner in the CORRECT form (owner 2026-07-21).

Not the serialized-netlist crutch (gate indices + in_map + host executor). The correct form, from the arcade + your
rule "connection = a shared physical storage location": EVERY wire is a real byte in titan.gguf's binary; a gate reads
its input bytes and writes its output byte IN PLACE; connected gates share the same byte. The STATE (nonce, latch,
header, target) IS the pfc's own RAM — real byte regions in the file. The self-routed clock is a SHARED LOCATION: the
next-state output bit (nonce', latch') occupies the SAME physical byte as the state input bit (nonce, latch), so the
computed next state is fed back into the state by being the same storage location. No in_map, no executor, no host
clock — the feedback is physical.

Fabrication only: it CONSTRUCTS the gate netlist (no ripple, no evaluation) and EDITS the actual file bytes to lay the
physical-address gate table + the pfc-RAM state region. Reversible (genome). Runtime is signals + probes only.

  python host/pfc_fab_miner_physical.py           # lay the physical-form miner into titan.gguf (reversible)
  python host/pfc_fab_miner_physical.py revert     # restore titan.gguf byte-exact
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import pfc_miner as PM                                          # build_statemachine: pure construction, NO ripple

TITAN = PM.TITAN; REG = PM.REG
GENOME = "C:/llm/models/titan_miner_physical_genome.jsonl"
MAGIC = b"PFCPHYS1"; OPC = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}


def journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME):
        print("no physical-miner genome — nothing to revert."); return 0
    for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    reg = json.load(open(REG))
    for k in ("miner_physical", "miner_physical_wires", "miner_physical_gates"): reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan.gguf byte-exact; miner_physical removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))

    print("constructing the clocked miner netlist with the tool (construction only — NO ripple)…", flush=True)
    g, outs = PM.build_statemachine()                          # (header,nonce,target,latch) -> (nonce+1, win?nonce:latch)
    gates, out2 = g.dce(outs)
    n_in, n_gate = g.n_in, len(gates); n_wire = 2 + n_in + n_gate
    print(f"  {n_gate:,} gates, {n_wire:,} wires. laying every wire as a PHYSICAL byte in titan.gguf…", flush=True)

    # allocate one physical byte per wire (the whole machine's wires live in the file's binary)
    base, tname = TC._alloc(n_wire, reg)                        # base..base+n_wire-1 = the physical wire bytes
    reg["miner_physical_wires"] = {"tensor": tname, "offset": base, "len": n_wire}   # record it so the next _alloc avoids it
    def addr(w): return base + w                                # wire index -> real file byte address

    # THE pfc RAM (state) = real byte regions; the input signals + the answer live here, addressed by the button/probe
    # input wire layout (pfc_miner): header W0..18 = wires 2..2+607; nonce = 2+608..2+639; target = 2+640..2+895; latch = 2+896..2+927
    ram = {
        "header": [addr(2 + i) for i in range(608)],           # block header bits (signal in)
        "nonce":  [addr(2 + 608 + i) for i in range(32)],      # STATE: nonce (Muhlnickel RAM)
        "target": [addr(2 + 640 + i) for i in range(256)],     # target bits (signal in)
        "latch":  [addr(2 + 896 + i) for i in range(32)],      # ANSWER: latch (Muhlnickel RAM, probe reads this)
    }
    # SELF-ROUTED CLOCK = SHARED LOCATION: the next-state outputs (nonce', latch') ARE the state input bytes.
    # out2[0..31] = nonce'  -> share the SAME physical bytes as nonce inputs; out2[32..63] = latch' -> share latch inputs.
    shared = {}                                                # physical addr of an output wire forced to equal a state input addr
    for j in range(32): shared[out2[j]] = ram["nonce"][j]      # nonce'[j] writes the nonce[j] byte (feedback = same location)
    for j in range(32): shared[out2[32 + j]] = ram["latch"][j] # latch'[j] writes the latch[j] byte
    def out_addr(w): return shared.get(w, addr(w))             # a gate's output address (shared for state feedback)

    # write the PHYSICAL gate table: each gate = op(1) + in_a addr(8) + in_b addr(8) + out addr(8) = 25 bytes, all real
    # 64-bit byte addresses (titan.gguf is 40 GB, so wire addresses need 64 bits)
    tbl_bytes = bytearray()
    for k, (op, a, b) in enumerate(gates):
        wo = 2 + n_in + k                                      # this gate's own wire index
        tbl_bytes += struct.pack("<BQQQ", OPC[op], addr(a), addr(b), out_addr(wo))
    tbl_base, tbl_tname = TC._alloc(len(tbl_bytes), reg)       # distinct region (wires already recorded, so no overlap)
    reg["miner_physical_gates"] = {"tensor": tbl_tname, "offset": tbl_base, "len": len(tbl_bytes)}

    # initialize the physical wire bytes to 0 (clean pfc state), then lay the gate table — editing the actual file
    journal(base, b"\x00" * n_wire)                            # the wire/RAM region, clean
    journal(base + 1, b"\x01")                                 # wire 1 = const1 (physical), like every pfc
    journal(tbl_base, bytes(tbl_bytes))                        # the physical-address gate table

    reg["miner_physical"] = {
        "tensor": tname, "format": "physical-address", "n_gate": n_gate, "n_wire": n_wire, "n_in": n_in,
        "wire_base": base, "const1_addr": addr(1), "gate_table_off": tbl_base, "gate_bytes": len(tbl_bytes),
        "gate_stride": 25, "ram": {"header_off": ram["header"][0], "nonce_off": ram["nonce"][0],
                                   "target_off": ram["target"][0], "latch_off": ram["latch"][0]},
        "answer": "latch (Muhlnickel RAM) @ %d — probe reads this" % ram["latch"][0],
        "clock": "self-routed: nonce'/latch' outputs SHARE the nonce/latch state bytes (physical feedback)",
        "note": "correct form: physical-location gates, wires ARE file bytes, state IS the Muhlnickel's RAM, clock is shared-location feedback",
    }
    json.dump(reg, open(REG, "w"), indent=1)

    with open(TITAN, "rb") as f: gv = f.read(4) == b"GGUF"
    print(f"\nCHANGED THE FILE BINARY — miner_physical (correct form, reversible genome {GENOME}):", flush=True)
    print(f"  {n_gate:,} physical-address gates @ {tbl_base} (25 B each: op|in_a|in_b|out, all real 64-bit byte addresses)", flush=True)
    print(f"  wires ARE file bytes @ {base}..{base + n_wire - 1}  · const1 @ {addr(1)}", flush=True)
    print(f"  Muhlnickel RAM (state):  nonce @ {ram['nonce'][0]} · latch(ANSWER) @ {ram['latch'][0]} · header @ {ram['header'][0]} · target @ {ram['target'][0]}", flush=True)
    print(f"  self-routed clock: nonce'/latch' outputs SHARE the nonce/latch bytes — feedback is a physical shared location.", flush=True)
    print(f"  runtime = signals in (block->header/target bytes) + probe out (read latch bytes). titan GGUF-valid: {gv}.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
