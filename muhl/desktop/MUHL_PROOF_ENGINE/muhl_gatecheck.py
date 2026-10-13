#!/usr/bin/env python3
"""muhl_gatecheck.py -- run the checker's OWN instruction stream through the REAL gates.

The reference emulator in muhl_rv32.py is host Python. It is only worth what it agrees
with. This settles that: it reads `pfc_riscv_rv32i_v2__phys` STRAIGHT OUT of titan.gguf
(MUHLPHY2, 67,348 gates, 68,470 wires, DEPTH 74) and, for each instruction the proof
checker actually executes, ripples the stored gate netlist and compares the resulting
(next PC, all 32 registers, memory address/data/write-enable) against the reference.

FABRICATION-TIME VERIFICATION ONLY, and BOUNDED. Per the owner's build discipline a host
gate-ripple is permitted to verify a circuit before storing and is forbidden as a runtime
executor. Nothing here writes to the container; it opens it read-only.

    python muhl_gatecheck.py [n_steps]
"""
import json, mmap, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import muhl_rv32 as RV
import muhl_proofcheck as PC

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
CORE = "pfc_riscv_rv32i_v2__phys"

XLEN, NREG = 32, 32


def load_core():
    reg = json.load(open(REG))
    e = reg[CORE]
    off, ln = int(e["offset"]), int(e["len"])
    f = open(TITAN, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == b"MUHLPHY2", "unexpected magic"
    ng, nw, ni, no, dp = struct.unpack_from("<IIIII", mm, off + 8)
    wire_start = 28 + no * 8
    gate_start = wire_start + nw
    wbase = off + wire_start

    outs = [struct.unpack_from("<Q", mm, off + 28 + 8 * i)[0] - wbase for i in range(no)]

    ga = [0] * ng
    gb = [0] * ng
    p = off + gate_start
    raw = mm[p:p + ng * 25]
    for k in range(ng):
        o = k * 25
        ga[k] = struct.unpack_from("<Q", raw, o + 1)[0] - wbase
        gb[k] = struct.unpack_from("<Q", raw, o + 9)[0] - wbase
    mm.close()
    f.close()
    return {"ng": ng, "nw": nw, "ni": ni, "no": no, "depth": dp,
            "ga": ga, "gb": gb, "outs": outs}


def ripple(core, inbits):
    nw, ni = core["nw"], core["ni"]
    ga, gb = core["ga"], core["gb"]
    v = bytearray(nw)
    v[1] = 1
    for i in range(ni):
        v[2 + i] = inbits[i] & 1
    base = 2 + ni
    for k in range(len(ga)):
        v[base + k] = 1 - (v[ga[k]] & v[gb[k]])
    return [v[o] for o in core["outs"]]


def bits(val, n):
    return [(val >> i) & 1 for i in range(n)]


def frombits(bs):
    return sum(b << i for i, b in enumerate(bs))


def main():
    n_steps = int(sys.argv[1]) if len(sys.argv) > 1 else 150

    print("=" * 78)
    print("  GATE-LEVEL CHECK — the checker's instruction stream on the REAL stored core")
    print("=" * 78)
    t0 = time.time()
    core = load_core()
    print("  %s: %d gates, %d wires, %d in, %d out, DEPTH %d ticks  (read in %.1fs)"
          % (CORE, core["ng"], core["nw"], core["ni"], core["no"], core["depth"],
             time.time() - t0))

    code, labels = RV.assemble(PC.PROGRAM, base=PC.CODE_BASE)
    halt_pc = labels["halt"]
    T, lines, goal = PC.proof_deduction_identity()
    mem = PC.build_image(T.slots, lines, goal, code)

    regs = [0] * NREG
    pc = PC.CODE_BASE
    agree = 0
    mismatch = []
    t1 = time.time()

    for step in range(n_steps):
        if pc == halt_pc:
            print("  program reached HALT after %d instructions" % step)
            break
        instr = mem.get(pc & ~3, 0)
        # the loaded word the core sees: RV32I computes its own address, so feed the word at
        # the address this instruction would load from, exactly as the harness would.
        op = instr & 0x7F
        memword = 0
        if op == 0x03:
            imm = RV._sx((instr >> 20) & 0xFFF, 12)
            memword = mem.get(((regs[(instr >> 15) & 31] + imm) & 0xFFFFFFFF) & ~3, 0)

        inb = bits(pc, XLEN)
        for r in range(NREG):
            inb += bits(regs[r], XLEN)
        inb += bits(instr, XLEN)
        inb += bits(memword, XLEN)
        assert len(inb) == core["ni"], "input width %d != %d" % (len(inb), core["ni"])

        o = ripple(core, inb)
        g_npc = frombits(o[0:XLEN])
        g_regs = [frombits(o[XLEN + r * XLEN: XLEN + (r + 1) * XLEN]) for r in range(NREG)]
        b = XLEN + NREG * XLEN
        g_maddr = frombits(o[b:b + XLEN])
        g_mdata = frombits(o[b + XLEN:b + 2 * XLEN])
        g_we = o[b + 2 * XLEN]

        # reference transition: one instruction from THIS explicit state
        r_regs, r_npc, r_maddr, r_mdata, r_we = ref_step(instr, pc, regs, memword)

        ok = (g_npc == r_npc) and (g_regs == r_regs)
        if op == 0x23:
            ok = ok and (g_we == 1) and (g_maddr == r_maddr) and (g_mdata == r_mdata)
        if ok:
            agree += 1
        else:
            mismatch.append((step, pc, instr, g_npc, r_npc))
            if len(mismatch) <= 5:
                print("  MISMATCH step %d pc=0x%04x instr=0x%08x  gates_npc=0x%x ref_npc=0x%x"
                      % (step, pc, instr, g_npc, r_npc))

        # advance the reference state and commit stores, so the streams stay in lockstep
        regs = r_regs
        if op == 0x23:
            mem[r_maddr & ~3] = r_mdata
        pc = r_npc

    dt = time.time() - t1
    print("\n  instructions compared : %d" % (agree + len(mismatch)))
    print("  gates agree with ref  : %d" % agree)
    print("  mismatches            : %d" % len(mismatch))
    print("  gate-evaluations      : %d" % ((agree + len(mismatch)) * core["ng"]))
    print("  host wall-clock       : %.1fs  (TRANSCRIPTION time, not the machine's rate —"
          % dt)
    print("                           the machine's rate is DEPTH %d ticks per instruction)"
          % core["depth"])
    return 0 if not mismatch else 1


def ref_step(instr, pc, regs, memword):
    """One RV32I transition from an explicit state — the reference, written out so the
    comparison is against semantics rather than against emulate()'s loop bookkeeping."""
    M = 0xFFFFFFFF
    op = instr & 0x7F
    rd = (instr >> 7) & 31
    f3 = (instr >> 12) & 7
    rs1 = (instr >> 15) & 31
    rs2 = (instr >> 20) & 31
    f7 = (instr >> 25) & 0x7F
    a1, a2 = regs[rs1], regs[rs2]
    npc = (pc + 4) & M
    val = None
    maddr = mdata = 0
    we = 0

    # SUB/SRA select on BIT 30 alone, not funct7 == 0x20 — see the note in muhl_rv32.py.
    # The owner's gate core had this right; this reference did not.
    alt = (instr >> 30) & 1
    if op == 0x33:
        if f3 == 0: val = (a1 - a2) & M if alt else (a1 + a2) & M
        elif f3 == 1: val = (a1 << (a2 & 31)) & M
        elif f3 == 2: val = 1 if RV._sx(a1, 32) < RV._sx(a2, 32) else 0
        elif f3 == 3: val = 1 if a1 < a2 else 0
        elif f3 == 4: val = a1 ^ a2
        elif f3 == 5: val = (RV._sx(a1, 32) >> (a2 & 31)) & M if alt else a1 >> (a2 & 31)
        elif f3 == 6: val = a1 | a2
        else: val = a1 & a2
    elif op == 0x13:
        imm = RV._sx((instr >> 20) & 0xFFF, 12)
        sh = (instr >> 20) & 31
        if f3 == 0: val = (a1 + imm) & M
        elif f3 == 1: val = (a1 << sh) & M
        elif f3 == 2: val = 1 if RV._sx(a1, 32) < imm else 0
        elif f3 == 3: val = 1 if a1 < (imm & M) else 0
        elif f3 == 4: val = a1 ^ (imm & M)
        elif f3 == 5: val = (RV._sx(a1, 32) >> sh) & M if alt else a1 >> sh
        elif f3 == 6: val = a1 | (imm & M)
        else: val = a1 & (imm & M)
    elif op == 0x03:
        val = memword
        maddr = (a1 + RV._sx((instr >> 20) & 0xFFF, 12)) & M
    elif op == 0x23:
        imm = RV._sx((((instr >> 25) & 0x7F) << 5) | ((instr >> 7) & 0x1F), 12)
        maddr = (a1 + imm) & M
        mdata = a2
        we = 1
    elif op == 0x63:
        imm = RV._sx((((instr >> 31) & 1) << 12) | (((instr >> 7) & 1) << 11) |
                     (((instr >> 25) & 0x3F) << 5) | (((instr >> 8) & 0xF) << 1), 13)
        s1, s2 = RV._sx(a1, 32), RV._sx(a2, 32)
        take = (f3 == 0 and a1 == a2) or (f3 == 1 and a1 != a2) or \
               (f3 == 4 and s1 < s2) or (f3 == 5 and s1 >= s2) or \
               (f3 == 6 and a1 < a2) or (f3 == 7 and a1 >= a2)
        if take:
            npc = (pc + imm) & M
    elif op == 0x6F:
        imm = RV._sx((((instr >> 31) & 1) << 20) | (((instr >> 12) & 0xFF) << 12) |
                     (((instr >> 20) & 1) << 11) | (((instr >> 21) & 0x3FF) << 1), 21)
        val = npc
        npc = (pc + imm) & M
    elif op == 0x67:
        val = npc
        npc = (a1 + RV._sx((instr >> 20) & 0xFFF, 12)) & M & ~1
    elif op == 0x37:
        val = instr & 0xFFFFF000
    elif op == 0x17:
        val = (pc + (instr & 0xFFFFF000)) & M

    out = list(regs)
    if val is not None and rd != 0:
        out[rd] = val & M
    out[0] = 0
    return out, npc, maddr, mdata, we


if __name__ == "__main__":
    raise SystemExit(main())
