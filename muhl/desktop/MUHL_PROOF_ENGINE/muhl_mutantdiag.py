#!/usr/bin/env python3
"""muhl_mutantdiag.py -- WHICH single-bit instruction mutants survive, and WHY.

Not a bar adjustment. The functional battery only ever gets HARDER here: every distinct
check in the program has a case that fails only that check, plus four valid proofs, plus
bounds/rule/goal cases. This asks what a surviving mutant IS, so the answer is measured
rather than assumed -- the owner's law: "Dead logic is where a mutation hides -- prune it,
never excuse it."
"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import muhl_rv32 as RV
import muhl_proofcheck as PC

OPNAME = {0x33: "OP", 0x13: "OP-IMM", 0x03: "LOAD", 0x23: "STORE",
          0x63: "BRANCH", 0x6F: "JAL", 0x67: "JALR", 0x37: "LUI", 0x17: "AUIPC"}


def field_of(instr, bit):
    op = instr & 0x7F
    if bit <= 6:
        return "opcode"
    if op in (0x6F, 0x37, 0x17):
        return "rd" if 7 <= bit <= 11 else "imm"
    if op == 0x63:
        if 7 <= bit <= 11: return "imm[11|4:1]"
        if 12 <= bit <= 14: return "funct3"
        if 15 <= bit <= 19: return "rs1"
        if 20 <= bit <= 24: return "rs2"
        return "imm[12|10:5]"
    if op == 0x23:
        if 7 <= bit <= 11: return "imm[4:0]"
        if 12 <= bit <= 14: return "funct3"
        if 15 <= bit <= 19: return "rs1"
        if 20 <= bit <= 24: return "rs2"
        return "imm[11:5]"
    if 7 <= bit <= 11: return "rd"
    if 12 <= bit <= 14: return "funct3"
    if 15 <= bit <= 19: return "rs1"
    if op == 0x33:
        return "rs2" if 20 <= bit <= 24 else "funct7"
    return "imm"


def run_one(code, slots, lines, goal, halt_pc, fill=None):
    """Returns the verdict word, or None if the run did not HALT with a real verdict.
    A hang or a crash is NOT allowed to read as REJECT — that would mask mutants."""
    mem = PC.build_image(slots, lines, goal, code, fill=fill)
    _, _, halted, out = RV.emulate(mem, 0, PC.CODE_BASE, max_steps=60000, halt_pc=halt_pc)
    v = out.get(PC.RESULT_ADDR, PC.NO_VERDICT)
    if not halted or v not in (0, 1):
        return None
    return v


def battery_expected(cases):
    return [(nm, s, l, g, f, PC.check_reference(s, l, g)) for nm, s, l, g, f in cases]


def disagrees(code, expected, halt_pc):
    """True if this code disagrees with the reference on ANY battery case."""
    try:
        for nm, s, l, g, f, exp in expected:
            if run_one(code, s, l, g, halt_pc, fill=f) != exp:
                return True
    except Exception:
        return True
    return False


def main():
    code, labels = RV.assemble(PC.PROGRAM, base=PC.CODE_BASE)
    halt_pc = labels["halt"]
    cases = PC.case_battery()
    expected = battery_expected(cases)

    print("=" * 78)
    print("  MUTANT SWEEP — %d instructions x 32 bits, against a %d-case battery"
          % (len(code), len(cases)))
    print("=" * 78)

    # sanity: the clean program must match the reference on every case first
    base_bad = [nm for nm, s, l, g, f, exp in expected
                if run_one(code, s, l, g, halt_pc, fill=f) != exp]
    print("  clean program vs reference: %d/%d cases agree"
          % (len(cases) - len(base_bad), len(cases)))
    if base_bad:
        print("  DISAGREEMENTS: %s" % ", ".join(base_bad))
        print("  stopping — the program is not correct yet, mutant data would be noise.")
        return 1

    survivors = {}
    total = caught = 0
    for i in range(len(code)):
        for b in range(32):
            total += 1
            m = list(code)
            m[i] ^= (1 << b)
            if disagrees(m, expected, halt_pc):
                caught += 1
            else:
                survivors.setdefault(field_of(code[i], b), []).append((i, b))

    print("\n  mutants injected : %d" % total)
    print("  observable       : %d  (%.1f%%)" % (caught, 100.0 * caught / total))
    print("  survived         : %d  (%.1f%%)" % (total - caught, 100.0 * (total - caught) / total))

    print("\n  SURVIVORS BY ARCHITECTURAL FIELD:")
    for f in sorted(survivors, key=lambda k: -len(survivors[k])):
        print("    %-14s %4d" % (f, len(survivors[f])))

    byinstr = {}
    for f, lst in survivors.items():
        for i, b in lst:
            byinstr.setdefault(i, []).append(f)
    print("\n  SURVIVOR INSTRUCTIONS (decoded), all:")
    for i in sorted(byinstr, key=lambda k: -len(byinstr[k])):
        w = code[i]
        lab = next((k for k, v in labels.items() if v == 4 * i), "")
        print("    [%3d] pc=0x%04x %-8s rd=x%-2d  %2d bits: %-30s %s"
              % (i, 4 * i, OPNAME.get(w & 0x7F, "?"), (w >> 7) & 31, len(byinstr[i]),
                 ",".join(sorted(set(byinstr[i]))), ("<- " + lab) if lab else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
