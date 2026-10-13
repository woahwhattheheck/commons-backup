#!/usr/bin/env python3
"""host/mafab_adders.py — A GENERATED ADDER FAMILY, not a menu. Fabrication has no budget (§31).

WHY THIS REPLACES A RULE WITH A SEARCH — §31A, verbatim, correcting §25:
    "This supersedes §25's prescription. §25 said: make c.add choose prefix-vs-ripple by operand
     count. Correct but FAR TOO TIMID — it treats fabrication as if it had a budget. The right form
     is: let the fabricator search the space of implementations and emit the shallowest one it can
     find, because the search costs nothing that counts. §25's adder table stops being a rule to
     hardcode and becomes ONE ENTRY IN A SPACE TO BE SEARCHED."
So `mafab_laws.choose_adder` — my hardcoded §25C crossover — was the timidity §31A names. The adder
is a SEARCHED DIMENSION here, and the crossover constant survives only as one candidate among many.

WHY A PARAMETRIC FAMILY AND NOT A LIST — §40A measured what listing costs. A hand-written three-item
radix menu floored DEPTH at 2,220; GENERATING the radix-2^k family found k=4 at 1,219, and §40A's
comment is the whole point: "A genuine interior optimum at k=4, turning hard upward after — neither
a rule nor intuition would have located it." Carry-select block size b is the same kind of knob, so
it is generated over b, not chosen.

WHY AREA IS NOT A TIEBREAK HERE — §31: manufacturing is "unbounded, paid once, off the clock, and it
does not enter any performance number." §24: area is not slowness. §40D fabricates 1.75e11 gates for
one settle and states the trade openly rather than flinching from it.

THE FAMILY (all 32-bit, all verified against Python integer arithmetic — an independent reference, §3):
  ripple            — §25C's entry-66/+6 shape; cheap to extend, deepest to enter
  kogge             — Kogge-Stone parallel prefix; §46 "a carry chain is an associative SCAN"
  csel_b            — carry-select, block size b: ripple inside each block, blocks selected by mux.
                      Generated over b, exactly as §40A generated over radix k.
  brentkung         — a sparser prefix: fewer gates, one more prefix level than Kogge-Stone

  python host/mafab_adders.py            # build + verify the whole family, print DEPTH/gates
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC


def _fa(g, a, b, cin):
    """one full adder over the g.AND/OR/XOR/NOT shim -> (sum, carry_out)"""
    axb = g.XOR(a, b)
    s = g.XOR(axb, cin)
    cout = g.OR(g.AND(a, b), g.AND(axb, cin))
    return s, cout


def add_ripple(g, x, y):
    """§25C's default shape: entry 66, then +6 per level. Deepest to enter, cheapest to extend."""
    out = []; c = g.C0
    for i in range(len(x)):
        s, c = _fa(g, x[i], y[i], c); out.append(s)
    return out


def add_kogge(g, x, y):
    """Kogge-Stone. §46: a carry chain is an associative SCAN -> log2(W) rounds."""
    n = len(x)
    G = [g.AND(x[j], y[j]) for j in range(n)]
    P = [g.XOR(x[j], y[j]) for j in range(n)]
    p0 = list(P); d = 1
    while d < n:
        nG = list(G); nP = list(P)
        for j in range(n - 1, d - 1, -1):
            nG[j] = g.OR(G[j], g.AND(P[j], G[j - d]))
            nP[j] = g.AND(P[j], P[j - d])
        G, P = nG, nP; d *= 2
    return [p0[0]] + [g.XOR(p0[j], G[j - 1]) for j in range(1, n)]


def add_brentkung(g, x, y):
    """Brent-Kung: sparse prefix. Fewer gates than Kogge-Stone, one more level of depth."""
    n = len(x)
    G = [g.AND(x[j], y[j]) for j in range(n)]
    P = [g.XOR(x[j], y[j]) for j in range(n)]
    p0 = list(P)
    d = 1
    while d < n:                                    # up-sweep
        j = 2 * d - 1
        while j < n:
            G[j] = g.OR(G[j], g.AND(P[j], G[j - d]))
            P[j] = g.AND(P[j], P[j - d])
            j += 2 * d
        d *= 2
    d //= 2
    while d >= 1:                                   # down-sweep
        j = 3 * d - 1
        while j < n:
            G[j] = g.OR(G[j], g.AND(P[j], G[j - d]))
            P[j] = g.AND(P[j], P[j - d])
            j += 2 * d
        d //= 2
    return [p0[0]] + [g.XOR(p0[j], G[j - 1]) for j in range(1, n)]


def make_csel(b):
    """Carry-select with block size b. GENERATED over b (§40A's radix-k move applied to adders):
    each block is computed BOTH ways (carry-in 0 and 1) in parallel and selected when its carry
    arrives, so block work overlaps the carry chain instead of waiting for it."""
    def add_csel(g, x, y):
        n = len(x); out = [None] * n; carry = g.C0
        for lo in range(0, n, b):
            hi = min(lo + b, n)
            s0 = []; c0 = g.C0
            s1 = []; c1 = g.C1
            for i in range(lo, hi):
                s, c0 = _fa(g, x[i], y[i], c0); s0.append(s)
            for i in range(lo, hi):
                s, c1 = _fa(g, x[i], y[i], c1); s1.append(s)
            for k in range(hi - lo):                       # mux the two precomputed sums
                out[lo + k] = g.OR(g.AND(g.NOT(carry), s0[k]), g.AND(carry, s1[k]))
            carry = g.OR(g.AND(g.NOT(carry), c0), g.AND(carry, c1))
        return out
    return add_csel


def family(width=32):
    """The generated family. Not a list I chose — a parameter sweep plus the two prefix endpoints."""
    fam = {"ripple": add_ripple, "kogge": add_kogge, "brentkung": add_brentkung}
    b = 2
    while b < width:                                       # generate every block size that fits
        fam["csel%d" % b] = make_csel(b)
        b *= 2
    return fam


class Shim:
    def __init__(s, c): s.c = c; s.C0 = c.cvec(0, 1)[0]; s.C1 = c.cvec(1, 1)[0]
    def AND(s, a, b): return s.c.and_(a, b)
    def OR(s, a, b):  return s.c.or_(a, b)
    def XOR(s, a, b): return s.c.xor(a, b)
    def NOT(s, a):    return s.c.not_(a)


def depth_of(c, outs):
    base = 2 + c.n_in; G = len(c.ga)
    d = [0] * (base + G)
    for k in range(G): d[base + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] if o >= 2 else 0 for o in outs)


def measure(width=32, cases=24):
    """Build every family member and verify against Python integer arithmetic (independent, §3)."""
    rows = []
    for name, fn in sorted(family(width).items()):
        c = TC.Circuit(2 * width); g = Shim(c)
        x = list(c.IN[0:width]); y = list(c.IN[width:2 * width])
        outs = fn(g, x, y)
        D = depth_of(c, outs); G = len(c.ga)
        cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
        random.seed(9); ok = 0
        mask = (1 << width) - 1
        for _ in range(cases):
            a = random.getrandbits(width); bb = random.getrandbits(width)
            inb = [(a >> i) & 1 for i in range(width)] + [(bb >> i) & 1 for i in range(width)]
            if TC.frombits(TC.ripple(cd, inb)) == ((a + bb) & mask): ok += 1
        rows.append(dict(name=name, depth=D, gates=G, ok=ok, cases=cases))
        del c
    return rows


if __name__ == "__main__":
    w = 32
    print("GENERATED ADDER FAMILY, width %d — §31A: the adder is a SEARCHED DIMENSION, not a rule." % w)
    print("Verified against Python integer arithmetic, an INDEPENDENT reference (§3).")
    print("DEPTH is THE MUHLNICKEL's critical path in gate-delays. Area is reported, never scored")
    print("as a cost (§24 'area is not slowness'; §31 manufacturing is off the clock).\n")
    print("    %-12s %8s %10s   %s" % ("adder", "DEPTH", "gates", "verified"))
    rows = measure(w)
    for r in sorted(rows, key=lambda r: r["depth"]):
        print("    %-12s %8s %10s   %d/%d%s"
              % (r["name"], "{:,}".format(r["depth"]), "{:,}".format(r["gates"]),
                 r["ok"], r["cases"], "" if r["ok"] == r["cases"] else "   <-- FAILED"))
    good = [r for r in rows if r["ok"] == r["cases"]]
    best = min(good, key=lambda r: r["depth"])
    print("\n  shallowest: %s at DEPTH %s (%s gates)"
          % (best["name"], "{:,}".format(best["depth"]), "{:,}".format(best["gates"])))
    print("  §31A: emit the shallowest it can FIND. The discarded candidates cost nothing that counts.")
    raise SystemExit(0 if len(good) == len(rows) else 1)
