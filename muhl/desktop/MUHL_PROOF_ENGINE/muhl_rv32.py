#!/usr/bin/env python3
"""muhl_rv32.py -- RV32I ASSEMBLER + REFERENCE EMULATOR. FABRICATION TOOLING ONLY.

Owner, 2026-08-06: "DONT RECREATE DOESNT MEAN DONT PUT IT IN THE SUBSTRATE" and
"whatever that is just put it in the muhlnickel recreate it as logic dont install it
thats dumb muhlnickel has better specs than host".

So a proof checker is NOT hand-etched as gates and NOT installed on the host. It is
SOFTWARE, and the muhlnickel is the COMPUTER: the substrate already holds a real
RV32I CPU as gates -- `pfc_riscv_rv32i_v2__phys`, 67,348 gates, DEPTH 74 ticks per
instruction retired, at offset 93,732,617,344. Real machine code runs on it.

This file is a FABRICATION tool (RULE ZERO: the foundry is manufacturing, not runtime).
It never runs at runtime and never touches the container. Two jobs:
  1. ASSEMBLE mnemonics -> real RV32I machine words (the same encoding a real toolchain
     emits, which is the whole point of the core being RV32I and not a custom ISA).
  2. EMULATE those words in pure Python as an INDEPENDENT REFERENCE, so a program can be
     proven correct BEFORE a byte of it is stored -- "catch mutants BEFORE any write or
     write nothing".

No numpy (permanently banned in this repo). Pure Python ints and lists.
"""

XLEN = 32
MASK = 0xFFFFFFFF

# ---------------------------------------------------------------- register names
REGS = {"x%d" % i: i for i in range(32)}
REGS.update({
    "zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4,
    "t0": 5, "t1": 6, "t2": 7, "s0": 8, "fp": 8, "s1": 9,
    "a0": 10, "a1": 11, "a2": 12, "a3": 13, "a4": 14, "a5": 15, "a6": 16, "a7": 17,
    "s2": 18, "s3": 19, "s4": 20, "s5": 21, "s6": 22, "s7": 23, "s8": 24, "s9": 25,
    "s10": 26, "s11": 27, "t3": 28, "t4": 29, "t5": 30, "t6": 31,
})

OPC_OPIMM = 0x13
OPC_OP    = 0x33
OPC_LOAD  = 0x03
OPC_STORE = 0x23
OPC_BR    = 0x63
OPC_JAL   = 0x6F
OPC_JALR  = 0x67
OPC_LUI   = 0x37
OPC_AUIPC = 0x17

# mnemonic -> (kind, opcode, funct3, funct7)
ISA = {
    "add":  ("R", OPC_OP, 0x0, 0x00), "sub":  ("R", OPC_OP, 0x0, 0x20),
    "sll":  ("R", OPC_OP, 0x1, 0x00), "slt":  ("R", OPC_OP, 0x2, 0x00),
    "sltu": ("R", OPC_OP, 0x3, 0x00), "xor":  ("R", OPC_OP, 0x4, 0x00),
    "srl":  ("R", OPC_OP, 0x5, 0x00), "sra":  ("R", OPC_OP, 0x5, 0x20),
    "or":   ("R", OPC_OP, 0x6, 0x00), "and":  ("R", OPC_OP, 0x7, 0x00),

    "addi": ("I", OPC_OPIMM, 0x0, None), "slti": ("I", OPC_OPIMM, 0x2, None),
    "sltiu":("I", OPC_OPIMM, 0x3, None), "xori": ("I", OPC_OPIMM, 0x4, None),
    "ori":  ("I", OPC_OPIMM, 0x6, None), "andi": ("I", OPC_OPIMM, 0x7, None),
    "slli": ("SH", OPC_OPIMM, 0x1, 0x00), "srli": ("SH", OPC_OPIMM, 0x5, 0x00),
    "srai": ("SH", OPC_OPIMM, 0x5, 0x20),

    "lw":   ("IL", OPC_LOAD, 0x2, None),
    "sw":   ("S",  OPC_STORE, 0x2, None),

    "beq":  ("B", OPC_BR, 0x0, None), "bne": ("B", OPC_BR, 0x1, None),
    "blt":  ("B", OPC_BR, 0x4, None), "bge": ("B", OPC_BR, 0x5, None),
    "bltu": ("B", OPC_BR, 0x6, None), "bgeu":("B", OPC_BR, 0x7, None),

    "jal":  ("J",  OPC_JAL, None, None),
    "jalr": ("IL", OPC_JALR, 0x0, None),
    "lui":  ("U",  OPC_LUI, None, None),
    "auipc":("U",  OPC_AUIPC, None, None),
}


def _r(tok):
    t = tok.strip().rstrip(",")
    if t not in REGS:
        raise ValueError("not a register: %r" % tok)
    return REGS[t]


def _sx(v, bits):
    """sign-extend a `bits`-wide two's complement value to a Python int"""
    v &= (1 << bits) - 1
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def enc_r(op, f3, f7, rd, rs1, rs2):
    return ((f7 & 0x7F) << 25) | ((rs2 & 31) << 20) | ((rs1 & 31) << 15) | \
           ((f3 & 7) << 12) | ((rd & 31) << 7) | (op & 0x7F)


def enc_i(op, f3, rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | ((rs1 & 31) << 15) | ((f3 & 7) << 12) | \
           ((rd & 31) << 7) | (op & 0x7F)


def enc_s(op, f3, rs1, rs2, imm):
    imm &= 0xFFF
    return ((imm >> 5) << 25) | ((rs2 & 31) << 20) | ((rs1 & 31) << 15) | \
           ((f3 & 7) << 12) | ((imm & 0x1F) << 7) | (op & 0x7F)


def enc_b(op, f3, rs1, rs2, imm):
    """imm is a BYTE offset, must be even; bit layout [12|10:5] rs2 rs1 f3 [4:1|11]"""
    imm &= 0x1FFF
    b12 = (imm >> 12) & 1; b11 = (imm >> 11) & 1
    b10_5 = (imm >> 5) & 0x3F; b4_1 = (imm >> 1) & 0xF
    return (b12 << 31) | (b10_5 << 25) | ((rs2 & 31) << 20) | ((rs1 & 31) << 15) | \
           ((f3 & 7) << 12) | (b4_1 << 8) | (b11 << 7) | (op & 0x7F)


def enc_u(op, rd, imm):
    return ((imm & 0xFFFFF) << 12) | ((rd & 31) << 7) | (op & 0x7F)


def enc_j(op, rd, imm):
    """imm is a BYTE offset; layout [20|10:1|11|19:12]"""
    imm &= 0x1FFFFF
    b20 = (imm >> 20) & 1; b10_1 = (imm >> 1) & 0x3FF
    b11 = (imm >> 11) & 1; b19_12 = (imm >> 12) & 0xFF
    return (b20 << 31) | (b10_1 << 21) | (b11 << 20) | (b19_12 << 12) | \
           ((rd & 31) << 7) | (op & 0x7F)


def assemble(src, base=0):
    """Two-pass assembler. Returns (words, labels). Addresses are BYTE addresses from `base`.

    Supported directives: `.word <int|label>`. Labels are `name:`. `li rd, imm` is the one
    pseudo-instruction (expands to lui+addi or a single addi), because writing 32-bit
    constants by hand is where hand-assembly goes wrong.
    """
    # ---- pass 0: tokenize into (label|instr) preserving order
    items = []
    for raw in src.splitlines():
        line = raw.split("#")[0].split(";")[0].strip()
        while ":" in line:
            i = line.index(":")
            lab = line[:i].strip()
            if not lab or " " in lab:
                break
            items.append(("label", lab))
            line = line[i + 1:].strip()
        if line:
            items.append(("instr", line))

    # ---- pass 1: assign addresses (li may take 2 words)
    addr = base
    labels = {}
    sized = []
    for kind, val in items:
        if kind == "label":
            labels[val] = addr
            continue
        parts = val.replace(",", " ").split()
        mn = parts[0].lower()
        if mn == "li":
            imm = None
            try:
                imm = int(parts[2], 0)
            except ValueError:
                imm = None                      # a label -> always 2 words, keep it stable
            n = 1 if (imm is not None and -2048 <= imm < 2048) else 2
        else:
            n = 1
        sized.append((addr, parts, n))
        addr += 4 * n

    # ---- pass 2: emit
    words = []
    for a, parts, n in sized:
        mn = parts[0].lower()

        if mn == ".word":
            t = parts[1]
            v = labels[t] if t in labels else int(t, 0)
            words.append(v & MASK)
            continue

        if mn == "li":
            rd = _r(parts[1])
            t = parts[2]
            imm = labels[t] if t in labels else int(t, 0)
            if n == 1:
                words.append(enc_i(OPC_OPIMM, 0x0, rd, 0, imm & 0xFFF))
            else:
                # lui gets imm[31:12] with the +0x800 round so addi's sign-extension cancels
                hi = ((imm + 0x800) >> 12) & 0xFFFFF
                lo = imm - (_sx(hi, 20) << 12)
                words.append(enc_u(OPC_LUI, rd, hi))
                words.append(enc_i(OPC_OPIMM, 0x0, rd, rd, lo & 0xFFF))
            continue

        if mn not in ISA:
            raise ValueError("unknown mnemonic %r at byte %d" % (mn, a))
        kind, op, f3, f7 = ISA[mn]

        if kind == "R":
            words.append(enc_r(op, f3, f7, _r(parts[1]), _r(parts[2]), _r(parts[3])))

        elif kind == "I":
            t = parts[3]
            imm = labels[t] if t in labels else int(t, 0)
            words.append(enc_i(op, f3, _r(parts[1]), _r(parts[2]), imm & 0xFFF))

        elif kind == "SH":
            words.append(enc_r(op, f3, f7, _r(parts[1]), _r(parts[2]), int(parts[3], 0) & 31))

        elif kind == "IL":
            # lw rd, off(rs1)  |  jalr rd, off(rs1)
            rd = _r(parts[1])
            rest = "".join(parts[2:])
            off_s, rs1_s = rest.split("(")
            rs1 = _r(rs1_s.rstrip(")"))
            off = labels[off_s] if off_s in labels else int(off_s or "0", 0)
            words.append(enc_i(op, f3, rd, rs1, off & 0xFFF))

        elif kind == "S":
            rs2 = _r(parts[1])
            rest = "".join(parts[2:])
            off_s, rs1_s = rest.split("(")
            rs1 = _r(rs1_s.rstrip(")"))
            off = labels[off_s] if off_s in labels else int(off_s or "0", 0)
            words.append(enc_s(op, f3, rs1, rs2, off & 0xFFF))

        elif kind == "B":
            t = parts[3]
            tgt = labels[t] if t in labels else int(t, 0)
            words.append(enc_b(op, f3, _r(parts[1]), _r(parts[2]), (tgt - a) & 0x1FFF))

        elif kind == "J":
            t = parts[2]
            tgt = labels[t] if t in labels else int(t, 0)
            words.append(enc_j(op, _r(parts[1]), (tgt - a) & 0x1FFFFF))

        elif kind == "U":
            words.append(enc_u(op, _r(parts[1]), int(parts[2], 0) & 0xFFFFF))

        else:
            raise ValueError("unhandled kind %r" % kind)

    return words, labels


# ==================================================================== reference emulator
def emulate(mem_words, base, pc, max_steps=2_000_000, halt_pc=None):
    """INDEPENDENT RV32I REFERENCE. `mem_words` is a dict {byte_addr -> word} OR a list
    indexed from `base`. Returns (regs, steps, halted, mem). Word-addressed loads/stores only
    (lw/sw), which is all the checker program uses.

    This is a fabrication-time reference so a program can be proven correct BEFORE storage.
    It is NOT a runtime executor and never runs against the container.
    """
    if isinstance(mem_words, list):
        mem = {base + 4 * i: w & MASK for i, w in enumerate(mem_words)}
    else:
        mem = dict(mem_words)

    regs = [0] * 32
    steps = 0
    halted = False

    def ld(a):
        return mem.get(a & ~3, 0) & MASK

    while steps < max_steps:
        if halt_pc is not None and pc == halt_pc:
            halted = True
            break
        instr = ld(pc)
        if instr == 0:                      # all-zero word is not a valid RV32I instruction
            halted = True
            break
        op = instr & 0x7F
        rd = (instr >> 7) & 31
        f3 = (instr >> 12) & 7
        rs1 = (instr >> 15) & 31
        rs2 = (instr >> 20) & 31
        f7 = (instr >> 25) & 0x7F
        npc = (pc + 4) & MASK
        a1 = regs[rs1]
        a2 = regs[rs2]
        val = None

        # RV32I selects SUB/SRA on BIT 30 ALONE, not on funct7 == 0x20. Measured 2026-08-06
        # against the owner's stored gate core: it reads f7_5 = I[30] and is spec-correct;
        # this reference was over-constrained and disagreed on 6 of 624 encodings. The gates
        # were right. Fixed here, not there.
        alt = (instr >> 30) & 1
        if op == OPC_OP:
            if f3 == 0x0: val = (a1 - a2) & MASK if alt else (a1 + a2) & MASK
            elif f3 == 0x1: val = (a1 << (a2 & 31)) & MASK
            elif f3 == 0x2: val = 1 if _sx(a1, 32) < _sx(a2, 32) else 0
            elif f3 == 0x3: val = 1 if a1 < a2 else 0
            elif f3 == 0x4: val = a1 ^ a2
            elif f3 == 0x5: val = (_sx(a1, 32) >> (a2 & 31)) & MASK if alt else a1 >> (a2 & 31)
            elif f3 == 0x6: val = a1 | a2
            elif f3 == 0x7: val = a1 & a2

        elif op == OPC_OPIMM:
            imm = _sx((instr >> 20) & 0xFFF, 12)
            sh = (instr >> 20) & 31
            if f3 == 0x0: val = (a1 + imm) & MASK
            elif f3 == 0x1: val = (a1 << sh) & MASK
            elif f3 == 0x2: val = 1 if _sx(a1, 32) < imm else 0
            elif f3 == 0x3: val = 1 if a1 < (imm & MASK) else 0
            elif f3 == 0x4: val = a1 ^ (imm & MASK)
            elif f3 == 0x5: val = (_sx(a1, 32) >> sh) & MASK if alt else a1 >> sh
            elif f3 == 0x6: val = a1 | (imm & MASK)
            elif f3 == 0x7: val = a1 & (imm & MASK)

        elif op == OPC_LOAD:
            imm = _sx((instr >> 20) & 0xFFF, 12)
            val = ld((a1 + imm) & MASK)

        elif op == OPC_STORE:
            imm = _sx((((instr >> 25) & 0x7F) << 5) | ((instr >> 7) & 0x1F), 12)
            mem[(a1 + imm) & MASK & ~3] = a2 & MASK

        elif op == OPC_BR:
            imm = _sx((((instr >> 31) & 1) << 12) | (((instr >> 7) & 1) << 11) |
                      (((instr >> 25) & 0x3F) << 5) | (((instr >> 8) & 0xF) << 1), 13)
            s1, s2 = _sx(a1, 32), _sx(a2, 32)
            take = (f3 == 0 and a1 == a2) or (f3 == 1 and a1 != a2) or \
                   (f3 == 4 and s1 < s2) or (f3 == 5 and s1 >= s2) or \
                   (f3 == 6 and a1 < a2) or (f3 == 7 and a1 >= a2)
            if take:
                npc = (pc + imm) & MASK

        elif op == OPC_JAL:
            imm = _sx((((instr >> 31) & 1) << 20) | (((instr >> 12) & 0xFF) << 12) |
                      (((instr >> 20) & 1) << 11) | (((instr >> 21) & 0x3FF) << 1), 21)
            val = npc
            npc = (pc + imm) & MASK

        elif op == OPC_JALR:
            imm = _sx((instr >> 20) & 0xFFF, 12)
            val = npc
            npc = (a1 + imm) & MASK & ~1

        elif op == OPC_LUI:
            val = (instr & 0xFFFFF000) & MASK

        elif op == OPC_AUIPC:
            val = (pc + (instr & 0xFFFFF000)) & MASK

        else:
            halted = True
            break

        if val is not None and rd != 0:
            regs[rd] = val & MASK
        regs[0] = 0
        pc = npc
        steps += 1

    return regs, steps, halted, mem
