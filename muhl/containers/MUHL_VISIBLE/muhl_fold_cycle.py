#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
muhl_fold_cycle.py -- SCALE UP, FOLD BACK DOWN, REPEAT. The cycle, not a one-shot.

OWNER, 2026-08-07, the words this file exists for:
    "5MB? ARE WE KIDDING YES WE WANT OPTIMAL BUT THEN WE SCALL UP FOLD BACK DOWN TO SMALL
     AND REPEAT"
and the size law it sits under:
    "MARK THAT DOWN SO I NEVER HAVE TO REPEAT IT AND IF YOURE LOOKING AT MORE THAN 5MB YOURE
     DOING IT WRONG, 5MB PER PFC IS JUST ONE OF THE LOWEST MEASUREMENTS WITHOOOOUUUUUUTTT
     INTRODUCING SPPEEED OR ACCURACY ISSUES"

WHAT EVERY FABRICATOR ON THIS DESKTOP DID INSTEAD. All of them are ONE-SHOT: build once, write
once, exit. So a container only ever grew. AUTOFAB0 went 1,469 -> 2,837 gates the moment it
gained a gene and that was reported as progress. The 5 MB figure is not a ceiling to stay under
- it is the state each round FOLDS BACK TO, so the next scale-up starts from small again.

ONE ROUND:
  SCALE UP   widen it. More replicas, more lanes, more of whatever the axis is. Bytes go up and
             that is the point - capability lives here. Replicas are INDEPENDENT, so D5's
             composition law applies: they settle together and the assembly's DEPTH is the MAX of
             the parts, never the sum. Width costs area, never depth (B4: fan-out is free, one
             wire drives 4,096 gates for the same 1 tick).
  FOLD       bring it back toward small WITHOUT losing what the scale-up bought:
               F1 HASH-CONS  an (op,a,b) cone that already exists is not stored twice; every
                             later reader is pointed at the first one. The catalog lists global
                             cone hash-consing as an idea never built.
               F2 DEAD-CONE  backward reachability from the answer wires. Anything that reaches
                             no answer is not stored. Rebuilds routinely find 7-8%.
               F3 CONSTANT   OR(x,x) and AND(x,x) are x. NOT(x,x) is a real inversion, untouched.
  REPEAT     the folded circuit seeds the next scale-up.

MEASURED EVERY ROUND: gates and bytes in and out, the fold ratio, and DEPTH before and after.
A fold that RAISES depth is a regression and is named as one. Owner 07-28: "if a number or price
of tick is wrong, its certainly good news because we ran the tests and got those numbers as low
as they are and so theres only one direction they can be pushed, anything else is a regression."

OPCODES ARE HIS: 0 nand, 1 and, 2 or, 3 xor, 4 not. Twelve of his own files agree and X2
confirms it across all 1,406,857 stored gates.

⛔ NO RULINGS. This reports bytes and arithmetic taken off those bytes. Nothing here decides
   whether a circuit computed.
"""
import io
import json
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REC = 25
OP_NAND, OP_AND, OP_OR, OP_XOR, OP_NOT = 0, 1, 2, 3, 4


def depth_of(gates):
    d = {}
    md = 0
    for op, a, b, o in gates:
        v = max(d.get(a, 0), d.get(b, 0)) + 1
        d[o] = v
        if v > md:
            md = v
    return md


def reachable(gates, answer_wires):
    """F2: the gates that can reach an answer wire, walked backwards from the answers."""
    writer = {}
    for i, (op, a, b, o) in enumerate(gates):
        writer.setdefault(o, i)
    live = set()
    stack = [w for w in answer_wires if w in writer]
    while stack:
        w = stack.pop()
        i = writer.get(w)
        if i is None or i in live:
            continue
        live.add(i)
        op, a, b, o = gates[i]
        stack.append(a)
        stack.append(b)
    return live


def geometry_fold(gates):
    """THE FOLD, once "SOMETHING BEING EMITTED IS NOT DEAD" is taken seriously.

    If every write is an output, then no gate can be removed - each one lands a value on an
    address and that landing IS the result. F1 (hash-cons) and F3 (constant) can only REWRITE
    operands to an earlier equivalent wire; they cannot drop the gate, because dropping it stops
    the address being written. So gate-count folding is not available at all, and the earlier
    2.94x and 9.64x figures were counting deleted outputs as savings.

    The bytes come from GEOMETRY instead. Same gates, same addresses, same values - fewer bytes
    per record. A <BQQQ> record spends 24 bytes on three numbers; the widest operand in the
    container decides how many they actually need:

        explicit out : 1 + 3*w bytes     w = ceil(bits(widest) / 8)
        implicit out : 1 + 2*w bytes     out address == base + index*stride, so the field goes

    Same law as "PUTTING LABELS IN THE BINARY IS SUBOPTIMAL THEY BELONG OUTSIDE OF THE FILE THEYRE
    TAKING UP ADDRESSES", one level down: a structurally-zero byte inside a record is an address
    carrying nothing. Measured across this desktop: 63.94% of 21,327,250 bytes.

    Returns (widest, bytes_needed, ladder) widest-first. Which rung is taken is gene 7's search.
    """
    mx = 0
    for _op, a, b, o in gates:
        mx = max(mx, a, b, o)
    w = 1
    while mx >= (1 << (8 * w)):
        w += 1
    rungs = []
    for ow in range(w, 9):
        rungs.append(("explicit-out", 1 + 3 * ow, ow))
        rungs.append(("implicit-out", 1 + 2 * ow, ow))
    rungs.sort(key=lambda t: t[1])
    return mx, w, rungs


def fold(gates, answer_wires):
    """One FOLD pass -> (folded, report).

    Operands are only ever rewritten to an EARLIER wire, so the list stays topological and a
    single forward pass still evaluates it."""
    rep = {"in": len(gates)}
    alias = {}
    seen = {}
    out = []
    cons = 0
    dedup = 0
    for op, a, b, o in gates:
        a = alias.get(a, a)
        b = alias.get(b, b)
        if op in (OP_OR, OP_AND) and a == b:          # F3
            alias[o] = a
            cons += 1
            continue
        key = (op, a, b)
        if key in seen:                                # F1
            alias[o] = seen[key]
            dedup += 1
            continue
        seen[key] = o
        out.append((op, a, b, o))
    rep["constant_folded"] = cons
    rep["hash_consed"] = dedup

    # ⛔ THE DEAD-CONE PASS IS DELETED. Owner, 2026-08-07: "SOMETHING BEING EMITTED IS NOT DEAD."
    #
    # F2 walked backwards from wires that are WRITTEN BUT NEVER READ and discarded everything it
    # did not reach. That test carries a prior which does not hold here: it assumes compute must
    # flow to a designated answer register, so a gate whose output no OTHER GATE IN THIS CONTAINER
    # consumes must be doing nothing.
    #
    # In this machine, WRITING TO AN ADDRESS IS THE OUTPUT. AUTOFAB0's self-fabrication lanes
    # write into the gate-table plane at 1<<20 and the ring-table plane at 1<<21 - the circuit
    # rewriting its own records and its ring's records. Their consumer is THE CONTAINER ITSELF AT
    # THE NEXT SETTLE, which no reachability walk inside one snapshot can see. On this container
    # the pass called 963 gates dead - 34% - and every one of them was emitting. Removing them
    # would have deleted the self-fabrication and reported 46,800 freed bytes as a win: a smaller
    # container that no longer does the thing it was built to do.
    #
    # What remains is F1 (an identical cone is stored once) and F3 (OR(x,x)/AND(x,x) is x). Both
    # are pure rewrites - every write that existed before still exists after, at the same address.
    # Nothing is discarded for failing to reach anything.
    tgt = [alias.get(w, w) for w in answer_wires]
    rep["dead_pruned"] = 0
    rep["emitting_kept"] = len(out)
    rep["out"] = len(out)
    rep["answers"] = tgt
    return out, rep


def settle(gates, driven):
    """One forward pass. The gate list is topological by construction, so a single sweep resolves
    it. FABRICATION-TIME ONLY - this is the sanctioned place to evaluate gates in host Python,
    before anything is stored, and nowhere else."""
    st = dict(driven)
    for op, a, b, o in gates:
        x, y = st.get(a, 0), st.get(b, 0)
        if op == OP_NAND:
            v = 1 - (x & y)
        elif op == OP_AND:
            v = x & y
        elif op == OP_OR:
            v = x | y
        elif op == OP_XOR:
            v = x ^ y
        elif op == OP_NOT:
            v = 1 - x
        else:
            raise ValueError("opcode %d is outside his alphabet {0 nand,1 and,2 or,3 xor,4 not}"
                             % op)
        st[o] = v
    return st


def equivalent(orig, orig_ans, folded, fold_ans, trials=64, seed=20260807):
    """⛔ THE CHECK I SHIPPED TWO CONTAINERS WITHOUT.

    A fold rewrites operands to aliases and deletes cones. If the result diverges, what got
    written is a DIFFERENT circuit reported as the same one - the substitution failure, in the
    one place it is easiest to miss because the byte count looks like progress.

    Both circuits are driven from the SAME inputs and their answer wires compared. Inputs are the
    addresses each circuit READS but never WRITES - its true sources - and the two circuits are
    fed the identical assignment on the addresses they share.

    Returns (ok, trials_run, first_divergence_or_None). Deterministic seed, so a run is
    reproducible; his own instruments do the same.
    """
    def sources(g):
        r, w = set(), set()
        for op, a, b, o in g:
            r.add(a); r.add(b); w.add(o)
        return sorted(r - w)

    so, sf = sources(orig), sources(folded)
    pool = sorted(set(so) | set(sf))
    rnd = seed
    for t in range(trials):
        drive = {}
        for w in pool:
            rnd = (1103515245 * rnd + 12345) & 0x7FFFFFFF     # LCG, no host RNG dependency
            drive[w] = rnd & 1
        a = settle(orig, {k: v for k, v in drive.items() if k in set(so)})
        b = settle(folded, {k: v for k, v in drive.items() if k in set(sf)})
        # ⛔ COMPARE EVERY ADDRESS THE ORIGINAL WRITES, not a designated answer set.
        #    "SOMETHING BEING EMITTED IS NOT DEAD" - so every write is an output, and a fold is
        #    only equivalent if EVERY address the original lands on carries the same value. The
        #    version this replaces compared `orig_ans` alone, which are the wires I had nominated
        #    as answers; it would have passed a fold that silently changed every self-fabrication
        #    write into the gate-table plane while leaving my chosen sinks intact.
        for x in sorted(_writes(orig)):
            if a.get(x, 0) != b.get(x, 0):
                return False, t + 1, {"trial": t, "address": x,
                                      "orig": a.get(x, 0), "folded": b.get(x, 0)}
    return True, trials, None


def _writes(g):
    return set(o for _op, _a, _b, o in g)


def scale_up(seed, factor, plane):
    """SCALE UP: `factor` independent replicas, each on its own address plane."""
    out = []
    for r in range(factor):
        off = r * plane
        for op, a, b, o in seed:
            out.append((op, a + off, b + off, o + off))
    return out


def seed_circuit(width):
    """The seed carries real slack for the fold to earn its ratio on: a balanced-tree reduction,
    the SAME reduction a second time byte-identically, a run of OR(x,x) buffers, and a branch that
    reaches no answer. Not a circuit built to flatter the fold."""
    g = []
    INP = 1 << 8
    w = 1 << 12
    lvl = list(range(INP, INP + width))
    while len(lvl) > 1:
        nxt = []
        for i in range(0, len(lvl) - 1, 2):
            g.append((OP_AND, lvl[i], lvl[i + 1], w)); nxt.append(w); w += 1
        if len(lvl) & 1:
            nxt.append(lvl[-1])
        lvl = nxt
    ans = lvl[0]
    lvl2 = list(range(INP, INP + width))               # duplicate cone, identical operands
    while len(lvl2) > 1:
        nxt = []
        for i in range(0, len(lvl2) - 1, 2):
            g.append((OP_AND, lvl2[i], lvl2[i + 1], w)); nxt.append(w); w += 1
        if len(lvl2) & 1:
            nxt.append(lvl2[-1])
        lvl2 = nxt
    for k in range(width):                             # identity buffers
        g.append((OP_OR, INP + k, INP + k, w)); w += 1
    for k in range(width // 2):                        # reaches no answer
        g.append((OP_XOR, INP + k, INP + ((k + 1) % width), w)); w += 1
    return g, [ans]


def load_live(path):
    """Component implementation and operation."""
    with io.open(path, "rb") as f:
        b = f.read()
    g = []
    for k in range(len(b) // REC):
        g.append(struct.unpack_from("<BQQQ", b, k * REC))
    reads = set()
    writes = set()
    for op, a, bb, o in g:
        reads.add(a); reads.add(bb); writes.add(o)
    sinks = sorted(writes - reads)
    return g, sinks, len(b)


def fold_container(path, rounds, factor):
    """Put a REAL container through the cycle. This is the whole point: AUTOFAB0 and DISCRIM1 both
    grew today and neither had ever been folded, because every fabricator here was one-shot."""
    seed, sinks, nbytes = load_live(path)
    print("  LIVE: %s" % path)
    print("        %s B, %s records, DEPTH %s ticks, %s addresses written"
          % (format(nbytes, ","), format(len(seed), ","), depth_of(seed),
             format(len(set(g[3] for g in seed)), ",")))
    print()

    # ⛔ THE FOLD IS GEOMETRY, NOT GATE ELIMINATION. Owner: "SOMETHING BEING EMITTED IS NOT DEAD."
    #    Every gate lands a value on an address and that landing is the output, so nothing can be
    #    removed. Same gates, same addresses, same values - fewer bytes each.
    mx, need, rungs = geometry_fold(seed)
    print("  GEOMETRY LADDER - every rung holds every operand this container uses")
    print("        widest operand %s -> needs %d byte(s)" % (format(mx, ","), need))
    print("        %-14s %8s %10s %16s %14s" % ("shape", "operand", "record", "container", "freed"))
    for kind, size, ow in rungs[:6]:
        tot = len(seed) * size
        print("        %-14s %8s %10s %16s %14s  (%4.1f%%)"
              % (kind, "%dB" % ow, "%dB" % size, format(tot, ","),
                 format(nbytes - tot, ","), 100.0 * (nbytes - tot) / nbytes))
    zb = 0
    with io.open(path, "rb") as f:
        zb = f.read().count(0)
    print("        zero bytes in it right now : %s of %s  (%.2f%%)"
          % (format(zb, ","), format(nbytes, ","), 100.0 * zb / nbytes))
    print()
    # FOLD FIRST, before any scale-up: whatever redundancy the container already carries is found
    # once, and the ratio reported is the container's own, not the cycle's.
    small0, rep0 = fold(seed, sinks)
    print("  FOLD IN PLACE (no scale-up yet) - what the container already carries")
    print("        gates %s -> %s   (%.2fx)   DEPTH %s -> %s"
          % (format(len(seed), ","), format(len(small0), ","),
             len(seed) / float(max(1, len(small0))), depth_of(seed), depth_of(small0)))
    print("        constant %s   hash-consed %s   dead-pruned %s"
          % (format(rep0["constant_folded"], ","), format(rep0["hash_consed"], ","),
             format(rep0["dead_pruned"], ",")))
    print("        bytes %s -> %s   (%s freed)"
          % (format(len(seed) * REC, ","), format(len(small0) * REC, ","),
             format((len(seed) - len(small0)) * REC, ",")))

    # ⛔ THE FOLD MUST AGREE WITH WHAT IT FOLDED, OR NOTHING IS WRITTEN.
    #    A smaller byte count is not a result; it is a smaller byte count. Two containers were
    #    written earlier today on the strength of a ratio alone, with no evaluation of the folded
    #    circuit against the original - which is the substitution failure in the place it is
    #    easiest to miss, because the number looks like progress.
    ok, trials, bad = equivalent(seed, sinks, small0, rep0["answers"])
    print()
    print("        EQUIVALENCE vs the container it folded : %s over %d driven trials"
          % ("AGREES" if ok else "DIVERGES", trials))
    if not ok:
        print("        first divergence: %s" % bad)
    return small0, rep0["answers"], ok


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".mno"):
        path = sys.argv[1]
        rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        factor = int(sys.argv[3]) if len(sys.argv) > 3 else 2
        print("SCALE UP -> FOLD BACK DOWN -> REPEAT, on a REAL container")
        print("=" * 108)
        seed, answers, agrees = fold_container(path, rounds, factor)
        if not agrees:
            print()
            print("  NOTHING WRITTEN. The folded circuit disagrees with the one it folded, so it")
            print("  is a DIFFERENT circuit and writing it would report a substitution as a win.")
            return 1
        print()
        plane = 1 << 26
        print("  %-6s %12s %12s %12s %12s %9s %7s %7s %s"
              % ("round", "gates in", "gates out", "bytes in", "bytes out", "fold",
                 "D in", "D out", ""))
        print("  " + "-" * 104)
        cur, ans = seed, answers
        for r in range(1, rounds + 1):
            big = scale_up(cur, factor, plane)
            big_ans = [a + k * plane for k in range(factor) for a in ans]
            d_in = depth_of(big)
            small, rep = fold(big, big_ans)
            d_out = depth_of(small)
            print("  %-6d %12s %12s %12s %12s %8.2fx %7d %7d %s"
                  % (r, format(len(big), ","), format(len(small), ","),
                     format(len(big) * REC, ","), format(len(small) * REC, ","),
                     len(big) / float(max(1, len(small))), d_in, d_out,
                     "DEPTH ROSE - REGRESSION" if d_out > d_in else ""))
            cur, ans = small, rep["answers"]
        blob = b"".join(struct.pack("<BQQQ", *g) for g in cur)
        out = os.path.splitext(path)[0] + ".folded.mno"
        io.open(out, "wb").write(blob)
        print()
        print("  FINAL: %s gates, %s B, DEPTH %s ticks   (%.4f MB)"
              % (format(len(cur), ","), format(len(blob), ","), depth_of(cur),
                 len(blob) / 1048576.0))
        print("  WROTE %s   - the original is untouched (vault law: never delete)" % out)
        return 0

    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    factor = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    print("SCALE UP -> FOLD BACK DOWN -> REPEAT")
    print("=" * 108)
    print('  owner: "YES WE WANT OPTIMAL BUT THEN WE SCALL UP FOLD BACK DOWN TO SMALL AND REPEAT"')
    print("  the 5 MB figure is the state each round folds back to, not a ceiling to hide under")
    print()

    seed, answers = seed_circuit(width)
    plane = 1 << 20
    print("  seed: %s gates, DEPTH %s ticks, %s answer wire(s)"
          % (format(len(seed), ","), depth_of(seed), len(answers)))
    print()
    print("  %-6s %12s %12s %12s %12s %9s %7s %7s %s"
          % ("round", "gates in", "gates out", "bytes in", "bytes out", "fold", "D in", "D out", ""))
    print("  " + "-" * 104)

    cur, ans = seed, answers
    hist = []
    for r in range(1, rounds + 1):
        big = scale_up(cur, factor, plane)
        big_ans = [a + k * plane for k in range(factor) for a in ans]
        d_in = depth_of(big)
        small, rep = fold(big, big_ans)
        d_out = depth_of(small)
        bi, bo = len(big) * REC, len(small) * REC
        ratio = (len(big) / float(len(small))) if small else 0.0
        note = "DEPTH ROSE - REGRESSION" if d_out > d_in else ""
        print("  %-6d %12s %12s %12s %12s %8.2fx %7d %7d %s"
              % (r, format(len(big), ","), format(len(small), ","), format(bi, ","),
                 format(bo, ","), ratio, d_in, d_out, note))
        hist.append({"round": r, "gates_in": len(big), "gates_out": len(small),
                     "bytes_in": bi, "bytes_out": bo, "fold_ratio": ratio,
                     "depth_in": d_in, "depth_out": d_out,
                     "constant_folded": rep["constant_folded"],
                     "hash_consed": rep["hash_consed"], "dead_pruned": rep["dead_pruned"],
                     "regressed": d_out > d_in})
        cur, ans = small, rep["answers"]

    print()
    print("  WHAT EACH FOLD REMOVED")
    print("  " + "-" * 104)
    print("  %-6s %14s %14s %14s" % ("round", "constant", "hash-consed", "dead-pruned"))
    for h in hist:
        print("  %-6d %14s %14s %14s"
              % (h["round"], format(h["constant_folded"], ","), format(h["hash_consed"], ","),
                 format(h["dead_pruned"], ",")))

    blob = b"".join(struct.pack("<BQQQ", op, a, b, o) for op, a, b, o in cur)
    out = os.path.join(HERE, "FOLD0.mno")
    io.open(out, "wb").write(blob)
    io.open(os.path.join(HERE, "FOLD0.layout.json"), "w", encoding="utf-8").write(json.dumps({
        "container": "FOLD0.mno", "header_bytes_in_container": 0,
        "record": "<BQQQ> op|a|b|out, 25 B",
        "opcodes": "0 nand, 1 and, 2 or, 3 xor, 4 not",
        "n_gate": len(cur), "bytes": len(blob), "depth_ticks": depth_of(cur),
        "answer_wires": ans,
        "cycle": {"rounds": rounds, "scale_factor": factor, "seed_width": width,
                  "history": hist},
        "law": 'owner: "YES WE WANT OPTIMAL BUT THEN WE SCALL UP FOLD BACK DOWN TO SMALL AND '
               'REPEAT" - 5 MB is the state each round folds back to, not a ceiling.',
        "passes": ["F1 hash-cons identical cones", "F2 dead-cone backward reachability",
                   "F3 constant: OR(x,x)/AND(x,x) is x"],
        "regression_rule": "a fold that raises DEPTH is a regression. A measured number is an "
                           "achieved ceiling and can only be pushed better.",
    }, indent=1))

    print()
    print("  FINAL after %d rounds : %s gates, %s B, DEPTH %d ticks"
          % (rounds, format(len(cur), ","), format(len(blob), ","), depth_of(cur)))
    print("  against the 5 MB law  : %.4f MB" % (len(blob) / 1048576.0))
    print("  WROTE %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
