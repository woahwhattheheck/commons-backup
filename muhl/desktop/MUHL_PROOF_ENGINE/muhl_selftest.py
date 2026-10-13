#!/usr/bin/env python3
"""muhl_selftest.py -- prove the checker program is correct BEFORE any byte is stored.

Fabrication-time only. Nothing here touches titan.gguf.
"""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import muhl_rv32 as RV
import muhl_proofcheck as PC


def run_program(code, slots, lines, goal, halt_pc):
    mem = PC.build_image(slots, lines, goal, code)
    regs, steps, halted, out = RV.emulate(mem, 0, PC.CODE_BASE, max_steps=200000, halt_pc=halt_pc)
    return out.get(PC.RESULT_ADDR, None), steps, halted


def main():
    print("=" * 78)
    print("  MUHL PROOF CHECKER — self-test (fabrication-time, stores nothing)")
    print("=" * 78)

    code, labels = RV.assemble(PC.PROGRAM, base=PC.CODE_BASE)
    halt_pc = labels["halt"]
    print("  assembled: %d instruction words (%d bytes), halt @ 0x%04x"
          % (len(code), 4 * len(code), halt_pc))
    print("  labels: %s" % ", ".join("%s=0x%x" % (k, v) for k, v in sorted(labels.items(), key=lambda x: x[1])))

    T, lines, goal = PC.proof_deduction_identity()
    slots = T.slots
    print("\n  THE THEOREM: A -> A   (Hilbert implicational fragment, 5-line derivation)")
    print("  term graph : %d interned slots" % len(slots))
    print("  proof      : %d lines" % len(lines))

    ref = PC.check_reference(slots, lines, goal)
    got, steps, halted = run_program(code, slots, lines, goal, halt_pc)
    print("\n  reference checker : %s" % ("ACCEPT" if ref == 1 else "REJECT"))
    print("  program on RV32I  : %s   (%d instructions retired, halted=%s)"
          % ("ACCEPT" if got == 1 else "REJECT", steps, halted))
    agree = (ref == got)
    print("  agreement         : %s" % ("MATCH" if agree else "MISMATCH"))

    if not agree or ref != 1:
        print("\n  VALID PROOF DID NOT VERIFY — stopping, nothing is fit to store.")
        return 1

    print("\n  --- defect cases: each MUST be rejected by BOTH ---")
    rng = random.Random(4242)
    kinds = ["circular", "wrong_goal", "bad_mp", "bad_axiom", "oob", "bad_rule"]
    bad = 0
    for k in kinds:
        ml, mg = PC.mutate_proof(T, lines, goal, k, rng)
        r = PC.check_reference(slots, ml, mg)
        g, st, hl = run_program(code, slots, ml, mg, halt_pc)
        status = "ok" if (r == g == 0) else "PROBLEM"
        if r != g or r != 0:
            bad += 1
        print("    %-11s reference=%s program=%s  %s"
              % (k, "ACCEPT" if r else "REJECT", "ACCEPT" if g else "REJECT", status))

    print("\n  --- random proofs: program vs reference, agreement on every case ---")
    mism = 0
    trials = 400
    for t in range(trials):
        rr = random.Random(1000 + t)
        nl = rr.randrange(1, 8)
        ml = []
        for i in range(nl):
            rule = rr.choice([PC.RULE_K, PC.RULE_S, PC.RULE_MP, 9])
            ml.append((rule, rr.randrange(0, max(1, nl)), rr.randrange(0, max(1, nl)),
                       rr.randrange(0, len(slots) + 2)))
        mg = rr.randrange(0, len(slots) + 2)
        r = PC.check_reference(slots, ml, mg)
        g, st, hl = run_program(code, slots, ml, mg, halt_pc)
        if r != g:
            mism += 1
            if mism <= 3:
                print("    MISMATCH ref=%s prog=%s lines=%s goal=%s" % (r, g, ml, mg))
    print("    %d/%d agreed, %d mismatched" % (trials - mism, trials, mism))

    print("\n  --- MUTANT CHECK: corrupt one instruction, it must change an answer ---")
    caught = 0
    tried = 0
    mrng = random.Random(999)
    for _ in range(12):
        idx = mrng.randrange(len(code))
        mutant = list(code)
        mutant[idx] ^= (1 << mrng.randrange(32))
        tried += 1
        differs = False
        try:
            g1, _, _ = run_program(mutant, slots, lines, goal, halt_pc)
            if g1 != 1:
                differs = True
            if not differs:
                for k in kinds:
                    ml, mg = PC.mutate_proof(T, lines, goal, k, random.Random(7))
                    g2, _, _ = run_program(mutant, slots, ml, mg, halt_pc)
                    if g2 != 0:
                        differs = True
                        break
        except Exception:
            differs = True
        if differs:
            caught += 1
    print("    %d/%d single-bit instruction mutants changed an answer" % (caught, tried))

    allgood = (bad == 0 and mism == 0 and caught == tried)
    print("\n  VERDICT: %s" % ("ALL CHECKS PASS — fit to store"
                               if allgood else "NOT CLEAN — storing nothing"))
    return 0 if allgood else 1


if __name__ == "__main__":
    raise SystemExit(main())
