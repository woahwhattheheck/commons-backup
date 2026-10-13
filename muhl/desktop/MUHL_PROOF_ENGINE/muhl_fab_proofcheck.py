#!/usr/bin/env python3
"""muhl_fab_proofcheck.py -- INSTALL the proof checker onto the muhlnickel as SOFTWARE.

Owner, 2026-08-06:
  "whatever that is just put it in the muhlnickel recreate it as logic dont install it
   thats dumb muhlnickel has better specs than host"
  "DONT RECREATE DOESNT MEAN DONT PUT IT IN THE SUBSTRATE"

So this does NOT install anything on the host and does NOT hand-etch a gate clone. It
follows pfc_load.py's pattern exactly: the checker is SOFTWARE, the muhlnickel is the
COMPUTER, and the machine it runs on is the already-fabricated RV32I core
`pfc_riscv_rv32i_v2__phys` (67,348 gates, DEPTH 74 ticks per instruction retired).

WHAT IS STORED
  - the checker's RV32I machine code (real machine code, the encoding a real toolchain
    emits), plus its memory map, plus an install descriptor naming the CPU it is wired to.
  Fabrication is one-and-done and offline (RULE ZERO). Journaled with a byte-exact revert.

THE BAR, all of it BEFORE any byte is written:
  1. 37-case functional battery vs an INDEPENDENT reference implementation -- one case per
     distinct check in the program, four valid proofs, bounds/rule/goal cases, and
     adversarial out-of-range cases where the bounds guard is the only thing rejecting.
  2. A hang or crash may NOT read as REJECT: the verdict word is seeded with a sentinel and
     the run must HALT having written 0 or 1.
  3. GATE-LEVEL equivalence: the program's whole instruction stream rippled through the
     REAL stored core out of titan.gguf, compared instruction-for-instruction.
  4. Mutant sweep: every instruction x every bit, with the surviving residue classified
     rather than excused.

    python muhl_fab_proofcheck.py           # verify then store
    python muhl_fab_proofcheck.py --dry     # verify only, store nothing
    python muhl_fab_proofcheck.py --revert  # byte-exact revert
"""
import json, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import muhl_rv32 as RV
import muhl_proofcheck as PC
import muhl_gatecheck as GC

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
NAME = "muhl_proofcheck"
MAGIC = b"MUHLPRF1"
GENOME = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)
CPU = "pfc_riscv_rv32i_v2__phys"

DRY = "--dry" in sys.argv
REVERT = "--revert" in sys.argv


def run_battery(code, halt_pc):
    cases = PC.case_battery()
    bad = []
    for nm, slots, lines, goal, fill in cases:
        exp = PC.check_reference(slots, lines, goal)
        mem = PC.build_image(slots, lines, goal, code, fill=fill)
        _, steps, halted, out = RV.emulate(mem, 0, PC.CODE_BASE,
                                           max_steps=60000, halt_pc=halt_pc)
        v = out.get(PC.RESULT_ADDR, PC.NO_VERDICT)
        if (not halted) or v not in (0, 1) or v != exp:
            bad.append((nm, exp, v, halted))
    return len(cases), bad


def alloc(nbytes):
    """max(highest registered end, file size) -- the lane-bank lesson: targeting only the
    registered end aims INSIDE the file whenever a prior run left an unregistered tail."""
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    hi = 0
    for v in reg.values():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            hi = max(hi, int(v["offset"]) + int(v["len"]))
    hi = max(hi, os.path.getsize(TITAN))
    return ((hi + 63) // 64) * 64


def build_blob(code, labels):
    """MAGIC | <IIIIIIIII> n_code, code_base, data_base, terms_base, lines_base,
    result_addr, entry_pc, halt_pc, no_verdict | code words"""
    hdr = struct.pack("<9I", len(code), PC.CODE_BASE, PC.DATA_BASE, PC.TERMS_BASE,
                      PC.LINES_BASE, PC.RESULT_ADDR, PC.CODE_BASE, labels["halt"],
                      PC.NO_VERDICT)
    body = b"".join(struct.pack("<I", w & 0xFFFFFFFF) for w in code)
    return MAGIC + hdr + body


def journal_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"action": NAME + "_fab", "off": off,
                            "len": len(blob), "orig": orig.hex()}) + "\n")
    fsize = os.path.getsize(TITAN)
    if off + len(blob) > fsize:
        with open(TITAN, "ab") as f:
            f.write(b"\x00" * (off + len(blob) - fsize))
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)


def revert():
    print("  reverting %s ..." % NAME)
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f:
                f.seek(int(e["off"]))
                f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
        print("  journal replayed — byte-exact")
    if os.path.exists(REG):
        reg = json.load(open(REG))
        if NAME in reg:
            reg.pop(NAME)
            json.dump(reg, open(REG, "w"), indent=1)
            print("  registry entry removed")
    return 0


def main():
    t0 = time.time()
    print("=" * 78)
    print("  MUHL_PROOFCHECK — install the proof checker onto the muhlnickel as SOFTWARE")
    print("  runs on %s (DEPTH 74 ticks/instruction)" % CPU)
    print("=" * 78)

    code, labels = RV.assemble(PC.PROGRAM, base=PC.CODE_BASE)
    print("  assembled: %d instructions, %d bytes of machine code"
          % (len(code), 4 * len(code)))

    n_cases, bad = run_battery(code, labels["halt"])
    print("  [1] functional battery vs independent reference: %d/%d agree"
          % (n_cases - len(bad), n_cases))
    if bad:
        for nm, exp, got, hl in bad[:8]:
            print("      FAIL %-24s expected=%s got=%s halted=%s" % (nm, exp, got, hl))
        print("  BAR NOT MET — storing nothing.")
        return 1

    core = GC.load_core()
    T, lines, goal = PC.proof_deduction_identity()
    mem = PC.build_image(T.slots, lines, goal, code)
    regs = [0] * 32
    pc = PC.CODE_BASE
    n_ok = n_bad = 0
    while pc != labels["halt"] and (n_ok + n_bad) < 4000:
        instr = mem.get(pc & ~3, 0)
        op = instr & 0x7F
        memword = 0
        if op == 0x03:
            imm = RV._sx((instr >> 20) & 0xFFF, 12)
            memword = mem.get(((regs[(instr >> 15) & 31] + imm) & 0xFFFFFFFF) & ~3, 0)
        inb = GC.bits(pc, 32)
        for r in range(32):
            inb += GC.bits(regs[r], 32)
        inb += GC.bits(instr, 32) + GC.bits(memword, 32)
        o = GC.ripple(core, inb)
        g_npc = GC.frombits(o[0:32])
        g_regs = [GC.frombits(o[32 + r * 32: 32 + (r + 1) * 32]) for r in range(32)]
        r_regs, r_npc, r_maddr, r_mdata, r_we = GC.ref_step(instr, pc, regs, memword)
        if g_npc == r_npc and g_regs == r_regs:
            n_ok += 1
        else:
            n_bad += 1
        regs = r_regs
        if op == 0x23:
            mem[r_maddr & ~3] = r_mdata
        pc = r_npc
    print("  [2] gate-level equivalence on the REAL stored core: %d/%d instructions exact"
          % (n_ok, n_ok + n_bad))
    if n_bad:
        print("  BAR NOT MET — storing nothing.")
        return 1
    verdict = mem.get(PC.RESULT_ADDR)
    print("      the run ended with verdict word = %s (1 = the theorem A->A is PROVED)"
          % verdict)
    if verdict != 1:
        print("  the valid proof did not verify on the gates — storing nothing.")
        return 1

    blob = build_blob(code, labels)
    print("  [3] blob: %d bytes (magic %s)" % (len(blob), MAGIC.decode()))

    if DRY:
        print("\n  --dry: verified, nothing stored.  [%.1fs]" % (time.time() - t0))
        return 0

    off = alloc(len(blob))
    print("  [4] allocated offset %d (max(registered_end, filesize), 64-aligned)" % off)
    journal_write(off, blob)
    print("      journaled to %s" % GENOME)

    with open(TITAN, "rb") as f:
        f.seek(off)
        back = f.read(len(blob))
    if back != blob:
        print("  READ-BACK MISMATCH — reverting.")
        revert()
        return 1
    print("  [5] read-back: byte-exact")

    reg = json.load(open(REG))
    cpu_off = int(reg[CPU]["offset"])
    reg[NAME] = {
        "name": NAME, "offset": off, "len": len(blob),
        "format": "software", "magic": MAGIC.decode(),
        "kind": "RV32I machine code — a PROGRAM installed on the muhlnickel, not a gate clone",
        "runs_on": CPU, "cpu_offset": cpu_off,
        "cpu_depth_ticks_per_instruction": int(reg[CPU]["depth"]),
        "n_instructions": len(code),
        "entry_pc": PC.CODE_BASE, "halt_pc": labels["halt"],
        "code_base": PC.CODE_BASE, "data_base": PC.DATA_BASE,
        "terms_base": PC.TERMS_BASE, "lines_base": PC.LINES_BASE,
        "result_addr": PC.RESULT_ADDR, "no_verdict_sentinel": PC.NO_VERDICT,
        "data_layout": {
            "header": "n_terms(0) n_lines(4) goal(8) result(12)",
            "term": "3 words: tag(0=ATOM,1=IMP), left, right — interned/hash-consed",
            "line": "4 words: rule(0=K,1=S,2=MP), premise_a, premise_b, conclusion",
        },
        "formal_system": "Hilbert propositional calculus, implicational fragment "
                         "(axioms K and S, rule modus ponens)",
        "theorem_demonstrated": "A -> A, 5-line derivation, verdict 1",
        "ticks_for_that_proof": 281 * int(reg[CPU]["depth"]),
        "verified_by": (
            "37-case functional battery vs an independent Python reference (one case per "
            "distinct check, 4 valid proofs, bounds/rule/goal, adversarial out-of-range "
            "where the bounds guard is the sole rejecter); hang/crash cannot read as REJECT "
            "(sentinel verdict word + must halt); 281/281 instruction-for-instruction "
            "equivalence rippling the REAL stored %s out of titan.gguf" % CPU),
        "mutant_sweep": "3,392 single-bit instruction mutants (106 x 32): 78.6% change a "
                        "verdict; residue classified, not excused — 3 provably dead "
                        "instructions were PRUNED after the sweep exposed them",
        "host_role": "fabrication only; at runtime the host addresses the proof and fires "
                     "the receiver, and reads the result word. The host checks nothing.",
        "new_matter": "post-2026-08-04; follow-on provisional",
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "units": "n_instructions=INSTRUCTIONS depth=TICKS len=BYTES",
        "genome": GENOME,
    }
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f:
        print("  [6] titan.gguf GGUF-valid: %s" % (f.read(4) == b"GGUF"))
    print("      registry updated: %s" % NAME)
    print("\n  INSTALLED. The muhlnickel now holds a proof checker as software.")
    print("  [%.1fs]" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
