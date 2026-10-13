#!/usr/bin/env python3
"""host/pfc_fwd_engine2.py — THE FORWARD ENGINE WITH A MEMORY PORT (fabrication only, one-and-done, before runtime).

WHY: pfc_fwd_engine's ISA (ADD SUB MUL SILU EXP RSQRT GT MOV) is a FULL 3-bit opcode field with no way to read storage,
so its programs can only recombine seeded registers and immediates baked at fab time. Lengthening the ROM changes
nothing. The binding constraint is the missing LOAD. This adds it.

HOW (PFC_HARD_WON s1 -- "connection = a shared physical storage location"): the engine is wired to pfc_mmu IN SERIES,
IN STORAGE. No netlist composition (titan_circuit has no instantiate API) and no host in the loop:
  - the engine's ADDR-OUT bytes ARE the MMU's `addr` input bytes
  - the MMU's `fast_read` bytes ARE the engine's LDATA input bytes
Two new ops carry it:
  SETA rA,imm -> addr_out = regs[rA] + imm      (address arithmetic is ordinary ALU work)
  LDX  -> rD  -> regs[rD]  = ldata              (latch whatever the MMU settled into the shared location)

Opcode field widened 3 -> 4 bits (microcode 26 -> 27 bits). Register file layout is UNCHANGED and regs stay first, so
regs[ANSREG] keeps its byte offset and the PROVEN fwd_answer shared-location wire is not disturbed.

  python host/pfc_fwd_engine2.py verify    # build + byte-exact check IN THE TOOL. titan.gguf untouched.
  python host/pfc_fwd_engine2.py fab       # only after verify passes: store reversibly
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC
from sdc_bake_cpu import _ref, SC, _s16
from pfc_fwd_engine import _alu, q88, from_q88, _cd

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
NAME = "pfc_fwd_engine2"
NREG = 8; RW = 16; PCW = 5; AW = 40                    # 8 regs x 16b, 5-bit pc, 40-bit address (matches pfc_mmu)
STATE_BITS = NREG * RW + PCW + 1 + AW                  # regs | pc | halt | addr_out
OPC = {"ADD": 0, "SUB": 1, "MUL": 2, "SILU": 3, "EXP": 4, "RSQRT": 5, "GT": 6, "MOV": 7, "SETA": 8, "LDX": 9, "BRNZ": 10}
ANSREG = 6

# demo program exercising the memory port: address a cell, latch it, use it in arithmetic
PROGRAM = [
    ("SETA", 0, 1, 0x0010, 0),                         # 0: addr_out = regs[0] + 0x10   (address the model)
    ("LDX",  0, 0, 0, 4),                              # 1: R4 = ldata                  (latch the real bytes)
    ("ADD",  6, 0, 4, 6),                              # 2: R6 += R4                    (accumulate <- ANSREG)
    ("ADD",  0, 1, 2, 0),                              # 3: R0 += 2                     (next word)
    ("SUB",  7, 1, 1, 7),                              # 4: R7 -= 1                     (loop counter)
    ("BRNZ", 7, 1, 0, 0),                              # 5: if R7 != 0 -> pc = 0        THE LOOP
]
PROGLEN = len(PROGRAM)


def _microcode(op, rA, useImm, immB, rD):              # 27 bits: op(4) rA(3) useImm(1) immB(16) rD(3)
    return (OPC[op] & 15) | (rA & 7) << 4 | (useImm & 1) << 7 | (immB & 0xFFFF) << 8 | (rD & 7) << 24


def ref_run(x_q88, ldata, addr0=0):
    """reference interpreter — the byte-exact target the fabricated circuit must match."""
    regs = [0] * NREG
    for i, v in enumerate(x_q88[:NREG]): regs[i] = v & 0xFFFF
    pc = 0; addr = addr0; guard = 0
    while pc < PROGLEN and guard < 256:
        guard += 1
        op, rA, useImm, immB, rD = PROGRAM[pc]
        A = regs[rA]; B = immB if useImm else regs[immB & 7]
        if op == "SETA":   addr = (addr + A + B) & ((1 << AW) - 1); pc += 1
        elif op == "LDX":  regs[rD] = ldata & 0xFFFF; pc += 1
        elif op == "BRNZ": pc = (immB & ((1 << PCW) - 1)) if A != 0 else pc + 1
        else:              regs[rD] = _ref(OPC[op], A, B) & 0xFFFF; pc += 1
    return regs, addr


def build_engine():
    c = TC.Circuit(STATE_BITS + RW + 1)                # state | ldata(16, shared location w/ MMU fast_read) | clk
    IN = c.IN
    regs = [IN[r * RW:(r + 1) * RW] for r in range(NREG)]
    base = NREG * RW
    pc = IN[base: base + PCW]
    halt = IN[base + PCW]
    addr_out = IN[base + PCW + 1: base + PCW + 1 + AW]
    ldata = IN[STATE_BITS: STATE_BITS + RW]
    clk = IN[STATE_BITS + RW]

    def mux_tree(sel_bits, nodes, w):
        nd = [list(n) for n in nodes]
        for s in sel_bits:
            nd = [[c.mux(s, nd[j][b], nd[j + 1][b]) for b in range(w)] for j in range(0, len(nd), 2)]
        return nd[0]
    def pad(nodes, n, w): return nodes + [c.cvec(0, w) for _ in range(n - len(nodes))]

    rom = pad([c.cvec(_microcode(*ins), 27) for ins in PROGRAM], 1 << PCW, 27)
    mc = mux_tree(list(pc), rom, 27)
    op = mc[0:4]; rA = mc[4:7]; useImm = mc[7]; immB = mc[8:24]; rD = mc[24:27]

    A = mux_tree(list(rA), pad(regs, 8, RW), RW)
    regB = mux_tree(list(immB[0:3]), pad(regs, 8, RW), RW)
    B = [c.mux(useImm, regB[b], immB[b]) for b in range(RW)]

    alu = _alu(c, op[0:3], A, B)                       # the existing datapath, selected by the low 3 opcode bits
    is_ldx = c.eq_const(op, OPC["LDX"])
    is_seta = c.eq_const(op, OPC["SETA"])
    result = [c.mux(is_ldx, alu[b], ldata[b]) for b in range(RW)]   # LDX writes back the shared-location load data

    is_brnz = c.eq_const(op, OPC["BRNZ"])
    step = c.and_(clk, c.not_(halt))
    wr = c.and_(step, c.not_(c.or_(is_seta, is_brnz))) # SETA writes the address bus; BRNZ writes only the pc
    next_regs = []
    for r in range(NREG):
        is_dst = c.and_(c.eq_const(rD, r), wr)
        next_regs.append([c.mux(is_dst, regs[r][b], result[b]) for b in range(RW)])

    # ADDR-OUT: on SETA, addr_out = A + B (zero-extended to AW). These bytes ARE the MMU's addr input (shared location).
    # SETA ACCUMULATES: addr_out += (A + B), full 40-bit width. Registers are 16-bit, so one SETA can advance the
    # address by at most 64KB -- but the bus is 40 bits, so iterating SETA reaches the entire 24.6GB model. Without
    # this the address was a 16-bit value zero-extended, capping reach at the model's first 64KB.
    sum_ab = c.add(list(A), list(B))
    delta = sum_ab + [c.cvec(0, 1)[0]] * (AW - RW)
    new_addr = c.add(list(addr_out), delta)[:AW]
    set_now = c.and_(step, is_seta)
    next_addr = [c.mux(set_now, addr_out[b], new_addr[b]) for b in range(AW)]

    pc_inc = c.add(list(pc), c.cvec(1, PCW))
    # BRNZ: pc = imm when regs[rA] != 0, else pc+1. This is the LOOP -- without it a program is 32 straight-line
    # instructions and cannot walk a 4096-element dot product.
    taken = c.and_(is_brnz, c.not_(c.is_zero(list(A))))
    seq_pc = [c.mux(taken, pc_inc[b], immB[b]) for b in range(PCW)]
    next_pc = [c.mux(step, pc[b], seq_pc[b]) for b in range(PCW)]
    next_halt = c.or_(halt, c.eq_const(next_pc, PROGLEN))

    outs = []
    for r in range(NREG): outs += next_regs[r]
    outs += next_pc; outs += [next_halt]; outs += next_addr
    return c, outs


def _sim(cd, regs, pc, halt, addr, ldata, clk):
    inb = []
    for r in range(NREG): inb += [(regs[r] >> b) & 1 for b in range(RW)]
    inb += [(pc >> b) & 1 for b in range(PCW)] + [halt & 1]
    inb += [(addr >> b) & 1 for b in range(AW)]
    inb += [(ldata >> b) & 1 for b in range(RW)] + [clk & 1]
    v = TC.ripple(cd, inb)                       # FABRICATION-TIME verification only (the one sanctioned host eval)
    nr = [sum(v[r * RW + b] << b for b in range(RW)) for r in range(NREG)]
    o = NREG * RW
    npc = sum(v[o + b] << b for b in range(PCW)); nhalt = v[o + PCW]
    naddr = sum(v[o + PCW + 1 + b] << b for b in range(AW))
    return nr, npc, nhalt, naddr


def verify(trials=8):
    c, outs = build_engine()
    print(f"  built {NAME}: {len(c.ga):,} gates · state {STATE_BITS} b (regs|pc|halt|addr{AW}) · ISA {len(OPC)} ops", flush=True)
    cd = _cd(c, outs)                                   # in-memory circuit -> the dict TC.ripple wants
    import random; random.seed(7)
    ok = 0
    for t in range(trials):
        xs = [random.randint(0, 0xFFFF) for _ in range(NREG)]
        xs[7] = random.randint(1, 4)          # loop counter: small + bounded, so ref and circuit run the same passes
        xs[6] = 0                             # accumulator starts clean
        ld = random.randint(0, 0xFFFF)
        addr0 = random.randint(0, (1 << 24) - 1)
        regs = list(xs); pc = 0; halt = 0; addr = addr0; ticks = 0
        while not halt and ticks < 256:
            regs, pc, halt, addr = _sim(cd, regs, pc, halt, addr, ld, 1); ticks += 1
        rr, ra = ref_run(xs, ld, addr0)
        good = (regs == rr and addr == ra)
        ok += good
        if not good:
            print(f"    trial {t}: MISMATCH regs={regs[:7]} ref={rr[:7]} addr={addr} refaddr={ra}", flush=True)
    print(f"  byte-exact vs reference (regs + address bus): {ok}/{trials}", flush=True)
    return c, outs, ok == trials


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    c, outs, good = verify()
    if not good:
        print("  VERIFY FAILED — nothing stored, titan.gguf untouched."); return 1
    if cmd != "fab":
        print("  verify only. titan.gguf untouched. run `fab` to store."); return 0
    info = TC.store(NAME, c, outs)
    reg = json.load(open(REG))
    reg[NAME].update({"state_bits": STATE_BITS, "nreg": NREG, "rw": RW, "pcw": PCW, "aw": AW,
                      "proglen": PROGLEN, "ansreg": ANSREG, "isa": " ".join(OPC),
                      "wiring": "SERIES IN STORAGE with pfc_mmu: addr_out bytes ARE mmu.addr; mmu.fast_read bytes ARE ldata"})
    json.dump(reg, open(REG, "w"), indent=1)
    print(f"  stored {NAME} @ {info}. reversible via genome.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
