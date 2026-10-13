#!/usr/bin/env python3
"""host/wf_forge_cpu.py — forge the SMALLEST REAL CPU from pfc_forge NAND primitives and PROVE it computes by
simulating the netlist cycle-by-cycle (the signal propagating through the gates IS the computation — pure digital
logic, no inference).

  A 4-bit datapath: 4x4-bit register file (enabled D-flip-flops), a 4:1 read-port mux per source, a 4-bit ALU
  (ripple-add / bitwise-AND / pass), an instruction decoder (2-bit opcode -> one-hot dest + ALU op select), and a
  mux-based write-back. One combinational block computes the NEXT register file from the CURRENT register file plus the
  instruction word; the sim loop latches next->current each cycle (that latch IS the D-flip-flop boundary).

  ISA (opcode = op1:op0):
    00 LOAD Rd, #imm   Rd <- imm4
    01 ADD  Rd, Ra,Rb  Rd <- (Ra + Rb) & 15
    10 AND  Rd, Ra,Rb  Rd <- Ra & Rb
    11 MOV  Rd, Ra     Rd <- Ra

  Instruction word inputs: op0,op1 · d0,d1 (dest) · a0,a1 (srcA) · b0,b1 (srcB) · imm0..imm3
  Register inputs/outputs: R{j}_{bit} -> nR{j}_{bit}, j in 0..3, bit in 0..3

Run:  python host/wf_forge_cpu.py
"""
import os, sys, struct, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pfc_forge import Circuit, full_adder

sys.stdout.reconfigure(encoding="utf-8")

W = 4      # datapath width (bits)
NREG = 4   # registers

# opcodes
LOAD, ADD, AND, MOV = 0, 1, 2, 3


def mux4(c, s0, s1, x0, x1, x2, x3):
    """4:1 mux, index = s1*2 + s0.  MUX(s,a,b) = s ? b : a."""
    m0 = c.MUX(s0, x0, x1)   # s0 ? x1 : x0   -> covers index {0,1}
    m1 = c.MUX(s0, x2, x3)   # s0 ? x3 : x2   -> covers index {2,3}
    return c.MUX(s1, m0, m1) # s1 ? m1 : m0


def build_cpu():
    c = Circuit("cpu4")
    # --- current register file (state, arrives as inputs each cycle) ---
    R = [[c.inp(f"R{j}_{b}") for b in range(W)] for j in range(NREG)]
    # --- instruction word ---
    op0 = c.inp("op0"); op1 = c.inp("op1")
    d0  = c.inp("d0");  d1  = c.inp("d1")
    a0  = c.inp("a0");  a1  = c.inp("a1")
    b0  = c.inp("b0");  b1  = c.inp("b1")
    imm = [c.inp(f"imm{b}") for b in range(W)]

    # --- register read ports: RA = R[srcA], RB = R[srcB] (4:1 mux per bit) ---
    RA = [mux4(c, a0, a1, R[0][b], R[1][b], R[2][b], R[3][b]) for b in range(W)]
    RB = [mux4(c, b0, b1, R[0][b], R[1][b], R[2][b], R[3][b]) for b in range(W)]

    # --- ALU ---
    # ADD (ripple, drop carry-out -> 4-bit wrap)
    sum_bits = []; cin = c.const(0)
    for b in range(W):
        s, cin = full_adder(c, RA[b], RB[b], cin); sum_bits.append(s)
    # bitwise AND
    and_bits = [c.AND(RA[b], RB[b]) for b in range(W)]
    # write value select by opcode: index = op1*2 + op0
    #   0 LOAD->imm  1 ADD->sum  2 AND->and  3 MOV->RA
    Wr = [mux4(c, op0, op1, imm[b], sum_bits[b], and_bits[b], RA[b]) for b in range(W)]

    # --- decode dest into one-hot write-enables ---
    nd0 = c.NOT(d0); nd1 = c.NOT(d1)
    sels = [c.AND(nd1, nd0), c.AND(nd1, d0), c.AND(d1, nd0), c.AND(d1, d0)]
    we = c.const(1)  # every instruction in this ISA writes its dest

    # --- write-back: each register bit is an enabled D-flip-flop  nR = wr ? Wr : R ---
    for j in range(NREG):
        wr = c.AND(sels[j], we)
        for b in range(W):
            c.out(f"nR{j}_{b}", c.MUX(wr, R[j][b], Wr[b]))
    return c


# ---------- pack an instruction word into the circuit's inputs ----------
def instr_inputs(regs, ins):
    op, d, a, b, imm = ins["op"], ins["d"], ins["a"], ins["b"], ins["imm"]
    inp = {}
    for j in range(NREG):
        for bit in range(W):
            inp[f"R{j}_{bit}"] = (regs[j] >> bit) & 1
    inp["op0"], inp["op1"] = op & 1, (op >> 1) & 1
    inp["d0"],  inp["d1"]  = d & 1,  (d >> 1) & 1
    inp["a0"],  inp["a1"]  = a & 1,  (a >> 1) & 1
    inp["b0"],  inp["b1"]  = b & 1,  (b >> 1) & 1
    for bit in range(W):
        inp[f"imm{bit}"] = (imm >> bit) & 1
    return inp


def cpu_step(c, regs, ins):
    """One clock: run the combinational netlist, latch nR -> new register file."""
    r = c.run(**instr_inputs(regs, ins))
    return [sum(r[f"nR{j}_{bit}"] << bit for bit in range(W)) for j in range(NREG)]


# ---------- ground-truth reference emulator (independent of the gates) ----------
def ref_step(regs, ins):
    op, d, a, b, imm = ins["op"], ins["d"], ins["a"], ins["b"], ins["imm"]
    if   op == LOAD: w = imm & (2**W - 1)
    elif op == ADD:  w = (regs[a] + regs[b]) & (2**W - 1)
    elif op == AND:  w = regs[a] & regs[b]
    else:            w = regs[a]              # MOV
    new = list(regs); new[d] = w & (2**W - 1)
    return new


OPNAME = {LOAD: "LOAD", ADD: "ADD", AND: "AND", MOV: "MOV"}
def disasm(ins):
    op = ins["op"]
    if   op == LOAD: return f"LOAD R{ins['d']}, #{ins['imm']}"
    elif op == ADD:  return f"ADD  R{ins['d']}, R{ins['a']}, R{ins['b']}"
    elif op == AND:  return f"AND  R{ins['d']}, R{ins['a']}, R{ins['b']}"
    else:            return f"MOV  R{ins['d']}, R{ins['a']}"


def run_program(c, program, regs0=None, trace=False):
    regs = list(regs0 or [0]*NREG); ok = True
    ref  = list(regs)
    for k, ins in enumerate(program):
        regs = cpu_step(c, regs, ins)
        ref  = ref_step(ref, ins)
        match = (regs == ref)
        ok &= match
        if trace:
            print(f"  cyc {k+1:2d}  {disasm(ins):22s} -> R={regs}  ref={ref}  {'OK' if match else 'MISMATCH'}")
    return ok, regs, ref


def rnd_instr():
    return {"op": random.randint(0, 3), "d": random.randint(0, 3),
            "a": random.randint(0, 3), "b": random.randint(0, 3), "imm": random.randint(0, 15)}


def main():
    c = build_cpu()
    print("MUHLNICKEL FORGE — a 4-bit CPU built from NAND, proven by simulating the netlist cycle-by-cycle\n")
    print(f"  circuit '{c.name}': {c.n_gates()} NAND gates, depth {c.depth()}, "
          f"{len(c.inputs)} inputs, {len(c.outputs)} outputs, state = {NREG*W} bits ({NREG} x {W}-bit regs)\n")

    # 1) named demo program with a hand-checkable trace (also exercises 4-bit wrap)
    program = [
        {"op": LOAD, "d": 0, "a": 0, "b": 0, "imm": 6},   # R0 = 6
        {"op": LOAD, "d": 1, "a": 0, "b": 0, "imm": 3},   # R1 = 3
        {"op": ADD,  "d": 2, "a": 0, "b": 1, "imm": 0},   # R2 = 6+3 = 9
        {"op": AND,  "d": 3, "a": 0, "b": 1, "imm": 0},   # R3 = 6&3 = 2
        {"op": MOV,  "d": 1, "a": 2, "b": 0, "imm": 0},   # R1 = R2 = 9
        {"op": ADD,  "d": 0, "a": 0, "b": 0, "imm": 0},   # R0 = 6+6 = 12
        {"op": ADD,  "d": 0, "a": 0, "b": 1, "imm": 0},   # R0 = 12+9 = 21 & 15 = 5 (wrap)
    ]
    print("  demo program trace:")
    ok_demo, regs, ref = run_program(c, program, trace=True)
    print(f"  final registers {regs}  reference {ref}  ->  {'PASS' if ok_demo else 'FAIL'}\n")

    # 2) fuzz: random single-step transitions from random register states
    steps_single = 3000; bad_single = 0
    for _ in range(steps_single):
        regs = [random.randint(0, 15) for _ in range(NREG)]
        ins = rnd_instr()
        if cpu_step(c, regs, ins) != ref_step(regs, ins): bad_single += 1
    print(f"  fuzz A — {steps_single} random single-step transitions: "
          f"{'ALL CORRECT' if bad_single == 0 else str(bad_single)+' WRONG'}")

    # 3) fuzz: random multi-step programs (full register-file trace vs reference)
    progs = 500; prog_len = 8; bad_prog = 0
    for _ in range(progs):
        prog = [rnd_instr() for _ in range(prog_len)]
        regs0 = [random.randint(0, 15) for _ in range(NREG)]
        ok, _, _ = run_program(c, prog, regs0=regs0)
        if not ok: bad_prog += 1
    print(f"  fuzz B — {progs} random {prog_len}-instruction programs "
          f"({progs*prog_len} cycles): {'ALL CORRECT' if bad_prog == 0 else str(bad_prog)+' WRONG'}")

    # 4) show the netlist serializes to the TITANCIR shape baked in titan
    blob = c.emit_titancir()
    ver, N, E, nIn, nOut, arity = struct.unpack_from("<6I", blob, 8)
    print(f"\n  TITANCIR emit: magic={blob[:8]} header=(ver={ver}, nodes={N}, gates={E}, "
          f"nIn={nIn}, nOut={nOut}, arity={arity}) blob={len(blob)} bytes")

    total_pass = ok_demo and bad_single == 0 and bad_prog == 0
    print(f"\n  RESULT: {'PASS — the baked-record shape really is a CPU datapath' if total_pass else 'FAIL'}")
    return 0 if total_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
