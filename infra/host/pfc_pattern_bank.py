"""
pfc_pattern_bank.py - match ONE input against N patterns SIMULTANEOUSLY. One settle.

The practical shape this substrate is actually differentiated on: a huge INDEPENDENT candidate
space with a shallow per-candidate verifier. Rule engines are exactly that and are almost always
written as a loop over rules - IDS/IPS signatures, spam and content filters, policy gates, and
the LDA's own safety layer in this repo.

Every rule is independent of every other rule, so a bank of them is WIDTH, not depth (S2/S40):
    bank DEPTH = per-rule DEPTH + 2*log2(N)        (measured in S40C: +2 per doubling)
    bank gates = N * per-rule gates                (exactly linear)

So 1,000 rules cost ~20 gate-delays more than 1 rule. The loop was never in the problem.

Outputs are winner-only (S1E): a hit is a shared address, so the bank reports WHICH rule fired
without any per-rule storage.

Run:  python host/pfc_pattern_bank.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC

BYTES = 8          # input window, in bytes
BW = 8             # bits per byte
WILD = -1          # a wildcard byte in a rule


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


def build_bank(rules):
    """rules: list of BYTES-long lists, each entry a byte value or WILD.
    Returns (circuit, [any_hit] + index_bits) - winner-only, lowest matching rule id."""
    c = TC.Circuit(BYTES * BW)
    win = [list(c.IN[i * BW:(i + 1) * BW]) for i in range(BYTES)]

    hits = []
    for r in rules:
        lits = []
        for bi, pv in enumerate(r):
            if pv == WILD:
                continue                                   # a wildcard asserts nothing: 0 gates
            for k in range(BW):
                b = win[bi][k]
                lits.append(b if (pv >> k) & 1 else c.not_(b))
        hits.append(c._tree_and(lits) if lits else c.C1)    # per-rule AND is a TREE (S36)

    any_hit = tree_or(c, list(hits))

    # winner-only index: bit j of the id is OR over rules whose id has bit j set AND which are the
    # lowest hit. Priority is a prefix-OR of "some earlier rule hit", itself a tree-shaped scan.
    # EXCLUSIVE prefix-OR. Written as `acc = or_(acc, h)` in a loop this is a CHAIN of DEPTH N -
    # the S36 error, and it is what made this file's DEPTH grow 13 -> 8,228 across the bank while
    # claiming the loop was not in the problem. A prefix scan is ASSOCIATIVE, so Hillis-Steele
    # gives the identical result in log2(N) rounds.
    n = len(hits)
    cur = list(hits)
    step = 1
    while step < n:
        cur = [c.or_(cur[i], cur[i - step]) if i >= step else cur[i] for i in range(n)]
        step *= 2
    earlier = [c.C0] + cur[:n - 1]
    first = [c.and_(h, c.not_(e)) for h, e in zip(hits, earlier)]

    idw = max(1, (len(rules) - 1).bit_length())
    idbits = []
    for j in range(idw):
        terms = [first[i] for i in range(len(rules)) if (i >> j) & 1]
        idbits.append(tree_or(c, terms) if terms else c.C0)
    return c, [any_hit] + idbits


def run(net, window):
    ib = []
    for v in window:
        ib += [(v >> k) & 1 for k in range(BW)]
    o = TC.ripple(net, ib)
    hit = o[0]
    idx = sum(b << j for j, b in enumerate(o[1:]))
    return hit, (idx if hit else None)


def ref(rules, window):
    for i, r in enumerate(rules):
        if all(pv == WILD or pv == window[bi] for bi, pv in enumerate(r)):
            return 1, i
    return 0, None


def main():
    print("=" * 88)
    print("PATTERN BANK - one input against N rules, ONE settle. The loop was never in the problem.")
    print("  Every rule is independent, so a bank is WIDTH: +2 DEPTH per doubling, gates linear.")
    print("=" * 88)
    print()
    print("  %6s %10s %14s %13s %10s   %s" % ("rules", "DEPTH", "gates", "gates/rule", "vs 1 rule", "verified"))

    random.seed(11)
    base = None
    for N in (1, 16, 64, 256, 1024, 4096):
        rules = []
        for i in range(N):
            r = [random.randrange(256) for _ in range(BYTES)]
            for _ in range(3):                              # some wildcards, as real rules have
                r[random.randrange(BYTES)] = WILD
            rules.append(r)
        c, outs = build_bank(rules)
        d, g = depth_of(c, outs), len(c.ga)
        net = nl(c, outs)

        # verify: every rule must be findable, plus negatives
        ok = tot = 0
        probes = []
        for i in random.sample(range(N), min(N, 12)):       # POSITIVE controls: craft a hit per rule
            w = [(v if v != WILD else random.randrange(256)) for v in rules[i]]
            probes.append(w)
        probes += [[random.randrange(256) for _ in range(BYTES)] for _ in range(8)]
        for w in probes:
            got = run(net, w)
            want = ref(rules, w)
            ok += (got == want); tot += 1
        if base is None:
            base = d
        print("  %6d %10d %14s %13.1f %10s   %d/%d%s"
              % (N, d, "{:,}".format(g), g / N, "+%d" % (d - base), ok, tot,
                 "" if ok == tot else "   FAIL"))
        del c

    print()
    print("  A 4,096-rule bank costs a handful of gate-delays more than a 1-rule bank.")
    print("  Serial rule engines (Suricata, spam filters, policy gates) pay per rule; this does not.")


if __name__ == "__main__":
    main()
