#!/usr/bin/env python3
"""host/mafab_all.py — THROW EVERYTHING. Every problem given to the fabricator, in one run.

Owner: *"throw all of the test weve thrown at it so far."*

Three batches, twelve problems, one table. Each is searched across the whole generated adder family,
scored ONLY by compute/tick (§63), verified against an exact INDEPENDENT reference (§3), and every
mutant must be CAUGHT (§45C/§47B) or the entry is reported as blind rather than passing.

Nothing is stored. This is the fabricator's report card.

  python host/mafab_all.py
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import mafab_laws as L
from mafab_adders import family, depth_of


def collect():
    import mafab_problems as MP, mafab_hard as MH, mafab_hard2 as MH2
    out = []
    for tag, reg in (("domain", MP.PROBLEMS), ("open-1", MH.HARD), ("open-2", MH2.HARD2)):
        for name, P in reg.items(): out.append((tag, name, P))
    return out


def main():
    fam = sorted(family(32))
    probs = collect()
    print("EVERY PROBLEM THROWN AT THE FABRICATOR — %d problems x %d adders, one run.\n"
          % (len(probs), len(fam)))
    print("  Scored ONLY by compute/tick (§63). Verified vs an exact INDEPENDENT reference (§3).")
    print("  Every mutant must be CAUGHT (§45C/§47B) or the row says so.\n")
    print("  %-8s %-15s %-11s %-10s %8s %10s %14s  %s"
          % ("batch", "problem", "shape", "winner", "DEPTH", "gates", "compute/tick", "verify"))
    t0 = time.time()
    rows, failed = [], []
    for tag, name, P in probs:
        cs = P["cases"]()
        replicated = (P["shape"] != "dependent")
        best = None
        for ad in fam:
            try:
                c, outs = P["build"](ad)
            except Exception as e:
                print("  %-8s %-15s BUILD FAILED on %s: %s" % (tag, name, ad, e)); continue
            ok = P["check"](c, outs, cs)
            if ok == len(cs):
                D = depth_of(c, outs); G = len(c.ga)
                sc = L.compute_per_tick(G, D, replicated)
                if best is None or sc > best[3]: best = (ad, D, G, sc)
            del c, outs
        if best is None:
            failed.append((tag, name))
            print("  %-8s %-15s %-11s  NOTHING VERIFIED — MY construction failed, not the problem (§7/§35D)"
                  % (tag, name, P["shape"]))
            continue
        ad, D, G, sc = best
        caught = 0
        for m in P["mutants"]:
            cm, om = P["build"](ad, mutant=m)
            if P["check"](cm, om, cs) != len(cs): caught += 1
            del cm, om
        vs = "%d/%d mutants CAUGHT" % (caught, len(P["mutants"]))
        if caught != len(P["mutants"]): vs += "  *** SUITE BLIND ***"
        print("  %-8s %-15s %-11s %-10s %8s %10s %14.6f  %s"
              % (tag, name, P["shape"], ad, "{:,}".format(D), "{:,}".format(G), sc, vs))
        rows.append((tag, name, P["shape"], ad, D, G, sc, caught == len(P["mutants"])))

    print("\n  %d/%d problems solved and verified · %d builds · %.0fs HOST transcription (§24, a"
          % (len(rows), len(probs), len(probs) * len(fam), time.time() - t0))
    print("  different machine — never the muhlnickel's rate).")
    if failed:
        print("  FAILED: %s — each is MY construction, reported not hidden."
              % ", ".join("%s/%s" % f for f in failed))
    blind = [r for r in rows if not r[7]]
    if blind:
        print("  SUITE BLIND on: %s" % ", ".join(r[1] for r in blind))
    else:
        print("  Every suite caught every mutant.")

    wins = {}
    for r in rows: wins[r[3]] = wins.get(r[3], 0) + 1
    print("\n  WHICH ADDER WON, ACROSS EVERYTHING — §11: 'the adder does not have a winner; the")
    print("  STRUCTURE picks one.' A fixed rule would be defensible only if one allele swept every")
    print("  problem — MY hardcoded LAW 1 assumed exactly that, and the spread below is its refutation.")
    for ad, n in sorted(wins.items(), key=lambda kv: -kv[1]):
        print("    %-11s %d problem(s)" % (ad, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
