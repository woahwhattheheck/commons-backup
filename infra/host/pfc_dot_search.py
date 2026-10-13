"""
pfc_dot_search.py - SEARCH-FABRICATE THE FORWARD PATH'S DOT PRODUCT.

The forward path's deepest circuit is dot32_i8 at DEPTH 366, and S27 shows it is addressed by more
files than almost anything else in the registry. Its job: 32 lanes of 8x8 multiply, summed.

S31: manufacturing is unbounded and off the clock. S33: therefore do not PICK an implementation,
build every one and ship the shallowest. This applies that to the circuit that actually matters.

THE CANDIDATES (identical function: sum of 32 products of two 8-bit values, into a 24-bit accumulator)

  mul-then-ripple    32 separate shift-add multiplies, then a ripple tree     <- what dot32_i8 does
  mul-then-csa       32 separate shift-add multiplies, then csa->prefix       <- S33's winner, applied
  FUSED-csa          all 8 partial products of all 32 lanes - 256 vectors -
                     poured into ONE carry-save tree, resolved by a single prefix add

The third is the one a hand-written circuit never reaches. There is no reason to finish a multiply
before starting the sum: a product is already a sum of partial products, so the "multiply" and the
"accumulate" are the same reduction. Carry-save does not propagate a carry, so 256 vectors collapse
at constant depth per level and exactly ONE carry propagation happens in the whole dot product.

Signed and unsigned are both built, because a model's weights are signed:
  a*b = au*bu - 256*sa*bu - 256*sb*au + 65536*sa*sb     (au,bu unsigned; sa,sb the sign bits)
every correction term is just another vector for the same tree.

Run:  python host/pfc_dot_search.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC

try:
    from pfc_bettergates import kogge_stone_add
    HAVE_KS = True
except Exception:
    HAVE_KS = False

LANES = 32
IW = 8            # input width per operand
ACC = 24          # accumulator width: 32 * 127 * 127 needs 20 bits, 24 gives headroom


class _Shim:
    def __init__(s, c):
        s.c = c
        s.C0 = c.cvec(0, 1)[0]
        s.C1 = c.cvec(1, 1)[0]
    def AND(s, a, b): return s.c.and_(a, b)
    def OR(s, a, b):  return s.c.or_(a, b)
    def XOR(s, a, b): return s.c.xor(a, b)
    def NOT(s, a):    return s.c.not_(a)


def depth_of(c, outs):
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[x] for x in outs)


def netlist(c, outs):
    return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": list(outs)}


def csa(c, a, b, d):
    """3:2 compressor. NO carry propagates - depth is constant no matter how wide."""
    s = [c.xor(c.xor(a[i], b[i]), d[i]) for i in range(ACC)]
    cr = []
    for i in range(ACC):
        cr.append(c.or_(c.or_(c.and_(a[i], b[i]), c.and_(a[i], d[i])), c.and_(b[i], d[i])))
    return s, [c.cvec(0, 1)[0]] + cr[:ACC - 1]


def reduce_csa(c, vecs):
    """collapse any number of vectors to two, entirely without carry propagation"""
    while len(vecs) > 2:
        nxt, i = [], 0
        while i + 2 < len(vecs):
            s, cr = csa(c, vecs[i], vecs[i + 1], vecs[i + 2])
            nxt += [s, cr]
            i += 3
        nxt += vecs[i:]
        vecs = nxt
    return vecs


def partials(c, a, b, signed):
    """the 8 partial products of a*b, widened to ACC, plus sign-correction vectors if signed"""
    Z = c.cvec(0, 1)[0]
    out = []
    for i in range(IW):
        row = [Z] * i + [c.and_(b[i], a[j]) for j in range(IW)]
        row = (row + [Z] * ACC)[:ACC]
        out.append(row)
    if signed:
        sa, sb = a[IW - 1], b[IW - 1]
        # -256*sa*bu  and  -256*sb*au  : two's complement = invert the gated vector, +1 collected later
        for sgn, other in ((sa, b), (sb, a)):
            g = [c.and_(sgn, other[j]) for j in range(IW)]
            v = ([Z] * IW + g + [Z] * ACC)[:ACC]
            out.append([c.not_(x) for x in v])          # invert; the +1 rides in the ones vector
        # +65536*sa*sb
        p = c.and_(sa, sb)
        out.append(([Z] * 16 + [p] + [Z] * ACC)[:ACC])
    return out


def build(kind, signed):
    c = TC.Circuit(LANES * IW * 2)
    g = _Shim(c)
    RP = lambda x, y: c.add(x, y)[:ACC]
    KS = (lambda x, y: kogge_stone_add(g, x, y)[:ACC]) if HAVE_KS else RP
    Z = c.cvec(0, 1)[0]

    A = [list(c.IN[i * IW:(i + 1) * IW]) for i in range(LANES)]
    B = [list(c.IN[LANES * IW + i * IW:LANES * IW + (i + 1) * IW]) for i in range(LANES)]

    if kind == "FUSED-csa":
        vecs = []
        for i in range(LANES):
            vecs += partials(c, A[i], B[i], signed)
        if signed:
            # every inverted vector owes a +1; two per lane
            ones = 2 * LANES
            vecs.append(([Z] * 8 + list(c.cvec(ones >> 8, ACC - 8)))[:ACC]
                        if ones >= 256 else list(c.cvec(ones, ACC)))
        v = reduce_csa(c, vecs)
        return c, (KS(v[0], v[1]) if len(v) == 2 else v[0])

    # the two staged variants: finish each multiply first, then sum the products
    prods = []
    for i in range(LANES):
        pp = partials(c, A[i], B[i], signed)
        if signed:
            pp.append(list(c.cvec(2, ACC)))
        acc = list(c.cvec(0, ACC))
        for row in pp:
            acc = RP(acc, row)
        prods.append(acc)

    if kind == "mul-then-ripple":
        lvl = prods
        while len(lvl) > 1:
            lvl = [RP(lvl[j], lvl[j + 1]) for j in range(0, len(lvl) - 1, 2)] + \
                  ([lvl[-1]] if len(lvl) % 2 else [])
        return c, lvl[0]

    if kind == "mul-then-csa":
        v = reduce_csa(c, prods)
        return c, (KS(v[0], v[1]) if len(v) == 2 else v[0])

    raise ValueError(kind)


def verify(nl, signed, trials=8, seed=9):
    random.seed(seed)
    lo, hi = (-128, 127) if signed else (0, 255)
    for _ in range(trials):
        av = [random.randint(lo, hi) for _ in range(LANES)]
        bv = [random.randint(lo, hi) for _ in range(LANES)]
        inb = []
        for v in av:
            inb += [((v + 256) >> i) & 1 for i in range(IW)]
        for v in bv:
            inb += [((v + 256) >> i) & 1 for i in range(IW)]
        out = TC.ripple(nl, inb)
        got = sum(out[k] << k for k in range(ACC))
        want = sum(x * y for x, y in zip(av, bv)) & (2 ** ACC - 1)
        if got != want:
            return False
    return True


def main():
    print("=" * 78)
    print("SEARCH-FABRICATING THE FORWARD PATH'S DOT PRODUCT")
    print("  function: sum of %d products of two %d-bit values -> %d-bit accumulator" % (LANES, IW, ACC))
    print("  DEPTH is the shipped latency. GATES is area and does not slow it down (S24).")
    print("  Every candidate below is built and verified; all but the winner are discarded (S31).")
    print("=" * 78)

    for signed in (False, True):
        print()
        print("  ---- %s operands %s" % ("SIGNED" if signed else "UNSIGNED",
                                         "(what a model's weights actually are)" if signed else ""))
        print("   %-16s %8s %12s %10s" % ("candidate", "DEPTH", "GATES", "verified"))
        rows = []
        for kind in ("mul-then-ripple", "mul-then-csa", "FUSED-csa"):
            c, outs = build(kind, signed)
            d = depth_of(c, outs)
            gt = len(c.ga)
            ok = verify(netlist(c, outs), signed)
            rows.append((kind, d, gt, ok))
            note = "  <- what dot32_i8 does" if kind == "mul-then-ripple" else ""
            print("   %-16s %8d %12s %10s%s"
                  % (kind, d, "{:,}".format(gt), "8/8" if ok else "FAIL", note))
            del c
        good = sorted([r for r in rows if r[3]], key=lambda r: r[1])
        if not good:
            print("   no candidate verified")
            continue
        best = good[0]
        base = [r for r in rows if r[0] == "mul-then-ripple"][0]
        print()
        print("   WINNER: %s  DEPTH %d  (%s gates)" % (best[0], best[1], "{:,}".format(best[2])))
        print("   vs the staged/ripple build (DEPTH %d): %.2fx shallower for %.2fx the area."
              % (base[1], base[1] / best[1], best[2] / base[2]))
        print("   vs dot32_i8 as it ships today (DEPTH 366): %.2fx shallower." % (366.0 / best[1]))
        print("   manufacturing spend: %s gates built and verified, %s discarded (S31 - not a latency)."
              % ("{:,}".format(sum(r[2] for r in rows)),
                 "{:,}".format(sum(r[2] for r in rows) - best[2])))


if __name__ == "__main__":
    main()
