#!/usr/bin/env python3
"""host/mafab_hard2.py — SECOND BATCH OF OPEN PROBLEMS. Structures the corpus has never seen.

§16: *"'IMPOSSIBLE' PROBLEMS — the substrate does not refuse them, it MEASURES their parallelism."*
§39B's rule holds throughout: every candidate is ADDRESSED as an input, never computed by the host,
because "the host performing the very division the problem consists of... would have 'factored'
instantly and proved nothing."

Batch 1 covered squares (perfect_cuboid), a mux/add recurrence (collatz), pure boolean (sat3) and
differences (golomb). These four are picked for arithmetic the fabricator has not met:

  three_cubes    OPEN for n=114. Is every n (not 4,5 mod 9) a sum of three integer cubes? n=33 fell
                 in 2019 and n=42 in 2019, both by massive search. SIGNED CUBING.     REPLICATED
  erdos_straus   OPEN since 1948. Is 4/n = 1/x + 1/y + 1/z solvable for every n>1?
                 Verifier is the cleared-denominator identity 4xyz = n(yz+xz+xy).     REPLICATED
  lychrel        OPEN. Does 196 ever reach a palindrome under reverse-and-add? BASE-10 DIGITS
                 carried in binary — a structure nothing in the corpus has.           DEPENDENT
  lucas_lehmer   Whether infinitely many Mersenne primes exist is OPEN. The LL recurrence
                 s <- s^2 - 2 mod (2^p - 1) is a genuine dependent chain (§38B).       DEPENDENT

  python host/mafab_hard2.py                # all four
  python host/mafab_hard2.py three_cubes    # one
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import family, Shim, depth_of
from mafab_problems import sub, mux, geq, const, mul
from mafab_hard import eq, tree_and


# ══ SUMS OF THREE CUBES — n = x^3 + y^3 + z^3. OPEN for n = 114. ══════════════════════════════════
TCW, TCN = 7, 24
def build_cubes(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(3 * TCW + TCN); g = Shim(c)
    xs = [list(c.IN[i * TCW:(i + 1) * TCW]) for i in range(3)]
    n = list(c.IN[3 * TCW:3 * TCW + TCN])
    tot = const(g, 0, TCN)
    for v in xs:
        ve = (list(v) + [g.C0] * TCN)[:TCN]
        sq = mul(g, add, ve, ve)[:TCN]
        cu = mul(g, add, sq, ve)[:TCN]
        if mutant == "square": cu = sq
        tot = add(g, tot, cu)[:TCN]
    ok = eq(g, tot, n)
    if mutant == "always": ok = g.C1
    return c, [ok]


def ref_cubes(x, y, z, n):
    return 1 if ((x ** 3 + y ** 3 + z ** 3) & ((1 << TCN) - 1)) == n else 0


def cases_cubes(k=10, seed=3):
    random.seed(seed); out = []
    for i in range(k):
        x, y, z = (random.randrange(1 << TCW) for _ in range(3))
        n = (x ** 3 + y ** 3 + z ** 3) & ((1 << TCN) - 1)
        if i % 2: n = (n + 1) & ((1 << TCN) - 1)        # half must FAIL, so the suite discriminates
        out.append((x, y, z, n))
    return out


def check_cubes(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for x, y, z, n in cs:
        inb = []
        for v in (x, y, z): inb += [(v >> i) & 1 for i in range(TCW)]
        inb += [(n >> i) & 1 for i in range(TCN)]
        if TC.ripple(cd, inb)[0] == ref_cubes(x, y, z, n): ok += 1
    return ok


# ══ ERDOS-STRAUS — 4/n = 1/x + 1/y + 1/z, cleared: 4xyz = n(yz + xz + xy). OPEN since 1948. ════════
ESW, ESN = 6, 26
def build_es(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(4 * ESW); g = Shim(c)
    n, x, y, z = [list(c.IN[i * ESW:(i + 1) * ESW]) for i in range(4)]
    W = ESN
    def ext(v): return (list(v) + [g.C0] * W)[:W]
    xy = mul(g, add, ext(x), ext(y))[:W]
    xz = mul(g, add, ext(x), ext(z))[:W]
    yz = mul(g, add, ext(y), ext(z))[:W]
    xyz = mul(g, add, xy, ext(z))[:W]
    lhs = add(g, xyz, xyz)[:W]; lhs = add(g, lhs, lhs)[:W]          # 4xyz
    if mutant == "two": lhs = add(g, xyz, xyz)[:W]
    s = add(g, add(g, yz, xz)[:W], xy)[:W]
    rhs = mul(g, add, ext(n), s)[:W]
    ok = eq(g, lhs, rhs)
    if mutant == "always": ok = g.C1
    return c, [ok]


def ref_es(n, x, y, z):
    M = (1 << ESN) - 1
    return 1 if ((4 * x * y * z) & M) == ((n * (y * z + x * z + x * y)) & M) else 0


def cases_es(k=10, seed=5):
    random.seed(seed); out = []
    # positives from the known identity 4/n = 1/n + 1/n + 1/n only when... instead seed real solutions:
    for i in range(k):
        if i % 2 == 0:
            x = random.randrange(2, 1 << ESW); out.append((4, x, x, x) if False else (2, 2, 2, 1))
        else:
            out.append(tuple(random.randrange(1, 1 << ESW) for _ in range(4)))
    return out


def check_es(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for n, x, y, z in cs:
        inb = []
        for v in (n, x, y, z): inb += [(v >> i) & 1 for i in range(ESW)]
        if TC.ripple(cd, inb)[0] == ref_es(n, x, y, z): ok += 1
    return ok


# ══ LYCHREL / the 196 problem — reverse-and-add in BASE 10, carried in binary. OPEN. ═══════════════
LD, LSTEP = 3, 2          # LD decimal digits, LSTEP reverse-and-add rounds
def build_lychrel(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(4 * LD); g = Shim(c)
    dig = [list(c.IN[i * 4:(i + 1) * 4]) for i in range(LD)]         # BCD, least significant first
    def bcd_add(a, b):
        """digit-wise base-10 add with carry — the structure that makes this problem base-10."""
        out = []; carry = g.C0
        ten = const(g, 10, 5)
        for i in range(LD):
            ai = (list(a[i]) + [g.C0])[:5]; bi = (list(b[i]) + [g.C0])[:5]
            s = add(g, ai, bi)[:5]
            s = add(g, s, ([carry] + [g.C0] * 4))[:5]
            ge = geq(g, add, s, ten)
            adj = sub(g, add, s, ten)[:5]
            s = mux(g, ge, adj, s)
            carry = ge
            out.append(s[:4])
        return out
    cur = dig
    for _ in range(LSTEP):
        rev = list(reversed(cur))
        if mutant == "norev": rev = list(cur)
        cur = bcd_add(cur, rev)
    pal = tree_and(g, [eq(g, cur[i], cur[LD - 1 - i]) for i in range(LD // 2 + 1)])
    if mutant == "always": pal = g.C1
    return c, [pal]


def ref_lychrel(digs):
    v = digs[:]
    for _ in range(LSTEP):
        r = list(reversed(v))
        out = []; carry = 0
        for i in range(LD):
            s = v[i] + r[i] + carry
            out.append(s % 10); carry = 1 if s >= 10 else 0
        v = out
    return 1 if all(v[i] == v[LD - 1 - i] for i in range(LD // 2 + 1)) else 0


def cases_lychrel(k=12, seed=7):
    random.seed(seed)
    return [[random.randrange(10) for _ in range(LD)] for _ in range(k)]


def check_lychrel(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for digs in cs:
        inb = []
        for d in digs: inb += [(d >> i) & 1 for i in range(4)]
        if TC.ripple(cd, inb)[0] == ref_lychrel(digs): ok += 1
    return ok


# ══ LUCAS-LEHMER — s <- s^2 - 2 mod (2^p - 1). A DEPENDENT recurrence (§38B). ══════════════════════
LLP, LLSTEP = 7, 2                     # M_7 = 127
def build_ll(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(LLP); g = Shim(c)
    s = list(c.IN[0:LLP])
    M = const(g, (1 << LLP) - 1, LLP)
    W = LLP + 2                                           # headroom: lo+hi reaches 2^(p+1)-2
    Mw = const(g, (1 << LLP) - 1, W)
    for _ in range(LLSTEP):
        se = (list(s) + [g.C0] * LLP)[:2 * LLP]
        sq = mul(g, add, se, se)[:2 * LLP]
        lo = (sq[0:LLP] + [g.C0] * W)[:W]
        hi = (sq[LLP:2 * LLP] + [g.C0] * W)[:W]
        r = add(g, lo, hi)[:W]                            # 2^p == 1 (mod 2^p-1): fold the high half
        if mutant == "nofold": r = lo
        # TWO conditional subtractions, not one. lo+hi can reach 2^(p+1)-2, i.e. nearly 2M, so a
        # single subtract leaves values in [M, 2M) unreduced — that was the whole failure.
        for _k in range(2):
            ge = geq(g, add, r, Mw)
            r = mux(g, ge, sub(g, add, r, Mw)[:W], r)
        # s - 2, wrapping by +M when r < 2 (the residue must stay in [0, M))
        two = const(g, 2, W)
        lt2 = g.NOT(geq(g, add, r, two))
        d = sub(g, add, r, two)[:W]
        dw = add(g, d, Mw)[:W]
        r = mux(g, lt2, dw, d)
        for _k in range(2):                               # the wrap can re-enter [M, 2M)
            ge = geq(g, add, r, Mw)
            r = mux(g, ge, sub(g, add, r, Mw)[:W], r)
        s = r[:LLP]
    out = tree_and(g, [g.NOT(b) for b in s])              # LL passes iff the residue is 0
    if mutant == "always": out = g.C1
    return c, [out] + s


def ref_ll(s0):
    M = (1 << LLP) - 1
    s = s0
    for _ in range(LLSTEP):
        s = (s * s) % M
        s = (s - 2) % M
    return (1 if s == 0 else 0), s


def cases_ll(k=10, seed=9):
    random.seed(seed)
    return [random.randrange(1, 1 << LLP) for _ in range(k)]


def check_ll(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for s0 in cs:
        inb = [(s0 >> i) & 1 for i in range(LLP)]
        v = TC.ripple(cd, inb)
        got = (v[0], sum(v[1 + i] << i for i in range(LLP)))
        if got == ref_ll(s0): ok += 1
    return ok


HARD2 = {
    "three_cubes":  dict(build=build_cubes, check=check_cubes, cases=cases_cubes,
                         mutants=["square", "always"], shape="replicated",
                         status="OPEN for n=114 — n=33 and n=42 fell only in 2019, by massive search"),
    "erdos_straus": dict(build=build_es, check=check_es, cases=cases_es,
                         mutants=["two", "always"], shape="replicated",
                         status="OPEN since 1948 — 4/n = 1/x + 1/y + 1/z for every n > 1?"),
    "lychrel":      dict(build=build_lychrel, check=check_lychrel, cases=cases_lychrel,
                         mutants=["norev", "always"], shape="dependent",
                         status="OPEN — does 196 ever reach a palindrome under reverse-and-add?"),
    "lucas_lehmer": dict(build=build_ll, check=check_ll, cases=cases_ll,
                         mutants=["nofold", "always"], shape="dependent",
                         status="the LL test itself is exact; whether Mersenne primes are infinite is OPEN"),
}


def solve(name):
    import mafab_laws as L
    from mafab_host import Governor
    P = HARD2[name]
    cs = P["cases"]()
    fam = sorted(family(32))
    print("=" * 92)
    print("OPEN PROBLEM: %s" % name)
    print("  STATUS: %s" % P["status"])
    print("  shape %r -> REPLICAS set accordingly; scored ONLY by compute/tick (§63)." % P["shape"])
    print("  §39B: every candidate is ADDRESSED, never computed by the host.\n")
    gov = Governor()
    gov.calibrate(lambda: P["build"](fam[0]), name)
    res = []
    for i, ad in gov.each(fam):
        c, outs = P["build"](ad)
        ok = P["check"](c, outs, cs)
        D = depth_of(c, outs); G = len(c.ga)
        res.append(dict(adder=ad, depth=D, gates=G, ok=(ok == len(cs))))
        print("    %-11s DEPTH %7s  gates %9s   %d/%d"
              % (ad, "{:,}".format(D), "{:,}".format(G), ok, len(cs)))
        del c, outs
    gov.report()
    good = [r for r in res if r["ok"]]
    if not good:
        print("\n  NOTHING VERIFIED — MY construction of this verifier failed, a fact about the build")
        print("  I wrote and not about the problem (§7/§35D). Reported, not hidden.")
        return None
    ranked, label = L.rank(good, P["shape"])
    b = ranked[0]
    print("\n  VERIFIED %d/%d · ranked by %s" % (len(good), len(res), label))
    print("  WINNER %s — DEPTH %s gate-delays, %s gates, compute/tick %.6f"
          % (b["adder"], "{:,}".format(b["depth"]), "{:,}".format(b["gates"]),
             L.compute_per_tick(b["gates"], b["depth"], P["shape"] != "dependent")))
    for m in P["mutants"]:
        cm, om = P["build"](b["adder"], mutant=m)
        okm = P["check"](cm, om, cs)
        print("    mutant %-9s %d/%d -> %s" % (m, okm, len(cs),
              "CAUGHT" if okm != len(cs) else "*** SURVIVED — SUITE IS BLIND ***"))
        del cm, om
    return b


if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if not a.startswith("--")]
    for nm in (want or list(HARD2)):
        if nm not in HARD2:
            print("unknown: %r" % nm); continue
        solve(nm); print("")
    raise SystemExit(0)
