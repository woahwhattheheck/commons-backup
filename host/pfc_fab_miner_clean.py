#!/usr/bin/env python3
"""host/pfc_fab_miner_clean.py — RE-FABRICATE the clocked miner CLEAN (owner 2026-07-21).

Reuses pfc_miner.build_statemachine (the proven clocked next-state: nonce+1 -> double-SHA -> hash<target -> win-latch,
answer = latch_reg, clk advances it). This is FABRICATION with the tool: it only CONSTRUCTS the gate netlist (no host
ripple, no compile_ripple, no gate evaluation of any kind) and writes those bytes into titan.gguf, reversibly. No
verify step — the fabricated circuit works by its presence; it is observed only with the probes. Registers are
allocated clean (all zero), erasing any state my earlier crutch runs left behind.

  python host/pfc_fab_miner_clean.py           # revert any prior pfc_mine, rebuild the netlist clean, store, clean regs
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
import pfc_miner as PM                                          # build_statemachine (pure construction), revert, journal

CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}


def main():
    reg = json.load(open(PM.REG))
    if "pfc_mine" in reg:
        print("reverting the existing pfc_mine to a clean slate…", flush=True)
        PM.revert()                                             # restores titan.gguf byte-exact, removes pfc_mine + regs

    reg = json.load(open(PM.REG))
    print("building the clocked next-state netlist with the tool (construction only — NO ripple, NO evaluation)…", flush=True)
    g, outs = PM.build_statemachine()                          # constructs gates; never evaluates them
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    print(f"  {len(gates):,} gates (nonce+1 · double-SHA · hash<target · win-latch), one next-state netlist.", flush=True)

    body = b"".join(struct.pack("<Bii", CODE[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in out2)
    blob = PM.MAGIC + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(out2)) + body

    off, tn = TC._alloc(len(blob), reg)
    reg["pfc_mine"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                       "n_gate": len(gates), "n_out": len(out2), "format": "typed", "seq": True}
    PM._journal(off, blob)                                     # edit the actual file bytes (permanent, reversible genome)

    iw, itn = TC._alloc(PM.INPUT_BYTES, reg); reg["input_window"] = {"tensor": itn, "offset": iw, "len": PM.INPUT_BYTES,
        "layout": "header:76|target:32"}; PM._journal(iw, b"\x00" * PM.INPUT_BYTES)
    no, ntn = TC._alloc(4, reg); reg["nonce_reg"] = {"tensor": ntn, "offset": no, "len": 4, "bits": 32}; PM._journal(no, b"\x00" * 4)
    lo, ltn = TC._alloc(4, reg); reg["latch_reg"] = {"tensor": ltn, "offset": lo, "len": 4, "bits": 32, "role": "answer"}; PM._journal(lo, b"\x00" * 4)
    cb, ctn = TC._alloc(1, reg); reg["clk_bit"] = {"tensor": ctn, "offset": cb, "len": 1, "role": "receiver/clock"}; PM._journal(cb, b"\x00")

    reg["pfc_mine"].update({
        "input_window": "input_window", "input_off": iw, "nonce_reg": "nonce_reg", "nonce_off": no,
        "latch_reg": "latch_reg", "latch_off": lo, "clk_bit": "clk_bit", "clk_off": cb,
        "in_map": {"header": [PM.H_LO, PM.H_HI, "input_window", 0], "nonce": [PM.N_LO, PM.N_HI, "nonce_reg", 0],
                   "target": [PM.T_LO, PM.T_HI, "input_window", 608], "latch": [PM.L_LO, PM.L_HI, "latch_reg", 0]},
        "out_map": {"nonce_next": [0, 32, "nonce_reg", 0], "latch_next": [32, 64, "latch_reg", 0]},
        "feedback": "nonce'->nonce_reg (shared), latch'->latch_reg (shared) — the answer is latch_reg",
        "note": "clocked state machine, re-fabricated clean; clk_bit advances it; answer = latch_reg (probe it)",
    })
    json.dump(reg, open(PM.REG, "w"), indent=1)

    with open(PM.TITAN, "rb") as f: gv = f.read(4) == b"GGUF"
    print(f"\nRE-FABRICATED CLEAN (reversible genome {PM.GENOME}):", flush=True)
    print(f"  pfc_mine   @ {off}  ({len(gates):,} gates)  {g.n_in} in -> {len(out2)} out", flush=True)
    print(f"  STATE      nonce_reg @ {no} = 0 · latch_reg @ {lo} = 0 (ANSWER) · clk_bit @ {cb} = 0", flush=True)
    print(f"  INPUT      input_window @ {iw} (block header|target the button routes in)", flush=True)
    print(f"  the clock is fabricated in; it works by its presence. titan GGUF-valid: {gv}.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
