"""
pfc_riscv_priv2.py - PRIVILEGE MODES + the mstatus TRAP STACK, as gates.

pfc_riscv_priv.py gave the core traps: an interrupt lands the PC at mtvec. That is preemption, but
it is not yet an OS, because nothing records WHERE the trap came from or restores it on return.
Without that, a trap taken inside a trap loses the outer context and MRET returns to the wrong
privilege with interrupts in the wrong state.

WHAT THIS ADDS (all as gates, all in the same single settle)
  PRIVILEGE   current mode is state: U=0, S=1, M=3
  mstatus     MIE (bit 3) · MPIE (bit 7) · MPP (bits 12:11) - the one-deep trap stack
  ON TRAP     MPIE <- MIE ; MIE <- 0 ; MPP <- current priv ; priv <- M ; mepc <- pc
              (MIE<-0 is what stops a second interrupt from clobbering the first's mepc)
  ON MRET     MIE <- MPIE ; MPIE <- 1 ; priv <- MPP ; MPP <- U
  GATING      an interrupt is only taken when MIE is set - a critical section really is critical

That MIE<-0 on entry and MIE<-MPIE on return IS the mechanism that lets a kernel run with
interrupts off and hand control back with them on. It is the smallest complete trap stack.

VERIFIED against an independent Python model of the same semantics, comparing privilege, mstatus
field by field, mepc, mcause and the next PC.

NOT YET BUILT toward Linux: page-table MMU (Sv32), atomics (RV32A), CLINT mtime/mtimecmp,
and delegation (medeleg/mideleg) so S-mode can take its own traps.

Run:  python host/pfc_riscv_priv2.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_riscv import XLEN, depth_of, nl, tree_or, mux_vec, addc

PRIV_U, PRIV_S, PRIV_M = 0, 1, 3
MIE_BIT, MPIE_BIT, MPP_LO = 3, 7, 11
CAUSE_ECALL_U, CAUSE_ECALL_S, CAUSE_ECALL_M = 8, 9, 11
CAUSE_TIMER = 0x80000007


def build():
    """inputs: pc[32] | priv[2] | mstatus[32] | mtvec[32] | mepc[32] | instr[32] | irq
       outputs: npc[32] | priv'[2] | mstatus'[32] | mepc'[32] | mcause[32] | trap"""
    NIN = XLEN + 2 + XLEN * 4 + 1
    c = TC.Circuit(NIN)
    o = 0
    PC = list(c.IN[o:o + XLEN]); o += XLEN
    PRIV = list(c.IN[o:o + 2]); o += 2
    MST = list(c.IN[o:o + XLEN]); o += XLEN
    MTVEC = list(c.IN[o:o + XLEN]); o += XLEN
    MEPC = list(c.IN[o:o + XLEN]); o += XLEN
    I = list(c.IN[o:o + XLEN]); o += XLEN
    IRQ = c.IN[o]
    Z = c.C0

    opcode = I[0:7]; funct3 = I[12:15]; imm12 = I[20:32]

    def match(bits, v, n):
        return c._tree_and([bits[k] if (v >> k) & 1 else c.not_(bits[k]) for k in range(n)])

    is_sys = match(opcode, 0b1110011, 7)
    f3_0 = match(funct3, 0, 3)
    is_ecall = c.and_(c.and_(is_sys, f3_0), match(imm12, 0, 12))
    is_mret = c.and_(c.and_(is_sys, f3_0), match(imm12, 0x302, 12))

    MIE = MST[MIE_BIT]
    MPIE = MST[MPIE_BIT]
    MPP = [MST[MPP_LO], MST[MPP_LO + 1]]

    # an interrupt is only taken when MIE is set. This is what makes a critical section critical.
    irq_taken = c.and_(IRQ, MIE)
    trap = c.or_(is_ecall, irq_taken)

    # ECALL's cause depends on the privilege it was issued from - that is how the kernel knows
    # whether a syscall came from user code or from itself.
    is_u = c._tree_and([c.not_(PRIV[0]), c.not_(PRIV[1])])
    is_s = c._tree_and([PRIV[0], c.not_(PRIV[1])])
    is_m = c._tree_and([PRIV[0], PRIV[1]])
    cause = list(c.cvec(0, XLEN))
    for sel, v in ((is_u, CAUSE_ECALL_U), (is_s, CAUSE_ECALL_S), (is_m, CAUSE_ECALL_M)):
        cause = mux_vec(c, c.and_(is_ecall, sel), cause, c.cvec(v, XLEN))
    cause = mux_vec(c, irq_taken, cause, c.cvec(CAUSE_TIMER, XLEN))

    # ---- the trap stack ----
    # on trap : MPIE <- MIE, MIE <- 0, MPP <- priv, priv <- M
    # on mret : MIE <- MPIE, MPIE <- 1, priv <- MPP, MPP <- U
    new_mie = c.mux(trap, c.mux(is_mret, MIE, MPIE), Z)
    new_mpie = c.mux(trap, c.mux(is_mret, MPIE, c.C1), MIE)
    new_mpp0 = c.mux(trap, c.mux(is_mret, MPP[0], Z), PRIV[0])
    new_mpp1 = c.mux(trap, c.mux(is_mret, MPP[1], Z), PRIV[1])

    newmst = list(MST)
    newmst[MIE_BIT] = new_mie
    newmst[MPIE_BIT] = new_mpie
    newmst[MPP_LO] = new_mpp0
    newmst[MPP_LO + 1] = new_mpp1

    npriv = [c.mux(trap, c.mux(is_mret, PRIV[0], MPP[0]), c.C1),
             c.mux(trap, c.mux(is_mret, PRIV[1], MPP[1]), c.C1)]     # trap -> M (0b11)

    pc4 = addc(c, PC, c.cvec(4, XLEN))
    npc = pc4
    npc = mux_vec(c, is_mret, npc, MEPC)
    npc = mux_vec(c, trap, npc, MTVEC)
    newmepc = mux_vec(c, trap, MEPC, PC)

    outs = list(npc) + npriv + newmst + newmepc + cause + [trap]
    return c, outs


def ref(pc, priv, mstatus, mtvec, mepc, instr, irq):
    M = (1 << 32) - 1
    op = instr & 0x7f
    f3 = (instr >> 12) & 7
    imm = (instr >> 20) & 0xfff
    is_ecall = (op == 0b1110011 and f3 == 0 and imm == 0)
    is_mret = (op == 0b1110011 and f3 == 0 and imm == 0x302)
    mie = (mstatus >> MIE_BIT) & 1
    mpie = (mstatus >> MPIE_BIT) & 1
    mpp = (mstatus >> MPP_LO) & 3
    irq_taken = irq and mie
    trap = 1 if (is_ecall or irq_taken) else 0
    npc = (pc + 4) & M
    npriv, nmst, nmepc = priv, mstatus, mepc
    cause = 0
    if trap:
        cause = CAUSE_TIMER if irq_taken else {0: CAUSE_ECALL_U, 1: CAUSE_ECALL_S,
                                               3: CAUSE_ECALL_M}[priv]
        nmst = (mstatus & ~(1 << MIE_BIT) & ~(1 << MPIE_BIT) & ~(3 << MPP_LO))
        nmst |= (mie << MPIE_BIT) | (priv << MPP_LO)
        npriv = PRIV_M
        nmepc = pc
        npc = mtvec
    elif is_mret:
        nmst = (mstatus & ~(1 << MIE_BIT) & ~(1 << MPIE_BIT) & ~(3 << MPP_LO))
        nmst |= (mpie << MIE_BIT) | (1 << MPIE_BIT)
        npriv = mpp
        npc = mepc
    return npc, npriv, nmst & M, nmepc, cause, trap


def run(net, pc, priv, mst, mtvec, mepc, instr, irq):
    ib = [(pc >> k) & 1 for k in range(XLEN)]
    ib += [(priv >> k) & 1 for k in range(2)]
    for v in (mst, mtvec, mepc, instr):
        ib += [(v >> k) & 1 for k in range(XLEN)]
    ib += [irq]
    o = TC.ripple(net, ib)
    g = lambda s, n=XLEN: sum(o[s + k] << k for k in range(n))
    p = 0
    npc = g(p); p += XLEN
    npriv = g(p, 2); p += 2
    nmst = g(p); p += XLEN
    nmepc = g(p); p += XLEN
    cause = g(p); p += XLEN
    return npc, npriv, nmst, nmepc, cause, o[p]


def main():
    print("=" * 92)
    print("PRIVILEGE MODES + mstatus TRAP STACK, AS GATES")
    print("=" * 92)
    c, outs = build()
    d, g = depth_of(c, outs), len(c.ga)
    net = nl(c, outs)
    print()
    print("  ONE SETTLE: DEPTH %d gate-delays, %s gates" % (d, "{:,}".format(g)))
    print("  privilege transition, mstatus stack push/pop, mepc and mcause all in that settle.")
    del c

    SYS = lambda imm: ((imm & 0xfff) << 20) | 0b1110011
    ECALL, MRET, NOP = SYS(0), SYS(0x302), 0x00000013
    MTVEC, EPC = 0x8000_0100, 0x4444
    mst_ie = (1 << MIE_BIT)                      # interrupts enabled
    mst_off = 0                                  # interrupts disabled
    mst_ret = (1 << MPIE_BIT) | (PRIV_U << MPP_LO)   # as left by a trap from U-mode

    cases = [
        ("ECALL from U",          0x2000, PRIV_U, mst_ie,  ECALL, 0),
        ("ECALL from S",          0x2000, PRIV_S, mst_ie,  ECALL, 0),
        ("ECALL from M",          0x2000, PRIV_M, mst_ie,  ECALL, 0),
        ("IRQ with MIE=1",        0x2000, PRIV_U, mst_ie,  NOP,   1),
        ("IRQ with MIE=0 (masked)", 0x2000, PRIV_U, mst_off, NOP, 1),
        ("MRET back to U",        0x8000_0100, PRIV_M, mst_ret, MRET, 0),
        ("MRET with IRQ pending", 0x8000_0100, PRIV_M, mst_ret, MRET, 1),
    ]
    print()
    print("  %-24s %6s %10s %10s %6s   %s" % ("case", "priv'", "npc", "mcause", "trap", "match"))
    ok = 0
    for nm, pc, priv, mst, ins, irq in cases:
        gr = run(net, pc, priv, mst, MTVEC, EPC, ins, irq)
        rr = ref(pc, priv, mst, MTVEC, EPC, ins, irq)
        same = gr == rr
        print("  %-24s %6d %10s %10s %6d   %s"
              % (nm, gr[1], hex(gr[0]), hex(gr[4]), gr[5], "OK" if same else "MISMATCH %s vs %s" % (gr, rr)))
        ok += same
    print()
    print("  %d/%d byte-exact vs the reference (npc, priv, mstatus, mepc, mcause, trap)." % (ok, len(cases)))
    print()
    print("  THE POINT: 'IRQ with MIE=0' does NOT trap - a critical section is really critical.")
    print("  And MIE<-0 on entry / MIE<-MPIE on MRET is what lets a kernel run with interrupts")
    print("  off and hand control back with them on. That is the smallest complete trap stack.")
    print()
    print("  NOT YET BUILT toward Linux: Sv32 page-table MMU, atomics (A), CLINT mtime/mtimecmp,")
    print("  and medeleg/mideleg so S-mode can take its own traps.")


if __name__ == "__main__":
    main()
