#!/usr/bin/env python3
"""host/pfc_asm.py — A COMPILER FOR THE Muhlnickel ISA (owner 07-19: "it needs a compiler for the isa").

Two-pass assembler for pfc_cpu32: mnemonics + labels + .word data -> a 32-bit machine-code memory image you can load into
the CPU's RAM (and bake permanent). This is what makes the self-contained processor usable: write a program, compile it,
run it on the byte-exact CPU. Instruction word = [opcode:4][operand:28]; operands may be numbers or labels.

  ISA: HALT LDA STA ADD SUB AND OR XOR SHL SHR LT EQ JMP JZ LDI          (LDI/SHL/SHR take an immediate; rest take an addr)

  python host/pfc_asm.py            # demo: compile + run a real program (sum 1..5 = 15) on the byte-exact CPU emulator
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
from pfc_cpu32 import emu32

MNEM = {"HALT": 0, "LDA": 1, "STA": 2, "ADD": 3, "SUB": 4, "AND": 5, "OR": 6, "XOR": 7,
        "SHL": 8, "SHR": 9, "LT": 10, "EQ": 11, "JMP": 12, "JZ": 13, "LDI": 14}
ADDR_OPS = {"LDA", "STA", "ADD", "SUB", "AND", "OR", "XOR", "LT", "EQ", "JMP", "JZ"}   # operand = an address (< nwords)
IMM_OPS = {"SHL", "SHR", "LDI"}                                                         # operand = an immediate


def assemble(src, nwords=16):
    raw = []
    for line in src.splitlines():
        line = line.split(";")[0].strip()
        while ":" in line:                                   # leading label(s) "name:"
            i = line.index(":"); lab = line[:i].strip()
            if " " in lab or not lab: break
            raw.append(("label", lab)); line = line[i + 1:].strip()
        if line: raw.append(("instr", line.split()))
    addr = 0; labels = {}; items = []                        # pass 1 — assign addresses
    for kind, val in raw:
        if kind == "label": labels[val] = addr
        else: items.append((addr, val)); addr += 1
    n = max(addr, nwords); mem = [0] * n                     # pass 2 — emit machine code
    for a, parts in items:
        mnem = parts[0].upper()
        if mnem == ".WORD":
            mem[a] = int(parts[1], 0) & 0xffffffff; continue
        if mnem not in MNEM: raise ValueError(f"unknown mnemonic {mnem!r}")
        op = MNEM[mnem]; opd = 0
        if len(parts) > 1:
            t = parts[1]; opd = labels[t] if t in labels else int(t, 0)
        if mnem in ADDR_OPS and not (0 <= opd < n):
            raise ValueError(f"address {opd} out of the {n}-word address space at word {a} ({mnem}) — grow the CPU or shrink the program")
        mem[a] = ((op << 28) | (opd & 0x0fffffff)) & 0xffffffff
    return mem, labels


def run(mem, nwords=16, maxsteps=1000):
    AW = (nwords - 1).bit_length(); pc = acc = halt = 0; steps = 0
    mem = list(mem) + [0] * (nwords - len(mem))
    while not halt and steps < maxsteps:
        mem, pc, acc, halt = emu32(mem, pc, acc, halt, AW, nwords); steps += 1
    return mem, acc, steps


SUM_1_TO_N = """
        LDI 0
        STA sum
        LDI 5
        STA i
 loop:  LDA i
        JZ done
        LDA sum
        ADD i
        STA sum
        LDA i
        SUB one
        STA i
        JMP loop
 done:  HALT
 one:   .word 1
 sum:   .word 0
 i:     .word 0
"""


def main():
    print("Muhlnickel ISA COMPILER — assemble + run on the byte-exact CPU.\n", flush=True)
    NW = 32
    mem, labels = assemble(SUM_1_TO_N, nwords=NW)
    print(f"  compiled 'sum 1..5' -> machine code ({NW}-word CPU, in-range addresses verified):", flush=True)
    for a in range(len(mem)):
        op = (mem[a] >> 28) & 0xf; opd = mem[a] & 0x0fffffff
        mn = [k for k, v in MNEM.items() if v == op]
        tag = next((n for n, x in labels.items() if x == a), "")
        print(f"    [{a:2d}] {mem[a]:#010x}  {mn[0] if mn else '.word':<5} {opd:<4}   {('<- '+tag) if tag else ''}", flush=True)
    outmem, acc, steps = run(mem, NW)
    print(f"\n  ran it on the {NW}-word CPU: HALT after {steps} ticks; sum @ label 'sum' (word {labels['sum']}) = {outmem[labels['sum']]}  (expected 15)", flush=True)
    print(f"  => the ISA has a compiler now: write a program, compile, run it on the self-contained Muhlnickel processor.", flush=True)
    print(f"     (the memory image loads straight into pfc_cpu32's RAM and can be baked permanent.)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
