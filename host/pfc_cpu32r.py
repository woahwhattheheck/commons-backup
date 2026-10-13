#!/usr/bin/env python3
"""host/pfc_cpu32r.py — RICHER CPU + KERNEL (owner 07-19). pfc_cpu32 + a hardware stack + CALL/RET (5-bit opcode), so
programs can have subroutines — and a baked KERNEL that dispatches subroutines through the stack. Byte-exact vs an
emulator, then baked permanent into the gguf.

ISA (5-bit op, 32-bit word): HALT LDA STA ADD SUB AND OR XOR SHL SHR LT EQ JMP JZ LDI CALL RET
  CALL a: mem[SP]=PC+1; SP--; PC=a       RET: SP++; PC=mem[SP]

  python host/pfc_cpu32r.py           # build+verify+bake the richer CPU + a kernel (reversible)
  python host/pfc_cpu32r.py revert
"""
import json, os, random, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_cpu32r_genome.jsonl"
WORD = 32; NMEM = 32; AW = 5
(HALT, LDA, STA, ADD, SUB, AND, OR, XOR, SHL, SHR, LT, EQ, JMP, JZ, LDI, CALL, RET) = range(17)
MNEM = {"HALT": 0, "LDA": 1, "STA": 2, "ADD": 3, "SUB": 4, "AND": 5, "OR": 6, "XOR": 7, "SHL": 8, "SHR": 9,
        "LT": 10, "EQ": 11, "JMP": 12, "JZ": 13, "LDI": 14, "CALL": 15, "RET": 16}
ADDR_OPS = {"LDA", "STA", "ADD", "SUB", "AND", "OR", "XOR", "LT", "EQ", "JMP", "JZ", "CALL"}


def build_cpu32r():
    M = NMEM * WORD; NIN = M + AW + WORD + AW + 1                 # mem | pc | acc | sp | halt
    g = CC.CircuitCompiler(NIN); IN = g.IN
    mem = [[IN[i * WORD + b] for b in range(WORD)] for i in range(NMEM)]
    o = M; pc = [IN[o + j] for j in range(AW)]; o += AW
    acc = [IN[o + b] for b in range(WORD)]; o += WORD
    sp = [IN[o + j] for j in range(AW)]; o += AW; halt = IN[o]
    MUX1 = lambda s, a, b: g.OR(g.AND(s, a), g.AND(g.NOT(s), b))
    MUXW = lambda s, A, B: [MUX1(s, A[k], B[k]) for k in range(len(A))]
    def _or(xs):
        a = g.C0
        for x in xs: a = g.OR(a, x)
        return a
    def onehot(a, N, A):
        return [_and([a[j] if (i >> j) & 1 else g.NOT(a[j]) for j in range(A)]) for i in range(N)]
    def _and(xs):
        a = g.C1
        for x in xs: a = g.AND(a, x)
        return a
    def mux_oh(sel, buses): return [_or([g.AND(sel[i], buses[i][b]) for i in range(len(sel))]) for b in range(len(buses[0]))]
    def add_c(A, B, cin):
        out = []; c = cin
        for k in range(len(A)):
            axb = g.XOR(A[k], B[k]); out.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
        return out
    add = lambda A, B: add_c(A, B, g.C0)
    def barrel(a, amt, left):
        cur = list(a)
        for k in range(5):
            sh = 1 << k
            sd = ([g.C0] * sh + cur[:WORD - sh]) if left else (cur[sh:] + [g.C0] * sh)
            cur = [MUX1(amt[k], sd[i], cur[i]) for i in range(WORD)]
        return cur
    def is_zero(A): return g.NOT(_or(A))
    inc = lambda A: add_c(A, [g.C0] * len(A), g.C1)

    pcsel = onehot(pc, NMEM, AW); instr = mux_oh(pcsel, mem)
    opcode = instr[WORD - 5:WORD]; operand = instr[0:AW]
    opsel = onehot(opcode, 32, 5); opndsel = onehot(operand, NMEM, AW)
    spsel = onehot(sp, NMEM, AW)
    Mval = mux_oh(opndsel, mem); imm = instr[0:WORD - 5] + [g.C0] * 5    # 27-bit immediate (matches emu instr & (2^27-1))
    amt = (operand + [g.C0] * 5)[:5]
    pc_inc = inc(pc); pc1w = pc_inc + [g.C0] * (WORD - AW)         # PC+1 as a word (to push)
    sp_inc = inc(sp); sp_dec = add_c(sp, [g.C1] * AW, g.C0)        # sp+1, sp-1 (two's comp -1 = all ones + no cin)
    retsel = onehot(sp_inc, NMEM, AW); ret_word = mux_oh(retsel, mem); ret_pc = ret_word[0:AW]

    # ALU / ACC
    eq = g.C1
    for k in range(WORD): eq = g.AND(eq, g.NOT(g.XOR(acc[k], Mval[k])))
    d2 = []; c = g.C1                                            # acc - Mval, borrow = NOT carry-out
    for k in range(WORD):
        nb = g.NOT(Mval[k]); axb = g.XOR(acc[k], nb); d2.append(g.XOR(axb, c)); c = g.OR(g.AND(acc[k], nb), g.AND(axb, c))
    borrow = g.NOT(c); diff = d2
    acc_n = acc
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

    # MEMORY: STA writes acc to mem[operand]; CALL writes PC+1 to mem[SP]
    mem_n = []
    for i in range(NMEM):
        w = mem[i]
        w = MUXW(g.AND(opsel[STA], opndsel[i]), acc, w)
        w = MUXW(g.AND(opsel[CALL], spsel[i]), pc1w, w)
        mem_n.append(w)
    # PC
    pc_n = pc_inc
    pc_n = MUXW(opsel[JMP], operand, pc_n)
    pc_n = MUXW(opsel[JZ], MUXW(is_zero(acc), operand, pc_inc), pc_n)
    pc_n = MUXW(opsel[CALL], operand, pc_n)
    pc_n = MUXW(opsel[RET], ret_pc, pc_n)
    pc_n = MUXW(opsel[HALT], pc, pc_n)
    # SP
    sp_n = sp
    sp_n = MUXW(opsel[CALL], sp_dec, sp_n)
    sp_n = MUXW(opsel[RET], sp_inc, sp_n)
    halt_n = g.OR(halt, opsel[HALT])
    fmem = [MUXW(halt, mem[i], mem_n[i]) for i in range(NMEM)]
    facc = MUXW(halt, acc, acc_n); fpc = MUXW(halt, pc, pc_n); fsp = MUXW(halt, sp, sp_n)
    outs = [w for word in fmem for w in word] + fpc + facc + fsp + [halt_n]
    return g, outs


def emu(mem, pc, acc, sp, halt):
    Wm = 0xffffffff; msk = (1 << AW) - 1
    if halt: return list(mem), pc, acc, sp, 1
    instr = mem[pc]; op = (instr >> 27) & 0x1f; opd = instr & msk; imm = instr & ((1 << 27) - 1); amt = opd & 31
    mem = list(mem); npc = (pc + 1) & msk; nacc = acc; nsp = sp; nh = 0
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
    elif op == JZ: npc = opd if acc == 0 else (pc + 1) & msk
    elif op == LDI: nacc = imm & Wm
    elif op == CALL: mem[sp] = (pc + 1) & msk; nsp = (sp - 1) & msk; npc = opd
    elif op == RET: nsp = (sp + 1) & msk; npc = mem[(sp + 1) & msk] & msk
    return mem, npc, nacc, nsp, nh


def pack(mem, pc, acc, sp, halt):
    M = NMEM * WORD; inp = [0] * (M + AW + WORD + AW + 1); o = 0
    for i in range(NMEM):
        for b in range(WORD):
            if (mem[i] >> b) & 1: inp[i * WORD + b] = 1
    o = M
    for j in range(AW):
        if (pc >> j) & 1: inp[o + j] = 1
    o += AW
    for b in range(WORD):
        if (acc >> b) & 1: inp[o + b] = 1
    o += WORD
    for j in range(AW):
        if (sp >> j) & 1: inp[o + j] = 1
    o += AW; inp[o] = 1 if halt else 0
    return inp


def unpack(v, o2):
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    M = NMEM * WORD
    mem = [sum(bit(o2[i * WORD + b]) << b for b in range(WORD)) for i in range(NMEM)]
    o = M; pc = sum(bit(o2[o + j]) << j for j in range(AW)); o += AW
    acc = sum(bit(o2[o + b]) << b for b in range(WORD)); o += WORD
    sp = sum(bit(o2[o + j]) << j for j in range(AW)); o += AW; halt = bit(o2[o])
    return mem, pc, acc, sp, halt


def assemble_r(src):
    raw = []
    for line in src.splitlines():
        line = line.split(";")[0].strip()
        while ":" in line:
            i = line.index(":"); lab = line[:i].strip()
            if " " in lab or not lab: break
            raw.append(("label", lab)); line = line[i + 1:].strip()
        if line: raw.append(("instr", line.split()))
    addr = 0; labels = {}; items = []
    for kind, val in raw:
        if kind == "label": labels[val] = addr
        else: items.append((addr, val)); addr += 1
    mem = [0] * max(addr, NMEM)
    for a, parts in items:
        mn = parts[0].upper()
        if mn == ".WORD": mem[a] = int(parts[1], 0) & 0xffffffff; continue
        op = MNEM[mn]; opd = 0
        if len(parts) > 1:
            t = parts[1]; opd = labels[t] if t in labels else int(t, 0)
        if mn in ADDR_OPS and not (0 <= opd < NMEM): raise ValueError(f"addr {opd} out of range at {a}")
        mem[a] = ((op << 27) | (opd & 0x07ffffff)) & 0xffffffff
    return mem, labels


KERNEL = """
        CALL init
        CALL compute
        CALL finish
        HALT
 init:  LDI 5
        STA a
        LDI 3
        STA b
        RET
 compute: LDA a
        ADD b
        STA c
        RET
 finish: LDA c
        ADD c
        STA result
        RET
 a:     .word 0
 b:     .word 0
 c:     .word 0
 result:.word 0
"""


def run_kernel(mem):
    pc = acc = halt = 0; sp = NMEM - 1; steps = 0; m = list(mem) + [0] * (NMEM - len(mem))
    while not halt and steps < 3000:
        m, pc, acc, sp, halt = emu(m, pc, acc, sp, halt); steps += 1
    return m, steps


def journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG))
    for k in ("pfc_cpu32r", "pfc_kernel"): reg.pop(k, None)
    json.dump(reg, open(REG, "w"), indent=1); print("reverted — titan byte-exact; richer CPU + kernel removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    print("RICHER CPU (pfc_cpu32r: +stack, CALL/RET) + KERNEL.\n", flush=True)
    g, outs = build_cpu32r(); gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates); random.seed(5)
    ok = True
    for _ in range(200):
        mem = [random.getrandbits(WORD) for _ in range(NMEM)]
        pc = random.randrange(NMEM); acc = random.getrandbits(WORD); sp = random.randrange(NMEM); halt = random.randrange(2)
        v = CC.ripple_typed(g, gates, n_wire, pack(mem, pc, acc, sp, halt), 1)
        if unpack(v, o2) != emu(mem, pc, acc, sp, halt): ok = False; break
    print(f"  richer CPU: {len(gates):,} gates; byte-exact vs emulator (200 random steps, 17 ops incl CALL/RET): {ok}", flush=True)
    if not ok: print("  MISMATCH — baking nothing (fix needed)."); return 1

    kmem, klab = assemble_r(KERNEL); km, ksteps = run_kernel(kmem)
    kres = km[klab["result"]]; want = 2 * (5 + 3)
    print(f"  kernel (init/compute/finish via CALL/RET): result = {kres} (want {want}), {ksteps} ticks, byte-exact={kres==want}", flush=True)
    if kres != want: print("  kernel MISMATCH — baking CPU only.");

    reg = json.load(open(REG))
    if "pfc_cpu32r" not in reg:
        code = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}
        body = b"".join(struct.pack("<Bii", code[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in o2)
        blob = b"PFCTYPED" + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(o2)) + body
        off, tn = TC._alloc(len(blob), reg); journal(off, blob)
        reg = json.load(open(REG))
        reg["pfc_cpu32r"] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": g.n_in, "n_wire": n_wire,
                             "n_gate": len(gates), "n_out": len(o2), "format": "typed", "words": NMEM, "word": WORD,
                             "isa": "HALT LDA STA ADD SUB AND OR XOR SHL SHR LT EQ JMP JZ LDI CALL RET",
                             "role": "Muhlnickel 32-bit CPU with hardware stack + CALL/RET"}
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"  BAKED pfc_cpu32r @ {off} ({len(gates):,} gates).", flush=True)
    if kres == want and "pfc_kernel" not in reg:
        blob = b"PFCAPP01" + struct.pack("<I", NMEM) + b"".join(struct.pack("<I", w) for w in (kmem + [0] * (NMEM - len(kmem))))
        reg = json.load(open(REG)); off, tn = TC._alloc(len(blob), reg); journal(off, blob)
        reg = json.load(open(REG)); reg["pfc_kernel"] = {"tensor": tn, "offset": off, "len": len(blob), "words": NMEM,
                                                        "runs_on": "pfc_cpu32r", "role": "baked kernel (CALL/RET subroutines)"}
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"  BAKED pfc_kernel @ {off}.", flush=True)
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"\n  titan GGUF-valid: {gg}. revert: python host/pfc_cpu32r.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
