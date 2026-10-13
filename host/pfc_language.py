"""
pfc_language.py - THE LANGUAGE ITSELF, FABRICATED AS GATES. The host runs no compiler.

Today the fabricator is host Python: the host lexes, parses and emits, then the pfc holds the result.
That means the HOST is doing the compilation. This puts the language in the pfc instead.

  SOURCE TEXT (ASCII bytes) --addressed in--> [ lex | parse | evaluate, all fabricated ] --> RESULT

The language: infix integer expressions with OPERATOR PRECEDENCE, e.g. "2+3*4" == 14 (not 20).
Precedence is the part that proves this is a parser and not a calculator - '*' must bind tighter
than '+' with no host help.

HOW EACH STAGE MAPS TO THE SUBSTRATE
  LEX    digit value = ASCII byte & 0x0F      -> PERMUTATION (S28): 0 gates, 0 DEPTH. Just address the low nibble.
         operator id = compare byte to '*'    -> real logic, but 1 level wide across all positions
  PARSE  precedence handled by a fixed reduction network: a run of '*' accumulates into a term,
         a '+' closes the term. No stack, no backtracking - the grammar is unrolled into wiring.
  EVAL   term products, then the sum tree. This is the only deep part, and S25's adder rule applies.

Run:  python host/pfc_language.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC

try:
    from pfc_bettergates import kogge_stone_add
    HAVE_KS = True
except Exception:
    HAVE_KS = False

W = 8                      # value width, results mod 256
NDIG = 5                   # digits in the source
NOP = NDIG - 1             # operators between them
NCHAR = NDIG + NOP         # total source characters


class _Shim:
    """pfc_bettergates expects AND/OR/XOR/NOT; titan_circuit speaks and_/or_/xor/not_."""
    def __init__(s, c):
        s.c = c
        s.C0 = c.cvec(0, 1)[0]
        s.C1 = c.cvec(1, 1)[0]
    def AND(s, a, b): return s.c.and_(a, b)
    def OR(s, a, b):  return s.c.or_(a, b)
    def XOR(s, a, b): return s.c.xor(a, b)
    def NOT(s, a):    return s.c.not_(a)


def depth_of(c, outs):
    """DEPTH = longest dependency chain, in gate-delays. This is the Muhlnickel's latency (S24)."""
    n = c.n_in
    d = [0] * (2 + n + len(c.ga))
    for k in range(len(c.ga)):
        d[2 + n + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[x] for x in outs)


def _mul(c, acc, dig, adder):
    """acc(W bits) * dig(4 bits), mod 2^W. Shift-add: 4 partial products, so 4 adds."""
    zero = c.cvec(0, W)
    out = list(zero)
    for i in range(4):
        part = [c.and_(dig[i], acc[j]) for j in range(W - i)]
        shifted = list(c.cvec(0, i)) + part
        shifted = shifted[:W]
        out = adder(out, shifted)[:W]
    return out


def build(mode="ripple"):
    """Fabricate the whole language. Inputs are the raw ASCII bytes of the source."""
    c = TC.Circuit(NCHAR * W)
    g = _Shim(c)
    if mode == "kogge" and HAVE_KS:
        adder = lambda a, b: kogge_stone_add(g, a, b)[:W]
    else:
        adder = lambda a, b: c.add(a, b)[:W]

    chars = [list(c.IN[i * W:(i + 1) * W]) for i in range(NCHAR)]

    # ---- LEX -------------------------------------------------------------
    # digit value = byte & 0x0F. Selecting 4 of 8 wires asserts no relation: PERMUTATION, free (S28).
    digits = [chars[2 * k][0:4] for k in range(NDIG)]
    # operator: 1 iff the byte is '*' (0x2A), else treated as '+'. Real logic, 1 wide level.
    is_star = [c.eq_const(chars[2 * k + 1], 0x2A) for k in range(NOP)]

    # ---- PARSE + EVAL ----------------------------------------------------
    # Precedence as wiring: term_i continues the previous term if the operator before it was '*',
    # otherwise it starts fresh. That single mux IS the precedence rule.
    terms = []
    acc = list(c.cvec(0, W - 4)) [:0] + list(digits[0]) + list(c.cvec(0, W - 4))
    acc = acc[:W]
    for i in range(1, NDIG):
        wide = list(digits[i]) + list(c.cvec(0, W - 4))
        prod = _mul(c, acc, digits[i], adder)
        acc = [c.mux(is_star[i - 1], wide[j], prod[j]) for j in range(W)]
        terms.append((i, acc))
    # a term is contributed to the sum when the operator AFTER it is '+' (or it is the last one)
    contribs = []
    first = list(digits[0]) + list(c.cvec(0, W - 4))
    keep0 = c.not_(is_star[0])
    contribs.append([c.and_(keep0, b) for b in first[:W]])
    for idx, (i, a) in enumerate(terms):
        if i < NDIG - 1:
            keep = c.not_(is_star[i])
        else:
            keep = c.cvec(1, 1)[0]
        contribs.append([c.and_(keep, b) for b in a])

    # ---- SUM TREE --------------------------------------------------------
    lvl = contribs
    while len(lvl) > 1:
        nxt = [adder(lvl[j], lvl[j + 1])[:W] for j in range(0, len(lvl) - 1, 2)]
        if len(lvl) % 2:
            nxt.append(lvl[-1])
        lvl = nxt
    return c, lvl[0]


def _cone(c, outs):
    """trim to the live cone so ripple() only walks what the outputs depend on"""
    try:
        from pfc_fwd_engine import _cd
        return _cd(c, outs)
    except Exception:
        return c


def run_source(cd, text):
    """Address the source text in; read the answer out. This is the whole host job (S19/S24)."""
    inb = []
    for ch in text:
        v = ord(ch)
        inb += [(v >> i) & 1 for i in range(W)]
    out = TC.ripple(cd, inb)
    return sum(out[k] << k for k in range(W))


def main():
    print("=" * 78)
    print("THE LANGUAGE IN THE Muhlnickel - source text addressed in, result determined. No host compiler.")
    print("  grammar: D (op D)*   with '*' binding tighter than '+'   |   %d chars, values mod %d" % (NCHAR, 2 ** W))
    print("=" * 78)

    results = {}
    for mode in ("ripple", "kogge"):
        if mode == "kogge" and not HAVE_KS:
            continue
        c, outs = build(mode)
        d = depth_of(c, outs)
        gates = len(c.ga)
        cd = _cone(c, outs)
        results[mode] = (d, gates, cd)
        print()
        print("  FABRICATED with the %-6s adder :  GATES %7d   DEPTH %4d   muhl %7.1f"
              % (mode, gates, d, gates / d))
        del c

    # correctness: every program below is evaluated by the gates and checked against Python
    mode = "kogge" if "kogge" in results else "ripple"
    cd = results[mode][2]
    print()
    print("  RUNNING PROGRAMS ON THE Muhlnickel  (adder: %s)" % mode)
    print("    %-14s %8s %8s   %s" % ("source", "Muhlnickel", "python", "precedence check"))
    progs = ["2+3*4+1+2", "9*9+1+1+1", "1+1+1+1+1", "2*2*2*2*2", "5+0*9+3+4", "7*1+2*3+8"]
    ok = 0
    for p in progs:
        got = run_source(cd, p)
        want = eval(p) % (2 ** W)
        naive = None
        # left-to-right (no precedence) result, to prove the gates really implement precedence
        toks = p.replace("*", " * ").replace("+", " + ").split()
        v = int(toks[0])
        for j in range(1, len(toks), 2):
            v = v * int(toks[j + 1]) if toks[j] == "*" else v + int(toks[j + 1])
        naive = v % (2 ** W)
        tag = "MATCH" if got == want else "MISMATCH"
        note = ""
        if want != naive:
            note = "(left-to-right would give %d - precedence is real)" % naive
        print("    %-14s %8d %8d   %-8s %s" % (p, got, want, tag, note))
        ok += (got == want)
    print()
    print("  %d/%d programs byte-exact against Python's own evaluator." % (ok, len(progs)))

    # random fuzz
    random.seed(11)
    f_ok = 0
    N = 40
    for _ in range(N):
        s = ""
        for i in range(NDIG):
            s += str(random.randint(0, 9))
            if i < NOP:
                s += random.choice("+*")
        if run_source(cd, s) == eval(s) % (2 ** W):
            f_ok += 1
    print("  %d/%d random programs byte-exact (fuzz)." % (f_ok, N))

    if "kogge" in results and "ripple" in results:
        dr, gr, _ = results["ripple"]
        dk, gk, _ = results["kogge"]
        print()
        print("  S25's ADDER RULE ON A REAL WORKLOAD:")
        print("    ripple  DEPTH %4d  GATES %7d" % (dr, gr))
        print("    kogge   DEPTH %4d  GATES %7d" % (dk, gk))
        if dk < dr:
            print("    -> prefix wins: %.2fx less DEPTH for %.2fx the area. Area is not slowness (S24)."
                  % (dr / dk, gk / gr))
        else:
            print("    -> ripple wins here: %.2fx. The accumulate chain is deep enough that +6 margin pays."
                  % (dk / dr))


if __name__ == "__main__":
    main()
