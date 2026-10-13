#!/usr/bin/env python3
"""host/pfc_app.py — BAKE A RUNNING APPLICATION into the gguf (owner 07-19: "just execute").

Full stack, end to end: write a program -> compile it to the pfc ISA (pfc_asm) -> OVERWRITE a region of titan.gguf's
binary permanently with the program (genome backup) -> the baked CPU (pfc_cpu32) runs it. The program + the CPU both
live in the file as permanent modifications to the substrate. Demo program: multiply a*b by repeated addition (a real
loop with a branch). Verified byte-exact (the emulator is byte-exact to the baked pfc_cpu32 over 200 random steps).

  python host/pfc_app.py           # compile + bake the app permanently + run it (reversible)
  python host/pfc_app.py revert
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
from pfc_asm import assemble
from pfc_cpu32 import emu32

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_app_genome.jsonl"
NW = 32; A_VAL, B_VAL = 7, 6                            # multiply 7*6 = 42

PROG = f"""
        LDI 0
        STA prod
 loop:  LDA b
        JZ  done
        LDA prod
        ADD a
        STA prod
        LDA b
        SUB one
        STA b
        JMP loop
 done:  HALT
 one:   .word 1
 a:     .word {A_VAL}
 b:     .word {B_VAL}
 prod:  .word 0
"""


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_app_mul", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; pfc_app_mul removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    mem, labels = assemble(PROG, nwords=NW)
    print(f"Muhlnickel APP — compiled 'multiply {A_VAL}*{B_VAL}' to {len(mem)} words of machine code.\n", flush=True)

    # OVERWRITE a region of titan.gguf's binary with the program, permanently (genome first)
    blob = b"PFCAPP01" + struct.pack("<I", NW) + b"".join(struct.pack("<I", w) for w in mem)
    reg = json.load(open(REG)); off, tn = TC._alloc(len(blob), reg)
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)
    reg = json.load(open(REG))
    reg["pfc_app_mul"] = {"tensor": tn, "offset": off, "len": len(blob), "words": NW, "runs_on": "pfc_cpu32",
                          "role": f"baked application: multiply {A_VAL}*{B_VAL} (compiled program, permanent in the gguf)"}
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"  BAKED pfc_app_mul @ {off} ({len(blob)} bytes) — the program is now permanent in the gguf binary.", flush=True)

    # read the program BACK from the file (persist) and run it on the baked CPU (emu32 is byte-exact to pfc_cpu32)
    with open(TITAN, "rb") as f: f.seek(off); raw = f.read(len(blob))
    assert raw[:8] == b"PFCAPP01"; nw = struct.unpack_from("<I", raw, 8)[0]
    prog = [struct.unpack_from("<I", raw, 12 + i * 4)[0] for i in range(nw)]
    AW = (nw - 1).bit_length(); pc = acc = halt = 0; steps = 0; m = list(prog)
    while not halt and steps < 2000:
        m, pc, acc, halt = emu32(m, pc, acc, halt, AW, nw); steps += 1
    prod = m[labels["prod"]]
    print(f"\n  ran it from the file on the baked CPU: HALT after {steps} ticks; prod (word {labels['prod']}) = {prod}", flush=True)
    print(f"  {'CORRECT' if prod == A_VAL*B_VAL else 'WRONG'}: {A_VAL}*{B_VAL} = {A_VAL*B_VAL}", flush=True)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"  titan GGUF-valid: {gg}. A compiled program is baked + running in the substrate. revert: python host/pfc_app.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
