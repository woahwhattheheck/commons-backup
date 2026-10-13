#!/usr/bin/env python3
"""host/fab_problems.py — FABRICATION ONLY. Stores the winners the fabricator found for the thrown
problems, so the corpus grows and the owner's theory becomes measurable.

Owner's theory: *"throwing different stuff at it will optimize it."* The mechanism, per §14, is that
the mined motif library is built FROM the corpus — "discover recurring sub-patterns in circuits that
score well, promote them to named primitives, and re-search with the enlarged library." A circuit
that is never stored cannot contribute a motif, so testing the theory requires storing the winners.

BASELINE, measured before these were added: 280,561 cones evaluated, **702 distinct functions**.
Re-mine after storing and the difference is the theory's answer, either way.

Every winner here passed the full bar in `mafab_problems.py` before reaching this file: exact
reference implemented INDEPENDENTLY of the circuit (§3), and every mutant CAUGHT (§45C/§47B).

ADDITIVE: new names only. Nothing existing is touched.

  python host/fab_problems.py --dry
  python host/fab_problems.py
  python host/fab_problems.py revert
"""
import json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
import mafab_problems as MP
import mafab_hard as MH
import mafab_hard2 as MH2
from mafab_adders import depth_of

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_problems_genome.jsonl"
MAGIC = b"TITANCIR"

# ⛔ THE FROZEN WINNERS ARE STRIPPED. This used to hold {"ntt_butterfly": "brentkung", ...} — the
# search's answers typed into the source. That is the §40A failure in its purest form: a result I
# transcribed becomes the ceiling, and it goes stale the moment the adder family, the metric, or the
# problem changes. It already had: these were chosen under the pre-§63 keys, and §63's one metric
# (compute/tick) re-ranked sw_cell from ripple back to kogge.
# The winner is now RE-SEARCHED at fabrication time, every time.
def winner_for(name, P, fam):
    """Search the family for this problem's best implementation under the ONE metric (§63)."""
    import mafab_laws as L
    from mafab_adders import depth_of
    cs = P["cases"](); replicated = (P["shape"] != "dependent")
    best = (None, -1.0)
    for ad in fam:
        built = P["build"](ad)          # NOT wrapped: a build that fails must be seen, not skipped
        c, outs = built
        if P["check"](c, outs, cs) == len(cs):
            sc = L.compute_per_tick(len(c.ga), depth_of(c, outs), replicated)
            if sc > best[1]: best = (ad, sc)
        del c, outs
    return best[0]


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())          # OUT OF CACHE, INTO STORAGE (§7)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG))
    for n in [k for k in list(reg) if k.startswith("prob_")]: reg.pop(n, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d entries." % len(ent)); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    print("STORING THE THROWN PROBLEMS' WINNERS — so the corpus grows and the theory is testable.\n")
    print("  %-16s %-10s %8s %10s   %s" % ("problem", "adder", "DEPTH", "gates", "verification"))
    stored = 0
    from mafab_adders import family
    fam = sorted(family(32))
    # the OPEN problems join the domain ones: owner 2026-07-28, 'THROW THE UNSOLVED MATH
    # Component implementation.
    ALL = {}
    for reg in (MP.PROBLEMS, MH.HARD, MH2.HARD2): ALL.update(reg)
    for name in sorted(ALL):
        P = ALL[name]
        adder = winner_for(name, P, fam)
        if adder is None:
            print("  %-16s no implementation verified — storing nothing" % name); continue
        cs = P["cases"]()
        c, outs = P["build"](adder)
        ok = P["check"](c, outs, cs)
        D = depth_of(c, outs); G = len(c.ga)
        caught = 0
        for m in P["mutants"]:
            cm, om = P["build"](adder, mutant=m)
            if P["check"](cm, om, cs) != len(cs): caught += 1
            del cm, om
        good = (ok == len(cs)) and caught == len(P["mutants"])
        print("  %-16s %-10s %8s %10s   %d/%d, %d/%d mutants CAUGHT %s"
              % (name, adder, "{:,}".format(D), "{:,}".format(G), ok, len(cs),
                 caught, len(P["mutants"]), "" if good else "  *** NOT STORING ***"))
        if not good or dry:
            del c, outs; continue
        reg = json.load(open(REG))
        nm = "prob_" + name
        if nm in reg:
            print("      %s already stored @ %s" % (nm, reg[nm]["offset"])); del c, outs; continue
        body = struct.pack("<%di" % G, *c.ga) + struct.pack("<%di" % G, *c.gb) + \
               struct.pack("<%di" % len(outs), *outs)
        blob = MAGIC + struct.pack("<IIII", c.n_in, c.n_wire(), G, len(outs)) + body
        off, tn = TC._alloc(len(blob), reg)
        t0 = time.time(); _journal(off, blob)
        reg = json.load(open(REG))
        reg[nm] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": c.n_in,
                   "n_wire": c.n_wire(), "n_gate": G, "n_out": len(outs), "format": "nand2",
                   "depth": D, "gates_measured": G, "area_delay": G * D, "adder": adder,
                   # the open problems carry `status` instead of `domain`; take whichever is there
                   "domain": P.get("domain") or P.get("status", ""), "shape": P["shape"],
                   "note": "thrown at the master autofab as a bare problem; it chose the adder. "
                           "Verified against an exact independent reference with all mutants CAUGHT."}
        json.dump(reg, open(REG, "w"), indent=1)
        stored += 1
        print("      STORED %s @ %s (%s B) [%.2fs byte edit]"
              % (nm, off, "{:,}".format(len(blob)), time.time() - t0))
        del c, outs
    if dry:
        print("\n  --dry: nothing written."); return 0
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  %d stored. titan GGUF-valid: %s. revert: python host/fab_problems.py revert" % (stored, valid))
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
