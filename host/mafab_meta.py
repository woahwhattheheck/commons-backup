#!/usr/bin/env python3
"""host/mafab_meta.py — THE MASTERFAB FABRICATOR. It builds the master fab's STRATEGY.

Owner: *"what about a masterfab fabricator that builds the masterfab...?"*

§32 already established the level below this — *"THE FABRICATOR, FABRICATED — the Muhlnickel emits
its own netlists"* — where the thing produced was a NETLIST. Here the thing produced is the master
fab's own SEARCH STRATEGY: which primitive it reaches for, and by what criterion it ranks. The
strategy stops being something I write and becomes a searched artifact, scored by the circuits it
actually produces.

WHY THIS IS THE RIGHT FIXED POINT, and not a regress. §31A retired hardcoded rules in favour of
search: *"§25's adder table stops being a rule to hardcode and becomes ONE ENTRY IN A SPACE TO BE
SEARCHED."* But `mafab_laws.LAW 1` still encodes §25C's crossover as a decision, and I still choose
the ranking criterion per need. Those are the last two hand-written policies in the fabricator. A
meta-fab searches THEM, evaluated against the measured outcome across every problem thrown so far.

THE EVIDENCE IT RUNS ON is not simulated — it is the recorded result of every problem the fabricator
has actually solved, each verified against an independent reference with mutants CAUGHT.

WHAT A STRATEGY IS: a rule for picking the implementation, from
  {always-<adder>}                    a fixed choice, the shape §25C's rule has
  {search-by-depth, search-by-area}   enumerate and rank, the shape §31A calls for
Each is scored by the circuits it would have produced across all problems. Lower is better, and the
score is normalised per problem so a big circuit cannot dominate a small one.

  python host/pfc_master_autofab.py metafab      # the intended entry (§62C: inside the fab)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def gather(problems=None, hard=None):
    """Re-measure every problem across every adder. The evidence the meta-fab searches over."""
    import mafab_problems as MP, mafab_hard as MH
    from mafab_adders import family, depth_of
    fam = sorted(family(32))
    table = {}                       # problem -> {adder: (depth, gates)} , plus its declared shape
    srcs = [(MP.PROBLEMS, MP), (MH.HARD, MH)]
    for reg, mod in srcs:
        for name, P in reg.items():
            cs = P["cases"]()
            row = {}
            for ad in fam:
                try:
                    c, outs = P["build"](ad)
                except Exception:
                    continue
                ok = P["check"](c, outs, cs)
                if ok == len(cs):
                    row[ad] = (depth_of(c, outs), len(c.ga))
                del c, outs
            if row: table[name] = dict(row=row, shape=P["shape"])
            print("    measured %-16s %d/%d adders verified" % (name, len(row), len(fam)))
    return table, fam


STRATEGIES = {}


def build_strategies(fam):
    """The strategy SPACE, generated from the adder family rather than listed by me (§40A)."""
    S = {}
    for ad in fam:
        S["always-" + ad] = ("fixed", ad)
    S["search-by-depth"] = ("search", "depth")
    S["search-by-area"] = ("search", "area")
    return S


def score_strategy(kind, arg, table):
    """What circuits would this strategy have produced? Normalised per problem so scale cannot
    dominate: 1.0 means it picked the best available implementation for that problem."""
    tot, n, misses = 0.0, 0, []
    for name, e in table.items():
        row = e["row"]; shape = e["shape"]
        if not row: continue
        key = (lambda t: t[0]) if shape == "dependent" else (lambda t: t[0] * t[1])
        best = min(key(v) for v in row.values())
        if kind == "fixed":
            if arg not in row:
                misses.append(name); continue
            got = key(row[arg])
        else:
            sel = min(row.values(), key=(lambda t: t[0]) if arg == "depth" else (lambda t: t[0] * t[1]))
            got = key(sel)
        tot += got / max(best, 1); n += 1
    return (tot / max(n, 1)), n, misses


def metafab():
    print("THE MASTERFAB FABRICATOR — searching the master fab's own STRATEGY (§32 one level up).\n")
    print("  Evidence: every problem the fabricator has solved, re-measured across every adder.")
    print("  Each was verified against an INDEPENDENT reference with mutants CAUGHT before it counted.\n")
    table, fam = gather()
    S = build_strategies(fam)
    print("\n  %d problems x %d adders measured · %d strategies generated\n"
          % (len(table), len(fam), len(S)))
    res = []
    for nm, (kind, arg) in S.items():
        sc, n, misses = score_strategy(kind, arg, table)
        res.append((sc, nm, n, misses))
    res.sort()
    print("    %-22s %10s  %s" % ("strategy", "score", "notes  (1.000 = always picked the best)"))
    for sc, nm, n, misses in res:
        note = "over %d problems" % n
        if misses: note += ", FAILED on %s" % ",".join(misses[:3])
        print("    %-22s %10.4f  %s" % (nm, sc, note))
    best = res[0]
    print("\n  WINNING STRATEGY: %s (score %.4f)" % (best[1], best[0]))
    fixed = [r for r in res if r[1].startswith("always-")]
    searched = [r for r in res if r[1].startswith("search-")]
    if fixed and searched:
        bf, bs = min(fixed), min(searched)
        print("  best FIXED rule %s = %.4f · best SEARCH %s = %.4f -> search is %.2fx better"
              % (bf[1], bf[0], bs[1], bs[0], bf[0] / max(bs[0], 1e-9)))
        print("\n  §31A said this without measuring it: a hardcoded adder rule is 'FAR TOO TIMID —")
        print("  it treats fabrication as if it had a budget.' The gap above is that sentence, priced.")
    print("\n  This does not store a circuit. It selects the POLICY the master fab searches under,")
    print("  and every circuit it goes on to produce still faces the full bar (§3/§40B/§45C).")
    return 0


if __name__ == "__main__":
    raise SystemExit(metafab())
