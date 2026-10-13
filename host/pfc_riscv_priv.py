"""
pfc_riscv_priv.py - CSRs + TRAPS as gates. The step that makes a core SCHEDULABLE.

pfc_riscv.py fabricated RV32I: real machine code, 16/16 byte-exact. A core that only does RV32I
can run a program. It cannot run an OS, because an OS needs to take control back - which means
traps, and traps mean CSRs.

WHAT THIS ADDS (all as gates, all in the SAME single settle as the instruction it belongs to)
  Zicsr        CSRRW / CSRRS / CSRRC and their immediate forms
  machine CSRs mstatus · mtvec · mepc · mcause · mtval · mscratch
  TRAP ENTRY   ECALL and EBREAK: PC -> mtvec, mepc <- PC, mcause <- code
  TRAP RETURN  MRET: PC <- mepc
  TIMER        an external interrupt-pending line that forces a trap, which is how a scheduler
               ever gets the CPU back from a running task

WHAT IS STILL NOT HERE: S-mode/U-mode separation, page tables (MMU), and atomics (A). Those are
the remaining pieces between this and booting Linux. They are gates to add, and per S31 the
fabrication is off the clock.

Everything is checked against a Python reference implementing the same semantics.

Run:  python host/pfc_riscv_priv.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_riscv import (XLEN, NREG, depth_of, nl, tree_or, mux_vec, addc, eq_vec)

# CSR addresses
MSTATUS, MTVEC, MEPC, MCAUSE, MTVAL, MSCRATCH = 0x300, 0x305, 0x341, 0x342, 0x343, 0x340
CSRS = [MSTATUS, MTVEC, MEPC, MCAUSE, MTVAL, MSCRATCH]
NCSR = len(CSRS)

CAUSE_ECALL = 11
CAUSE_EBREAK = 3
CAUSE_TIMER = 0x80000007          # interrupt bit set


def build_priv():
    """inputs: pc[32] | regs[32*32] | instr[32] | csr[NCSR*32] | irq
       outputs: npc[32] | regs'[32*32] | csr'[NCSR*32] | trapped"""
    NIN = XLEN + NREG * XLEN + XLEN + NCSR * XLEN + 1
    c = TC.Circuit(NIN)
    o = 0
    PC = list(c.IN[o:o + XLEN]); o += XLEN
    REG = [list(c.IN[o + i * XLEN:o + (i + 1) * XLEN]) for i in range(NREG)]; o += NREG * XLEN
    I = list(c.IN[o:o + XLEN]); o += XLEN
    CSR = [list(c.IN[o + i * XLEN:o + (i + 1) * XLEN]) for i in range(NCSR)]; o += NCSR * XLEN
    IRQ = c.IN[o]

    Z = c.C0
    opcode = I[0:7]; rd_b = I[7:12]; funct3 = I[12:15]; rs1_b = I[15:20]
    csr_addr = I[20:32]

    def sel(bits, arr, nb):
        cur = list(arr)
        for k in range(nb):
            cur = [mux_vec(c, bits[k], cur[j], cur[j + 1]) for j in range(0, len(cur), 2)]
        return cur[0]

    RS1 = sel(rs1_b, REG, 5)
    ZIMM = list(rs1_b) + [Z] * (XLEN - 5)          # immediate CSR forms use rs1 as a zero-ext imm

    def is_op(v, bits, n):
        return c._tree_and([bits[k] if (v >> k) & 1 else c.not_(bits[k]) for k in range(n)])

    is_sys = is_op(0b1110011, opcode, 7)
    f3_0 = is_op(0, funct3, 3)                      # ECALL/EBREAK/MRET live under funct3=0
    is_csr_op = c.and_(is_sys, c.not_(f3_0))

    # which CSR is addressed: one-hot over the small set we implement
    csr_hit = [c._tree_and([csr_addr[k] if (a >> k) & 1 else c.not_(csr_addr[k]) for k in range(12)])
               for a in CSRS]
    # current value of the addressed CSR (winner-only OR, a tree)
    csr_cur = []
    for b in range(XLEN):
        csr_cur.append(tree_or(c, [c.and_(csr_hit[i], CSR[i][b]) for i in range(NCSR)]))

    # source operand: register form (funct3 1/2/3) or immediate form (5/6/7 -> bit2 set)
    use_imm = funct3[2]
    SRC = mux_vec(c, use_imm, RS1, ZIMM)

    is_rw = c.or_(is_op(1, funct3, 3), is_op(5, funct3, 3))
    is_rs = c.or_(is_op(2, funct3, 3), is_op(6, funct3, 3))
    is_rc = c.or_(is_op(3, funct3, 3), is_op(7, funct3, 3))

    v_rw = SRC
    v_rs = [c.or_(csr_cur[b], SRC[b]) for b in range(XLEN)]
    v_rc = [c.and_(csr_cur[b], c.not_(SRC[b])) for b in range(XLEN)]
    csr_new = list(csr_cur)
    csr_new = mux_vec(c, is_rw, csr_new, v_rw)
    csr_new = mux_vec(c, is_rs, csr_new, v_rs)
    csr_new = mux_vec(c, is_rc, csr_new, v_rc)

    # ECALL / EBREAK / MRET are distinguished by imm[11:0]
    def imm_is(v):
        return c._tree_and([csr_addr[k] if (v >> k) & 1 else c.not_(csr_addr[k]) for k in range(12)])
    is_ecall = c.and_(c.and_(is_sys, f3_0), imm_is(0))
    is_ebreak = c.and_(c.and_(is_sys, f3_0), imm_is(1))
    is_mret = c.and_(c.and_(is_sys, f3_0), imm_is(0x302))

    # a trap is taken on ECALL, EBREAK, or a pending interrupt. The interrupt is what lets a
    # scheduler regain control from a task that never yields.
    trap = tree_or(c, [is_ecall, is_ebreak, IRQ])
    cause_e = c.cvec(CAUSE_ECALL, XLEN)
    cause_b = c.cvec(CAUSE_EBREAK, XLEN)
    cause_t = c.cvec(CAUSE_TIMER, XLEN)
    cause = list(c.cvec(0, XLEN))
    cause = mux_vec(c, is_ebreak, cause, cause_b)
    cause = mux_vec(c, is_ecall, cause, cause_e)
    cause = mux_vec(c, IRQ, cause, cause_t)          # interrupt wins

    pc4 = addc(c, PC, c.cvec(4, XLEN))
    idx = {a: i for i, a in enumerate(CSRS)}
    npc = pc4
    npc = mux_vec(c, is_mret, npc, CSR[idx[MEPC]])
    npc = mux_vec(c, trap, npc, CSR[idx[MTVEC]])     # trap wins over everything

    # register writeback: CSR ops return the OLD csr value in rd
    rd_nz = tree_or(c, list(rd_b))
    do_wb = c.and_(c.and_(is_csr_op, rd_nz), c.not_(trap))
    newregs = []
    for i in range(NREG):
        s = c._tree_and([rd_b[k] if (i >> k) & 1 else c.not_(rd_b[k]) for k in range(5)])
        newregs.append(mux_vec(c, c.and_(s, do_wb), REG[i], csr_cur))

    # CSR file update: an explicit write, or the trap writing mepc/mcause
    newcsr = []
    for i, a in enumerate(CSRS):
        v = mux_vec(c, c.and_(c.and_(is_csr_op, csr_hit[i]), c.not_(trap)), CSR[i], csr_new)
        if a == MEPC:
            v = mux_vec(c, trap, v, PC)              # mepc <- the faulting PC
        if a == MCAUSE:
            v = mux_vec(c, trap, v, cause)
        newcsr.append(v)

    outs = list(npc)
    for r in newregs:
        outs += r
    for v in newcsr:
        outs += v
    outs += [trap]
    return c, outs


def ref(pc, regs, instr, csr, irq):
    M = (1 << 32) - 1
    op = instr & 0x7f
    rd = (instr >> 7) & 31
    f3 = (instr >> 12) & 7
    rs1 = (instr >> 15) & 31
    imm = (instr >> 20) & 0xfff
    nr = list(regs); nc = dict(csr)
    npc = (pc + 4) & M
    trap = 0
    if op == 0b1110011:
        if f3 == 0:
            if imm == 0 or imm == 1:
                trap = 1
                nc[MEPC] = pc
                nc[MCAUSE] = CAUSE_ECALL if imm == 0 else CAUSE_EBREAK
                npc = csr[MTVEC]
            elif imm == 0x302:
                npc = csr[MEPC]
        else:
            src = ((instr >> 15) & 31) if (f3 & 4) else regs[rs1]
            old = csr.get(imm, 0)
            if imm in nc:
                if f3 in (1, 5): nc[imm] = src & M
                elif f3 in (2, 6): nc[imm] = (old | src) & M
                elif f3 in (3, 7): nc[imm] = (old & ~src) & M
            if rd:
                nr[rd] = old
    if irq:
        # an interrupt is taken BEFORE the instruction commits, so nothing it would have written
        # takes effect - not the register file and not the CSR file. Reverting only the registers
        # (as this reference first did) let a csrrw's CSR write survive a trap, which no real
        # RISC-V does. The CIRCUIT was right and the reference was wrong.
        trap = 1
        nr = list(regs)
        nc = dict(csr)
        nc[MEPC] = pc
        nc[MCAUSE] = CAUSE_TIMER
        npc = csr[MTVEC]
    nr[0] = 0
    return npc, nr, nc, trap


def run(net, pc, regs, instr, csr, irq):
    ib = [(pc >> k) & 1 for k in range(XLEN)]
    for r in regs:
        ib += [(r >> k) & 1 for k in range(XLEN)]
    ib += [(instr >> k) & 1 for k in range(XLEN)]
    for a in CSRS:
        ib += [(csr[a] >> k) & 1 for k in range(XLEN)]
    ib += [irq]
    o = TC.ripple(net, ib)
    g = lambda s: sum(o[s + k] << k for k in range(XLEN))
    npc = g(0)
    nr = [g(XLEN + i * XLEN) for i in range(NREG)]
    b = XLEN + NREG * XLEN
    nc = {a: g(b + i * XLEN) for i, a in enumerate(CSRS)}
    return npc, nr, nc, o[b + NCSR * XLEN]


def main():
    print("=" * 92)
    print("RV32I + Zicsr + TRAPS, AS GATES - the step that makes a core SCHEDULABLE")
    print("=" * 92)
    c, outs = build_priv()
    d, g = depth_of(c, outs), len(c.ga)
    net = nl(c, outs)
    print()
    print("  ONE SETTLE: DEPTH %d gate-delays, %s gates" % (d, "{:,}".format(g)))
    print("  CSR read-modify-write, trap entry, and MRET all resolve in that same settle.")
    del c

    def SYS(imm, rs1, f3, rd): return ((imm & 0xfff) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | 0b1110011
    regs = [0] * NREG
    regs[1] = 0xABCD1234
    regs[2] = 0x0000000F
    csr = {MSTATUS: 0x1800, MTVEC: 0x8000_0100, MEPC: 0, MCAUSE: 0, MTVAL: 0, MSCRATCH: 0x55}

    tests = [
        ("csrrw x5,mscratch,x1", SYS(MSCRATCH, 1, 1, 5), 0),
        ("csrrs x6,mscratch,x2", SYS(MSCRATCH, 2, 2, 6), 0),
        ("csrrc x7,mscratch,x2", SYS(MSCRATCH, 2, 3, 7), 0),
        ("csrrwi x8,mtvec,3",    SYS(MTVEC, 3, 5, 8), 0),
        ("csrr  x9,mstatus",     SYS(MSTATUS, 0, 2, 9), 0),
        ("ecall",                SYS(0, 0, 0, 0), 0),
        ("ebreak",               SYS(1, 0, 0, 0), 0),
        ("mret",                 SYS(0x302, 0, 0, 0), 0),
        ("timer IRQ (any instr)", SYS(MSCRATCH, 1, 1, 5), 1),
    ]
    print()
    print("  %-24s %12s %12s %8s   %s" % ("case", "Muhlnickel npc", "ref npc", "trap", "match"))
    ok = 0
    for nm, ins, irq in tests:
        gp, gr, gc, gt = run(net, 0x2000, regs, ins, csr, irq)
        rp, rr, rc, rt = ref(0x2000, regs, ins, csr, irq)
        same = (gp == rp and gr == rr and gc == rc and gt == rt)
        print("  %-24s %12s %12s %8d   %s" % (nm, hex(gp), hex(rp), gt, "OK" if same else "MISMATCH"))
        ok += same
    print()
    print("  %d/%d byte-exact against the reference (npc, all 32 regs, all %d CSRs, trap flag)."
          % (ok, len(tests), NCSR))
    print()
    print("  WHAT THIS MEANS: an interrupt now takes the PC away from a running task and lands it")
    print("  at mtvec with mepc/mcause set - that is preemption, and preemption is what an OS needs.")
    print("  STILL NOT BUILT toward Linux: S/U privilege split, page-table MMU, atomics (A).")


if __name__ == "__main__":
    main()
