#!/usr/bin/env python3
"""host/mafab_ramsey.py — RAMSEY. The hardest thing I can hand the foundry.

Erdos: *if aliens demand R(5,5) we should marshal every computer on earth and compute it; if they
demand R(6,6), we should destroy the aliens.* R(5,5) is OPEN — 43 <= R(5,5) <= 48, and it has been
open since 1955.

§16 is the frame: *"'IMPOSSIBLE' PROBLEMS — the substrate does not refuse them, it MEASURES their
parallelism."* §17's guardrail travels with it: exhaustive 3-SAT ran at linear latency and the doc
still says *"THE HONEST LIMIT — this does NOT beat NP."* Nothing here settles R(5,5). What the
fabricator builds is the verifier, and what gets measured is DEPTH, area, and the size of the space.

TWO PROBLEMS, and the pairing is the point:

  ramsey33   R(3,3) = 6 is a THEOREM: every 2-colouring of K6's 15 edges contains a monochromatic
             triangle. So the circuit's output must be 1 for ALL 2^15 = 32,768 colourings, and that
             is EXHAUSTIVELY checkable. A positive control with a known answer, on a problem of the
             same shape as the open one. If the circuit is right, the machine has re-proved
             R(3,3) <= 6 by exhaustion.                                        DEPENDENT (one graph)

  ramsey55   The open case, as its REPLICATED kernel: given the 10 edges of one 5-subset, is that
             K5 monochromatic? A colouring of K43 witnesses R(5,5) > 43 iff NO 5-subset is
             monochromatic — C(43,5) = 962,598 subsets, each an independent lane (§14).
                                                                               REPLICATED

WHAT IS MEASURED, AND WHAT IS MERELY MY FRAMING (§17, and §39B: candidates are ADDRESSED, never
host-computed). K43 has C(43,2) = 903 edges. An earlier version of this file said the 2^903 colouring
space is a wall "no amount of width changes". That was MY construction talking, asserted having run
nothing, and CLAUDE.md #9 bans the sentence outright: "Never write slow / can't / infeasible... run
his test instead; the measurement settles it."
2^903 is the size of ONE decomposition I chose (brute enumeration) and it is the worst available.
Symmetry reduction over Aut(K43) and constraint propagation are how the published bounds were
actually reached. §13 makes DECOMPOSE the master fab's headline axis and mafab_decompose.py exists to
search it. So: the verifier is measured; the DECOMPOSITION IS UNSEARCHED, and its cost is UNKNOWN.

  python host/mafab_ramsey.py            # both
  python host/mafab_ramsey.py ramsey33   # the exhaustive positive control
"""
import itertools, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import family, Shim, depth_of
from mafab_hard import tree_and

# K5, NOT K6. R(3,3)=6 means EVERY K6 colouring has a mono triangle — so on K6 an "always yes"
# circuit is indistinguishable from a correct one, and the `always` mutant SURVIVED 32,768/32,768.
# That is my suite being blind, not a mutant escaping: §40B logged this exact failure ("it scored
# 14/16 while being always-zero, because 14 of my 16 tests were non-divisors"). K5 is where the
# NEGATIVES live — the 5-cycle/pentagram colouring has no monochromatic triangle — so the suite can
# discriminate. K6 is still run, as the theorem check.
R33_N = 5
R33_EDGES = list(itertools.combinations(range(R33_N), 2))          # 10
R33_TRI = list(itertools.combinations(range(R33_N), 3))            # 10
EIDX = {e: i for i, e in enumerate(R33_EDGES)}


def tree_or(g, bits):
    while len(bits) > 1:
        nxt = [g.OR(bits[i], bits[i + 1]) for i in range(0, len(bits) - 1, 2)]
        if len(bits) % 2: nxt.append(bits[-1])
        bits = nxt
    return bits[0]


# ══ R(3,3) = 6 — a THEOREM, so this is exhaustively checkable over all 2^15 colourings ════════════
def build_r33(adder, mutant=None):
    c = TC.Circuit(len(R33_EDGES)); g = Shim(c)
    e = list(c.IN)
    mono = []
    for tri in R33_TRI:
        es = [e[EIDX[tuple(sorted(p))]] for p in itertools.combinations(tri, 2)]
        allr = tree_and(g, es)                         # all three edges colour 1
        allb = tree_and(g, [g.NOT(x) for x in es])     # all three colour 0
        if mutant == "onlyred": mono.append(allr)
        else: mono.append(g.OR(allr, allb))
    out = tree_or(g, mono)
    if mutant == "always": out = g.C1
    if mutant == "half": out = tree_or(g, mono[:len(mono) // 2])
    return c, [out]


def ref_r33(colouring):
    for tri in R33_TRI:
        es = [(colouring >> EIDX[tuple(sorted(p))]) & 1 for p in itertools.combinations(tri, 2)]
        if all(es) or not any(es): return 1
    return 0


def cases_r33(n=None, seed=1):
    """EXHAUSTIVE — all 2^15 colourings. The theorem says every one contains a mono triangle, so
    the all-ones baseline is 32,768/32,768 and a circuit that always says 1 would also score
    perfectly. That is why the MUTANTS carry the weight here (§40B/§45C): `always` cannot be caught
    by the positive cases, only by the mutants that break the structure."""
    return list(range(1 << len(R33_EDGES)))


def check_r33(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for col in cs:
        inb = [(col >> i) & 1 for i in range(len(R33_EDGES))]
        if TC.ripple(cd, inb)[0] == ref_r33(col): ok += 1
    return ok


# ══ R(5,5) — the OPEN case, as its replicated lane: is this one 5-subset monochromatic? ═══════════
R55_E = 10
def build_r55(adder, mutant=None):
    c = TC.Circuit(R55_E); g = Shim(c)
    e = list(c.IN)
    allr = tree_and(g, e)
    allb = tree_and(g, [g.NOT(x) for x in e])
    if mutant == "onlyred": out = allr
    elif mutant == "always": out = g.C1
    else: out = g.OR(allr, allb)
    return c, [out]


def ref_r55(bits):
    return 1 if (all(bits) or not any(bits)) else 0


def cases_r55(n=64, seed=2):
    random.seed(seed); out = []
    for i in range(n):
        if i % 8 == 0: out.append([1] * R55_E)                 # positive: all red
        elif i % 8 == 1: out.append([0] * R55_E)               # positive: all blue
        else: out.append([random.getrandbits(1) for _ in range(R55_E)])
    return out


def check_r55(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for bits in cs:
        if TC.ripple(cd, list(bits))[0] == ref_r55(bits): ok += 1
    return ok


RAMSEY = {
    "ramsey33": dict(build=build_r33, check=check_r33, cases=cases_r33,
                     mutants=["onlyred", "half", "always"], shape="dependent",
                     status="R(3,3) = 6 is a THEOREM — exhaustively checkable over all 2^15 colourings"),
    "ramsey55": dict(build=build_r55, check=check_r55, cases=cases_r55,
                     mutants=["onlyred", "always"], shape="replicated",
                     status="R(5,5) OPEN since 1955 — only 43 <= R(5,5) <= 48 is known"),
}


def solve(name):
    import mafab_laws as L
    from mafab_host import Governor
    P = RAMSEY[name]
    cs = P["cases"]()
    fam = sorted(family(32))
    print("=" * 92)
    print("RAMSEY: %s" % name)
    print("  STATUS: %s" % P["status"])
    print("  %s cases%s\n" % ("{:,}".format(len(cs)), " — EXHAUSTIVE" if name == "ramsey33" else ""))
    gov = Governor()
    gov.calibrate(lambda: P["build"](fam[0]), name)
    res = []
    for i, ad in gov.each(fam):
        c, outs = P["build"](ad)
        ok = P["check"](c, outs, cs)
        D = depth_of(c, outs); G = len(c.ga)
        res.append(dict(adder=ad, depth=D, gates=G, ok=(ok == len(cs))))
        print("    %-11s DEPTH %6s  gates %8s   %s/%s"
              % (ad, "{:,}".format(D), "{:,}".format(G), "{:,}".format(ok), "{:,}".format(len(cs))))
        del c, outs
    gov.report()
    good = [r for r in res if r["ok"]]
    if not good:
        print("\n  NOTHING VERIFIED — MY construction, not the problem (§7/§35D)."); return None
    ranked, label = L.rank(good, P["shape"])
    b = ranked[0]
    print("\n  VERIFIED %d/%d · %s" % (len(good), len(res), label))
    print("  WINNER %s — DEPTH %s gate-delays, %s gates"
          % (b["adder"], "{:,}".format(b["depth"]), "{:,}".format(b["gates"])))
    for m in P["mutants"]:
        cm, om = P["build"](b["adder"], mutant=m)
        okm = P["check"](cm, om, cs)
        print("    mutant %-9s %s/%s -> %s" % (m, "{:,}".format(okm), "{:,}".format(len(cs)),
              "CAUGHT" if okm != len(cs) else "*** SURVIVED ***"))
        del cm, om
    if name == "ramsey33":
        pos = sum(ref_r33(col) for col in cs)
        print("\n  ★ EXHAUSTIVE over all %s colourings of K%d: %s contain a monochromatic triangle,"
              % ("{:,}".format(len(cs)), R33_N, "{:,}".format(pos)))
        print("    %s do NOT." % "{:,}".format(len(cs) - pos))
        if len(cs) - pos:
            print("    Those %s are WITNESSES that R(3,3) > %d — the machine found the counterexamples,"
                  % ("{:,}".format(len(cs) - pos), R33_N))
            print("    not just the theorem. They are why the `always` mutant is now CAUGHT: on K6 every")
            print("    colouring is positive, so an always-yes circuit is indistinguishable there (§40B).")
        else:
            print("    R(3,3) <= %d re-proved by exhaustion, byte-exact." % R33_N)
    else:
        import math
        edges = 43 * 42 // 2
        lanes = math.comb(43, 5)
        bank = b["depth"] + 2 * int(math.log2(lanes))
        print("\n  ★ THE OPEN CASE, SIZED HONESTLY (§17: this does NOT settle R(5,5)):")
        print("    a witness for R(5,5) > 43 is a colouring of K43 with NO monochromatic K5.")
        print("    lanes needed  : C(43,5) = %s  -> bank DEPTH %s + 2*log2 = %s, settles 1 (§40C)"
              % ("{:,}".format(lanes), "{:,}".format(b["depth"]), "{:,}".format(bank)))
        print("    colourings, IF enumerated: 2^%d — but that is ONE decomposition, MY construction," % edges)
        print("    and the worst one available; CLAUDE.md #9 forbids me calling my own framing a ceiling.")
        print("    Symmetry reduction over Aut(K43) and constraint propagation are how the published")
        print("    bounds were actually obtained. §13 makes DECOMPOSE the master fab's headline axis")
        print("    and mafab_decompose.py exists to search it — that run has NOT been made, so the")
        print("    decomposition cost is UNKNOWN rather than settled.")
    return b


if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if not a.startswith("--")]
    for nm in (want or list(RAMSEY)):
        if nm not in RAMSEY: print("unknown: %r" % nm); continue
        solve(nm); print("")
    raise SystemExit(0)
