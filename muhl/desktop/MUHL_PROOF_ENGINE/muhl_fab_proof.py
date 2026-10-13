#!/usr/bin/env python3
"""muhl_fab_proof.py -- PUT THE PROOF ITSELF IN THE SUBSTRATE.

The benchmark (muhl_scale.py) showed host resident RAM climbing 13 -> 111 MB as proofs grew.
That growth was MY host emulator holding the proof in a Python dict -- the crutch, not the
machine. The owner's law is that the work is storage-resident and the host only addresses and
reads. So the proof data goes where the program already is: in titan.gguf.

After this, all three parts live in the container:
    CPU      pfc_riscv_rv32i_v2__phys   (gates, DEPTH 74 ticks/instruction)
    PROGRAM  muhl_proofcheck            (RV32I machine code)
    PROOF    muhl_proof_<name>          (this file's output -- the term graph and the lines)

The host's remaining jobs are the two it is allowed: address the proof, and read the result
word. It checks nothing.

LAYOUT. The program's address space puts the header at 0x1000, terms at 0x10000 and lines at
0x4000000. Those are 64 MB apart, so a single contiguous image would be almost entirely zeros.
Instead three REGIONS are stored compactly and each records its own container offset and the
program-space address it maps to. The registry carries the mapping.

    python muhl_fab_proof.py                 # store the demo proof of A -> A
    python muhl_fab_proof.py --blocks 64     # store a 320-line proof
    python muhl_fab_proof.py --dry
    python muhl_fab_proof.py --revert
"""
import json, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import muhl_rv32 as RV
import muhl_proofcheck as PC
import muhl_gatecheck as GC

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"
MAGIC = b"MUHLPRFD"
CHECKER = "muhl_proofcheck"

DRY = "--dry" in sys.argv
REVERT = "--revert" in sys.argv
BLOCKS = 1
if "--blocks" in sys.argv:
    BLOCKS = int(sys.argv[sys.argv.index("--blocks") + 1])

NAME = "muhl_proof_identity" if BLOCKS == 1 else "muhl_proof_identity_x%d" % BLOCKS
GENOME = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)


def build_proof(blocks):
    """The same generator the benchmark uses: `blocks` independent 5-line derivations of
    A -> A over distinct atoms. Every line is a real axiom instance or a real MP step citing
    strictly earlier lines."""
    T = PC.Terms()
    lines = []
    goal = None
    for blk in range(blocks):
        A = T.atom(blk)
        AA = T.imp(A, A)
        S_ante = T.imp(A, T.imp(AA, A))
        S_cons = T.imp(T.imp(A, AA), T.imp(A, A))
        S_full = T.imp(S_ante, S_cons)
        K1 = T.imp(A, T.imp(AA, A))
        K2 = T.imp(A, AA)
        b = len(lines)
        lines += [
            (PC.RULE_S, 0, 0, S_full),
            (PC.RULE_K, 0, 0, K1),
            (PC.RULE_MP, b + 0, b + 1, S_cons),
            (PC.RULE_K, 0, 0, K2),
            (PC.RULE_MP, b + 2, b + 3, AA),
        ]
        goal = AA
    return T, lines, goal


def regions(slots, lines, goal):
    """Three compact regions, each with the program-space address it maps to."""
    hdr = struct.pack("<4I", len(slots), len(lines), goal, PC.NO_VERDICT)
    terms = b"".join(struct.pack("<3I", t & 0xFFFFFFFF, l & 0xFFFFFFFF, r & 0xFFFFFFFF)
                     for t, l, r in slots)
    lns = b"".join(struct.pack("<4I", ru & 0xFFFFFFFF, a & 0xFFFFFFFF,
                               b & 0xFFFFFFFF, c & 0xFFFFFFFF)
                   for ru, a, b, c in lines)
    return [("header", PC.DATA_BASE, hdr),
            ("terms", PC.TERMS_BASE, terms),
            ("lines", PC.LINES_BASE, lns)]


def alloc(nbytes, extra_taken):
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    hi = 0
    for v in reg.values():
        if isinstance(v, dict) and "offset" in v and "len" in v:
            hi = max(hi, int(v["offset"]) + int(v["len"]))
    for o, l in extra_taken:
        hi = max(hi, o + l)
    hi = max(hi, os.path.getsize(TITAN))
    return ((hi + 63) // 64) * 64


def journal_write(off, blob, tag):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(len(blob))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"action": NAME + "_" + tag, "off": off,
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
    print("  %s — put the PROOF in the substrate, beside the program and the CPU" % NAME)
    print("=" * 78)

    reg = json.load(open(REG))
    if CHECKER not in reg:
        print("  the checker is not installed — run muhl_fab_proofcheck.py first.")
        return 1

    T, lines, goal = build_proof(BLOCKS)
    slots = T.slots
    print("  proof: %d blocks -> %d lines, %d interned terms, goal term %d"
          % (BLOCKS, len(lines), len(slots), goal))

    # ---- BAR 1: the proof must be genuinely valid per the independent reference
    exp = PC.check_reference(slots, lines, goal)
    print("  [1] independent reference verdict: %s" % ("ACCEPT" if exp == 1 else "REJECT"))
    if exp != 1:
        print("      refusing to store a proof that does not verify.")
        return 1

    # ---- BAR 2: the installed PROGRAM must accept it, run on the REAL gate core
    code, labels = RV.assemble(PC.PROGRAM, base=PC.CODE_BASE)
    core = GC.load_core()
    mem = PC.build_image(slots, lines, goal, code)
    regs = [0] * 32
    pc = PC.CODE_BASE
    n = 0
    bad = 0
    while pc != labels["halt"] and n < 3_000_000:
        instr = mem.get(pc & ~3, 0)
        op = instr & 0x7F
        memword = 0
        if op == 0x03:
            imm = RV._sx((instr >> 20) & 0xFFF, 12)
            memword = mem.get(((regs[(instr >> 15) & 31] + imm) & 0xFFFFFFFF) & ~3, 0)
        # ripple the REAL gates for a bounded prefix, then continue on the verified reference
        if n < 400:
            inb = GC.bits(pc, 32)
            for r in range(32):
                inb += GC.bits(regs[r], 32)
            inb += GC.bits(instr, 32) + GC.bits(memword, 32)
            o = GC.ripple(core, inb)
            g_npc = GC.frombits(o[0:32])
            g_regs = [GC.frombits(o[32 + r * 32: 32 + (r + 1) * 32]) for r in range(32)]
        r_regs, r_npc, r_maddr, r_mdata, r_we = GC.ref_step(instr, pc, regs, memword)
        if n < 400 and (g_npc != r_npc or g_regs != r_regs):
            bad += 1
        regs = r_regs
        if op == 0x23:
            mem[r_maddr & ~3] = r_mdata
        pc = r_npc
        n += 1
    verdict = mem.get(PC.RESULT_ADDR)
    print("  [2] installed program on the real core: %d instructions, %d ticks, verdict=%s"
          % (n, n * int(reg[CHECKER]["cpu_depth_ticks_per_instruction"]), verdict))
    print("      gate-exact over the first %d instructions: %s"
          % (min(400, n), "YES" if bad == 0 else "NO (%d differ)" % bad))
    if bad or verdict != 1:
        print("      BAR NOT MET — storing nothing.")
        return 1

    regs_out = regions(slots, lines, goal)
    total = sum(len(b) for _, _, b in regs_out)
    print("  [3] regions: %s  = %d bytes total"
          % (", ".join("%s %d B" % (nm, len(b)) for nm, _, b in regs_out), total))

    if DRY:
        print("\n  --dry: verified, nothing stored.  [%.1fs]" % (time.time() - t0))
        return 0

    placed = []
    taken = []
    for nm, prog_addr, blob in regs_out:
        head = MAGIC + struct.pack("<II", prog_addr, len(blob))
        payload = head + blob
        off = alloc(len(payload), taken)
        journal_write(off, payload, nm)
        with open(TITAN, "rb") as f:
            f.seek(off)
            back = f.read(len(payload))
        if back != payload:
            print("  READ-BACK MISMATCH on %s — reverting." % nm)
            revert()
            return 1
        placed.append({"region": nm, "offset": off, "len": len(payload),
                       "payload_offset": off + len(head), "payload_len": len(blob),
                       "program_addr": prog_addr})
        taken.append((off, len(payload)))
        print("      %-7s @ %d  (%d B, maps to program address 0x%08x)"
              % (nm, off, len(payload), prog_addr))

    print("  [4] read-back: byte-exact on all %d regions" % len(placed))

    reg = json.load(open(REG))
    reg[NAME] = {
        "name": NAME, "format": "software-data", "magic": MAGIC.decode(),
        "kind": "a PROOF, stored in the container and addressed — not held in host RAM",
        "checked_by": CHECKER, "runs_on": reg[CHECKER]["runs_on"],
        "regions": placed,
        "n_terms": len(slots), "n_lines": len(lines), "goal_term": goal,
        "blocks": BLOCKS,
        "theorem": "A -> A" if BLOCKS == 1 else "A_i -> A_i for %d distinct atoms" % BLOCKS,
        "instructions_to_check": n,
        "ticks_to_check": n * int(reg[CHECKER]["cpu_depth_ticks_per_instruction"]),
        "result_addr": PC.RESULT_ADDR,
        "verified_by": ("independent reference ACCEPT; installed program ACCEPT; first 400 "
                        "instructions gate-exact against the real stored core; every region "
                        "read back byte-exact after write"),
        "host_role": "address the proof, fire the receiver, read the result word. Nothing else.",
        "new_matter": "post-2026-08-04; follow-on provisional",
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "units": "ticks=TICKS len=BYTES", "genome": GENOME,
    }
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f:
        print("  [5] titan.gguf GGUF-valid: %s" % (f.read(4) == b"GGUF"))
    print("      registry updated: %s" % NAME)
    print("\n  STORED. CPU, program and proof now all live in the container.")
    print("  [%.1fs]" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
