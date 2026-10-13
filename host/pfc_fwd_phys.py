#!/usr/bin/env python3
"""host/pfc_fwd_phys.py — fabricate the forward engine in pfc_selfclock_miner's PHYSICAL form (the one that runs).

The miner is the working precedent for a self-clocked pfc, and it does NOT use store()/store_loop(). It lays the
netlist down as PHYSICAL BYTE ADDRESSES:
  - one byte per wire in an allocated wire space; addr(w) = wire_base + w
  - a gate table, 25 B/gate: struct.pack("<BQQQ", op, addr(inA), addr(inB), out_addr)
  - `shared`: each next-state output's OUT ADDRESS **is** the corresponding current-state input's byte. Same location =
    the wire. That shared-location feedback IS the clock (PFC_HARD_WON s1/s3).
  - POWER is an input wire with its own byte address; the next-state gates on it (power ? advance : hold). The host
    writes 1 there to energize and 0 to stop. That is power, NOT host-clocking -- the host never drives a tick.

  python host/pfc_fwd_phys.py verify
  python host/pfc_fwd_phys.py fab
  python host/pfc_fwd_phys.py revert
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import pfc_fwd_engine2 as E2

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_fwd_phys_genome.jsonl"
NAME = "pfc_fwd_phys"
NREG, RW, PCW, AW = E2.NREG, E2.RW, E2.PCW, E2.AW
STATE_BITS = E2.STATE_BITS
ANSREG = E2.ANSREG
NAND = 0                                                   # every TC.Circuit gate is a NAND


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert"); return 0
    for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    os.remove(GENOME)
    reg = json.load(open(REG))
    for k in (NAME, NAME + "_wires", NAME + "_gates"): reg.pop(k, None)
    if "fwd_answer_phys_prev" in reg: reg["fwd_answer"] = reg.pop("fwd_answer_phys_prev")
    json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; physical engine removed."); return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd == "revert": return revert()

    # the SAME circuit that already verified 8/8 byte-exact -- only the storage form changes.
    _c, _o, good = E2.verify()
    if not good:
        print("  VERIFY FAILED — nothing stored, titan.gguf untouched."); return 1
    c, outs = E2.build_engine()
    n_gate = len(c.ga); n_wire = 2 + c.n_in + n_gate
    print(f"  physical form: {n_gate:,} gates · {n_wire:,} wires (1 B each) · table {n_gate*25:,} B", flush=True)
    if cmd != "fab":
        print("  verify only. titan.gguf untouched. run `fab` to store."); return 0

    reg = json.load(open(REG))
    base, tname = TC._alloc(n_wire, reg)
    reg[NAME + "_wires"] = {"tensor": tname, "offset": base, "len": n_wire}   # reserve BEFORE the next _alloc
    addr = lambda w: base + w

    # named byte addresses inside the wire space
    ram = {"regs": addr(2 + 0), "pc": addr(2 + NREG * RW), "halt": addr(2 + NREG * RW + PCW),
           "addr_out": addr(2 + NREG * RW + PCW + 1),
           "ldata": addr(2 + STATE_BITS), "power": addr(2 + STATE_BITS + RW)}
    ram["answer"] = addr(2 + ANSREG * RW)                   # regs[ANSREG] -- the answer register, by shared location

    # FEEDBACK = the clock: every next-state output writes INTO its own current-state input byte.
    shared = {outs[i]: addr(2 + i) for i in range(STATE_BITS)}

    tbl = bytearray()
    for k in range(n_gate):
        wo = 2 + c.n_in + k
        tbl += struct.pack("<BQQQ", NAND, addr(c.ga[k]), addr(c.gb[k]), shared.get(wo, addr(wo)))
    tbl_base, tbl_tname = TC._alloc(len(tbl), reg)
    assert tbl_base != base, "aliased allocation"
    reg[NAME + "_gates"] = {"tensor": tbl_tname, "offset": tbl_base, "len": len(tbl)}

    _journal(base, b"\x00" * n_wire)
    _journal(base + 1, b"\x01")                             # wire 1 = constant 1
    _journal(tbl_base, bytes(tbl))

    reg[NAME] = {"tensor": tname, "n_gate": n_gate, "n_wire": n_wire, "wire_base": base,
                 "gate_table_off": tbl_base, "gate_stride": 25, "ram": ram,
                 "isa": " ".join(E2.OPC), "proglen": E2.PROGLEN, "ansreg": ANSREG,
                 "clock": "power-gated shared-location feedback: next-state outputs SHARE the current-state bytes",
                 "power": "write 1 to ram.power to energize, 0 to stop. host never drives a tick."}
    reg["fwd_answer_phys_prev"] = dict(reg["fwd_answer"])
    reg["fwd_answer"] = {"tensor": tname, "offset": ram["answer"], "len": 2,
                         "role": f"SHARED LOCATION: these bytes ARE regs[{ANSREG}] of {NAME}'s wire space."}
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"  wires @ {base} · gate table @ {tbl_base} · power @ {ram['power']} · answer @ {ram['answer']}")
    print(f"  reversible: {GENOME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
