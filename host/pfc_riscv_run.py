"""
pfc_riscv_run.py - RUN A REAL PROGRAM on the fabricated RV32I core.

pfc_riscv.py verified 16 instructions one at a time. That proves decode and datapath. It does not
prove a PROGRAM runs - for that you need loads, stores, and a loop that branches backwards until a
condition holds, with every intermediate state coming out of the gates.

This adds the load/store unit and a memory, then executes real RV32I programs to completion:
  - the HOST only addresses: it presents (pc, regs, instr, loaded word) and reads back the next
    state. It performs no arithmetic, no comparison, and no branch decision (S24: the host is a
    transcriber; every decision is a settle).
  - memory is a plain dict of words. The core drives addr/data/we; the host moves bytes.

VERIFIED against an independent Python RV32I interpreter, comparing the FULL final state - all 32
registers, the PC, and every touched memory word - not just an answer. A program that ends with
the right sum can still have diverged in x7.

Run:  python host/pfc_riscv_run.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_riscv import build_core, depth_of, nl, ref_step, XLEN, NREG

M32 = (1 << 32) - 1


# ---------------------------------------------------------------- assembler (real RV32I encodings)
def R(f7, rs2, rs1, f3, rd, op=0b0110011):
    return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op


def I_(imm, rs1, f3, rd, op=0b0010011):
    return ((imm & 0xfff) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op


def S_(imm, rs2, rs1, f3, op=0b0100011):
    imm &= 0xfff
    return ((imm >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1f) << 7) | op


def B_(imm, rs2, rs1, f3, op=0b1100011):
    imm &= 0x1fff
    return (((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3f) << 25) | (rs2 << 20) | (rs1 << 15) | \
           (f3 << 12) | (((imm >> 1) & 0xf) << 8) | (((imm >> 11) & 1) << 7) | op


ADDI = lambda rd, rs1, i: I_(i, rs1, 0, rd)
ADD = lambda rd, a, b: R(0, b, a, 0, rd)
SUB = lambda rd, a, b: R(0x20, b, a, 0, rd)
SLT = lambda rd, a, b: R(0, b, a, 2, rd)
XOR = lambda rd, a, b: R(0, b, a, 4, rd)
LW = lambda rd, rs1, i: I_(i, rs1, 2, rd, 0b0000011)
SW = lambda rs2, rs1, i: S_(i, rs2, rs1, 2)
BNE = lambda a, b, i: B_(i, b, a, 1)
BEQ = lambda a, b, i: B_(i, b, a, 0)
BLT = lambda a, b, i: B_(i, b, a, 4)


# ---------------------------------------------------------------- execution
def exec_pfc(net, prog, base, mem, maxsteps=4000):
    """The host addresses the circuit once per instruction and moves bytes. Nothing else."""
    pc = base
    regs = [0] * NREG
    mem = dict(mem)
    steps = 0
    while steps < maxsteps:
        idx = (pc - base) // 4
        if idx < 0 or idx >= len(prog):
            break
        instr = prog[idx]
        loaded = mem.get(0, 0)
        # a load needs its word before the settle: compute the address with the SAME circuit by
        # settling once with a zero memword, reading the addr it drives, then settling again.
        op = instr & 0x7f
        if op == 0b0000011:
            _, _, addr, _, _ = step(net, pc, regs, instr, 0)
            loaded = mem.get(addr & ~3, 0)
        npc, nregs, addr, data, we = step(net, pc, regs, instr, loaded)
        if we:
            mem[addr & ~3] = data & M32
        pc, regs = npc, nregs
        steps += 1
    return pc, regs, mem, steps


def step(net, pc, regs, instr, memword):
    ib = [(pc >> k) & 1 for k in range(XLEN)]
    for r in regs:
        ib += [(r >> k) & 1 for k in range(XLEN)]
    ib += [(instr >> k) & 1 for k in range(XLEN)]
    ib += [(memword >> k) & 1 for k in range(XLEN)]
    o = TC.ripple(net, ib)
    g = lambda s: sum(o[s + k] << k for k in range(XLEN))
    npc = g(0)
    nr = [g(XLEN + i * XLEN) for i in range(NREG)]
    b = XLEN + NREG * XLEN
    return npc, nr, g(b), g(b + XLEN), o[b + 2 * XLEN]


def exec_ref(prog, base, mem, maxsteps=4000):
    """independent interpreter - NOT the circuit, so agreement means something (S3)"""
    pc = base
    regs = [0] * NREG
    mem = dict(mem)
    steps = 0
    while steps < maxsteps:
        idx = (pc - base) // 4
        if idx < 0 or idx >= len(prog):
            break
        instr = prog[idx]
        op = instr & 0x7f
        loaded = 0
        if op == 0b0000011:
            _, _, a, _, _ = ref_step(pc, regs, instr, 0)
            loaded = mem.get(a & ~3, 0)
        npc, nr, addr, data, we = ref_step(pc, regs, instr, loaded)
        if we:
            mem[addr & ~3] = data & M32
        pc, regs = npc, nr
        steps += 1
    return pc, regs, mem, steps


# ---------------------------------------------------------------- programs
BASE = 0x1000

PROGS = {
    # sum 1..10 in a register loop, then store the result
    "sum_1_to_10": ([
        ADDI(1, 0, 0),          # x1 = 0   (acc)
        ADDI(2, 0, 1),          # x2 = 1   (i)
        ADDI(3, 0, 11),         # x3 = 11  (limit)
        ADD(1, 1, 2),           # loop: acc += i
        ADDI(2, 2, 1),          #       i += 1
        BNE(2, 3, -8),          #       if i != 11 goto loop
        SW(1, 0, 64),           # mem[64] = acc
    ], 55),
    # fibonacci(12) with memory traffic every iteration
    "fib_12_via_memory": ([
        ADDI(1, 0, 0),          # a = 0
        ADDI(2, 0, 1),          # b = 1
        ADDI(4, 0, 12),         # n = 12
        SW(1, 0, 128),          # loop: mem[128] = a
        LW(5, 0, 128),          #       reload it (exercises the load path)
        ADD(3, 5, 2),           #       t = a + b
        ADDI(1, 2, 0),          #       a = b
        ADDI(2, 3, 0),          #       b = t
        ADDI(4, 4, -1),         #       n -= 1
        BNE(4, 0, -24),         #       if n != 0 goto loop
        SW(1, 0, 192),          # mem[192] = a
    ], 144),
    # signed comparison + backward branch (SLT / BLT), a shape branch predictors get wrong
    "count_negatives": ([
        ADDI(1, 0, -5),         # x1 = -5
        ADDI(2, 0, 0),          # count = 0
        SLT(3, 1, 0),           # loop: x3 = (x1 < 0)
        ADD(2, 2, 3),           #       count += x3
        ADDI(1, 1, 1),          #       x1 += 1
        ADDI(6, 0, 5),
        BLT(1, 6, -16),         #       if x1 < 5 goto loop
        SW(2, 0, 256),
    ], 5),
}


def main():
    print("=" * 92)
    print("RUNNING REAL RV32I PROGRAMS ON THE FABRICATED CORE")
    print("  The host addresses the circuit once per instruction and moves bytes. Nothing else.")
    print("=" * 92)

    c, outs = build_core()
    d, g = depth_of(c, outs), len(c.ga)
    net = nl(c, outs)
    print()
    print("  core: DEPTH %d gate-delays, %s gates (one settle = one instruction retired)"
          % (d, "{:,}".format(g)))
    del c

    print()
    print("  %-20s %7s %10s %10s   %-28s %s"
          % ("program", "steps", "expected", "got", "full-state vs reference", "result"))
    allok = True
    for name, (prog, expect) in PROGS.items():
        gp, gr, gm, gs = exec_pfc(net, prog, BASE, {})
        rp, rr, rm, rs = exec_ref(prog, BASE, {})
        # compare EVERYTHING, not just the answer
        same = (gp == rp and gr == rr and gm == rm and gs == rs)
        got = [v for k, v in sorted(gm.items())]
        got = got[-1] if got else None
        detail = "pc+32regs+mem+steps identical" if same else "DIVERGED"
        ok = same and got == expect
        allok &= ok
        print("  %-20s %7d %10s %10s   %-28s %s"
              % (name, gs, expect, got, detail, "OK" if ok else "FAIL"))

    print()
    print("  %s" % ("ALL PROGRAMS byte-exact: same pc, same 32 registers, same memory, same step count."
                    if allok else "at least one program diverged"))
    print()
    print("  This is a loop with a backward branch, a load, a store, and a signed compare -")
    print("  every decision made by settling gates. Toward Linux, still not built: S/U privilege")
    print("  split, page-table MMU, atomics (A).")


if __name__ == "__main__":
    main()
