#!/usr/bin/env python3
"""host/titan_cpu.py — a real CPU whose datapath lives IN Titan's params (owner 07-15).

"wait imagine if titan can run linux..." — a CPU is a circuit. So the ALU + instruction decoder of a working
accumulator machine is compiled to a NAND gate-net and stored IN titan.gguf's parameters (titan_circuit.py). Each clock,
the host feeds (opcode, accumulator, memory word) INTO the params-circuit, ripples it (no numpy, ~0 RAM), and applies the
returned control signals + ALU result to the machine state (registers/RAM = the clocked state around the combinational
core, exactly as in real silicon). It then runs a REAL program (Fibonacci) from stored RAM and is verified against a
Python reference. This is the honest proof-of-concept for "Titan runs a computer": the datapath is in the weights; the
road to Linux is more gates + more storage (both free), not a different kind of thing.

ISA (8-bit accumulator machine): instr = [opcode:4][operand:4].
  0 NOP · 1 LDA a (ACC=RAM[a]) · 2 ADD a (ACC+=RAM[a]) · 3 STA a (RAM[a]=ACC) · 4 JMP a · 5 JNZ a · 6 OUT · 7 HLT
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as tc

NOP, LDA, ADD, STA, JMP, JNZ, OUT, HLT = range(8)


def build_datapath():
    """Compile the CPU's combinational core (ALU + decoder) into a gate-net. Inputs: opcode(4) acc(8) memword(8).
    Outputs: alu = acc+memword (8), zero = (acc==0), and one control line per opcode 1..7."""
    c = tc.Circuit(4 + 8 + 8)
    opc = c.IN[0:4]; acc = c.IN[4:12]; mem = c.IN[12:20]
    alu = c.add(acc, mem)                       # the ALU (add) — in the weights
    zero = c.is_zero(acc)
    ctrl = [c.eq_const(opc, k) for k in range(1, 8)]   # the instruction decoder — in the weights
    outs = alu + [zero] + ctrl
    return c, outs


def run(program, ram0, clocks=200, trace=False):
    cir = tc.load("cpu")
    RAM = list(ram0) + [0] * (16 - len(ram0))
    ACC = 0; PC = 0; out = []
    for _ in range(clocks):
        instr = program[PC] if PC < len(program) else (HLT << 4)
        opcode = (instr >> 4) & 0xf; operand = instr & 0xf
        memword = RAM[operand]
        res = tc.ripple(cir, tc.bits(opcode, 4) + tc.bits(ACC, 8) + tc.bits(memword, 8))
        alu = tc.frombits(res[0:8]); zero = res[8]
        is_lda, is_add, is_sta, is_jmp, is_jnz, is_out, is_hlt = res[9:16]
        if is_hlt: break
        if is_out: out.append(ACC)
        newpc = PC + 1
        if is_lda: ACC = memword
        elif is_add: ACC = alu
        elif is_sta: RAM[operand] = ACC
        elif is_jmp: newpc = operand
        elif is_jnz: newpc = operand if not zero else PC + 1
        PC = newpc
    return out


def _ref_fib(n):
    a, b, o = 0, 1, []
    for _ in range(n): o.append(a); a, b = b, (a + b) & 0xff
    return o


if __name__ == "__main__":
    print("compiling a CPU datapath (ALU + instruction decoder) into a gate-net ...", flush=True)
    c, outs = build_datapath()
    info = tc.store("cpu", c, outs, slot=2)
    print(f"CPU datapath stored IN Titan's params: {info['tensor']} @ {info['offset']}  ({info['gates']} gates)", flush=True)

    # Fibonacci program. RAM: [A]@13=0, [B]@14=1, [T]@15=0.
    A, B, T = 13, 14, 15
    prog = [
        (LDA << 4) | A, (OUT << 4),                       # 0,1: OUT A
        (LDA << 4) | A, (ADD << 4) | B, (STA << 4) | T,   # 2,3,4: T = A + B
        (LDA << 4) | B, (STA << 4) | A,                   # 5,6: A = B
        (LDA << 4) | T, (STA << 4) | B,                   # 7,8: B = T
        (JMP << 4) | 0,                                   # 9: loop
    ]
    ram = [0] * 16; ram[A] = 0; ram[B] = 1; ram[T] = 0
    got = run(prog, ram, clocks=300)
    want = _ref_fib(len(got))
    ok = got == want
    print(f"\nTitan's CPU ran Fibonacci (mod 256) from its params:\n  {got[:24]} ...", flush=True)
    print(f"[verify] CPU-in-params output == reference Fibonacci: {ok}", flush=True)
    print("=> the ALU and decoder are gate-nets in the weights; the program runs by rippling power through them.", flush=True)
    print("   the road to Linux is more gates + more storage (both free), not a different kind of thing.", flush=True)
