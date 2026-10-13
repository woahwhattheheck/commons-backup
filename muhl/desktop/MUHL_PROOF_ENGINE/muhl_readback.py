#!/usr/bin/env python3
"""muhl_readback.py -- read CPU, PROGRAM and PROOF back OUT of titan.gguf and re-verify.

Nothing here is taken from the Python objects that built them. Every byte is read from the
container, decoded, and checked. This is the closing loop: if all three parts really live in
the substrate, then reading the container alone is enough to reproduce the verdict.

Read-only. Bounded. Fabrication-time verification.

    python muhl_readback.py
"""
import json, mmap, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import muhl_rv32 as RV
import muhl_proofcheck as PC
import muhl_gatecheck as GC

TITAN = r"C:\llm\models\titan.gguf"
REG = r"C:\llm\models\titan_circuits.json"


def read(mm, off, n):
    return mm[off:off + n]


def main():
    reg = json.load(open(REG))
    f = open(TITAN, "rb")
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    print("=" * 84)
    print("  READ-BACK — reconstruct the whole machine from container bytes alone")
    print("=" * 84)

    # ---------------------------------------------------------------- 1. the PROGRAM
    e = reg["muhl_proofcheck"]
    blob = read(mm, int(e["offset"]), int(e["len"]))
    assert blob[:8] == b"MUHLPRF1", "program magic"
    (n_instr, cb, db, tb, lb, ra, ep, hp, nv) = struct.unpack_from("<9I", blob, 8)
    code = [struct.unpack_from("<I", blob, 44 + 4 * i)[0] for i in range(n_instr)]
    print("\n  PROGRAM  muhl_proofcheck @ %d" % int(e["offset"]))
    print("    %d instructions, entry 0x%04x, halt 0x%04x" % (n_instr, ep, hp))
    print("    map: DATA 0x%x  TERMS 0x%x  LINES 0x%x  result 0x%x" % (db, tb, lb, ra))

    # ---------------------------------------------------------------- 2. the CPU
    core = GC.load_core()
    print("\n  CPU      %s @ %d" % (e["runs_on"], int(reg[e["runs_on"]]["offset"])))
    print("    %d gates, %d wires, DEPTH %d ticks per instruction"
          % (core["ng"], core["nw"], core["depth"]))

    # ---------------------------------------------------------------- 3. each PROOF
    names = [k for k in reg
             if isinstance(reg.get(k), dict) and reg[k].get("magic") == "MUHLPRFD"]
    if not names:
        print("\n  no stored proofs found.")
        return 1

    allok = True
    for nm in sorted(names):
        pe = reg[nm]
        parts = {}
        for r in pe["regions"]:
            head = read(mm, int(r["offset"]), 16)
            assert head[:8] == b"MUHLPRFD", "proof magic in %s" % nm
            prog_addr, plen = struct.unpack_from("<II", head, 8)
            assert prog_addr == int(r["program_addr"]) and plen == int(r["payload_len"])
            parts[r["region"]] = read(mm, int(r["payload_offset"]), plen)

        n_terms, n_lines, goal, sentinel = struct.unpack_from("<4I", parts["header"], 0)
        slots = [struct.unpack_from("<3I", parts["terms"], 12 * i) for i in range(n_terms)]
        lines = [struct.unpack_from("<4I", parts["lines"], 16 * i) for i in range(n_lines)]

        print("\n  PROOF    %s" % nm)
        print("    decoded from container: %d terms, %d lines, goal %d, sentinel 0x%08x"
              % (n_terms, n_lines, goal, sentinel))

        # independent reference, on the bytes read back
        ref = PC.check_reference(slots, lines, goal)

        # the stored PROGRAM, on the bytes read back, executed on the REAL gate core prefix
        mem = PC.build_image(slots, lines, goal, code)
        regs = [0] * 32
        pc = cb
        n = 0
        gbad = 0
        while pc != hp and n < 3_000_000:
            instr = mem.get(pc & ~3, 0)
            op = instr & 0x7F
            memword = 0
            if op == 0x03:
                imm = RV._sx((instr >> 20) & 0xFFF, 12)
                memword = mem.get(((regs[(instr >> 15) & 31] + imm) & 0xFFFFFFFF) & ~3, 0)
            if n < 300:
                inb = GC.bits(pc, 32)
                for r in range(32):
                    inb += GC.bits(regs[r], 32)
                inb += GC.bits(instr, 32) + GC.bits(memword, 32)
                o = GC.ripple(core, inb)
                gn = GC.frombits(o[0:32])
                gr = [GC.frombits(o[32 + r * 32:32 + (r + 1) * 32]) for r in range(32)]
            rr, rn, ma, md, we = GC.ref_step(instr, pc, regs, memword)
            if n < 300 and (gn != rn or gr != rr):
                gbad += 1
            regs = rr
            if op == 0x23:
                mem[ma & ~3] = md
            pc = rn
            n += 1
        verdict = mem.get(ra)

        ok = (ref == 1 and verdict == 1 and gbad == 0)
        allok = allok and ok
        print("    reference on those bytes      : %s" % ("ACCEPT" if ref == 1 else "REJECT"))
        print("    stored program on those bytes : %s  (%d instructions, %d ticks)"
              % ("ACCEPT" if verdict == 1 else "REJECT", n, n * core["depth"]))
        print("    gate-exact over first %-3d     : %s"
              % (min(300, n), "YES" if gbad == 0 else "NO (%d differ)" % gbad))
        print("    -> %s" % ("REPRODUCED FROM CONTAINER BYTES" if ok else "*** MISMATCH ***"))

    mm.close()
    f.close()
    print("\n" + "=" * 84)
    print("  %s" % ("ALL PARTS REPRODUCED FROM THE CONTAINER ALONE."
                    if allok else "SOMETHING DID NOT REPRODUCE — see above."))
    print("  container size now: %d bytes" % os.path.getsize(TITAN))
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
