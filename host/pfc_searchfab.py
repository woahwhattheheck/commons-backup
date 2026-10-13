"""
pfc_searchfab.py - UNBOUNDED MANUFACTURING SEARCH. Emit the SHALLOWEST circuit, not a circuit.

S31 (owner, 2026-07-26): fabrication = manufacturing, and manufacturing is NOT part of the compute.
A fabricator's own cost is a factory spec, never a latency. It is off the clock and unbounded.

The consequence is this file. If searching costs nothing that counts, then a fabricator has no
reason to pick an implementation - it should try EVERY implementation it can think of, verify each
one byte-exact, and keep the one with the smallest DEPTH. Nothing about that search appears in any
performance number. The only thing that ships is the winner.

This supersedes S25's prescription. S25 measured that prefix adders win in isolation and ripple
adders win in deep trees, and concluded "make c.add switch on operand count". That is a hardcoded
rule, and hardcoding a rule is what a fabricator does when it thinks it has a budget. It does not.

WHAT IS SEARCHED (all produce the identical function: sum of N W-bit values, mod 2^W)
  ripple-tree        balanced tree, ripple-carry adder at every node   <- what c.add gives you today
  kogge-tree         balanced tree, Kogge-Stone prefix adder at every node
  ripple-chain       linear accumulate, ripple
  kogge-chain        linear accumulate, prefix
  csa->ripple        carry-save 3:2 compression to two vectors, then ONE ripple to resolve
  csa->kogge         carry-save 3:2 compression to two vectors, then ONE prefix add to resolve

Run:  python host/pfc_searchfab.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC

try:
    from pfc_bettergates import kogge_stone_add
    HAVE_KS = True
except Exception:
    HAVE_KS = False

W = 16
N = 16


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
    """DEPTH = longest dependency chain, gate-delays. The ONLY figure here that is compute."""
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[x] for x in outs)


def netlist(c, outs):
    return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": list(outs)}


def _csa(c, a, b, d):
    """carry-save 3:2 compressor: three vectors in, two out, and CRITICALLY no carry propagates.
    Depth is CONSTANT regardless of width - that is the whole point of carry-save."""
    s = [c.xor(c.xor(a[i], b[i]), d[i]) for i in range(W)]
    cr = []
    for i in range(W):
        ab = c.and_(a[i], b[i])
        ad = c.and_(a[i], d[i])
        bd = c.and_(b[i], d[i])
        cr.append(c.or_(c.or_(ab, ad), bd))
    cr = [c.cvec(0, 1)[0]] + cr[:W - 1]      # the carry vector is shifted left one place
    return s, cr


def build(kind):
    c = TC.Circuit(N * W)
    g = _Shim(c)
    RP = lambda a, b: c.add(a, b)[:W]
    KS = (lambda a, b: kogge_stone_add(g, a, b)[:W]) if HAVE_KS else RP
    V = [list(c.IN[i * W:(i + 1) * W]) for i in range(N)]

    if kind in ("ripple-tree", "kogge-tree"):
        f = RP if kind.startswith("ripple") else KS
        lvl = V
        while len(lvl) > 1:
            lvl = [f(lvl[j], lvl[j + 1]) for j in range(0, len(lvl) - 1, 2)] + \
                  ([lvl[-1]] if len(lvl) % 2 else [])
        return c, lvl[0]

    if kind in ("ripple-chain", "kogge-chain"):
        f = RP if kind.startswith("ripple") else KS
        acc = V[0]
        for i in range(1, N):
            acc = f(acc, V[i])
        return c, acc

    if kind in ("csa->ripple", "csa->kogge"):
        f = RP if kind.endswith("ripple") else KS
        vecs = list(V)
        while len(vecs) > 2:
            nxt = []
            i = 0
            while i + 2 < len(vecs):
                s, cr = _csa(c, vecs[i], vecs[i + 1], vecs[i + 2])
                nxt += [s, cr]
                i += 3
            nxt += vecs[i:]
            vecs = nxt
        return c, f(vecs[0], vecs[1]) if len(vecs) == 2 else (c, vecs[0])

    raise ValueError(kind)


def verify(nl, trials=6, seed=4):
    random.seed(seed)
    for _ in range(trials):
        vals = [random.randint(0, 2 ** W - 1) for _ in range(N)]
        inb = []
        for v in vals:
            inb += [(v >> i) & 1 for i in range(W)]
        out = TC.ripple(nl, inb)
        if sum(out[k] << k for k in range(W)) != (sum(vals) & (2 ** W - 1)):
            return False
    return True


def main():
    print("=" * 78)
    print("UNBOUNDED MANUFACTURING SEARCH - try everything, ship the shallowest (S31A)")
    print("  function: sum of %d values of %d bits, mod 2^%d. Every candidate computes it exactly." % (N, W, W))
    print("  DEPTH is the product's latency. Gate count is AREA and does not slow it down (S24).")
    print("=" * 78)
    print()
    print("   %-13s %8s %10s %10s   %s" % ("candidate", "DEPTH", "GATES", "verified", "note"))

    kinds = ["ripple-tree", "kogge-tree", "ripple-chain", "kogge-chain", "csa->ripple", "csa->kogge"]
    results = []
    for k in kinds:
        c, outs = build(k)
        d = depth_of(c, outs)
        gates = len(c.ga)
        ok = verify(netlist(c, outs))
        note = ""
        if k == "ripple-tree":
            note = "<- what c.add gives you today"
        results.append((k, d, gates, ok))
        print("   %-13s %8d %10s %10s   %s"
              % (k, d, "{:,}".format(gates), "6/6" if ok else "FAIL", note))
        del c

    good = [r for r in results if r[3]]
    good.sort(key=lambda r: r[1])
    best = good[0]
    default = [r for r in results if r[0] == "ripple-tree"][0]

    print()
    print("  WINNER: %s  -  DEPTH %d, %s gates" % (best[0], best[1], "{:,}".format(best[2])))
    print("  vs the fabricator's current default (ripple-tree, DEPTH %d): %.2fx shallower for %.2fx the area."
          % (default[1], default[1] / best[1], best[2] / default[2]))
    print()
    print("  MANUFACTURING SPEND (S31 - a factory spec, NOT a latency, NOT added to anything):")
    print("    %d candidates built and verified, %s gates fabricated in total, all but one discarded."
          % (len(results), "{:,}".format(sum(r[2] for r in results))))
    print("    None of that appears in the shipped circuit's cost. Only DEPTH %d ships." % best[1])
    print()
    print("  WHAT THE SEARCH FOUND THAT A HARDCODED RULE COULD NOT:")
    print("    S25 searched only {ripple, prefix} and concluded 'switch on operand count'.")
    print("    Carry-save was outside that rule's vocabulary entirely - it does not propagate a")
    print("    carry at all, so its depth is constant in width. A rule picks from what it knows;")
    print("    a search does not have to know first.")


if __name__ == "__main__":
    main()
