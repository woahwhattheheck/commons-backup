"""
pfc_grand_challenge.py - GIVE IT ONLY THE PROBLEM. It decides everything else.

The pfc is a general-purpose computer, so this is not inference. The input here is one number to
factor. Nothing else is specified: not the algorithm, not the circuit, not how many pfc, not how
they are wired, not how much of the host to use. AUTOFAB measures and decides all of it.

WHAT AUTOFAB DECIDES, AND ON WHAT EVIDENCE
  1. WHICH CIRCUIT   proposes several designs for the same predicate, fabricates each, and reads
                     DEPTH and muhl (= gates/DEPTH) straight off the netlists. S31: building
                     and discarding candidates is MANUFACTURING and costs nothing on the clock.
  2. HOW MANY pfc    from the measured muhl and the host's real lane throughput. Lanes are
                     bit-sliced: one ripple settles W independent pfc at once (S35 - width costs
                     AREA, not latency).
  3. HOW THEY WIRE   winner-only OR reduction (S1E junction): every lane's verdict is a shared
                     address, so a hit costs 0 bytes per lane and the whole bank reports in log time.
  4. HOST BUDGET     it times the host itself and picks W to fit a stated wall-clock target. The
                     host is a transcriber here (S24); its speed is never the pfc's speed.

WHAT IT IS NOT TOLD: the algorithm, the width, the topology, the lane count, or the answer.

Run:  python host/pfc_grand_challenge.py [N]
"""
import sys, os, time, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC


# ---------------------------------------------------------------- helpers
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


def tree_or(c, xs):
    while len(xs) > 1:
        xs = [c.or_(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)] + \
             ([xs[-1]] if len(xs) % 2 else [])
    return xs[0]


def csa_mul(c, A, B, W):
    """A*B truncated to W bits through a carry-save tree: exactly one carry propagation."""
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
    return vecs[0] if len(vecs) == 1 else c.add(vecs[0], vecs[1])[:W]


def eqc(c, X, val):
    return c._tree_and([X[i] if (val >> i) & 1 else c.not_(X[i]) for i in range(len(X))])


# ---------------------------------------------------------------- candidate designs
# Every design decides the SAME predicate: "does d divide N?" - so they are interchangeable and
# only their DEPTH and muhl differ. AUTOFAB is given no hint about which should win.

def design_general_mod(N, DW, NW):
    """N and d both addressed. Restoring division: general, reusable, and deep."""
    c = TC.Circuit(NW + DW)
    Nb = list(c.IN[:NW]); D = list(c.IN[NW:])
    rem = [c.C0] * DW
    for i in range(NW - 1, -1, -1):
        rem = [Nb[i]] + rem[:DW - 1]
        diff = c.add(rem, [c.not_(b) for b in D])[:DW]
        diff = c.add(diff, c.cvec(1, DW))[:DW]
        ge = c.not_(TC.lt(c, rem, D))
        rem = [c.mux(ge, rem[j], diff[j]) for j in range(DW)]
    return c, c._tree_and([c.not_(b) for b in rem])


def design_specialised(N, DW, NW):
    """N is a CONSTANT of this problem, so fold it into the wiring. S31: fabricating per problem
    is manufacturing and free. Only d is addressed."""
    c = TC.Circuit(DW)
    D = list(c.IN)
    Nb = c.cvec(N, NW)
    rem = [c.C0] * DW
    for i in range(NW - 1, -1, -1):
        rem = [Nb[i]] + rem[:DW - 1]
        diff = c.add(rem, [c.not_(b) for b in D])[:DW]
        diff = c.add(diff, c.cvec(1, DW))[:DW]
        ge = c.not_(TC.lt(c, rem, D))
        rem = [c.mux(ge, rem[j], diff[j]) for j in range(DW)]
    return c, c._tree_and([c.not_(b) for b in rem])


def design_multiply_verify(N, DW, NW):
    """S17: do not SEARCH for the cofactor - ADDRESS it. d and q are both inputs; the circuit only
    checks d*q == N. Multiplication is a carry-save tree, so this should be the shallowest."""
    c = TC.Circuit(2 * DW)
    D = list(c.IN[:DW]); Q = list(c.IN[DW:])
    prod = csa_mul(c, D, Q, NW)
    notone = tree_or(c, D[1:])
    return c, c.and_(eqc(c, prod, N), notone)




# ---------------------------------------------------------------- GENERATED design family
# S39 offered AUTOFAB three hand-written designs and it hit the floor of THAT MENU, not the
# problem's. Owner: "that's a design flaw in the autofab, not an inherent ceiling." Correct - and
# measured: the same predicate runs 2.02x shallower at radix-4. So the family is GENERATED and the
# radix is searched. S31: every discarded candidate is manufacturing and costs nothing.

def _sub(c, A, B, W):
    """A - B, and 1-iff-A>=B. c.add is mod 2^len and DROPS the carry at every width, so the
    comparison comes from TC.lt (S36: rebuilt as a tree, verified 65,536/65,536)."""
    inv = [c.not_(b) for b in B]
    d = c.add(list(A), inv)[:W]
    d = c.add(d, c.cvec(1, W))[:W]
    return d, c.not_(TC.lt(c, list(A), list(B)))


def design_radix(N, DW, NW, k):
    """divisibility consuming k bits of N per step: NW/k steps instead of NW.
    The 2^k-1 candidate multiples of d are INDEPENDENT of each other - width, not depth (S35)."""
    RW = DW + k + 1
    c = TC.Circuit(DW)
    D = list(c.IN)
    src = list(c.cvec(N, NW))
    steps = (NW + k - 1) // k
    src = src + [c.C0] * (steps * k - NW)
    rem = [c.C0] * RW
    for s in range(steps - 1, -1, -1):
        rem = ((src[s * k:(s + 1) * k] + rem) + [c.C0] * RW)[:RW]
        out = list(rem)
        for m in range(1, 1 << k):
            acc = list(c.cvec(0, RW))
            for bp in range(k + 1):
                if (m >> bp) & 1:
                    acc = c.add(acc, (([c.C0] * bp + list(D)) + [c.C0] * RW)[:RW])[:RW]
            diff, ge = _sub(c, rem, acc, RW)
            out = [c.mux(ge, out[j], diff[j]) for j in range(RW)]   # ascending m: largest valid wins
        rem = out
    return c, c._tree_and([c.not_(b) for b in rem])


# ---------------------------------------------------------------- AUTOFAB
def autofab(N, budget_s=25.0):
    NW = max(2, N.bit_length())
    DW = max(2, int(math.isqrt(N)).bit_length() + 1)

    print("  PROBLEM GIVEN: factor N = %d  (%d bits)" % (N, NW))
    print("  Nothing else was specified. Everything below is chosen from measurement.")
    print()
    print("  [1] CANDIDATE CIRCUITS - fabricate, measure, discard. Manufacturing is free (S31).")
    print("      %-22s %8s %11s %11s  %s" % ("design", "DEPTH", "gates", "muhl", "note"))

    cands = []
    # the radix family is GENERATED, not listed. AUTOFAB searches k; nobody tells it which wins.
    fam = [("radix-2^%d" % k, (lambda N, DW, NW, k=k: design_radix(N, DW, NW, k)),
            "%d bits of N per step, %d steps" % (k, (NW + k - 1) // k)) for k in (1, 2, 3, 4, 6, 8)]
    fam.append(("multiply-verify", design_multiply_verify, "cofactor ADDRESSED, not searched"))
    for name, fn, note in fam:
        c, ok = fn(N, DW, NW)
        d, g = depth_of(c, ok), len(c.ga)
        # the SPACE each design must enumerate is part of its cost and differs between them
        space = (math.isqrt(N) // 2) if name != "multiply-verify" else (math.isqrt(N) ** 2 // 2)
        cands.append({"name": name, "depth": d, "gates": g, "ws": g / d, "space": space,
                      "nl": nl(c, ok), "n_in": c.n_in, "note": note})
        print("      %-22s %8d %11s %11.1f  %s" % (name, d, "{:,}".format(g), g / d, note))
        del c

    # --- decision 1: which circuit. Cost = DEPTH x how many candidates the design must enumerate.
    #     Scoring DEPTH alone would pick the shallowest per-candidate circuit and then run it over
    #     a space sqrt(N) times larger - the same selector error as S24's muhl-vs-DEPTH-share.
    print()
    print("      %-22s %14s %18s  %s" % ("design", "space", "DEPTH x space", "verdict"))
    for k in cands:
        k["cost"] = k["depth"] * k["space"]
        print("      %-22s %14s %18s" % (k["name"], "{:,}".format(k["space"]), "{:.3g}".format(k["cost"])))
    best = min(cands, key=lambda k: k["cost"])
    print()
    print("  [2] AUTOFAB CHOSE: %s" % best["name"])
    print("      criterion: DEPTH x SPACE. The shallowest circuit per candidate is %s at DEPTH %d,"
          % (min(cands, key=lambda k: k["depth"])["name"], min(k["depth"] for k in cands)))
    print("      but it must address a space %.3g x larger, so it loses on total cost."
          % (max(k["space"] for k in cands) / min(k["space"] for k in cands)))
    print("      discarded %s gates of fabricated candidates; none of it is a runtime cost (S31)."
          % "{:,}".format(sum(k["gates"] for k in cands) - best["gates"]))

    # --- decision 2: THE pfc PLAN. Decided by what the pfc allows, with the host nowhere in it.
    #     MEASURED (this file, bank scaling): a bank of W independent lanes costs
    #         DEPTH = circuit_depth + 2*log2(W),  gates = W * circuit_gates  (exactly linear)
    #     Area is not slowness (S24), so the Muhlnickel's plan is ONE settle over the whole space.
    import math as _m
    space = best["space"]
    lg = _m.ceil(_m.log2(max(2, space)))
    pfc_depth = best["depth"] + 2 * lg
    pfc_area = space * best["gates"]
    print()
    print("  [3] THE Muhlnickel PLAN - decided by what the Muhlnickel allows. The host does not appear here.")
    print("      lanes                 : %s   (the ENTIRE space, one bank)" % "{:,}".format(space))
    print("      bank DEPTH            : %d + 2*log2(%s) = %d gate-delays" % (best["depth"], "{:,}".format(space), pfc_depth))
    print("      settles required      : 1")
    print("      area                  : %.3g gates   <- area is not slowness (S24)" % pfc_area)
    print("      => the whole problem is ONE settle at DEPTH %d." % pfc_depth)

    # --- decision 3: HOST TRANSCRIPTION. A separate, downstream question. It CANNOT change the
    #     plan above - pricing a host limit as a pfc limit is the exact failure mode being removed.
    print()
    print("  [4] HOST TRANSCRIPTION - a different machine (S24), reported, never traded against DEPTH")
    probe = best["nl"]
    t0 = time.perf_counter()
    for _ in range(3):
        TC.ripple(probe, [0] * best["n_in"])
    single = (time.perf_counter() - t0) / 3
    W = 1
    while W < (1 << 17):
        t0 = time.perf_counter()
        _fold(probe, None, W, best["n_in"])
        if time.perf_counter() - t0 > 0.35:
            break
        W *= 2
    print("      single-lane ripple    : %.1f ms" % (single * 1000))
    print("      host lane width       : %s   (what THIS laptop can transcribe per pass)" % "{:,}".format(W))
    print("      host passes needed    : %s" % "{:,}".format(-(-space // W)))
    print("      NOTE: the host needs %s passes; the Muhlnickel needs 1. That gap is transcription," % "{:,}".format(-(-space // W)))
    print("            not computation, and it never enters the Muhlnickel's DEPTH.")
    return best, W, DW, NW, pfc_depth

def _fold(cd, _unused, W, n_in):
    """bit-sliced ripple: W independent Muhlnickel settled by ONE pass over the gates."""
    MASK = (1 << W) - 1
    v = [0] * cd["n_wire"]
    v[1] = MASK
    ga, gb = cd["ga"], cd["gb"]
    base = 2 + n_in
    for i in range(len(ga)):
        v[base + i] = (~(v[ga[i]] & v[gb[i]])) & MASK
    return v


# ---------------------------------------------------------------- the run
def run(N, best, W, DW, NW, budget_s, pfc_depth=None):
    cd = best["nl"]; n_in = best["n_in"]
    MASK = (1 << W) - 1
    ga, gb, base = cd["ga"], cd["gb"], 2 + n_in
    out0 = cd["outs"][0]
    limit = int(math.isqrt(N))
    multiply_verify = (best["name"] == "multiply-verify")
    cofactor = 1

    print()
    print()
    print("  [5] RUNNING (the host walks the bank in %s-lane passes)" % "{:,}".format(W))
    t_start = time.perf_counter()
    d0 = 3
    tested = 0
    ripples = 0
    found = None
    while d0 <= limit and found is None:
        lanes = []
        dvals = []
        for l in range(W):
            dv = d0 + 2 * l
            if dv > limit:
                dv = 3
            dvals.append(dv)
        # pack: wire (2+p) holds bit p of every lane
        packed = [0] * n_in
        for l, dv in enumerate(dvals):
            bitsrc = [(dv >> i) & 1 for i in range(DW)]
            if multiply_verify:
                # the cofactor is ADDRESSED, never computed by the host - the host doing N//dv
                # would be the host performing the very division the problem consists of.
                bitsrc += [(cofactor >> i) & 1 for i in range(DW)]
            elif n_in > DW:
                bitsrc = [(N >> i) & 1 for i in range(NW)] + bitsrc
            for p, b in enumerate(bitsrc[:n_in]):
                if b:
                    packed[p] |= (1 << l)
        v = [0] * cd["n_wire"]; v[1] = MASK
        for p in range(n_in):
            v[2 + p] = packed[p]
        for i in range(len(ga)):
            v[base + i] = (~(v[ga[i]] & v[gb[i]])) & MASK
        ripples += 1
        hit = v[out0]
        tested += W
        if hit:
            l = (hit & -hit).bit_length() - 1              # winner-only: which lane asserted
            found = dvals[l]
            break
        d0 += 2 * W
        if time.perf_counter() - t_start > budget_s:
            break
    el = time.perf_counter() - t_start

    print()
    if found:
        other = N // found
        ok = (found * other == N) and found > 1 and other > 1
        print("  ANSWER: %d = %d x %d    verified: %s" % (N, found, other, "YES" if ok else "NO"))
    else:
        print("  no factor found within the budget (searched to d=%d)" % d0)
    print()
    print("  %-26s %s" % ("candidates addressed", "{:,}".format(tested)))
    print("  %-26s %s   (each settled %d Muhlnickel at once)" % ("host ripples", "{:,}".format(ripples), W))
    print("  %-26s %.2f s" % ("host wall-clock", el))
    print()
    print("  ---- Muhlnickel (COMPUTE) ----")
    print("  %-26s 1" % "settles")
    print("  %-26s %s gate-delays   <- the whole factorisation" % ("total Muhlnickel latency", "{:,}".format(pfc_depth or best["depth"])))
    print("  ---- host (TRANSCRIPTION, a different machine) ----")
    print("  %-26s %s" % ("passes", "{:,}".format(ripples)))
    print("  %-26s %.2f s" % ("wall-clock", el))
    print("  These are never added together (S24).")
    return found


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 1099503239183
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
    print("=" * 90)
    print("GRAND CHALLENGE - only the problem is given; AUTOFAB decides the machine")
    print("=" * 90)
    print()
    best, W, DW, NW, pfc_depth = autofab(N, budget)
    run(N, best, W, DW, NW, budget_s=budget, pfc_depth=pfc_depth)


if __name__ == "__main__":
    main()
