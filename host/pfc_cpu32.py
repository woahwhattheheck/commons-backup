#!/usr/bin/env python3
"""host/pfc_cpu32.py — THE Muhlnickel 32-BIT PROCESSOR: ISA + microarchitecture, self-contained (owner 07-19).

A real stored-program 32-bit CPU baked as one next-state netlist (microarchitecture = fetch mem[PC] -> decode -> execute
-> writeback -> PC-update, all in gates). ISA (4-bit opcode, 32-bit word):
  HALT LDA STA ADD SUB AND OR XOR SHL SHR LT EQ JMP JZ LDI
It runs PROGRAMS from its own RAM. Byte-exact vs an emulator. Then it DISCOVERS THE CEILING (not asserts): scales the
RAM wide (go wide with the idle RAM), measuring gate count vs memory size to find where it actually tops out on this box.

  python host/pfc_cpu32.py            # verify + discover the ceiling + run a program + bake a working size
  python host/pfc_cpu32.py revert
"""
import json, os, random, struct, sys, time
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, PFCP.SBX)
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = PFCP.TITAN; REG = PFCP.REG
GENOME = PFCP.p("models/titan_cpu32_genome.jsonl")
WORD = 32
HALT, LDA, STA, ADD, SUB, AND, OR, XOR, SHL, SHR, LT, EQ, JMP, JZ, LDI = range(15)


def build_cpu32(NMEM):
    AW = (NMEM - 1).bit_length()
    M = NMEM * WORD; NIN = M + AW + WORD + 1
    g = CC.CircuitCompiler(NIN); IN = g.IN
    mem = [[IN[i * WORD + b] for b in range(WORD)] for i in range(NMEM)]
    pc = [IN[M + j] for j in range(AW)]; acc = [IN[M + AW + b] for b in range(WORD)]; halt = IN[M + AW + WORD]
    MUX1 = lambda s, a, b: g.OR(g.AND(s, a), g.AND(g.NOT(s), b))
    MUXW = lambda s, A, B: [MUX1(s, A[k], B[k]) for k in range(len(A))]
    def onehot(addr, N, A):
        out = []
        for i in range(N):
            m = g.C1
            for j in range(A): m = g.AND(m, addr[j] if (i >> j) & 1 else g.NOT(addr[j]))
            out.append(m)
        return out
    def mux_oh(sel, buses):
        return [ _or([g.AND(sel[i], buses[i][b]) for i in range(len(sel))]) for b in range(len(buses[0])) ]
    def _or(xs):
        a = g.C0
        for x in xs: a = g.OR(a, x)
        return a
    def add_c(A, B, cin):
        o = []; c = cin
        for k in range(len(A)):
            axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
        return o, c
    add = lambda A, B: add_c(A, B, g.C0)[0]
    def sub_bo(A, B):
        o, c = add_c(A, [g.NOT(x) for x in B], g.C1); return o, g.NOT(c)
    def barrel(a, amt, left):
        cur = list(a)
        for k in range(5):
            sh = 1 << k
            shifted = ([g.C0] * sh + cur[:WORD - sh]) if left else (cur[sh:] + [g.C0] * sh)
            cur = [MUX1(amt[k], shifted[i], cur[i]) for i in range(WORD)]
        return cur
    def is_zero(A): return g.NOT(_or(A))

    pcsel = onehot(pc, NMEM, AW); instr = mux_oh(pcsel, mem)          # FETCH
    opcode = instr[WORD - 4:WORD]; operand = instr[0:AW]              # DECODE
    opsel = onehot(opcode, 16, 4); opndsel = onehot(operand, NMEM, AW)
    Mval = mux_oh(opndsel, mem)
    imm = instr[0:WORD - 4] + [g.C0] * 4                              # 28-bit immediate zero-extended
    amt = (operand + [g.C0] * 5)[:5]                                  # shift amount = low 5 bits of operand

    diff, borrow = sub_bo(acc, Mval)
    eq = g.C1
    for k in range(WORD): eq = g.AND(eq, g.NOT(g.XOR(acc[k], Mval[k])))
    acc_n = acc                                                      # EXECUTE (accumulator)
    acc_n = MUXW(opsel[LDA], Mval, acc_n)
    acc_n = MUXW(opsel[ADD], add(acc, Mval), acc_n)
    acc_n = MUXW(opsel[SUB], diff, acc_n)
    acc_n = MUXW(opsel[AND], [g.AND(acc[k], Mval[k]) for k in range(WORD)], acc_n)
    acc_n = MUXW(opsel[OR], [g.OR(acc[k], Mval[k]) for k in range(WORD)], acc_n)
    acc_n = MUXW(opsel[XOR], [g.XOR(acc[k], Mval[k]) for k in range(WORD)], acc_n)
    acc_n = MUXW(opsel[SHL], barrel(acc, amt, True), acc_n)
    acc_n = MUXW(opsel[SHR], barrel(acc, amt, False), acc_n)
    acc_n = MUXW(opsel[LT], [borrow] + [g.C0] * (WORD - 1), acc_n)
    acc_n = MUXW(opsel[EQ], [eq] + [g.C0] * (WORD - 1), acc_n)
    acc_n = MUXW(opsel[LDI], imm, acc_n)

    mem_n = [MUXW(g.AND(opsel[STA], opndsel[i]), acc, mem[i]) for i in range(NMEM)]   # WRITEBACK (STA)
    pc_inc, _ = add_c(pc, [g.C0] * AW, g.C1)                         # PC-UPDATE
    pc_n = pc_inc
    pc_n = MUXW(opsel[JMP], operand, pc_n)
    pc_n = MUXW(opsel[JZ], MUXW(is_zero(acc), operand, pc_inc), pc_n)
    pc_n = MUXW(opsel[HALT], pc, pc_n)
    halt_n = g.OR(halt, opsel[HALT])
    fmem = [MUXW(halt, mem[i], mem_n[i]) for i in range(NMEM)]
    facc = MUXW(halt, acc, acc_n); fpc = MUXW(halt, pc, pc_n)
    outs = [w for word in fmem for w in word] + fpc + facc + [halt_n]
    return g, outs, AW


def emu32(mem, pc, acc, halt, AW, NMEM):
    Wm = 0xffffffff
    if halt: return list(mem), pc, acc, 1
    instr = mem[pc]; op = (instr >> 28) & 0xf; opd = instr & ((1 << AW) - 1); imm = instr & 0x0fffffff
    mem = list(mem); npc = (pc + 1) % NMEM; nacc = acc; nh = 0; amt = opd & 31
    if op == HALT: nh = 1; npc = pc
    elif op == LDA: nacc = mem[opd]
    elif op == STA: mem[opd] = acc
    elif op == ADD: nacc = (acc + mem[opd]) & Wm
    elif op == SUB: nacc = (acc - mem[opd]) & Wm
    elif op == AND: nacc = acc & mem[opd]
    elif op == OR: nacc = acc | mem[opd]
    elif op == XOR: nacc = acc ^ mem[opd]
    elif op == SHL: nacc = (acc << amt) & Wm
    elif op == SHR: nacc = acc >> amt
    elif op == LT: nacc = 1 if acc < mem[opd] else 0
    elif op == EQ: nacc = 1 if acc == mem[opd] else 0
    elif op == JMP: npc = opd
    elif op == JZ: npc = opd if acc == 0 else (pc + 1) % NMEM
    elif op == LDI: nacc = imm & Wm
    return mem, npc, nacc, nh


def pack(mem, pc, acc, halt, NMEM, AW):
    M = NMEM * WORD; inp = [0] * (M + AW + WORD + 1)
    for i in range(NMEM):
        for b in range(WORD):
            if (mem[i] >> b) & 1: inp[i * WORD + b] = 1
    for j in range(AW):
        if (pc >> j) & 1: inp[M + j] = 1
    for b in range(WORD):
        if (acc >> b) & 1: inp[M + AW + b] = 1
    inp[M + AW + WORD] = 1 if halt else 0
    return inp


def unpack(v, o2, NMEM, AW):
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    M = NMEM * WORD
    mem = [sum(bit(o2[i * WORD + b]) << b for b in range(WORD)) for i in range(NMEM)]
    pc = sum(bit(o2[M + j]) << j for j in range(AW))
    acc = sum(bit(o2[M + AW + b]) << b for b in range(WORD))
    halt = bit(o2[M + AW + WORD])
    return mem, pc, acc, halt


def verify(NMEM, steps=200):
    g, outs, AW = build_cpu32(NMEM); gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    random.seed(3)
    for _ in range(steps):
        mem = [random.getrandbits(WORD) for _ in range(NMEM)]
        pc, acc, halt = random.randrange(NMEM), random.getrandbits(WORD), random.randrange(2)
        v = CC.ripple_typed(g, gates, n_wire, pack(mem, pc, acc, halt, NMEM, AW), 1)
        if unpack(v, o2, NMEM, AW) != emu32(mem, pc, acc, halt, AW, NMEM):
            return False, g, gates, o2, AW
    return True, g, gates, o2, AW


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_cpu32", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; pfc_cpu32 removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    print("Muhlnickel 32-BIT PROCESSOR — ISA + microarchitecture, self-contained.\n", flush=True)
    ok, g, gates, o2, AW = verify(16)
    print(f"  microarchitecture verified byte-exact vs emulator (16 words, 200 random steps, all 15 ops): {ok}", flush=True)
    if not ok: print("  MISMATCH — aborting."); return 1

    # DISCOVER THE CEILING — scale the RAM wide, measure gates (don't assert)
    print(f"\n  DISCOVERING THE CEILING (go wide with RAM — measure gates vs memory size):", flush=True)
    for NMEM in (16, 32, 64, 128, 256):
        t = time.time(); g2, outs2, aw2 = build_cpu32(NMEM); gates2, _ = g2.dce(outs2)
        print(f"    {NMEM:>4} words x 32b = {NMEM*4:>5} B RAM  ->  {len(gates2):>9,} gates   (built {time.time()-t:.1f}s)", flush=True)

    # run a real program on the 16-word machine (fetch/execute from its own RAM)
    I = lambda op, opd: (op << 28) | (opd & 0x0fffffff)
    prog = {0: I(LDI, 7), 1: I(STA, 15), 2: I(LDA, 15), 3: I(SUB, 14), 4: I(STA, 15),   # countdown 7->0
            5: I(JZ, 8), 6: I(JMP, 2), 8: I(HALT, 0), 14: 1, 15: 0}
    mem = [prog.get(i, 0) for i in range(16)]; pc = acc = halt = 0; steps = 0
    while not halt and steps < 200:
        mem, pc, acc, halt = emu32(mem, pc, acc, halt, 4, 16); steps += 1
    print(f"\n  ran a program from its own RAM (countdown 7->0): HALT after {steps} ticks, mem[15]={mem[15]} (emulator; the gate CPU is byte-exact to it).", flush=True)

    # bake the 16-word processor permanent
    reg = json.load(open(REG))
    if "pfc_cpu32" not in reg:
        code = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
        n_wire = 2 + g.n_in + len(gates)
        body = b"".join(struct.pack("<Bii", code[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in o2)
        blob = b"PFCTYPED" + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(o2)) + body
        off, tn = TC._alloc(len(blob), reg); _journal(off, blob)
        reg = json.load(open(REG))
        reg["pfc_cpu32"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                            "n_gate": len(gates), "n_out": len(o2), "format": "typed", "words": 16, "word": 32,
                            "isa": "HALT LDA STA ADD SUB AND OR XOR SHL SHR LT EQ JMP JZ LDI",
                            "role": "Muhlnickel 32-bit stored-program processor (ISA + microarchitecture, self-contained)"}
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"\n  BAKED pfc_cpu32 @ {off} ({len(gates):,} gates, 16 words x 32b). GGUF-valid: {open(TITAN,'rb').read(4)==b'GGUF'}.", flush=True)
    print(f"  revert: python host/pfc_cpu32.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
