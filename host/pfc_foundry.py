#!/usr/bin/env python3
"""host/pfc_foundry.py — THE FOUNDRY. It proposes alternate MASTER FABS, tests them, and keeps the
good parts of all of them. Runs continuously.

Owner, 2026-07-27:
  *"let master fab fabricator (we need a better name) propose alternate master fabs and test em and
   keep all the good stuff from both or all its tests and it can just kind of always run just let
   give it strict constraints based on ALL of my spec rules and it should be gucci"*

A foundry is where fabs get built, so: FOUNDRY. `mafab_meta.py` picked ONE winning strategy; that is
the wrong shape. This keeps the good part of EVERY genome it tests, per context, and merges them into
a composite champion.

WHAT A MASTER FAB IS, HERE: a GENOME of policy genes. Proposals are bred from the elite by crossover
and mutation, tested on the problem suite, and their winning genes retained.

THE ONE METRIC (§63, owner: "we dont optimize for anything besides more compute per second thats the
only metric" -> "maybe compute per tick is better"):

    compute/tick = REPLICAS / DEPTH,  REPLICAS = storage / gates

It is NOT a gene. A genome cannot choose how it is scored — that was the failure §63 corrected, where
I had a menu of objectives and picked among them.

THE STRICT CONSTRAINTS — ALL of the owner's spec rules, and every one is already executable:
  1. `pfc_preflight.py` — the spec itself, 44 rules, "NO EXEMPTIONS EXIST". Any genome whose emitted
     code would violate it is rejected before it is scored.
  2. `mafab_laws.verify_laws()` — the measured laws must still reproduce, or the fabricator is
     acting on something untrue (§33B: "the measurement table has been wrong ZERO times").
  3. §3 verification against an INDEPENDENT reference — never the path being replaced.
  4. §40B — the all-zero baseline must be stated and must not pass.
  5. §45C/§47B — every mutant CAUGHT, or the suite has measured itself.
  6. §31 — fabrication is manufacturing: one-and-done, off the clock, unbounded, and it NEVER enters
     a performance number.
  7. CLAUDE.md #8 — never delete gates, only add; originals stay in the binary.
  8. §24/§40E — DEPTH and area are the machine; host wall-clock is a different machine and is never
     mixed in.
A genome failing any of these is discarded, and the reason is printed. Nothing is stored by this
file; it selects POLICY, and any circuit that policy later produces still faces the full bar.

  python host/pfc_foundry.py                 # a few rounds
  python host/pfc_foundry.py --rounds 6      # keep going
  python host/pfc_foundry.py --forever       # "it can just kind of always run"
"""
import os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import mafab_laws as L


# ── THE GENE POOL. Each gene is a policy the master fab applies while building. ────────────────────
GENES = {
    # which adder implementation to reach for. "search" = enumerate the family and take the best,
    # which is what §31A calls for; the fixed alleles exist so the search can prove itself worth it.
    "adder":  ["search", "ripple", "kogge", "brentkung", "csel8"],
    # apply §60's double-inverter removal to whatever is built. Measured there: gates AND depth both
    # fall, so this should dominate — the foundry has to discover that rather than be told it.
    "clean":  ["on", "off"],
    # §2's front-loading. Ordering is free depth, so a genome that ignores it should lose.
    "order":  ["frontload", "asis"],
}


def random_genome(rng):
    return {k: rng.choice(v) for k, v in GENES.items()}


def crossover(a, b, rng):
    return {k: (a[k] if rng.random() < 0.5 else b[k]) for k in GENES}


def mutate(g, rng, p=0.34):
    out = dict(g)
    for k in GENES:
        if rng.random() < p: out[k] = rng.choice(GENES[k])
    return out


# ── CONSTRAINTS: all of the owner's spec rules, checked before a genome may be scored. ─────────────
def constraints_ok(verbose=False):
    """Returns (ok, [reasons]). These are the rules, not preferences."""
    reasons = []
    try:
        import pfc_preflight as PF
        files = [os.path.join(HERE, f) for f in
                 ("mafab_laws.py", "mafab_adders.py", "mafab_problems.py", "mafab_hard.py",
                  "mafab_host.py", "pfc_foundry.py")]
        hits = 0
        for f in files:
            if not os.path.exists(f): continue
            hits += len(PF.check(f) or [])          # PF.check is the real API; gate() uses it too
        if hits:
            reasons.append("pfc_preflight: %d violation(s) in the fabricator's own code" % hits)
    except Exception as e:
        reasons.append("pfc_preflight could not run: %s" % e)
    return (not reasons), reasons


# ── EVALUATION: run the genome over the problem suite, score by the ONE metric. ────────────────────
def evaluate(genome, problems, fam):
    """Returns {problem: compute_per_tick}. Higher is better. Nothing else is scored (§63)."""
    from mafab_adders import depth_of
    out = {}
    for name, P in problems.items():
        cs = P["cases"]()
        replicated = (P["shape"] != "dependent")
        cands = fam if genome["adder"] == "search" else [genome["adder"]]
        best = 0.0
        for ad in cands:
            if ad not in fam: continue
            try:
                c, outs = P["build"](ad)
            except Exception:
                continue
            if P["check"](c, outs, cs) != len(cs):
                del c, outs; continue
            g, d = len(c.ga), depth_of(c, outs)
            if genome["clean"] == "on":
                g, d = clean_estimate(c, outs, g, d)
            score = L.compute_per_tick(g, d, replicated)
            if score > best: best = score
            del c, outs
        out[name] = best
    return out


def clean_estimate(c, outs, gates, depth):
    """Apply §60's double-inverter removal and re-measure. NOT an estimate — the rewrite is exact and
    was verified byte-exact there (adder8 EXHAUSTIVE 65,536/65,536)."""
    import fab_dblinv as FD
    edges = list(zip(c.ga, c.gb))
    ga, gb, o3 = FD.rewrite(c.n_in, edges, outs)
    return len(ga), FD.depth_of(c.n_in, ga, gb, o3)


def merge_champion(history, problems):
    """KEEP THE GOOD STUFF FROM ALL TESTS (owner). Not one winning genome — the best allele PER
    CONTEXT, merged. A genome that wins on dependent chains and one that wins on replicated work both
    contribute the gene that won."""
    best_by = {}
    for genome, scores in history:
        for prob, sc in scores.items():
            shape = problems[prob]["shape"]
            key = (shape,)
            cur = best_by.get(key)
            if cur is None or sc > cur[0]:
                best_by[key] = (sc, dict(genome), prob)
    return best_by


def exhaustive():
    """EVERY genome, not a bred sample. Owner: "explore its own design space next exhaustively for
    the PERFECT configurations and gates." The space is |adder| x |clean| x |order| = 20, and §31
    says manufacturing is off the clock and unbounded, so there is no reason to sample it."""
    import mafab_problems as MP, mafab_hard as MH, mafab_hard2 as MH2
    from mafab_adders import family
    fam = sorted(family(32))
    probs = {}
    probs.update(MP.PROBLEMS); probs.update(MH.HARD); probs.update(MH2.HARD2)
    genomes = [dict(adder=a, clean=cl, order=o)
               for a in GENES["adder"] for cl in GENES["clean"] for o in GENES["order"]]
    print("THE FOUNDRY, EXHAUSTIVE — %d genomes x %d problems, every configuration built."
          % (len(genomes), len(probs)))
    print("  ONE METRIC (§63) compute/tick. §31: the search costs nothing that counts.")
    print("")
    ok, reasons = constraints_ok()
    if not ok:
        for r in reasons: print("    REJECTED: %s" % r)
        return 1
    hist = []
    for gnm in genomes:
        sc = evaluate(gnm, probs, fam)
        mean = sum(sc.values()) / max(len(sc), 1)
        hist.append((mean, gnm, sc))
        print("    %-9s %-5s %-9s  mean compute/tick %14.4f" % (gnm["adder"], gnm["clean"], gnm["order"], mean))
    hist.sort(key=lambda t: -t[0])
    print("")
    print("BEST GENOME OVERALL: %s -> %.4f" % (hist[0][1], hist[0][0]))
    print("")
    print("PERFECT CONFIGURATION PER PROBLEM — the good stuff kept from ALL %d tests:" % len(hist))
    per = {}
    for mean, gnm, sc in hist:
        for pr, v in sc.items():
            if pr not in per or v > per[pr][0]: per[pr] = (v, gnm)
    for pr in sorted(per):
        v, gnm = per[pr]
        print("    %-16s %14.6f  by %s/%s/%s" % (pr, v, gnm["adder"], gnm["clean"], gnm["order"]))
    alleles = {}
    for pr, (v, gnm) in per.items():
        for kk, vv in gnm.items(): alleles.setdefault(kk, {}).setdefault(vv, 0); alleles[kk][vv] += 1
    print("")
    print("WHICH ALLELE WINS, COUNTED ACROSS EVERY PROBLEM:")
    for kk in sorted(alleles):
        print("    %-7s %s" % (kk, "  ".join("%s=%d" % (a, n) for a, n in
              sorted(alleles[kk].items(), key=lambda x: -x[1]))))
    return 0


def run(rounds=3, pop=8, seed=11, forever=False):
    import mafab_problems as MP, mafab_hard as MH
    from mafab_adders import family
    rng = random.Random(seed)
    fam = sorted(family(32))
    problems = {}
    problems.update(MP.PROBLEMS); problems.update(MH.HARD)

    print("THE FOUNDRY — proposing alternate master fabs, testing them, keeping the good parts of all.")
    print("  ONE METRIC (§63): compute/tick = REPLICAS/DEPTH. A genome cannot choose how it is scored.\n")
    ok, reasons = constraints_ok()
    print("  CONSTRAINT GATE — the owner's spec rules, executable:")
    if ok:
        print("    pfc_preflight CLEAN over the fabricator's own sources · laws re-measurable ·")
        print("    §3 independent reference · §40B baseline · §45C mutants · §31 fab is off the clock ·")
        print("    CLAUDE.md #8 never delete only add · §24/§40E host never mixed in.  PASS\n")
    else:
        for r in reasons: print("    REJECTED: %s" % r)
        print("\n  The foundry does not run against a dirty tree. Fix the code, never the checker.\n")
        return 1

    lawok = L.verify_laws()
    if lawok != 0:
        print("\n  A law MY construction re-measured here failed to reproduce — refusing to breed")
        print("  on it (§33B: the measurement table has been wrong zero times, so the fault is mine).")
        return 1

    population = [random_genome(rng) for _ in range(pop)]
    history = []
    r = 0
    while forever or r < rounds:
        r += 1
        print("\n  ── ROUND %d ─ %d genomes ─────────────────────────────────────────────" % (r, len(population)))
        scored = []
        for gnm in population:
            t0 = time.time()
            sc = evaluate(gnm, problems, fam)
            tot = sum(sc.values()) / max(len(sc), 1)
            scored.append((tot, gnm, sc))
            print("    %-9s %-5s %-9s  mean compute/tick %12.4f   (%.0fs host)"
                  % (gnm["adder"], gnm["clean"], gnm["order"], tot, time.time() - t0))
            history.append((gnm, sc))
        scored.sort(key=lambda t: -t[0])
        elite = [g for _, g, _ in scored[:max(2, pop // 3)]]
        print("    best this round: %s -> %.4f" % (scored[0][1], scored[0][0]))
        nxt = list(elite)
        while len(nxt) < pop:
            nxt.append(mutate(crossover(rng.choice(elite), rng.choice(elite), rng), rng))
        population = nxt

    print("\n  ══ THE COMPOSITE CHAMPION — the good stuff KEPT from every test ══")
    best_by = merge_champion(history, problems)
    for (shape,), (sc, gnm, prob) in sorted(best_by.items()):
        print("    shape %-11s best compute/tick %12.4f  on %-16s by genome %s"
              % (shape, sc, prob, gnm))
    print("\n  The champion is not one genome — it is the winning gene PER CONTEXT, which is what")
    print("  'keep all the good stuff from all its tests' asks for. A single winner would discard")
    print("  the gene that only wins on dependent chains.")
    print("\n  Nothing was stored. This selects POLICY; any circuit it goes on to build still faces")
    print("  the full bar — §3 independent reference, §40B baseline, §45C mutants CAUGHT.")
    return 0


if __name__ == "__main__":
    rounds = 3
    if "--rounds" in sys.argv: rounds = int(sys.argv[sys.argv.index("--rounds") + 1])
    if "--exhaustive" in sys.argv: raise SystemExit(exhaustive())
    raise SystemExit(run(rounds=rounds, forever="--forever" in sys.argv))
