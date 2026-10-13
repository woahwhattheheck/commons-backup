"""
pfc_serial_audit.py - find ASSISTANT-PRODUCED SEQUENCING: serial folds over associative operations.

S35 found the pattern in the dot product: a matvec's blocks are SUMMED, so they were never
dependent - chaining them was my construction. The generalisable form is:

    acc = identity
    for x in items:            <- a CHAIN. DEPTH = N * depth(op)
        acc = op(acc, x)

If `op` is associative - add, mul, max, min, and, or, xor, csa - the same result comes from a TREE:

    while len(items) > 1:      <- a TREE. DEPTH = log2(N) * depth(op)
        items = [op(a, b) for a, b in pairs(items)]

Identical function, identical gate count, and the only thing that changes is DEPTH: N -> log2(N).
For N=32 that is 6.4x. For N=4096 it is 341x. Nothing has to be invented; the work was already
independent and was made sequential by how the loop was written.

THE CHECK, applied to every hit: is this work dependent, or did I make it sequential?

Run:  python host/pfc_serial_audit.py            (audit)
      python host/pfc_serial_audit.py --prove    (also measure the payoff on a real circuit)
"""
import sys, os, re, glob

ASSOC = ("add", "mul", "max", "min", "and_", "or_", "xor", "csa", "sum",
         "mux", "mux_vec", "onehot", "add_prefix")
# S48: `mux` belongs here. A chain of muxes with MUTUALLY EXCLUSIVE selectors IS a one-hot
# reduction, so it is a tree at 1+log2(N), not a chain at N. The first version of this list
# omitted mux and therefore MISSED the RV32I core's own 8-deep ALU select, 5-deep writeback
# and 3-deep next-PC chains - which owned the core's critical path (DEPTH 222 -> 186).

# A serial fold is `x = op(x, ...)` ANYWHERE inside a loop body - not only as the first statement.
# The first version of this tool required it to be the first statement and therefore MISSED a live
# instance in pfc_pattern_bank.py (a prefix-OR written as a chain). A detector with that gap is
# worse than none, because a clean report reads as proof.
ASSIGN = re.compile(r"^(\s*)(\w+)\s*=\s*[\w\.]*(" + "|".join(ASSOC) + r")\s*\((?P<args>[^)]*)")
FORLN = re.compile(r"^(\s*)(for|while)")


def audit():
    hits = []
    for path in sorted(glob.glob("host/*.py")):
        try:
            lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
        except Exception:
            continue
        # for each loop header, walk its indented body and look for a self-referential assoc assign
        for i, ln in enumerate(lines):
            mf = FORLN.match(ln)
            if not mf:
                continue
            ind = len(mf.group(1))
            for j in range(i + 1, len(lines)):
                body = lines[j]
                if body.strip() and (len(body) - len(body.lstrip())) <= ind:
                    break                                   # left the loop body
                ma = ASSIGN.match(body)
                if ma and re.search(r"(^|[\s,(])" + re.escape(ma.group(2)) + r"($|[\s,)\[])",
                                    ma.group("args")):        # x = op(..., x, ...) - ANY position
                    rec = (path, j + 1, ma.group(2), ma.group(3), ln.strip()[:66])
                    if rec not in hits:
                        hits.append(rec)
    return hits


def main():
    print("=" * 92)
    print("SERIAL FOLDS OVER ASSOCIATIVE OPS - work that is independent but was written as a chain")
    print("  DEPTH of a fold is N x depth(op). DEPTH of a tree is log2(N) x depth(op). Same gates.")
    print("=" * 92)
    hits = audit()
    if not hits:
        print("  none found")
    else:
        print()
        print("  %-30s %6s %-9s %-7s %s" % ("file", "line", "accum", "op", "the loop"))
        for path, ln, name, op, text in hits:
            print("  %-30s %6d %-9s %-7s %s" % (os.path.basename(path), ln, name, op, text))
        print()
        print("  %d serial folds found. Each is a candidate tree." % len(hits))
        print("  Not every hit is a bug: a fold is CORRECT when each step genuinely depends on the")
        print("  previous one (an accumulator across time, a running state). The check is the same")
        print("  one that caught the dot product: IS THIS WORK DEPENDENT, OR DID I MAKE IT SEQUENTIAL?")

    if "--prove" not in sys.argv:
        print()
        print("  re-run with --prove to measure the payoff on a real circuit.")
        return

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import titan_circuit as TC
    import random

    W = 16

    def depth_of(c, outs):
        n = c.n_in
        d = [0] * (2 + n + len(c.ga))
        for k in range(len(c.ga)):
            d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
        return max(d[x] for x in outs)

    print()
    print("=" * 92)
    print("THE PAYOFF, MEASURED - identical function, identical gates, fold vs tree")
    print("=" * 92)
    print()
    print("  %5s | %11s %9s | %11s %9s | %8s   %s" %
          ("N", "fold DEPTH", "gates", "tree DEPTH", "gates", "shallower", "verified"))
    for N in (4, 8, 16, 32, 64):
        out = {}
        for mode in ("fold", "tree"):
            c = TC.Circuit(N * W)
            V = [list(c.IN[i * W:(i + 1) * W]) for i in range(N)]
            if mode == "fold":
                acc = V[0]
                for i in range(1, N):
                    acc = c.add(acc, V[i])[:W]          # THE CHAIN
                res = acc
            else:
                lvl = V
                while len(lvl) > 1:                      # THE TREE
                    lvl = [c.add(lvl[j], lvl[j + 1])[:W] for j in range(0, len(lvl) - 1, 2)] + \
                          ([lvl[-1]] if len(lvl) % 2 else [])
                res = lvl[0]
            nl = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": list(res)}
            random.seed(2)
            ok = 0
            for _ in range(3):
                vals = [random.randint(0, 2 ** W - 1) for _ in range(N)]
                inb = []
                for v in vals:
                    inb += [(v >> i) & 1 for i in range(W)]
                got = sum(b << k for k, b in enumerate(TC.ripple(nl, inb)))
                ok += (got == (sum(vals) & (2 ** W - 1)))
            out[mode] = (depth_of(c, res), len(c.ga), ok)
            del c
        f, t = out["fold"], out["tree"]
        print("  %5d | %11d %9s | %11d %9s | %7.2fx   %d/3 %d/3"
              % (N, f[0], "{:,}".format(f[1]), t[0], "{:,}".format(t[1]), f[0] / t[0], f[2], t[2]))
    print()
    print("  Gate counts are IDENTICAL - the tree costs nothing extra. Only the wiring order changed.")
    print("  This is the purest case of an assistant-produced bottleneck: same work, same area,")
    print("  and the DEPTH difference was created entirely by writing a loop instead of a tree.")


if __name__ == "__main__":
    main()
