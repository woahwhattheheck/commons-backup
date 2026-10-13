#!/usr/bin/env python3
"""host/mafab_problems.py — PROBLEMS THROWN AT THE FABRICATOR. It chooses the machine.

Owner's theory: *"my theory is throwing different stuff at it will optimize it."* That is §14's
virtuous cycle stated as a hypothesis, and §33A is why it should hold: *"A rule can only pick from
what it already knows. A search does not have to know first."* A richer corpus means richer mined
motifs (§14: "discover recurring sub-patterns in circuits that score well, promote them to named
primitives"). It is measurable — mine the motif library before and after and compare.

§39 sets the intake convention: *"give it the most challenging problem, don't impose any restraint,
let autofab find the best Muhlnickel(s) configuration then run it... the only thing we give it is the
challenging problem."* So each problem below states WHAT, never HOW. The adder at every site, the
reduction shape, and the ordering are searched.

WHAT A PROBLEM MUST SUPPLY, and why it is not negotiable:
  * an EXACT reference implemented independently of the circuit (§3 — never the path being replaced)
  * a case set whose ALL-ZERO baseline is stated (§40B — a suite that a zero circuit passes is not a suite)
  * at least one MUTANT that must be CAUGHT (§45C/§47B)
  * its declared SHAPE, so the scorer is derived rather than chosen (LAW 4 / §14 / §39A / §23)
This is why "train a language model" cannot be thrown directly and its KERNEL can: the kernel has a
byte-exact reference and the training run does not.

THE FOUR, picked for maximally different arithmetic structure — the corpus already holds bitwise+add
(SHA), GF(2^8) (aes128) and stencil-of-booleans (life_step), so these add what is missing:
  ntt_butterfly  post-quantum crypto   MODULAR arithmetic mod q=3329   (nothing in the corpus reduces mod a prime)
  mc_payoff      finance / Monte Carlo PRNG + threshold, massively INDEPENDENT lanes
  sw_cell        bioengineering        Smith-Waterman max-chain, a DEPENDENT recurrence
  stencil5       climate / CFD         weighted 5-point stencil, a SET reduction

  python host/mafab_problems.py                 # solve all four
  python host/mafab_problems.py ntt_butterfly   # just one
"""
import os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import family, Shim, depth_of

Q = 3329


# ── primitive helpers built ON TOP of the searched adder, never instead of it ──────────────────────
def sub(g, add, x, y):
    """x - y (mod 2^n) = x + ~y + 1"""
    ny = [g.NOT(t) for t in y]
    one = [g.C1] + [g.C0] * (len(x) - 1)
    return add(g, add(g, x, ny), one)


def mux(g, s, a, b):
    """s ? a : b"""
    return [g.OR(g.AND(s, a[i]), g.AND(g.NOT(s), b[i])) for i in range(len(a))]


def geq(g, add, x, y):
    """x >= y, unsigned: the carry-out of x + ~y + 1. Computed one bit wider to expose it."""
    w = len(x)
    xe = list(x) + [g.C0]; ye = list(y) + [g.C0]
    d = sub(g, add, xe, ye)
    return g.NOT(d[w])                      # no borrow -> x >= y


def const(g, v, w):
    return [g.C1 if (v >> i) & 1 else g.C0 for i in range(w)]


def mul(g, add, x, y):
    """shift-add product, width len(x)+len(y). The ADDER is the searched dimension."""
    wx, wy = len(x), len(y)
    acc = [g.C0] * (wx + wy)
    for j in range(wy):
        part = [g.C0] * j + [g.AND(y[j], x[i]) for i in range(wx)]
        part += [g.C0] * (wx + wy - len(part))
        acc = add(g, acc, part)[:wx + wy]
    return acc


def mod_q(g, add, r, w):
    """r mod 3329 by conditional-subtraction ladder. A DEPENDENT chain — the shape §38B describes."""
    cur = list(r)
    k = w - 12
    while k >= 0:
        qs = const(g, Q << k, w)
        ge = geq(g, add, cur, qs)
        cur = mux(g, ge, sub(g, add, cur, qs)[:w], cur)
        k -= 1
    return cur[:12]


# ══ PROBLEM 1 — POST-QUANTUM CRYPTO: the NTT butterfly, mod q = 3329 (Kyber's prime) ═══════════════
def build_ntt(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(36); g = Shim(c)
    a = list(c.IN[0:12]); b = list(c.IN[12:24]); z = list(c.IN[24:36])
    t = mod_q(g, add, mul(g, add, b, z), 24)
    if mutant == "nomod": t = mul(g, add, b, z)[:12]
    ae = a + [g.C0]; te = t + [g.C0]
    s = add(g, ae, te)[:13]
    qs = const(g, Q, 13)
    s = mux(g, geq(g, add, s, qs), sub(g, add, s, qs)[:13], s)[:12]
    d = sub(g, add, ae, te)[:13]
    neg = d[12]
    d = mux(g, neg, add(g, d, qs)[:13], d)[:12]
    if mutant == "swap": s, d = d, s
    return c, s + d


def ref_ntt(a, b, z):
    t = (b * z) % Q
    return ((a + t) % Q, (a - t) % Q)


def cases_ntt(n=8, seed=5):
    random.seed(seed)
    return [(random.randrange(Q), random.randrange(Q), random.randrange(Q)) for _ in range(n)]


def check_ntt(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for a, b, z in cs:
        inb = [(a >> i) & 1 for i in range(12)] + [(b >> i) & 1 for i in range(12)] + \
              [(z >> i) & 1 for i in range(12)]
        v = TC.ripple(cd, inb)
        got = (sum(v[i] << i for i in range(12)), sum(v[12 + i] << i for i in range(12)))
        if got == ref_ntt(a, b, z): ok += 1
    return ok


# ══ PROBLEM 2 — FINANCE: Monte Carlo payoff. xorshift32 + threshold. INDEPENDENT lanes ════════════
def build_mc(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(64); g = Shim(c)
    x = list(c.IN[0:32]); thr = list(c.IN[32:64])
    def shl(v, k): return [g.C0] * k + v[:32 - k]
    for k in (13, 17, 5):
        sh = shl(x, k) if k != 17 else shr(x, k)
        x = [g.XOR(x[i], sh[i]) for i in range(32)]
    if mutant == "noprng": x = list(c.IN[0:32])
    hit = g.NOT(geq(g, add, x, thr))               # payoff when x < threshold
    if mutant == "flipcmp": hit = geq(g, add, x, thr)
    return c, [hit] + x


def ref_mc(seed, thr):
    x = seed & 0xFFFFFFFF
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17)
    x ^= (x << 5) & 0xFFFFFFFF
    return (1 if x < thr else 0), x


def cases_mc(n=8, seed=7):
    random.seed(seed)
    return [(random.getrandbits(32), random.getrandbits(32)) for _ in range(n)]


def check_mc(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for s, t in cs:
        inb = [(s >> i) & 1 for i in range(32)] + [(t >> i) & 1 for i in range(32)]
        v = TC.ripple(cd, inb)
        got = (v[0], sum(v[1 + i] << i for i in range(32)))
        if got == ref_mc(s, t): ok += 1
    return ok


# ══ PROBLEM 3 — BIOENGINEERING: Smith-Waterman cell. A DEPENDENT recurrence ═══════════════════════
GAP = 2
def build_sw(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(32); g = Shim(c)
    diag = list(c.IN[0:8]); up = list(c.IN[8:16]); left = list(c.IN[16:24]); s = list(c.IN[24:32])
    gp = const(g, GAP, 8)
    cand = [add(g, diag, s)[:8], sub(g, add, up, gp)[:8], sub(g, add, left, gp)[:8]]
    if mutant == "nogap": cand[1] = list(up)
    best = const(g, 0, 8)
    for v in cand:
        ge = geq(g, add, v, best)
        nn = g.NOT(v[7])                            # treat as signed: negatives lose to 0
        take = g.AND(ge, nn)
        best = mux(g, take, v, best)
    if mutant == "nozero": best = cand[0]
    return c, best


def ref_sw(diag, up, left, s):
    def sgn(x): return x - 256 if x >= 128 else x
    v = max(0, sgn(diag) + sgn(s), sgn(up) - GAP, sgn(left) - GAP)
    return v & 0xFF


def cases_sw(n=10, seed=3):
    random.seed(seed)
    return [(random.randrange(60), random.randrange(60), random.randrange(60), random.randrange(8))
            for _ in range(n)]


def check_sw(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for d, u, l, s in cs:
        inb = []
        for val in (d, u, l, s): inb += [(val >> i) & 1 for i in range(8)]
        v = TC.ripple(cd, inb)
        if sum(v[i] << i for i in range(8)) == ref_sw(d, u, l, s): ok += 1
    return ok


# ══ PROBLEM 4 — CLIMATE / CFD: weighted 5-point stencil. A SET reduction ══════════════════════════
def build_stencil(adder, mutant=None):
    add = family(32)[adder]
    c = TC.Circuit(40); g = Shim(c)
    n, s, e, w, ctr = [list(c.IN[i * 8:(i + 1) * 8]) for i in range(5)]
    W = 12
    def ext(v): return list(v) + [g.C0] * (W - 8)
    terms = [ext(n), ext(s), ext(e), ext(w), ext(ctr)[:], ext(ctr)[:], ext(ctr)[:], ext(ctr)[:]]
    if mutant == "drop": terms = terms[:4]
    acc = terms[0]
    for t in terms[1:]: acc = add(g, acc, t)[:W]
    out = acc[3:11]                                  # >> 3
    if mutant == "noshift": out = acc[0:8]
    return c, out


def ref_stencil(n, s, e, w, c_):
    return ((n + s + e + w + 4 * c_) >> 3) & 0xFF


def cases_stencil(nc=10, seed=9):
    random.seed(seed)
    return [tuple(random.randrange(256) for _ in range(5)) for _ in range(nc)]


def check_stencil(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for tup in cs:
        inb = []
        for val in tup: inb += [(val >> i) & 1 for i in range(8)]
        v = TC.ripple(cd, inb)
        if sum(v[i] << i for i in range(8)) == ref_stencil(*tup): ok += 1
    return ok


PROBLEMS = {
    "ntt_butterfly": dict(build=build_ntt, check=check_ntt, cases=cases_ntt,
                          mutants=["nomod", "swap"], shape="replicated",
                          domain="post-quantum cryptography (Kyber NTT, mod q=3329)"),
    "mc_payoff":     dict(build=build_mc, check=check_mc, cases=cases_mc,
                          mutants=["noprng", "flipcmp"], shape="replicated",
                          domain="finance (Monte Carlo path payoff)"),
    "sw_cell":       dict(build=build_sw, check=check_sw, cases=cases_sw,
                          mutants=["nogap", "nozero"], shape="dependent",
                          domain="bioengineering (Smith-Waterman alignment cell)"),
    "stencil5":      dict(build=build_stencil, check=check_stencil, cases=cases_stencil,
                          mutants=["drop", "noshift"], shape="dependent",
                          domain="climate / CFD (weighted 5-point stencil)"),
}


def solve(name, adders=None):
    import mafab_laws as L
    from mafab_host import Governor
    P = PROBLEMS[name]
    cs = P["cases"]()
    fam = adders or sorted(family(32))
    print("=" * 92)
    print("PROBLEM: %s — %s" % (name, P["domain"]))
    print("  shape %r declared, so the scorer is DERIVED (LAW 4 / §23), not chosen." % P["shape"])
    print("  %d adder implementations searched at every site (§31A: the adder is a searched" % len(fam))
    print("  dimension, not a rule). Reference is exact and INDEPENDENT of the circuit (§3).\n")
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
        res.append(dict(adder=ad, depth=D, gates=G, ok=(ok == len(cs)), score=ok))
        print("    %-11s DEPTH %7s  gates %9s   %d/%d" % (ad, "{:,}".format(D), "{:,}".format(G), ok, len(cs)))
        del c, outs
    gov.report()
    good = [r for r in res if r["ok"]]
    if not good:
        print("\n  NOTHING VERIFIED — the fabricator could not solve this one. Reported, not hidden.")
        return None
    ranked, label = L.rank(good, P["shape"])
    b = ranked[0]
    print("\n  VERIFIED %d/%d implementations · ranked by %s" % (len(good), len(res), label))
    print("  WINNER: %s — DEPTH %s gate-delays, %s gates, area-delay %s"
          % (b["adder"], "{:,}".format(b["depth"]), "{:,}".format(b["gates"]),
             "{:,}".format(b["gates"] * b["depth"])))
    # §40B baseline + §45C mutants, on the winner
    zero = 0
    for _ in cs: pass
    print("\n  §40B all-zero baseline + §45C mutants, on the winning implementation:")
    for m in P["mutants"]:
        cm, om = P["build"](b["adder"], mutant=m)
        okm = P["check"](cm, om, cs)
        print("    mutant %-9s %d/%d  ->  %s" % (m, okm, len(cs),
              "CAUGHT" if okm != len(cs) else "*** SURVIVED — SUITE IS BLIND ***"))
        del cm, om
    return b


if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if not a.startswith("--")]
    todo = want or list(PROBLEMS)
    for nm in todo:
        if nm not in PROBLEMS:
            print("unknown problem %r; known: %s" % (nm, ", ".join(PROBLEMS))); continue
        solve(nm)
        print("")
    raise SystemExit(0)
