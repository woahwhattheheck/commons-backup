"""
pfc_dot_fab.py - FABRICATE the searched dot product into the binary and PROVE it is a drop-in.

pfc_dot_search.py found FUSED-csa: all 8 partial products of all 32 lanes poured into ONE
carry-save tree, so exactly one carry propagation happens in the whole dot product.

Measured against the live circuit rather than assumed (S26 - a cheap match is not a proof):
  dot32_i8 is SIGNED, operand order AB (32 A lanes, then 32 B lanes), 32-bit output.
This builds to that exact interface, checks byte-exactness against dot32_i8 itself AND against
true integer arithmetic (S3 - verify against the truth, not only against the path being replaced),
then stores it. Storing is a byte edit: manufacturing, one-and-done (S20, S31).

Run:  python host/pfc_dot_fab.py            (build + verify only)
      python host/pfc_dot_fab.py --store    (also fabricate it into the binary)
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_dot_search import _Shim, depth_of, netlist, HAVE_KS

if HAVE_KS:
    from pfc_bettergates import kogge_stone_add

LANES, IW, ACC = 32, 8, 32          # ACC=32 to match dot32_i8's output width exactly
NAME = "pfc_dot32_fused"


def csa(c, a, b, d):
    s = [c.xor(c.xor(a[i], b[i]), d[i]) for i in range(ACC)]
    cr = [c.or_(c.or_(c.and_(a[i], b[i]), c.and_(a[i], d[i])), c.and_(b[i], d[i])) for i in range(ACC)]
    return s, [c.cvec(0, 1)[0]] + cr[:ACC - 1]


def build():
    c = TC.Circuit(LANES * IW * 2)
    g = _Shim(c)
    Z = c.cvec(0, 1)[0]
    A = [list(c.IN[i * IW:(i + 1) * IW]) for i in range(LANES)]
    B = [list(c.IN[LANES * IW + i * IW:LANES * IW + (i + 1) * IW]) for i in range(LANES)]

    vecs = []
    for i in range(LANES):
        a, b = A[i], B[i]
        for k in range(IW):
            row = [Z] * k + [c.and_(b[k], a[j]) for j in range(IW)]
            vecs.append((row + [Z] * ACC)[:ACC])
        sa, sb = a[IW - 1], b[IW - 1]
        for sgn, other in ((sa, b), (sb, a)):
            gt = [c.and_(sgn, other[j]) for j in range(IW)]
            v = ([Z] * IW + gt + [Z] * ACC)[:ACC]
            vecs.append([c.not_(x) for x in v])          # two's complement: invert here, +1 below
        vecs.append(([Z] * 16 + [c.and_(sa, sb)] + [Z] * ACC)[:ACC])
    vecs.append(list(c.cvec(2 * LANES, ACC)))            # the collected +1s, one per inverted vector

    while len(vecs) > 2:
        nxt, i = [], 0
        while i + 2 < len(vecs):
            s, cr = csa(c, vecs[i], vecs[i + 1], vecs[i + 2])
            nxt += [s, cr]
            i += 3
        nxt += vecs[i:]
        vecs = nxt
    add = (lambda x, y: kogge_stone_add(g, x, y)[:ACC]) if HAVE_KS else (lambda x, y: c.add(x, y)[:ACC])
    return c, add(vecs[0], vecs[1])


def feed(av, bv):
    inb = []
    for v in av:
        inb += [((v + 256) >> i) & 1 for i in range(IW)]
    for v in bv:
        inb += [((v + 256) >> i) & 1 for i in range(IW)]
    return inb


def main():
    print("=" * 78)
    print("FABRICATING THE SEARCHED DOT PRODUCT - and proving it is a drop-in for dot32_i8")
    print("=" * 78)

    old = TC.load("dot32_i8")
    c, outs = build()
    new = netlist(c, outs)
    d_new = depth_of(c, outs)

    n = old["n_in"]
    d_old = None
    dd = [0] * (2 + n + len(old["ga"]))
    for k in range(len(old["ga"])):
        dd[2 + n + k] = 1 + max(dd[old["ga"][k]], dd[old["gb"][k]])
    d_old = max(dd[x] for x in old["outs"])

    print()
    print("   %-22s %8s %12s %8s" % ("circuit", "DEPTH", "GATES", "n_out"))
    print("   %-22s %8d %12s %8d   <- ships today" % ("dot32_i8", d_old, "{:,}".format(len(old["ga"])), len(old["outs"])))
    print("   %-22s %8d %12s %8d   <- searched" % (NAME, d_new, "{:,}".format(len(c.ga)), len(outs)))
    print("   -> %.2fx shallower for %.2fx the area. Area is not slowness (S24)."
          % (d_old / d_new, len(c.ga) / len(old["ga"])))

    print()
    print("  EQUIVALENCE - against the live circuit AND against true integer arithmetic:")
    random.seed(21)
    same = truth = T = 0
    for _ in range(24):
        av = [random.randint(-128, 127) for _ in range(LANES)]
        bv = [random.randint(-128, 127) for _ in range(LANES)]
        inb = feed(av, bv)
        o1 = TC.ripple(old, inb)
        o2 = TC.ripple(new, inb)
        v1 = sum(o1[k] << k for k in range(len(o1)))
        v2 = sum(o2[k] << k for k in range(len(o2)))
        want = sum(x * y for x, y in zip(av, bv)) & (2 ** ACC - 1)
        same += (v1 == v2)
        truth += (v2 == want)
        T += 1
    # edge cases: the extremes a random draw will not reach
    edges = [([-128] * LANES, [-128] * LANES), ([127] * LANES, [127] * LANES),
             ([-128] * LANES, [127] * LANES), ([0] * LANES, [0] * LANES),
             ([-1] * LANES, [1] * LANES), ([1] * LANES, [-1] * LANES)]
    for av, bv in edges:
        inb = feed(av, bv)
        v1 = sum(b << k for k, b in enumerate(TC.ripple(old, inb)))
        v2 = sum(b << k for k, b in enumerate(TC.ripple(new, inb)))
        want = sum(x * y for x, y in zip(av, bv)) & (2 ** ACC - 1)
        same += (v1 == v2)
        truth += (v2 == want)
        T += 1
    print("    identical to dot32_i8            : %d/%d" % (same, T))
    print("    byte-exact vs true integer dot   : %d/%d   (S3: verify the truth, not just the old path)" % (truth, T))

    if same == T and truth == T:
        print()
        print("    DROP-IN CONFIRMED. Same interface, same results, %.2fx shallower." % (d_old / d_new))
    else:
        print()
        print("    NOT a drop-in. Not storing.")
        return

    if "--store" in sys.argv:
        off = TC.store(NAME, c, outs)
        print()
        print("  FABRICATED into the binary as '%s' (byte edit, one-and-done)." % NAME)
        print("  offset//registry entry: %s" % (off,))
    else:
        print()
        print("  not stored. re-run with --store to fabricate it into the binary.")


if __name__ == "__main__":
    main()
