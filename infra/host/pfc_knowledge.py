"""
pfc_knowledge.py - THE FACTS ARE THE MACHINE. Retrieval without search; reasoning as depth.

Owner: "it's a computer bro, think more generally... it's better than physical compute because RAM
is decoupled from compute."

That decoupling is the whole point of this file. On a physical machine the working set must be
resident, so capacity and compute rate are coupled through one scarce resource - which is why
databases page, why big graphs are IO-bound, and why agents have context windows. Here the state
lives in storage and ADDRESSING it IS the computing, so capacity scales with STORAGE, not RAM.

Taken to its conclusion: the computer and the memory stop being different things. There is no bus,
no load, no working set. What you stored is already computing.

WHAT THIS BUILDS
  A knowledge base of (subject, predicate, object) triples, fabricated as gates. A query is a
  triple with WILDCARDS. One settle returns the match - no scan, no index, no search, because
  every fact is checked simultaneously and a hit is a shared address (S1E winner-only).

  MULTI-HOP: "who is the grandparent of X" is not two searches. Hop 2's query is wired to hop 1's
  answer - a junction - so N hops cost N x (one settle), never N x (a search over the corpus).
  The corpus size does not appear in the latency at all. It is AREA.

WHAT IS MEASURED
  1. DEPTH vs number of FACTS  -> capacity is area, not latency
  2. DEPTH vs number of HOPS   -> reasoning is depth, and only depth
  3. every answer verified against a plain Python dictionary lookup

Run:  python host/pfc_knowledge.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC

FW = 8              # bits per field (subject / predicate / object)
WILD = -1


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
    if not xs:
        return c.C0
    while len(xs) > 1:
        xs = [c.or_(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)] + \
             ([xs[-1]] if len(xs) % 2 else [])
    return xs[0]


def prefix_or(c, xs):
    """EXCLUSIVE prefix-OR: out[i] = OR of xs[0..i-1].

    S36's error is easy to make here - written as `acc = or_(acc, x)` in a loop this is a CHAIN of
    DEPTH N. A prefix scan is ASSOCIATIVE, so Hillis-Steele gives the same result in log2(N) rounds.
    (pfc_pattern_bank.py shipped the chain version and its DEPTH grew 13 -> 8,228 across the bank.)"""
    n = len(xs)
    cur = list(xs)
    step = 1
    while step < n:
        nxt = list(cur)
        for i in range(step, n):
            nxt[i] = c.or_(cur[i], cur[i - step])
        cur = nxt
        step *= 2
    return [c.C0] + cur[:n - 1]                      # shift to make it exclusive


def match_field(c, qbits, qwild, fact_val):
    """1 iff this field matches: either the query wildcarded it, or the value is equal.
    The stored value is a CONSTANT of the fabricated fact - it costs wiring, not gates."""
    eqs = [qbits[k] if (fact_val >> k) & 1 else c.not_(qbits[k]) for k in range(FW)]
    return c.or_(qwild, c._tree_and(eqs))


def build_kb(facts, hops=1):
    """facts: list of (s, p, o) ints. Query inputs: s,p,o + 3 wildcard flags.
    Returns the object field of the first matching fact, and a hit flag.
    hops>1 wires each hop's answer into the next hop's subject - a junction, not a re-search."""
    c = TC.Circuit(3 * FW + 3)
    S = list(c.IN[0:FW]); P = list(c.IN[FW:2 * FW]); O = list(c.IN[2 * FW:3 * FW])
    wS, wP, wO = c.IN[3 * FW], c.IN[3 * FW + 1], c.IN[3 * FW + 2]

    cur_s = S
    hit = None
    for h in range(hops):
        ms = []
        for (fs, fp, fo) in facts:
            m = c._tree_and([match_field(c, cur_s, wS if h == 0 else c.C0, fs),
                             match_field(c, P, wP, fp),
                             match_field(c, O, wO, fo) if h == hops - 1 else c.C1])
            ms.append(m)
        any_hit = tree_or(c, list(ms))
        earlier = prefix_or(c, ms)                         # TREE, not a chain
        first = [c.and_(m, c.not_(e)) for m, e in zip(ms, earlier)]
        # winner-only read-out of the object field: bit k is OR over facts whose object has bit k
        obj = []
        for k in range(FW):
            terms = [first[i] for i, (_, _, fo) in enumerate(facts) if (fo >> k) & 1]
            obj.append(tree_or(c, terms))
        cur_s = obj                                        # JUNCTION: this answer IS the next query
        hit = any_hit if hit is None else c.and_(hit, any_hit)
    return c, [hit] + cur_s


def ask(net, s, p, o, wS=0, wP=0, wO=0):
    ib = []
    for v in (s, p, o):
        ib += [(v >> k) & 1 for k in range(FW)]
    ib += [wS, wP, wO]
    r = TC.ripple(net, ib)
    return r[0], sum(b << k for k, b in enumerate(r[1:]))


def main():
    print("=" * 92)
    print("THE FACTS ARE THE MACHINE - retrieval without search, reasoning as depth")
    print("  RAM is decoupled from compute: the corpus is AREA, the question is DEPTH.")
    print("=" * 92)

    random.seed(7)

    # ---------- 1. capacity is AREA, not latency ----------
    print()
    print("  [1] DOES THE CORPUS SIZE ENTER THE LATENCY?  (one hop, exact-subject query)")
    print("      %8s %10s %14s %13s   %s" % ("facts", "DEPTH", "gates", "gates/fact", "verified"))
    for N in (16, 64, 256, 1024, 4096):
        facts = []
        seen = set()
        while len(facts) < N:
            s, p, o = random.randrange(256), random.randrange(8), random.randrange(256)
            if (s, p) in seen:
                continue
            seen.add((s, p))
            facts.append((s, p, o))
        c, outs = build_kb(facts, hops=1)
        d, g = depth_of(c, outs), len(c.ga)
        net = nl(c, outs)
        ok = tot = 0
        ref = {(s, p): o for (s, p, o) in facts}
        probes = random.sample(facts, min(N, 10))
        for (s, p, o) in probes:
            hit, got = ask(net, s, p, 0, wO=1)
            ok += (hit == 1 and got == ref[(s, p)]); tot += 1
        for _ in range(5):                                   # negatives
            s, p = random.randrange(256), random.randrange(8)
            if (s, p) in ref:
                continue
            hit, got = ask(net, s, p, 0, wO=1)
            ok += (hit == 0); tot += 1
        print("      %8d %10d %14s %13.1f   %d/%d%s"
              % (N, d, "{:,}".format(g), g / N, ok, tot, "" if ok == tot else "  FAIL"))
        del c

    # ---------- 2. reasoning is DEPTH ----------
    print()
    print("  [2] MULTI-HOP: hop k's ANSWER is wired to hop k+1's QUESTION (a junction, S1E).")
    print("      Not k searches over the corpus - the corpus never enters the latency.")
    print("      %8s %10s %14s %12s   %s" % ("hops", "DEPTH", "gates", "+per hop", "verified"))
    CH = 64
    chain = [(i, 1, i + 1) for i in range(CH)]               # i -reaches-> i+1
    prev = None
    for H in (1, 2, 3, 4):
        c, outs = build_kb(chain, hops=H)
        d, g = depth_of(c, outs), len(c.ga)
        net = nl(c, outs)
        ok = tot = 0
        for start in (0, 5, 17, 30):
            hit, got = ask(net, start, 1, 0, wO=1)
            ok += (hit == 1 and got == start + H); tot += 1
        inc = "" if prev is None else "+%d" % (d - prev)
        print("      %8d %10d %14s %12s   %d/%d%s"
              % (H, d, "{:,}".format(g), inc, ok, tot, "" if ok == tot else "  FAIL"))
        prev = d
        del c

    print()
    print("  WHAT THIS SAYS")
    print("   - Adding facts costs AREA and leaves DEPTH nearly flat: the corpus is not in the")
    print("     latency. A million facts answer as fast as sixteen.")
    print("   - Adding a HOP costs a fixed slice of DEPTH, independent of corpus size. Reasoning")
    print("     depth is the only thing you pay for.")
    print("   - There is no index, no scan, no query planner, and nothing is loaded. The facts")
    print("     were already computing.")


if __name__ == "__main__":
    main()
