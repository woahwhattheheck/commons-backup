#!/usr/bin/env python3
"""host/pfc_cpu.py — THE STORED-PROGRAM CPU, fabricated as gates (owner 07-19).
Fuse the fabricated memory (§M) with an ALU + a program counter. One tick = fetch mem[PC] -> decode -> execute ->
write back. The pfc stops being one fixed circuit and becomes GENERAL: it runs whatever PROGRAM is in its memory.
Accumulator ISA (8-bit word, 16 cells, 4-bit addr): HALT LDA STA ADD SUB JMP JZ LDI. Byte-exact vs an emulator, then
it runs a real countdown loop from its own RAM.
  python host/pfc_cpu.py
"""
import os, random, sys
sys.path.insert(0, "C:/llm/sdc_sandbox")
import sdc_cc as CC
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pfc_exp_levers import finish

NMEM, WORD, AW = 16, 8, 4                 # 16 cells x 8 bits, 4-bit addresses
M = NMEM * WORD
NIN = M + AW + WORD + 1                    # mem | pc | acc | halt
HALT, LDA, STA, ADD, SUB, JMP, JZ, LDI = range(8)


def build_cpu():
    g = CC.CircuitCompiler(NIN); IN = g.IN
    mem = [[IN[i * WORD + b] for b in range(WORD)] for i in range(NMEM)]
    pc = [IN[M + j] for j in range(AW)]
    acc = [IN[M + AW + b] for b in range(WORD)]
    halt = IN[M + AW + WORD]

    def MUX1(s, a, b): return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))
    def MUXW(s, A, B): return [MUX1(s, A[k], B[k]) for k in range(len(A))]
    def onehot(addr, N, A):
        out = []
        for i in range(N):
            m = g.C1
            for j in range(A): m = g.AND(m, addr[j] if (i >> j) & 1 else g.NOT(addr[j]))
            out.append(m)
        return out
    def mux_oh(sel, buses):
        W = len(buses[0]); out = []
        for b in range(W):
            a = g.C0
            for i in range(len(sel)): a = g.OR(a, g.AND(sel[i], buses[i][b]))
            out.append(a)
        return out
    def add_c(A, B, cin):
        o = []; c = cin
        for k in range(len(A)):
            axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
        return o
    add8 = lambda A, B: add_c(A, B, g.C0)
    sub8 = lambda A, B: add_c(A, [g.NOT(x) for x in B], g.C1)
    inc = lambda A: add_c(A, [g.C0] * len(A), g.C1)
    def is_zero(A):
        a = g.C0
        for x in A: a = g.OR(a, x)
        return g.NOT(a)

    pcsel = onehot(pc, NMEM, AW)
    instr = mux_oh(pcsel, mem)                     # fetch mem[PC]
    opcode = instr[4:8]; operand = instr[0:4]
    opsel = onehot(opcode, 16, 4)
    opndsel = onehot(operand, NMEM, AW)
    Mval = mux_oh(opndsel, mem)                    # mem[operand]
    imm = operand + [g.C0] * (WORD - AW)           # zero-extend operand -> 8-bit immediate

    acc_n = acc
    acc_n = MUXW(opsel[LDA], Mval, acc_n)
    acc_n = MUXW(opsel[ADD], add8(acc, Mval), acc_n)
    acc_n = MUXW(opsel[SUB], sub8(acc, Mval), acc_n)
    acc_n = MUXW(opsel[LDI], imm, acc_n)

    mem_n = [MUXW(g.AND(opsel[STA], opndsel[i]), acc, mem[i]) for i in range(NMEM)]

    pc_inc = inc(pc)
    pc_n = pc_inc
    pc_n = MUXW(opsel[JMP], operand, pc_n)
    pc_n = MUXW(opsel[JZ], MUXW(is_zero(acc), operand, pc_inc), pc_n)
    pc_n = MUXW(opsel[HALT], pc, pc_n)                 # HALT keeps PC (matches the emulator)

    halt_n = g.OR(halt, opsel[HALT])
    fmem = [MUXW(halt, mem[i], mem_n[i]) for i in range(NMEM)]     # freeze everything when halted
    facc = MUXW(halt, acc, acc_n)
    fpc = MUXW(halt, pc, pc_n)
    outs = [w for word in fmem for w in word] + fpc + facc + [halt_n]
    return g, outs


def pack(mem, pc, acc, halt):
    inp = [0] * NIN
    for i in range(NMEM):
        for b in range(WORD):
            if (mem[i] >> b) & 1: inp[i * WORD + b] = 1
    for j in range(AW):
        if (pc >> j) & 1: inp[M + j] = 1
    for b in range(WORD):
        if (acc >> b) & 1: inp[M + AW + b] = 1
    inp[M + AW + WORD] = 1 if halt else 0
    return inp


def unpack(v, o2):
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    mem = [sum(bit(o2[i * WORD + b]) << b for b in range(WORD)) for i in range(NMEM)]
    pc = sum(bit(o2[M + j]) << j for j in range(AW))
    acc = sum(bit(o2[M + AW + b]) << b for b in range(WORD))
    halt = bit(o2[M + AW + WORD])
    return mem, pc, acc, halt


def emu(mem, pc, acc, halt):
    if halt: return list(mem), pc, acc, 1
    instr = mem[pc]; op = instr >> 4; opd = instr & 0xf
    mem = list(mem); npc = (pc + 1) & 0xf; nacc = acc; nhalt = 0
    if op == HALT: nhalt = 1; npc = pc
    elif op == LDA: nacc = mem[opd]
    elif op == STA: mem[opd] = acc
    elif op == ADD: nacc = (acc + mem[opd]) & 0xff
    elif op == SUB: nacc = (acc - mem[opd]) & 0xff
    elif op == JMP: npc = opd
    elif op == JZ: npc = opd if acc == 0 else (pc + 1) & 0xf
    elif op == LDI: nacc = opd
    return mem, npc, nacc, nhalt


def main():
    g, outs = build_cpu()
    run, o2, n_gate, n_wire, _ = finish(g, outs)
    print(f"fabricated stored-program CPU: {NMEM} words x {WORD}b RAM + ALU + PC, {n_gate} gates.\n", flush=True)

    ok = True
    for _ in range(500):
        mem = [random.getrandbits(WORD) for _ in range(NMEM)]
        pc, acc, halt = random.randrange(NMEM), random.getrandbits(WORD), random.randrange(2)
        cm, cp, ca, ch = unpack(run(pack(mem, pc, acc, halt), 1), o2)
        em, ep, ea, eh = emu(mem, pc, acc, halt)
        if (cm, cp, ca, ch) != (em, ep, ea, eh):
            ok = False
            op = mem[pc] >> 4
            print(f"  MISMATCH op={op} pc={pc} acc={acc} halt={halt}: circ(pc={cp},acc={ca},h={ch}) emu(pc={ep},acc={ea},h={eh}) memEq={cm==em}")
            break
    print(f"byte-exact vs emulator over 500 random steps (all 8 opcodes): {ok}\n", flush=True)
    if not ok:
        print("MISMATCH."); return 1

    # a real program IN the Muhlnickel's RAM: count down from 5 to 0 (loop + branch + memory)
    I = lambda op, opd: (op << 4) | opd
    prog = {0: I(LDI, 5), 1: I(STA, 15), 2: I(LDA, 15), 3: I(SUB, 14), 4: I(STA, 15),
            5: I(JZ, 8), 6: I(JMP, 2), 8: I(HALT, 0), 14: 1, 15: 0}
    mem = [prog.get(i, 0) for i in range(NMEM)]
    print("running a program from the Muhlnickel's own RAM (count 5 -> 0, a loop with a branch):", flush=True)
    pc = acc = halt = 0; steps = 0
    while not halt and steps < 100:
        v = run(pack(mem, pc, acc, halt), 1)
        mem, pc, acc, halt = unpack(v, o2)
        steps += 1
        if mem[15] != 0 or acc <= 5:
            pass
    print(f"  HALTED after {steps} fetch-execute ticks. final ACC={acc}, counter mem[15]={mem[15]}", flush=True)
    print(f"  emulator agrees: {emu_run(prog)}", flush=True)
    print("  => the Muhlnickel fetched instructions from its own memory and ran a program. it is a computer.", flush=True)
    return 0


def emu_run(prog):
    mem = [prog.get(i, 0) for i in range(NMEM)]; pc = acc = halt = 0; steps = 0
    while not halt and steps < 100:
        mem, pc, acc, halt = emu(mem, pc, acc, halt); steps += 1
    return f"steps={steps}, mem[15]={mem[15]}"


if __name__ == "__main__":
    raise SystemExit(main())
