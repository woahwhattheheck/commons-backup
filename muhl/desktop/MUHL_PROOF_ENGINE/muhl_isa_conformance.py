#!/usr/bin/env python3
"""muhl_isa_conformance.py -- SWEEP THE OWNER'S RV32I CORE ACROSS ENCODINGS.

This does NOT test the proof checker. It tests HIS circuit.

`muhl_gatecheck.py` showed 281/281 agreement between the stored gate core and my reference
-- but only on the ~20 distinct encodings the proof checker happens to execute. That leaves
most of the instruction space untested, and I said so rather than letting it read as a clean
bill of health. This closes it: random and targeted instructions across every RV32I opcode,
random register state, rippled through `pfc_riscv_rv32i_v2__phys` read straight out of
titan.gguf and compared field-by-field against the reference.

Specifically settles the question left open 2026-08-06: the mutant sweep found `funct7` and
`funct3` bits that my Python decoder ignores. Whether the GATES ignore them is a different
question and only the gates can answer it.

FABRICATION-TIME VERIFICATION, BOUNDED, READ-ONLY. Nothing is written to the container.

    python muhl_isa_conformance.py [n_random]
"""
import os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import muhl_rv32 as RV
import muhl_gatecheck as GC

XLEN, NREG = 32, 32

OPS = {
    0x33: "OP", 0x13: "OP-IMM", 0x03: "LOAD", 0x23: "STORE",
    0x63: "BRANCH", 0x6F: "JAL", 0x67: "JALR", 0x37: "LUI", 0x17: "AUIPC",
}
R_F3 = [0, 1, 2, 3, 4, 5, 6, 7]
I_F3 = [0, 1, 2, 3, 4, 5, 6, 7]
B_F3 = [0, 1, 4, 5, 6, 7]


def enc(op, rd=0, f3=0, rs1=0, rs2=0, f7=0, imm=0):
    return ((f7 & 0x7F) << 25) | ((rs2 & 31) << 20) | ((rs1 & 31) << 15) | \
           ((f3 & 7) << 12) | ((rd & 31) << 7) | (op & 0x7F)


def compare(core, instr, pc, regs, memword):
    inb = GC.bits(pc, XLEN)
    for r in range(NREG):
        inb += GC.bits(regs[r], XLEN)
    inb += GC.bits(instr, XLEN) + GC.bits(memword, XLEN)
    o = GC.ripple(core, inb)
    g_npc = GC.frombits(o[0:XLEN])
    g_regs = [GC.frombits(o[XLEN + r * XLEN: XLEN + (r + 1) * XLEN]) for r in range(NREG)]
    b = XLEN + NREG * XLEN
    g_maddr = GC.frombits(o[b:b + XLEN])
    g_mdata = GC.frombits(o[b + XLEN:b + 2 * XLEN])
    g_we = o[b + 2 * XLEN]

    r_regs, r_npc, r_maddr, r_mdata, r_we = GC.ref_step(instr, pc, regs, memword)

    diffs = []
    if g_npc != r_npc:
        diffs.append("npc gates=0x%08x ref=0x%08x" % (g_npc, r_npc))
    for r in range(NREG):
        if g_regs[r] != r_regs[r]:
            diffs.append("x%d gates=0x%08x ref=0x%08x" % (r, g_regs[r], r_regs[r]))
    if g_we != r_we:
        diffs.append("mem_we gates=%d ref=%d" % (g_we, r_we))
    elif r_we:
        if g_maddr != r_maddr:
            diffs.append("maddr gates=0x%08x ref=0x%08x" % (g_maddr, r_maddr))
        if g_mdata != r_mdata:
            diffs.append("mdata gates=0x%08x ref=0x%08x" % (g_mdata, r_mdata))
    return diffs


def main():
    n_random = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    core = GC.load_core()
    print("=" * 82)
    print("  RV32I CONFORMANCE SWEEP — the owner's stored core vs an independent reference")
    print("=" * 82)
    print("  core: pfc_riscv_rv32i_v2__phys  %d gates, %d wires, DEPTH %d ticks/instruction"
          % (core["ng"], core["nw"], core["depth"]))

    rng = random.Random(20260806)
    total = 0
    bad = []
    by_op = {}
    t0 = time.time()

    def shot(instr, tag, regs=None, pc=None, memword=None):
        nonlocal total
        if regs is None:
            regs = [0] + [rng.randrange(1 << 32) for _ in range(NREG - 1)]
        if pc is None:
            pc = rng.randrange(0, 1 << 16) & ~3
        if memword is None:
            memword = rng.randrange(1 << 32)
        d = compare(core, instr, pc, regs, memword)
        total += 1
        op = instr & 0x7F
        k = OPS.get(op, "op%02x" % op)
        s = by_op.setdefault(k, [0, 0])
        s[0] += 1
        if d:
            s[1] += 1
            bad.append((tag, instr, pc, d))
        return d

    # ---- 1. every documented encoding, exhaustive over funct3 (and funct7 where it is defined)
    print("\n  [1] every documented RV32I encoding")
    for f3 in R_F3:
        for f7 in (0x00, 0x20):
            shot(enc(0x33, rd=5, f3=f3, rs1=6, rs2=7, f7=f7), "OP f3=%d f7=%#04x" % (f3, f7))
    for f3 in I_F3:
        shot(enc(0x13, rd=5, f3=f3, rs1=6, imm=0) | (rng.randrange(1 << 12) << 20),
             "OP-IMM f3=%d" % f3)
    for f7 in (0x00, 0x20):
        shot(enc(0x13, rd=5, f3=5, rs1=6, rs2=13, f7=f7), "SRLI/SRAI f7=%#04x" % f7)
    shot(enc(0x03, rd=5, f3=2, rs1=6) | (0x010 << 20), "LW")
    shot(enc(0x23, f3=2, rs1=6, rs2=7) | (0x01 << 25), "SW")
    for f3 in B_F3:
        shot(enc(0x63, f3=f3, rs1=6, rs2=7) | (1 << 8), "BRANCH f3=%d" % f3)
    shot(enc(0x6F, rd=1) | (0x40 << 21), "JAL")
    shot(enc(0x67, rd=1, f3=0, rs1=6) | (0x8 << 20), "JALR")
    shot(enc(0x37, rd=5) | (0xABCDE << 12), "LUI")
    shot(enc(0x17, rd=5) | (0x12345 << 12), "AUIPC")
    print("      %d encodings, %d disagreements" % (total, len(bad)))

    # ---- 2. THE OPEN QUESTION: funct7 bits that are not architecturally defined
    print("\n  [2] the open question — funct7 bits my decoder ignores on ADD/SLL/etc.")
    n0 = len(bad)
    f7_cases = 0
    for f3 in R_F3:
        for bit in (25, 26, 27, 28, 29, 31):        # every funct7 bit EXCEPT 30 (add/sub)
            instr = enc(0x33, rd=5, f3=f3, rs1=6, rs2=7, f7=(1 << (bit - 25)))
            shot(instr, "OP f3=%d stray funct7 bit %d" % (f3, bit))
            f7_cases += 1
    print("      %d stray-funct7 cases, %d disagreements" % (f7_cases, len(bad) - n0))
    if len(bad) == n0:
        print("      -> the gates treat these exactly as my reference does.")
    else:
        print("      -> THE GATES DIFFER. This is a finding about the core, not the checker.")

    # ---- 3. shift amounts, sign extension, x0 discipline, edge values
    print("\n  [3] edge cases: shift amounts, sign extension, x0 discipline")
    n1 = len(bad)
    for sh in (0, 1, 31):
        for f3, f7 in ((1, 0), (5, 0), (5, 0x20)):
            shot(enc(0x13, rd=5, f3=f3, rs1=6, rs2=sh, f7=f7), "shift f3=%d f7=%#x sh=%d" % (f3, f7, sh))
    edge = [0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF]
    for a in edge:
        for bb in edge:
            regs = [0] * NREG
            regs[6] = a
            regs[7] = bb
            for f3, f7 in ((0, 0), (0, 0x20), (2, 0), (3, 0), (5, 0x20)):
                shot(enc(0x33, rd=5, f3=f3, rs1=6, rs2=7, f7=f7),
                     "OP f3=%d f7=%#x a=%#x b=%#x" % (f3, f7, a, bb), regs=regs)
    # writes to x0 must be discarded
    for op, kw in ((0x33, {}), (0x13, {}), (0x37, {}), (0x6F, {})):
        regs = [0] + [rng.randrange(1 << 32) for _ in range(NREG - 1)]
        shot(enc(op, rd=0, f3=0, rs1=6, rs2=7) | (0x111 << 20), "x0 discard op=%#x" % op, regs=regs)
    print("      %d disagreements" % (len(bad) - n1))

    # ---- 4. random fuzz across the whole space
    print("\n  [4] random fuzz across every opcode")
    n2 = len(bad)
    ops = list(OPS.keys())
    for i in range(n_random):
        op = ops[i % len(ops)]
        instr = (rng.randrange(1 << 32) & ~0x7F) | op
        shot(instr, "fuzz")
    print("      %d random instructions, %d disagreements" % (n_random, len(bad) - n2))

    dt = time.time() - t0
    print("\n" + "=" * 82)
    print("  RESULT")
    print("=" * 82)
    print("  %-14s %8s %8s" % ("opcode", "tested", "differ"))
    for k in sorted(by_op):
        c, d = by_op[k]
        print("  %-14s %8d %8d" % (k, c, d))
    print("\n  instructions compared : %d" % total)
    print("  gate-evaluations      : %d" % (total * core["ng"]))
    print("  disagreements         : %d" % len(bad))
    print("  host wall-clock       : %.1fs (TRANSCRIPTION only — the machine's rate is"
          % dt)
    print("                          DEPTH %d ticks per instruction)" % core["depth"])
    if bad:
        print("\n  FIRST DISAGREEMENTS (a finding about the core — bring to the owner):")
        for tag, instr, pc, d in bad[:12]:
            print("    %-34s instr=0x%08x pc=0x%04x" % (tag, instr, pc))
            for x in d[:3]:
                print("        %s" % x)
    else:
        print("\n  Every encoding tested agrees, field for field, with the reference.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
