#!/usr/bin/env python3
"""Component implementation and operation."""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import family, Shim, depth_of
from mafab_problems import sub, mux, geq, const, mul


def eq(g, x, y):
    """x == y, as a tree of AND over XNOR — a tree, never a chain (§2/§36)."""
    bits = [g.NOT(g.XOR(x[i], y[i])) for i in range(len(x))]
    while len(bits) > 1:
        nxt = [g.AND(bits[i], bits[i + 1]) for i in range(0, len(bits) - 1, 2)]
        if len(bits) % 2: nxt.append(bits[-1])
        bits = nxt
    return bits[0]


def tree_and(g, bits):
    while len(bits) > 1:
        nxt = [g.AND(bits[i], bits[i + 1]) for i in range(0, len(bits) - 1, 2)]
        if len(bits) % 2: nxt.append(bits[-1])
        bits = nxt
    return bits[0]


# ══ PERFECT CUBOID — OPEN SINCE EULER. Verifier only; the roots are ADDRESSED (§39B). ═════════════
CW = 8
def build_cuboid(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(3 * CW + 4 * (CW + 2)); g = Shim(c)
    a = list(c.IN[0:CW]); b = list(c.IN[CW:2 * CW]); d = list(c.IN[2 * CW:3 * CW])
    base = 3 * CW; RW = CW + 2
    r = [list(c.IN[base + i * RW: base + (i + 1) * RW]) for i in range(4)]
    W = 2 * CW + 2
    def sq(v, w):
        p = mul(g, add, v, v)
        return (p + [g.C0] * w)[:w]
    aa, bb, cc = sq(a, W), sq(b, W), sq(d, W)
    ab = add(g, aa, bb)[:W]
    bc = add(g, bb, cc)[:W]
    ac = add(g, aa, cc)[:W]
    abc = add(g, ab, cc)[:W]
    tgt = [ab, bc, ac, abc]
    chk = []
    for i in range(4):
        ri = sq(r[i], W)
        chk.append(eq(g, ri, tgt[i]))
    if mutant == "drop3": chk = chk[:1]
    ok = tree_and(g, chk)
    if mutant == "always": ok = g.C1
    return c, [ok]


def ref_cuboid(a, b, d, rs):
    t = [a * a + b * b, b * b + d * d, a * a + d * d, a * a + b * b + d * d]
    return 1 if all(rs[i] * rs[i] == t[i] for i in range(4)) else 0


def cases_cuboid(n=10, seed=4):
    random.seed(seed); out = []
    for i in range(n):
        a = random.randrange(1, 1 << CW); b = random.randrange(1, 1 << CW); d = random.randrange(1, 1 << CW)
        if i % 2 == 0:                       # POSITIVE controls: make two faces exact (3-4-5 style)
            a, b = 3, 4
        rs = [int((a * a + b * b) ** 0.5), int((b * b + d * d) ** 0.5),
              int((a * a + d * d) ** 0.5), int((a * a + b * b + d * d) ** 0.5)]
        out.append((a, b, d, rs))
    return out


def check_cuboid(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    RW = CW + 2
    for a, b, d, rs in cs:
        inb = []
        for v, w in ((a, CW), (b, CW), (d, CW)): inb += [(v >> i) & 1 for i in range(w)]
        for rv in rs: inb += [(rv >> i) & 1 for i in range(RW)]
        if TC.ripple(cd, inb)[0] == ref_cuboid(a, b, d, rs): ok += 1
    return ok


# ══ COLLATZ — OPEN. A DEPENDENT chain: each step needs the previous (§38B). ════════════════════════
CB, STEPS = 12, 6
def build_collatz(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(CB); g = Shim(c)
    n = list(c.IN[0:CB])
    for _ in range(STEPS):
        odd = n[0]
        half = n[1:] + [g.C0]
        tri = add(g, add(g, n, n[:])[:CB], n)[:CB]        # 3n via 2n + n
        tri = add(g, tri, const(g, 1, CB))[:CB]           # 3n+1
        if mutant == "no3n1": tri = list(n)
        n = mux(g, odd, tri, half)
    one = eq(g, n, const(g, 1, CB))
    if mutant == "alwaysone": one = g.C1
    return c, [one] + n


def ref_collatz(n0):
    n = n0
    for _ in range(STEPS):
        n = ((3 * n + 1) if (n & 1) else (n >> 1)) & ((1 << CB) - 1)
    return (1 if n == 1 else 0), n


def cases_collatz(n=10, seed=6):
    random.seed(seed)
    return [random.randrange(1, 1 << CB) for _ in range(n)]


def check_collatz(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for n0 in cs:
        inb = [(n0 >> i) & 1 for i in range(CB)]
        v = TC.ripple(cd, inb)
        got = (v[0], sum(v[1 + i] << i for i in range(CB)))
        if got == ref_collatz(n0): ok += 1
    return ok


# ══ 3-SAT — NP-complete. §17 precedent, and §17's own "this does NOT beat NP" stays attached. ══════
NV, NC = 12, 10
def build_sat(adder, mutant=None):
    c = TC.Circuit(NV + NC * 3 * 5); g = Shim(c)
    asg = list(c.IN[0:NV])
    lits = c.IN[NV:]
    sat = []
    for j in range(NC):
        cl = []
        for k in range(3):
            o = j * 15 + k * 5
            idx = list(lits[o:o + 4]); neg = lits[o + 4]
            sel = []
            for vv in range(NV):
                m = [idx[t] if (vv >> t) & 1 else g.NOT(idx[t]) for t in range(4)]
                sel.append(g.AND(tree_and(g, m), asg[vv]))
            val = sel[0]
            for s in sel[1:]: val = g.OR(val, s)
            cl.append(g.XOR(val, neg))
        lit = g.OR(g.OR(cl[0], cl[1]), cl[2])
        if mutant == "andclause": lit = tree_and(g, cl)
        sat.append(lit)
    out = tree_and(g, sat)
    if mutant == "always": out = g.C1
    return c, [out]


def ref_sat(asg, clauses):
    for cl in clauses:
        if not any(((asg >> v) & 1) ^ ng for v, ng in cl): return 0
    return 1


def cases_sat(n=8, seed=8):
    random.seed(seed); out = []
    for _ in range(n):
        asg = random.getrandbits(NV)
        clauses = [[(random.randrange(NV), random.randrange(2)) for _ in range(3)] for _ in range(NC)]
        out.append((asg, clauses))
    return out


def check_sat(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for asg, clauses in cs:
        inb = [(asg >> i) & 1 for i in range(NV)]
        for cl in clauses:
            for v, ng in cl:
                inb += [(v >> t) & 1 for t in range(4)] + [ng]
        if TC.ripple(cd, inb)[0] == ref_sat(asg, clauses): ok += 1
    return ok


# ══ GOLOMB RULER — optimal orders past OGR-28 are OPEN. Verifier: all differences distinct. ════════
GM, GW = 5, 7
def build_golomb(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(GM * GW); g = Shim(c)
    m = [list(c.IN[i * GW:(i + 1) * GW]) for i in range(GM)]
    diffs = []
    for i in range(GM):
        for j in range(i + 1, GM):
            diffs.append(sub(g, add, m[j], m[i])[:GW])
    distinct = []
    for i in range(len(diffs)):
        for j in range(i + 1, len(diffs)):
            distinct.append(g.NOT(eq(g, diffs[i], diffs[j])))
    if mutant == "half": distinct = distinct[:len(distinct) // 2]
    ok = tree_and(g, distinct)
    if mutant == "always": ok = g.C1
    return c, [ok]


def ref_golomb(marks):
    d = [marks[j] - marks[i] for i in range(GM) for j in range(i + 1, GM)]
    return 1 if len(set(d)) == len(d) else 0


def cases_golomb(n=16, seed=2):
    """A narrow range makes collisions COMMON and, crucially, SCATTERED across all 10 difference
    pairs. The first version forced a collision into one fixed pair, so the `half` mutant (which
    drops half the distinctness checks) SURVIVED 10/10 — the suite could not see it. §45C/§47B: a
    mutant that survives means the CASES are wrong, not the mutant."""
    random.seed(seed); out = []
    for _ in range(n):
        out.append(sorted(random.sample(range(24), GM)))
    return out


def check_golomb(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for marks in cs:
        inb = []
        for v in marks: inb += [(v >> i) & 1 for i in range(GW)]
        if TC.ripple(cd, inb)[0] == ref_golomb(marks): ok += 1
    return ok


HARD = {
    "perfect_cuboid": dict(build=build_cuboid, check=check_cuboid, cases=cases_cuboid,
                           mutants=["drop3", "always"], shape="replicated",
                           status="OPEN since Euler — no perfect cuboid is known to exist or not"),
    "collatz":        dict(build=build_collatz, check=check_collatz, cases=cases_collatz,
                           mutants=["no3n1", "alwaysone"], shape="dependent",
                           status="OPEN — the 3n+1 conjecture is unproven"),
    "sat3":           dict(build=build_sat, check=check_sat, cases=cases_sat,
                           mutants=["andclause", "always"], shape="replicated",
                           status="NP-complete. §17: 'this does NOT beat NP' — the verifier is what is built"),
    "golomb":         dict(build=build_golomb, check=check_golomb, cases=cases_golomb,
                           mutants=["half", "always"], shape="replicated",
                           status="OPEN past OGR-28 — optimal rulers unknown"),
}


def solve(name):
    import mafab_laws as L
    from mafab_host import Governor
    P = HARD[name]
    cs = P["cases"]()
    fam = sorted(family(32))
    print("=" * 92)
    print("HARD PROBLEM: %s" % name)
    print("  STATUS: %s" % P["status"])
    print("  shape %r declared -> scorer DERIVED (LAW 4). The fabricator builds the VERIFIER;" % P["shape"])
    print("  §39B: every candidate is ADDRESSED as an input, never computed by the host.\n")
    gov = Governor()
    gov.calibrate(lambda: P["build"](fam[0]), name)
    res = []
    for i, ad in gov.each(fam):
        try:
            c, outs = P["build"](ad)
        except Exception as e:
            gov.drop(ad, "build failed: %s" % e); continue
        ok = P["check"](c, outs, cs)
        D = depth_of(c, outs); G = len(c.ga)
        res.append(dict(adder=ad, depth=D, gates=G, ok=(ok == len(cs))))
        print("    %-11s DEPTH %7s  gates %9s   %d/%d"
              % (ad, "{:,}".format(D), "{:,}".format(G), ok, len(cs)))
        del c, outs
    gov.report()
    good = [r for r in res if r["ok"]]
    if not good:
        print("\n  NOTHING VERIFIED — MY construction of this verifier failed, a fact about the")
        print("  build I wrote and not about the problem (§7/§35D). Reported, not hidden.")
        return None
    ranked, label = L.rank(good, P["shape"])
    b = ranked[0]
    print("\n  VERIFIED %d/%d · ranked by %s" % (len(good), len(res), label))
    print("  WINNER %s — DEPTH %s gate-delays, %s gates"
          % (b["adder"], "{:,}".format(b["depth"]), "{:,}".format(b["gates"])))
    print("  §40C bank law: W replicas cost DEPTH + 2*log2(W), settles 1. The whole candidate space")
    print("  in one settle is an AREA question, never a latency one (§24: area is not slowness).")
    for m in P["mutants"]:
        cm, om = P["build"](b["adder"], mutant=m)
        okm = P["check"](cm, om, cs)
        print("    mutant %-10s %d/%d -> %s" % (m, okm, len(cs),
              "CAUGHT" if okm != len(cs) else "*** SURVIVED ***"))
        del cm, om
    return b


if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if not a.startswith("--")]
    for nm in (want or list(HARD)):
        if nm not in HARD:
            print("unknown: %r" % nm); continue
        solve(nm); print("")
    raise SystemExit(0)
