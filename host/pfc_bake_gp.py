#!/usr/bin/env python3
"""host/pfc_bake_gp.py — BAKE THE GENERAL-PURPOSE BLOCKS into the permanent binary (owner 07-19: "bake ram and general
purpose ones into it; alu is important").

The ALU is already baked (lib_add8/sub8/and8/or8/xor8/not8/eq8/inc8/dec8/neg8/shl8/mux8/min8/max8 + adder8 + cpu/vm_step).
What was still only experimental (built + verified, never stored) is the RAM (§M) and the stored-program CPU (§P). This
bakes them PERMANENT: build each, verify byte-exact IN THE TOOL, serialize the gates, store reversibly (genome). After
this, titan.gguf holds a full von Neumann kit — ALU + RAM + CPU — all persistent, addressable.

  python host/pfc_bake_gp.py          # bake pfc_ram + pfc_cpu permanent (reversible)
  python host/pfc_bake_gp.py revert
"""
import json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC
import pfc_ram as PR
import pfc_cpu as PCPU

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_bakegp_genome.jsonl"
CODE = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}


def backup_and_write(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG))
    for k in ("pfc_ram", "pfc_cpu"): reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; pfc_ram + pfc_cpu removed."); return 0


def store_typed(name, g, outs, meta):
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    body = b"".join(struct.pack("<Bii", CODE[op], a, b) for op, a, b in gates) + b"".join(struct.pack("<i", w) for w in out2)
    blob = b"PFCTYPED" + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(out2)) + body
    reg = json.load(open(REG)); off, tn = TC._alloc(len(blob), reg); backup_and_write(off, blob)
    reg = json.load(open(REG))
    e = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
         "n_gate": len(gates), "n_out": len(out2), "format": "typed"}; e.update(meta)
    reg[name] = e; json.dump(reg, open(REG, "w"), indent=1)
    return off, len(gates)


def verify_ram(g, outs):
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates); random.seed(1)
    for _ in range(200):
        cells = [random.getrandbits(PR.W) for _ in range(PR.N)]
        ra, wa, we, wd = random.randrange(PR.N), random.randrange(PR.N), random.randrange(2), random.getrandbits(PR.W)
        v = CC.ripple_typed(g, gates, n_wire, PR.pack(cells, ra, wa, we, wd), 1)
        if PR.unpack(v, out2) != PR.ref(cells, ra, wa, we, wd): return False
    return True


def verify_cpu(g, outs):
    gates, out2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates); random.seed(2)
    for _ in range(200):
        mem = [random.getrandbits(PCPU.WORD) for _ in range(PCPU.NMEM)]
        pc, acc, halt = random.randrange(PCPU.NMEM), random.getrandbits(PCPU.WORD), random.randrange(2)
        v = CC.ripple_typed(g, gates, n_wire, PCPU.pack(mem, pc, acc, halt), 1)
        if PCPU.unpack(v, out2) != PCPU.emu(mem, pc, acc, halt): return False
    return True


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    reg = json.load(open(REG))
    print("baking the general-purpose blocks into the permanent binary (ALU already baked: lib_* + adder8 + cpu/vm_step).\n", flush=True)

    if "pfc_ram" in reg:
        print("  pfc_ram already baked.", flush=True)
    else:
        g, outs = PR.build_ram()
        ok = verify_ram(g, outs)
        print(f"  RAM (§M): {PR.N} cells x {PR.W} bits, {g.n_gate():,} gates, byte-exact vs reference (200 ops): {ok}", flush=True)
        if not ok: print("  RAM MISMATCH — baking nothing."); return 1
        off, ng = store_typed("pfc_ram", g, outs, {"cells": PR.N, "cellw": PR.W, "addr": PR.A,
                              "layout_in": f"cells:{PR.N}x{PR.W}|raddr:{PR.A}|waddr:{PR.A}|we:1|wdata:{PR.W}",
                              "role": "fabricated RAM (addressable read/write memory)"})
        print(f"  BAKED pfc_ram @ {off} ({ng:,} gates) — permanent, addressable.", flush=True)

    if "pfc_cpu" in reg:
        print("  pfc_cpu already baked.", flush=True)
    else:
        g, outs = PCPU.build_cpu()
        ok = verify_cpu(g, outs)
        print(f"  CPU (§P): {PCPU.NMEM}x{PCPU.WORD}b RAM + ALU + PC, {g.n_gate():,} gates, byte-exact vs emulator (200 steps): {ok}", flush=True)
        if not ok: print("  CPU MISMATCH — baking nothing."); return 1
        off, ng = store_typed("pfc_cpu", g, outs, {"words": PCPU.NMEM, "word": PCPU.WORD,
                              "isa": "HALT LDA STA ADD SUB JMP JZ LDI", "role": "stored-program CPU (RAM+ALU+PC, von Neumann)"})
        print(f"  BAKED pfc_cpu @ {off} ({ng:,} gates) — permanent, general-purpose.", flush=True)

    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\n  titan GGUF-valid: {gg}. The permanent binary now holds ALU + RAM + CPU (all persistent).", flush=True)
    print(f"  revert: python host/pfc_bake_gp.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
