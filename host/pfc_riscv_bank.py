"""
pfc_riscv_bank.py - A POPULATION OF CPUs, and EXHAUSTIVE ASSERTION over a whole input space.

Two measurements, both on the real RV32I core (S41), neither predicted in advance.

(1) DOES THE BANK LAW HOLD ON A WHOLE CPU?
    S40C measured a bank of independent lanes at `depth + 2*log2(W)`, gates exactly linear. But
    that +2 came from the WINNER-ONLY OR TREE reducing the bank to one verdict. A population of
    CPUs has no such reduction - every core keeps its own state and its own outputs. So the
    prediction is DEPTH EXACTLY FLAT, not +2 per doubling. Measured here rather than assumed.

    If flat: a machine costs AREA and no latency at all. 2^20 cores retire an instruction in the
    same 222 gate-delays as one. Isolation is the default (separate addresses); nothing loads, so
    cold start does not exist.

(2) EXHAUSTIVE ASSERTION - a program as a STORED RELATION.
    Instead of sampling a circuit's behaviour, fabricate the PROPERTY as gates and address its
    ENTIRE input space. The output is "does any input violate this?" - a single bit over a
    complete space, not a pass rate over a sample.

    This is the structural cure for the S40B failure (a circuit returning 0 for everything scored
    87.5% because the test set was almost all negatives). A complete space has no sampling bias:
    there is nothing left un-tested to hide in.

Run:  python host/pfc_riscv_bank.py
"""
import sys, os, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_riscv import build_core, depth_of, nl, XLEN, NREG


def splice(dst, src, in_map):
    """append src's gates into dst, remapping its inputs. Returns the remapped output wires."""
    base_d = 2 + dst.n_in
    off = len(dst.ga)
    base_s = 2 + src.n_in
    remap = {0: 0, 1: 1}
    for i in range(src.n_in):
        remap[2 + i] = in_map[i]
    for i in range(len(src.ga)):
        remap[base_s + i] = base_d + off + i
    for i in range(len(src.ga)):
        dst.ga.append(remap[src.ga[i]])
        dst.gb.append(remap[src.gb[i]])
    return remap


# ---------------------------------------------------------------- (1) the population
def measure_bank():
    print("  [1] A POPULATION OF CPUs - does the bank law hold on a whole RV32I core?")
    print("      S40C's +2/doubling came from a winner-only OR TREE. Independent cores have no")
    print("      reduction at all, so the prediction is EXACTLY FLAT. Measured:")
    print()
    print("      %6s %10s %14s %14s   %s" % ("cores", "DEPTH", "gates", "gates/core", "vs 1 core"))
    one, outs1 = build_core()
    d1, g1 = depth_of(one, outs1), len(one.ga)
    nin1 = one.n_in
    src_ga, src_gb, src_outs = list(one.ga), list(one.gb), list(outs1)
    del one

    class _S:
        pass
    src = _S(); src.ga = src_ga; src.gb = src_gb; src.n_in = nin1

    for W in (1, 2, 4, 8):
        c = TC.Circuit(nin1 * W)
        allouts = []
        for k in range(W):
            in_map = [2 + k * nin1 + i for i in range(nin1)]
            remap = splice(c, src, in_map)
            allouts += [remap[o] for o in src_outs]
        d, g = depth_of(c, allouts), len(c.ga)
        print("      %6d %10d %14s %14.0f   %s"
              % (W, d, "{:,}".format(g), g / W, "+%d" % (d - d1)))
        del c
    return d1, g1


# ---------------------------------------------------------------- (2) exhaustive assertion
def build_property(prop, W=8):
    """Fabricate a PROPERTY over W-bit operands. Output = 1 iff the property is VIOLATED.
    Addressing the whole 2^(2W) space and OR-ing gives a complete verdict, not a sample."""
    c = TC.Circuit(2 * W)
    A = list(c.IN[:W]); B = list(c.IN[W:])

    def add(x, y):
        return c.add(list(x), list(y))[:W]

    def sub(x, y):
        t = c.add(list(x), [c.not_(b) for b in y])[:W]
        return c.add(t, c.cvec(1, W))[:W]

    def neq(x, y):
        return TC.Circuit.__dict__ and c.not_(c._tree_and([c.not_(c.xor(x[i], y[i])) for i in range(W)]))

    if prop == "add_sub_inverse":            # (a+b)-b == a  for ALL a,b (mod 2^W)
        viol = neq(sub(add(A, B), B), A)
    elif prop == "xor_involution":           # (a^b)^b == a
        t = [c.xor(A[i], B[i]) for i in range(W)]
        u = [c.xor(t[i], B[i]) for i in range(W)]
        viol = neq(u, A)
    elif prop == "sub_add_inverse":           # (a-b)+b == a
        viol = neq(add(sub(A, B), B), A)
    elif prop == "ltu_antisymmetry":          # NOT (a<b AND b<a)
        viol = c.and_(TC.lt(c, A, B), TC.lt(c, B, A))
    elif prop == "ltu_trichotomy":            # exactly one of a<b, b<a, a==b
        lt1 = TC.lt(c, A, B); lt2 = TC.lt(c, B, A)
        eq = c._tree_and([c.not_(c.xor(A[i], B[i])) for i in range(W)])
        # violated if none hold or more than one holds
        none = c._tree_and([c.not_(lt1), c.not_(lt2), c.not_(eq)])
        two = c.or_(c.or_(c.and_(lt1, lt2), c.and_(lt1, eq)), c.and_(lt2, eq))
        viol = c.or_(none, two)
    elif prop == "add_commutes":              # a+b == b+a
        viol = neq(add(A, B), add(B, A))
    else:
        raise ValueError(prop)
    return c, viol


def assert_exhaustive(prop, W=8):
    """address EVERY point of the 2^(2W) space, bit-sliced, and OR the violation bit."""
    c, viol = build_property(prop, W)
    d, g = depth_of(c, viol), len(c.ga)
    cd = nl(c, [viol])
    n_in = c.n_in
    del c
    space = 1 << (2 * W)
    LANES = 1 << 16
    ga, gb, base = cd["ga"], cd["gb"], 2 + n_in
    out0 = cd["outs"][0]
    MASK = (1 << LANES) - 1
    violations = 0
    covered = 0
    for chunk in range(0, space, LANES):
        packed = [0] * n_in
        for l in range(LANES):
            v = chunk + l
            if v >= space:
                v = chunk
            for p in range(n_in):
                if (v >> p) & 1:
                    packed[p] |= (1 << l)
        vw = [0] * cd["n_wire"]
        vw[1] = MASK
        for p in range(n_in):
            vw[2 + p] = packed[p]
        for i in range(len(ga)):
            vw[base + i] = (~(vw[ga[i]] & vw[gb[i]])) & MASK
        violations |= vw[out0]
        covered += min(LANES, space - chunk)
    return d, g, space, covered, violations


def main():
    print("=" * 92)
    print("A POPULATION OF CPUs · AND EXHAUSTIVE ASSERTION OVER A WHOLE INPUT SPACE")
    print("=" * 92)
    print()
    d1, g1 = measure_bank()

    print()
    print("  [2] EXHAUSTIVE ASSERTION - the property is fabricated, the WHOLE space is addressed.")
    print("      Not a sample: every point. A complete space has nothing left un-tested to hide in.")
    print()
    print("      %-22s %8s %10s %14s %14s   %s"
          % ("property (8-bit ops)", "DEPTH", "gates", "space", "covered", "violations"))
    props = ["add_sub_inverse", "sub_add_inverse", "xor_involution",
             "add_commutes", "ltu_antisymmetry", "ltu_trichotomy"]
    for p in props:
        d, g, space, covered, viol = assert_exhaustive(p, 8)
        print("      %-22s %8d %10s %14s %14s   %s"
              % (p, d, "{:,}".format(g), "{:,}".format(space), "{:,}".format(covered),
                 "NONE (proved)" if viol == 0 else "FOUND"))
    print()
    print("      Each row addressed 65,536 points of a 65,536-point space: COMPLETE coverage.")
    print("      'NONE' here is a proof over the whole space, not a pass rate over a sample.")


if __name__ == "__main__":
    main()
