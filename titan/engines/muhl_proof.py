#!/usr/bin/env python3
"""muhl_proof.py -- THE PROOF CHECKER, fabricated as gates on the Muhlnickel substrate.

The seed of Titan's reasoning core. Reasoning as PURE VERIFIED COMPUTATION: an inference
step is not PREDICTED (the way a trained model would, where `true` and `false` sit at cosine
+0.533 -- smeared into the same grammatical slot), it is COMPUTED by a netlist of AND/OR/XOR/NOT
gates and CHECKED byte-exact against an independent reference. Truth is preserved by construction.

Two gates:

  (a) RESOLUTION / MODUS-PONENS STEP VERIFIER.  Two clauses over K boolean variables are supplied
      AS DATA (per variable: a `pos` bit = literal x_i present, a `neg` bit = literal !x_i present).
      One fixed circuit outputs the RESOLVENT (pos/neg bits of the derived clause) and a VALIDITY bit
      (a binary resolution step is valid iff the two clauses have EXACTLY ONE complementary pair).
      Modus ponens  p, p->q |- q  IS resolution: {p} resolved with {!p, q} on p yields {q}.
      Verified byte-exact vs Python EXHAUSTIVELY over every pair of well-formed clauses.

  (b) PROPOSITIONAL TRUTH-TABLE DECIDER (a fabricated SAT/TAUT checker).  A fixed theorem is baked
      into a circuit; every one of the 2^K assignments is ADDRESSED through the gates by exhaustive
      evaluation.  A TAUTOLOGY evaluates TRUE on ALL 2^K assignments; a CONTRADICTION FALSE on ALL.
      Truth is COMPUTED and PRESERVED -- a proposition and its negation land on OPPOSITE outputs for
      every assignment (separation = 1 bit, the maximum), the antithesis of the +0.533 embedding fact.

Built with the White Box compiler (sdc_cc.CircuitCompiler), dead-code-eliminated, rippled, and
verified byte-exact against a pure-Python reference. PYTHONUTF8, no numpy, titan.gguf untouched.
"""
import sys, os
sys.path.insert(0, r"C:/llm/sdc_sandbox")
sys.path.insert(0, r"C:/llm/muhl_builds")
import sdc_cc as CC
from muhl_flex import bit, add_bits            # existing verified helpers

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


# ============================================================================
# gate helpers
# ============================================================================
def popcount(g, bits):
    """sum of a bit list -> SB-bit magnitude (ripple-carry accumulation)."""
    SB = max(1, len(bits).bit_length())
    acc = [g.C0] * SB
    for b in bits:
        acc, _ = add_bits(g, acc, [b] + [g.C0] * (SB - 1))
    return acc

def eq_one(g, acc):
    """acc == 1  (bit0 set, all higher bits clear)."""
    r = acc[0]
    for b in acc[1:]:
        r = g.AND(r, g.NOT(b))
    return r


# ============================================================================
# (a) RESOLUTION / MODUS-PONENS STEP VERIFIER  (two clauses supplied as data)
# ============================================================================
# Clause encoding over K vars: pos[i]=1 iff literal x_i is in the clause,
#                              neg[i]=1 iff literal !x_i is in the clause.
# Inputs = pos1[K], neg1[K], pos2[K], neg2[K]  (4K bits).
# clash[i] = the clause pair is complementary on variable i.
# valid    = EXACTLY ONE clash  (binary resolution derives a single-pivot resolvent).
# resolvent[i] = union of the two clauses' literals on i, with the pivot literals removed.
def build_resolution(K):
    g = CC.CircuitCompiler(4 * K); IN = g.IN
    pos1 = IN[0:K]; neg1 = IN[K:2 * K]; pos2 = IN[2 * K:3 * K]; neg2 = IN[3 * K:4 * K]

    clash = [g.OR(g.AND(pos1[i], neg2[i]), g.AND(neg1[i], pos2[i])) for i in range(K)]
    valid = eq_one(g, popcount(g, clash))
    # remove the pivot variable from the resolvent (clash[i]==1 only at the unique pivot when valid)
    pos_res = [g.AND(g.OR(pos1[i], pos2[i]), g.NOT(clash[i])) for i in range(K)]
    neg_res = [g.AND(g.OR(neg1[i], neg2[i]), g.NOT(clash[i])) for i in range(K)]

    outs = pos_res + neg_res + [valid]
    gates, out2 = g.dce(outs)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    idx = {"pos_res": out2[0:K], "neg_res": out2[K:2 * K], "valid": out2[2 * K]}
    return g, run, idx, gates


def ref_resolve(K, c1, c2):
    """Independent reference. c=(pos,neg), each a K-tuple of {0,1}."""
    p1, n1 = c1; p2, n2 = c2
    clash = [(p1[i] & n2[i]) | (n1[i] & p2[i]) for i in range(K)]
    valid = 1 if sum(clash) == 1 else 0
    pos_res = [(p1[i] | p2[i]) & (1 - clash[i]) for i in range(K)]
    neg_res = [(n1[i] | n2[i]) & (1 - clash[i]) for i in range(K)]
    return pos_res, neg_res, valid


def all_clauses(K):
    """Every WELL-FORMED clause over K vars (each var: absent / positive / negative) -> 3^K clauses."""
    out = []
    def rec(i, pos, neg):
        if i == K: out.append((tuple(pos), tuple(neg))); return
        rec(i + 1, pos + [0], neg + [0])   # var i absent
        rec(i + 1, pos + [1], neg + [0])   # positive literal x_i
        rec(i + 1, pos + [0], neg + [1])   # negative literal !x_i
    rec(0, [], [])
    return out


def pack_clausepair(K, c1, c2):
    p1, n1 = c1; p2, n2 = c2
    return list(p1) + list(n1) + list(p2) + list(n2)


def clause_str(K, pos, neg):
    lits = []
    for i in range(K):
        if pos[i]: lits.append(f"x{i}")
        if neg[i]: lits.append(f"!x{i}")
    return "{" + ", ".join(lits) + "}" if lits else "{} (empty = FALSE)"


def part_a(K=4):
    print(f"\n[a] RESOLUTION / MODUS-PONENS STEP VERIFIER  (two clauses over K={K} vars, supplied as data)")
    g, run, idx, gates = build_resolution(K)
    print(f"    inputs = {4*K} bits (pos1,neg1,pos2,neg2)   fabricated gates = {len(gates):,}")

    # EXHAUSTIVE byte-exact check over every pair of well-formed clauses
    clauses = all_clauses(K)
    ok = True; nvalid = 0; ntot = 0
    for c1 in clauses:
        for c2 in clauses:
            inp = pack_clausepair(K, c1, c2)
            v = run(inp, 1)
            gp = [bit(v, w) for w in idx["pos_res"]]
            gn = [bit(v, w) for w in idx["neg_res"]]
            gv = bit(v, idx["valid"])
            rp, rn, rv = ref_resolve(K, c1, c2)
            ntot += 1; nvalid += rv
            if gp != rp or gn != rn or gv != rv:
                ok = False
                print("    MISMATCH", c1, c2, (gp, gn, gv), (rp, rn, rv)); break
        if not ok: break
    print(f"    byte-exact vs Python over ALL {ntot:,} clause pairs ({len(clauses)} x {len(clauses)}): {ok}")
    print(f"    valid single-pivot resolution steps among them: {nvalid:,}")

    # CONCRETE MODUS PONENS:  p, p->q  |-  q   (x0=p, x1=q ; p->q == {!p, q})
    c_p    = ((1, 0, 0, 0), (0, 0, 0, 0))    # {p}
    c_pimq = ((0, 1, 0, 0), (1, 0, 0, 0))    # {!p, q}
    inp = pack_clausepair(K, c_p, c_pimq); v = run(inp, 1)
    gp = [bit(v, w) for w in idx["pos_res"]]; gn = [bit(v, w) for w in idx["neg_res"]]; gv = bit(v, idx["valid"])
    print(f"    modus ponens:  {clause_str(K,*c_p)} resolved with {clause_str(K,*c_pimq)}")
    print(f"                -> resolvent {clause_str(K, gp, gn)}   valid={gv}   (expected {{x1}}, valid=1)")
    mp_ok = (gv == 1 and gp == [0, 1, 0, 0] and gn == [0, 0, 0, 0])
    return ok and mp_ok


# ============================================================================
# (b) PROPOSITIONAL TRUTH-TABLE DECIDER  (fixed theorem baked, all 2^K addressed)
# ============================================================================
# A formula is an AST of tuples: ('var',i) ('const',b) ('not',a)
#   ('and',a,b) ('or',a,b) ('imp',a,b)  (a->b == !a|b)   ('iff',a,b) (a<->b == !(a^b)).
def nvars(ast):
    t = ast[0]
    if t == "var": return ast[1] + 1
    if t == "const": return 0
    if t == "not": return nvars(ast[1])
    return max(nvars(ast[1]), nvars(ast[2]))

def emit(g, ast, IN):
    t = ast[0]
    if t == "var":   return IN[ast[1]]
    if t == "const": return g.C1 if ast[1] else g.C0
    if t == "not":   return g.NOT(emit(g, ast[1], IN))
    a = emit(g, ast[1], IN)
    if t == "and":   return g.AND(a, emit(g, ast[2], IN))
    if t == "or":    return g.OR(a, emit(g, ast[2], IN))
    if t == "imp":   return g.OR(g.NOT(a), emit(g, ast[2], IN))
    if t == "iff":   return g.NOT(g.XOR(a, emit(g, ast[2], IN)))
    raise ValueError(t)

def py_eval(ast, asn):
    t = ast[0]
    if t == "var":   return asn[ast[1]]
    if t == "const": return ast[1]
    if t == "not":   return 1 - py_eval(ast[1], asn)
    a = py_eval(ast[1], asn)
    if t == "and":   return a & py_eval(ast[2], asn)
    if t == "or":    return a | py_eval(ast[2], asn)
    if t == "imp":   return (1 - a) | py_eval(ast[2], asn)
    if t == "iff":   return 1 - (a ^ py_eval(ast[2], asn))
    raise ValueError(t)

# AST constructors
def V(i): return ("var", i)
def N(a): return ("not", a)
def A(a, b): return ("and", a, b)
def O(a, b): return ("or", a, b)
def I(a, b): return ("imp", a, b)
def F(a, b): return ("iff", a, b)

P, Q, R = V(0), V(1), V(2)

THEOREMS = [
    ("excluded middle        p | !p",                       O(P, N(P))),
    ("modus ponens (taut)    (p & (p->q)) -> q",            I(A(P, I(P, Q)), Q)),
    ("Peirce's law           ((p->q)->p) -> p",             I(I(I(P, Q), P), P)),
    ("hypothetical syllogism ((p->q)&(q->r)) -> (p->r)",    I(A(I(P, Q), I(Q, R)), I(P, R))),
    ("De Morgan              !(p&q) <-> (!p | !q)",          F(N(A(P, Q)), O(N(P), N(Q)))),
    ("contradiction          p & !p",                       A(P, N(P))),
    ("self-negation          p <-> !p",                     F(P, N(P))),
    ("contingent             p -> q",                       I(P, Q)),
]

def build_theorem(ast):
    K = max(1, nvars(ast))
    g = CC.CircuitCompiler(K)
    out = emit(g, ast, g.IN)
    gates, out2 = g.dce([out])
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    return run, out2[0], gates, K

def part_b():
    print(f"\n[b] PROPOSITIONAL TRUTH-TABLE DECIDER  (each theorem baked as gates, all 2^K assignments addressed)")
    all_ok = True; total_gates = 0
    for name, ast in THEOREMS:
        run, outw, gates, K = build_theorem(ast)
        total_gates += len(gates)
        trues = 0; ok = True
        for a in range(1 << K):
            asn = [(a >> i) & 1 for i in range(K)]
            gv = bit(run(asn, 1), outw)
            ev = py_eval(ast, asn)
            if gv != ev: ok = False; break
            trues += gv
        n = 1 << K
        verdict = "TAUTOLOGY   (TRUE on all)" if trues == n else \
                  "CONTRADICTION (FALSE on all)" if trues == 0 else \
                  f"CONTINGENT  (TRUE on {trues}/{n})"
        all_ok = all_ok and ok
        flag = "" if ok else "   <-- BYTE MISMATCH"
        print(f"    {name:52s}  {gates and len(gates):>4} g  K={K}  {trues:>2}/{n:<2} true  {verdict}{flag}")
    print(f"    (fabricated {total_gates:,} gates total across the {len(THEOREMS)} theorems; every one byte-exact vs Python: {all_ok})")
    return all_ok

def part_c():
    """TRUTH PRESERVED BY CONSTRUCTION: a tautology and its negation are ANTIPODAL on every assignment."""
    print(f"\n[c] TRUTH IS COMPUTED, NOT PREDICTED  (the contrast with trained embeddings)")
    name, ast = THEOREMS[3]                              # hypothetical syllogism (a tautology)
    K = max(1, nvars(ast))
    g = CC.CircuitCompiler(K)
    T = emit(g, ast, g.IN)                               # the theorem
    notT = g.NOT(T)                                      # its negation
    sep = g.XOR(T, notT)                                 # separation (must be 1 for ALL assignments)
    gates, out2 = g.dce([T, notT, sep])
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    tw, ntw, sw = out2
    min_T = 1; max_notT = 0; sep_all_one = True
    for a in range(1 << K):
        asn = [(a >> i) & 1 for i in range(K)]
        v = run(asn, 1)
        min_T = min(min_T, bit(v, tw)); max_notT = max(max_notT, bit(v, ntw))
        if bit(v, sw) != 1: sep_all_one = False
    print(f"    theorem: {name.split('  ')[0].strip()}   fabricated {len(gates)} gates")
    print(f"    over ALL {1<<K} assignments:  TRUE-formula min = {min_T} (always 1),  its negation max = {max_notT} (always 0)")
    print(f"    separation XOR(true, !true) == 1 on every assignment: {sep_all_one}   (= 1 bit, the MAXIMUM for a bit)")
    print(f"    -> true and false are ANTIPODAL because the GATES make them so, computed and preserved.")
    print(f"       Contrast the device's trained SmolLM2 token_embd: true/false cosine = +0.533 (opposites SMEARED")
    print(f"       into one grammatical slot). A predictor minimizes surprise; this reasoner preserves the distinction.")
    return (min_T == 1 and max_notT == 0 and sep_all_one)


def main():
    print("MUHLNICKEL PROOF CHECKER -- the seed of Titan's reasoning core (fabricated, verified byte-exact)")
    a = part_a()
    b = part_b()
    c = part_c()
    ok = a and b and c
    print(f"\n[done] resolution verifier: {'PASS' if a else 'FAIL'} · truth-table decider: {'PASS' if b else 'FAIL'} · "
          f"truth-preservation: {'PASS' if c else 'FAIL'} · no numpy · titan.gguf untouched.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
