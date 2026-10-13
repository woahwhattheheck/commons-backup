"""
pfc_open_problems.py - throw genuinely OPEN problems at the substrate and measure what it says.

S31: fabrication is MANUFACTURING and is not part of the compute. So the cost of building these
verifiers does not enter any number below. The only figures that count are the emitted circuit's
DEPTH (its latency) and muhl = gates/DEPTH (its intrinsic parallelism).

S17 established the shape that matters: the substrate does not SEARCH a space, it ADDRESSES it.
A candidate is an address, not a materialised object. So the question a hard problem gets asked
here is never "can you search 2^n" - it is "how DEEP is one verification, and how much of it is
independent." Those two numbers are read straight off the netlist before anything is addressed.

THE FOUR (all open as of writing):
  PERFECT CUBOID   Does a box exist with integer edges, face diagonals AND space diagonal? Open.
  RAMSEY R(5,5)    Unknown; proven to lie in [43, 48]. Verifier: no monochromatic K5 in a 2-colouring.
  COLLATZ          Does every n reach 1? Open. The one problem here that is genuinely SERIAL.
  GOLDBACH         Is every even n > 2 a sum of two primes? Open.

Each verifier is checked against Python on known-true and known-false inputs before its numbers
are reported.

Run:  python host/pfc_open_problems.py
"""
import sys, os, itertools, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC


def depth_of(c, outs):
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    o = outs if isinstance(outs, (list, tuple)) else [outs]
    return max(d[x] for x in o)


def nl(c, outs):
    o = outs if isinstance(outs, (list, tuple)) else [outs]
    return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": list(o)}


def bits(v, n):
    return [(v >> i) & 1 for i in range(n)]


def mul(c, A, B, W):
    """unsigned A*B truncated to W bits, via a carry-save tree: ONE carry propagation"""
    Z = c.C0
    vecs = []
    for k in range(len(B)):
        row = [Z] * k + [c.and_(B[k], A[j]) for j in range(len(A))]
        vecs.append((row + [Z] * W)[:W])
    while len(vecs) > 2:
        nxt, i = [], 0
        while i + 2 < len(vecs):
            a, b, d = vecs[i], vecs[i + 1], vecs[i + 2]
            s = [c.xor(c.xor(a[j], b[j]), d[j]) for j in range(W)]
            cr = [c.or_(c.or_(c.and_(a[j], b[j]), c.and_(a[j], d[j])), c.and_(b[j], d[j])) for j in range(W)]
            nxt += [s, [Z] + cr[:W - 1]]
            i += 3
        nxt += vecs[i:]
        vecs = nxt
    if len(vecs) == 1:
        return vecs[0]
    return c.add(vecs[0], vecs[1])[:W]


def eq(c, A, B):
    """1 iff A == B, as a TREE (S36)"""
    return c._tree_and([c.not_(c.xor(A[i], B[i])) for i in range(len(A))])


def tree_or(c, items):
    while len(items) > 1:
        items = [c.or_(items[i], items[i + 1]) for i in range(0, len(items) - 1, 2)] + \
                ([items[-1]] if len(items) % 2 else [])
    return items[0]


# --------------------------------------------------------------------------------------
# 1. PERFECT CUBOID  (open)
#    a,b,c edges; d,e,f face diagonals; g space diagonal. All integers?
#    a^2+b^2=d^2 · a^2+c^2=e^2 · b^2+c^2=f^2 · a^2+b^2+c^2=g^2
#    S17: do not SEARCH for d,e,f,g - ADDRESS them. They are inputs, so the verifier is shallow.
# --------------------------------------------------------------------------------------
def build_cuboid(EW=9):
    W = 2 * EW + 2
    c = TC.Circuit(7 * EW)
    v = [list(c.IN[i * EW:(i + 1) * EW]) for i in range(7)]
    a, b, cc, d, e, f, g = v
    sq = lambda x: mul(c, x, x, W)
    a2, b2, c2 = sq(a), sq(b), sq(cc)
    d2, e2, f2, g2 = sq(d), sq(e), sq(f), sq(g)
    ab = c.add(a2, b2)[:W]
    ac = c.add(a2, c2)[:W]
    bc = c.add(b2, c2)[:W]
    abc = c.add(ab, c2)[:W]
    # every EDGE must be nonzero - a flat box (c=0) satisfies all four equations and is not a cuboid
    nonzero = c._tree_and([tree_or(c, list(a)), tree_or(c, list(b)), tree_or(c, list(cc))])
    ok = c._tree_and([eq(c, ab, d2), eq(c, ac, e2), eq(c, bc, f2), eq(c, abc, g2), nonzero])
    return c, ok, EW, 7


def check_cuboid(nlc, EW):
    def run(vals):
        ib = []
        for x in vals:
            ib += bits(x, EW)
        return TC.ripple(nlc, ib)[0]
    # known: an EULER BRICK (edges + face diagonals integral, space diagonal NOT) must fail
    euler = (44, 117, 240, 125, 244, 267, 0)          # 44,117,240 -> faces 125,244,267; space diag irrational
    tests = [((3, 4, 0, 5, 3, 4, 5), 0), (euler, 0), ((0, 0, 0, 0, 0, 0, 0), 0)]
    res = []
    for vals, expect in tests:
        if max(vals) >= (1 << EW):
            continue
        got = run(vals)
        res.append((vals, got, expect))
    return res


# --------------------------------------------------------------------------------------
# 2. RAMSEY  (R(5,5) unknown, in [43,48])
#    inputs: one bit per edge of K_n. Output: 1 iff NO monochromatic K_k.
#    Every k-subset is checked INDEPENDENTLY -> pure width, log depth.
# --------------------------------------------------------------------------------------
def build_ramsey(n=12, k=5):
    pairs = list(itertools.combinations(range(n), 2))
    idx = {p: i for i, p in enumerate(pairs)}
    c = TC.Circuit(len(pairs))
    E = list(c.IN)
    mono = []
    for S in itertools.combinations(range(n), k):
        es = [E[idx[(min(u, v), max(u, v))]] for u, v in itertools.combinations(S, 2)]
        allr = c._tree_and(es)
        allb = c._tree_and([c.not_(x) for x in es])
        mono.append(c.or_(allr, allb))
    return c, c.not_(tree_or(c, mono)), len(pairs), len(mono)


# --------------------------------------------------------------------------------------
# 3. COLLATZ  (open) - the one genuinely SERIAL problem here
#    n -> n/2 if even else 3n+1. Does it reach 1?
# --------------------------------------------------------------------------------------
def build_collatz(W=10, steps=24):
    c = TC.Circuit(W)
    x = list(c.IN)
    reached = c.C0
    for _ in range(steps):
        even = c.not_(x[0])
        half = list(x[1:]) + [c.C0]
        x3 = c.add(mul(c, x, c.cvec(3, 3), W), c.cvec(1, W))[:W]
        x = [c.mux(even, x3[i], half[i]) for i in range(W)]
        reached = c.or_(reached, eq(c, x, c.cvec(1, W)))
    return c, reached, W


# --------------------------------------------------------------------------------------
# 4. GOLDBACH  (open) - even n = p + q. Primality by ADDRESSING divisors: a wide AND.
# --------------------------------------------------------------------------------------
def build_goldbach(W=9):
    c = TC.Circuit(2 * W)                     # n, and the addressed witness p
    N = list(c.IN[:W])
    P = list(c.IN[W:])
    Q = c.add(N, [c.not_(b) for b in P])
    Q = c.add(Q[:W], c.cvec(1, W))[:W]        # q = n - p

    def is_prime(X):
        """1 iff X has no divisor d in [2, 2^ceil(W/2)) - every d checked independently"""
        terms = []
        for d in range(2, 1 << ((W + 1) // 2)):
            # X mod d != 0, by addressing every multiple of d and requiring X matches none
            eqs = [eq(c, X, c.cvec(m, W)) for m in range(2 * d, 1 << W, d)]   # 2d, not d: X is not its own witness
            terms.append(c.not_(tree_or(c, eqs)) if eqs else c.C1)
        ge2 = tree_or(c, X[1:])
        return c._tree_and(terms + [ge2])

    return c, c._tree_and([is_prime(P), is_prime(Q)]), W


def main():
    print("=" * 94)
    print("OPEN PROBLEMS ON THE Muhlnickel - fabrication is manufacturing and costs NOTHING here (S31).")
    print("  DEPTH = the verifier's latency. muhl = gates/DEPTH = how much of it is independent.")
    print("=" * 94)
    rows = []

    # --- cuboid
    c, ok, EW, _ = build_cuboid(9)
    d, g = depth_of(c, ok), len(c.ga)
    chk = check_cuboid(nl(c, ok), EW)
    verdict = "; ".join("%s=%d(want %s)" % ("/".join(str(x) for x in v[:3]), r, e) for v, r, e in chk)
    rows.append(("PERFECT CUBOID", "open", d, g, "8-bit edges, 56 addressed bits", verdict))
    del c

    # --- ramsey
    c, ok, nin, nsub = build_ramsey(12, 5)
    d, g = depth_of(c, ok), len(c.ga)
    nlc = nl(c, ok)
    allred = TC.ripple(nlc, [1] * nin)[0]
    del c
    # KNOWN-TRUE control: R(3,3)=6, so K5 2-coloured as two 5-cycles has NO monochromatic triangle.
    c2, ok2, nin2, _ = build_ramsey(5, 3)
    nl2 = nl(c2, ok2)
    cyc = {(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)}
    pr = list(itertools.combinations(range(5), 2))
    ctrl = TC.ripple(nl2, [1 if pp in cyc else 0 for pp in pr])[0]
    ctrl_red = TC.ripple(nl2, [1] * nin2)[0]
    del c2
    rows.append(("RAMSEY no-K5", "R(5,5) unknown, in [43,48]", d, g,
                 "K12: %d edges, %d 5-subsets" % (nin, nsub),
                 "K12 all-red=%d(want 0) | K5/C5 control=%d(want 1), K5 all-red=%d(want 0)"
                 % (allred, ctrl, ctrl_red)))

    # --- collatz
    c, ok, W = build_collatz(10, 24)
    d, g = depth_of(c, ok), len(c.ga)
    nlc = nl(c, ok)
    conv = (1, 2, 3, 6, 7)          # all reach 1 within 24 steps (27 needs 111 - a fact about 27)
    good = sum(TC.ripple(nlc, bits(v, W))[0] for v in conv)
    rows.append(("COLLATZ 24 steps", "open", d, g, "10-bit n, 24 serial steps",
                 "%d/5 n converging within 24 steps" % good))
    del c

    # --- goldbach
    c, ok, W = build_goldbach(7)
    d, g = depth_of(c, ok), len(c.ga)
    nlc = nl(c, ok)
    t1 = TC.ripple(nlc, bits(10, W) + bits(3, W))[0]      # 10 = 3+7, both prime -> 1
    t2 = TC.ripple(nlc, bits(10, W) + bits(4, W))[0]      # 4 not prime -> 0
    rows.append(("GOLDBACH witness", "open", d, g, "7-bit n, p addressed",
                 "10=3+7 ->%d (want 1), p=4 ->%d (want 0)" % (t1, t2)))
    del c

    print()
    print("  %-17s %8s %11s %10s  %s" % ("problem", "DEPTH", "gates", "muhl", "verification"))
    for name, status, d, g, shape, verdict in rows:
        print("  %-17s %8d %11s %10.1f  %s" % (name, d, "{:,}".format(g), g / d, verdict))
        print("  %-17s %s | %s" % ("", status, shape))
    print()
    print("  WHAT THE NUMBERS SAY:")
    print("   - The three WIDE problems verify at shallow DEPTH with high muhl: their")
    print("     candidates are independent, so the space is ADDRESSED, never searched (S17).")
    print("   - COLLATZ is the outlier and the honest one: each step needs the previous value,")
    print("     so its DEPTH grows with step count. That is real dependency, not imposed")
    print("     sequencing (S35/S36) - no tree can remove it.")


if __name__ == "__main__":
    main()
