#!/usr/bin/env python3
"""muhl_reason.py — the SEED OF TITAN'S REASONING CORE, fabricated as gates on the Muhlnickel substrate.

Reasoning as PURE VERIFIED COMPUTATION. Not prediction, not averaging over an embedding cloud where
true and false sit at cosine +0.533 (smeared together). Here a propositional formula is DECIDED by a
netlist of AND/OR/XOR/NOT gates, and TRUTH IS PRESERVED BY CONSTRUCTION: a proposition and its negation
are wired to OPPOSITE outputs on every single input, exhaustively — true and false are FAR APART because
the physics of the gates make them so, not because a loss function nudged them apart.

Everything below is built with the White Box compiler (sdc_cc.CircuitCompiler), dead-code-eliminated,
rippled, and VERIFIED BYTE-EXACT against an independent pure-Python reference. No numpy. titan.gguf untouched.

Contents:
  1. SAT-CLAUSE EVALUATOR (general)  — inputs: a truth assignment + a formula ENCODED AS DATA
     (M 3-literal clauses over K variables, each literal = one-hot variable selector + polarity bit).
     The circuit outputs one bit: is the formula satisfied by the assignment?  Verified byte-exact over
     random formulas x random assignments.
  2. DECISION / PROOF-CHECK        — bake a FIXED formula in as constants; address every assignment
     (sweep all 2^K) through the gates to DECIDE satisfiability, and CHECK a proof step (a claimed
     satisfying witness) — all vs an independent brute-force reference.
  3. TRUTH PRESERVATION            — build a NOT/consistency gate on the decision output and prove,
     EXHAUSTIVELY over all 2^K inputs, that sat and NOT-sat are ALWAYS opposite (separation = 1 bit,
     the maximum for a bit). Lift to a W-bit truth code where TRUE and its negation are ANTIPODAL
     (cosine = -1) on every input — the opposite of trained embeddings' +0.533.
"""
import sys, os, random, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
sys.path.insert(0, r"C:/llm/muhl_builds")
import sdc_cc as CC
from muhl_flex import bit, rd, setf, muxw           # existing verified helpers

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


# ============================================================================
# 1. GENERAL SAT-CLAUSE EVALUATOR  (formula supplied AS DATA)
# ============================================================================
# Encoding of ONE literal over K variables:  K one-hot "selector" bits pick which
# variable, then 1 "polarity" bit (0 = positive literal x_i, 1 = negated literal ~x_i).
#   selected_var = OR_i ( sel[i] AND assign[i] )        (one-hot read of the assignment)
#   literal_true = selected_var XOR polarity            (XOR flips it iff negated)
# A clause of 3 literals is satisfied = OR of the three literal_true.
# The formula (CNF) is satisfied = AND over all clauses.  ALL of this is gates.

def build_sat_evaluator(K, M):
    """General evaluator: inputs = assignment(K) then M clauses x 3 literals x (K sel + 1 pol)."""
    LIT = K + 1                                        # bits per literal
    n_in = K + M * 3 * LIT
    g = CC.CircuitCompiler(n_in); IN = g.IN
    assign = [IN[i] for i in range(K)]

    def lit_base(c, l): return K + (c * 3 + l) * LIT
    def literal_true(c, l):
        b = lit_base(c, l)
        sel = [IN[b + i] for i in range(K)]
        pol = IN[b + K]
        var = g.C0
        for i in range(K):
            var = g.OR(var, g.AND(sel[i], assign[i]))  # one-hot read
        return g.XOR(var, pol)                         # flip iff negated

    sat = g.C1                                          # AND-accumulate over clauses
    for c in range(M):
        clause = g.C0
        for l in range(3):
            clause = g.OR(clause, literal_true(c, l))   # OR over 3 literals
        sat = g.AND(sat, clause)

    gates, out2 = g.dce([sat])
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return g, run, out2[0], gates, n_in, LIT


def ref_eval(K, assign, clauses):
    """Independent reference. clauses = list of 3-lists of (var_index, polarity)."""
    for cl in clauses:
        if not any(assign[vi] ^ pol for (vi, pol) in cl):
            return 0
    return 1


def rand_clauses(K, M, rng):
    return [[(rng.randrange(K), rng.randrange(2)) for _ in range(3)] for _ in range(M)]


def pack_inputs(K, M, LIT, assign, clauses):
    n_in = K + M * 3 * LIT
    inp = [0] * n_in
    for i in range(K): inp[i] = assign[i] & 1
    for c in range(M):
        for l in range(3):
            vi, pol = clauses[c][l]
            b = K + (c * 3 + l) * LIT
            inp[b + vi] = 1                             # one-hot selector
            inp[b + K] = pol
    return inp


def part1_general(K=5, M=6, cases=800):
    print(f"\n[1] GENERAL SAT-CLAUSE EVALUATOR  (K={K} vars, M={M} clauses, formula supplied as data)")
    g, run, sat_w, gates, n_in, LIT = build_sat_evaluator(K, M)
    rng = random.Random(2026)
    ok = True; nsat = 0
    for _ in range(cases):
        assign = [rng.randrange(2) for _ in range(K)]
        clauses = rand_clauses(K, M, rng)
        inp = pack_inputs(K, M, LIT, assign, clauses)
        got = bit(run(inp, 1), sat_w)
        exp = ref_eval(K, assign, clauses)
        nsat += exp
        if got != exp: ok = False; print("   MISMATCH", assign, clauses); break
    print(f"    inputs={n_in} bits   gates={len(gates):,}   depth-limited straight-line netlist")
    print(f"    byte-exact vs Python over {cases} random (formula,assignment) pairs : {ok}  "
          f"({nsat} satisfied / {cases-nsat} not)")
    return ok


# ============================================================================
# 2. DECISION / PROOF-CHECK  (FIXED formula baked as constants, address assignments)
# ============================================================================
# With the formula fixed at build time, each literal's variable & polarity are known,
# so literal_true is just assign[vi] or NOT(assign[vi]).  Only the K assignment bits are
# inputs.  We then ADDRESS every one of the 2^K assignments through the gates: OR of all
# outputs => the formula is SATISFIABLE.  Checking a specific witness is one addressing.

def build_fixed(K, clauses, with_truthword=True, W=16):
    g = CC.CircuitCompiler(K); IN = g.IN
    assign = [IN[i] for i in range(K)]
    sat = g.C1
    for cl in clauses:
        clause = g.C0
        for (vi, pol) in cl:
            lit = g.NOT(assign[vi]) if pol else assign[vi]
            clause = g.OR(clause, lit)
        sat = g.AND(sat, clause)

    # --- truth-preservation apparatus (part 3) built on the SAME decision output ---
    notsat = g.NOT(sat)                                # the negation gate
    sep    = g.XOR(sat, notsat)                        # consistency: must be 1 for ALL inputs
    outs = [sat, notsat, sep]
    tw_true = tw_false = None
    if with_truthword:
        # W-bit "truth code": TRUE -> all ones, FALSE (its negation) -> all zeros.
        tw_true  = muxw(g, sat,    [g.C1] * W, [g.C0] * W)   # code of the proposition
        tw_false = muxw(g, notsat, [g.C1] * W, [g.C0] * W)   # code of its negation
        outs += tw_true + tw_false

    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    idx = {"sat": out2[0], "notsat": out2[1], "sep": out2[2]}
    if with_truthword:
        idx["tw_true"]  = out2[3:3 + W]
        idx["tw_false"] = out2[3 + W:3 + 2 * W]
    return g, run, idx, gates


def decide_sat_by_circuit(K, clauses, run, idx):
    """Address all 2^K assignments; OR the sat outputs."""
    witnesses = []
    for a in range(1 << K):
        assign = [(a >> i) & 1 for i in range(K)]
        v = run(assign, 1)
        if bit(v, idx["sat"]):
            witnesses.append(assign)
    return (len(witnesses) > 0), witnesses


def brute_sat(K, clauses):
    for a in range(1 << K):
        assign = [(a >> i) & 1 for i in range(K)]
        if ref_eval(K, assign, clauses):
            return True, assign
    return False, None


def part2_decision():
    print(f"\n[2] DECISION & PROOF-CHECK  (fixed formula baked as constant gates)")
    ok = True

    # (a) a SATISFIABLE formula over K=4
    K = 4
    sat_formula = [
        [(0, 0), (1, 1), (2, 0)],   # x0 OR ~x1 OR x2
        [(1, 0), (2, 1), (3, 0)],   # x1 OR ~x2 OR x3
        [(0, 1), (3, 1), (2, 0)],   # ~x0 OR ~x3 OR x2
        [(3, 0), (0, 0), (1, 0)],   # x3 OR x0 OR x1
    ]
    g, run, idx, gates = build_fixed(K, sat_formula)
    cyes, cwit = decide_sat_by_circuit(K, sat_formula, run, idx)
    byes, bwit = brute_sat(K, sat_formula)
    m = (cyes == byes)
    print(f"    formula A (4 clauses/4 vars): circuit says SAT={cyes} · brute-force SAT={byes} · match={m}")
    print(f"        {len(gates)} gates · witnesses found by addressing: {len(decide_sat_by_circuit(K, sat_formula, run, idx)[1])}")
    ok &= m

    # proof-step check: feed a claimed witness, the circuit must certify it
    if cwit:
        w = cwit[0]
        v = run(w, 1)
        certified = bit(v, idx["sat"])
        indep = ref_eval(K, w, sat_formula)
        print(f"        proof step: assignment {w} claimed to satisfy A -> circuit certifies={certified}, ref={indep}")
        ok &= (certified == 1 == indep)
        # a NON-witness must be rejected
        bad = [1 - b for b in w]
        while ref_eval(K, bad, sat_formula):            # ensure it's actually a non-model
            bad = [random.randrange(2) for _ in range(K)]
        rej = bit(run(bad, 1), idx["sat"])
        print(f"        counter-check: non-model {bad} -> circuit certifies={rej} (must be 0)  ok={rej==0}")
        ok &= (rej == 0)

    # (b) a provably UNSAT formula: all 8 polarity patterns over 3 variables
    K3 = 3
    unsat_formula = [[(0, (a >> 0) & 1), (1, (a >> 1) & 1), (2, (a >> 2) & 1)] for a in range(8)]
    g2, run2, idx2, gates2 = build_fixed(K3, unsat_formula)
    cyes2, _ = decide_sat_by_circuit(K3, unsat_formula, run2, idx2)
    byes2, _ = brute_sat(K3, unsat_formula)
    m2 = (cyes2 == byes2 == False)
    print(f"    formula B (all 8 clauses/3 vars, classic UNSAT): circuit SAT={cyes2} · brute={byes2} · "
          f"correctly UNSAT={m2}  ({len(gates2)} gates)")
    ok &= m2
    return ok


# ============================================================================
# 3. TRUTH PRESERVATION  (true != false, ALWAYS, by construction)
# ============================================================================
def part3_truth_preservation():
    print(f"\n[3] TRUTH PRESERVATION  —  true and its negation map to OPPOSITE outputs, exhaustively")
    K = 4
    W = 16
    formula = [
        [(0, 0), (1, 1), (2, 0)],
        [(1, 0), (2, 1), (3, 0)],
        [(0, 1), (3, 1), (2, 0)],
        [(3, 0), (0, 0), (1, 0)],
    ]
    g, run, idx, gates = build_fixed(K, formula, with_truthword=True, W=W)

    all_sep_one = True          # sat XOR notsat == 1 for every input?
    all_eval_ok = True          # sat matches independent reference?
    all_hamming_max = True      # W-bit true-code vs false-code differ in ALL W bits?
    all_antipodal = True        # +/-1 interpretation => cosine exactly -1?
    seen_true = seen_false = False

    for a in range(1 << K):
        assign = [(a >> i) & 1 for i in range(K)]
        v = run(assign, 1)
        sat    = bit(v, idx["sat"])
        notsat = bit(v, idx["notsat"])
        sep    = bit(v, idx["sep"])
        exp    = ref_eval(K, assign, formula)

        if sat != exp: all_eval_ok = False
        if sep != 1:   all_sep_one = False              # <-- the core: never equal
        if sat == notsat: all_sep_one = False
        seen_true |= (sat == 1); seen_false |= (sat == 0)

        tw_true  = [bit(v, w) for w in idx["tw_true"]]
        tw_false = [bit(v, w) for w in idx["tw_false"]]
        ham = sum(x ^ y for x, y in zip(tw_true, tw_false))
        if ham != W: all_hamming_max = False
        # interpret bits as +/-1 vectors; cosine of antipodal codes = -1
        u = [1 if x else -1 for x in tw_true]
        w_ = [1 if x else -1 for x in tw_false]
        dot = sum(p * q for p, q in zip(u, w_))
        nrm = (sum(p * p for p in u) * sum(q * q for q in w_)) ** 0.5
        cos = dot / nrm
        if abs(cos - (-1.0)) > 1e-12: all_antipodal = False

    print(f"    over all 2^{K}={1<<K} assignments (both TRUE and FALSE outputs occur: {seen_true and seen_false})")
    print(f"      - sat matches independent evaluator                : {all_eval_ok}")
    print(f"      - consistency gate  sat XOR (NOT sat) == 1  ALWAYS  : {all_sep_one}   (true != false, no exceptions)")
    print(f"      - W={W} truth-code Hamming(TRUE, negation) == {W} always: {all_hamming_max}   (separation is MAXIMAL)")
    print(f"      - +/-1 interpretation => cosine(TRUE, negation) = -1 : {all_antipodal}")
    print(f"    contrast: in trained embeddings cos(true,false) = +0.533 (smeared); here it is -1 BY CONSTRUCTION.")

    # standalone 1-variable consistency gate, fully exhaustive (the atom of the property)
    ga = CC.CircuitCompiler(1); b = ga.IN[0]
    nb = ga.NOT(b); sep = ga.XOR(b, nb)
    gts, o2 = ga.dce([b, nb, sep]); runa = ga.compile_ripple(gts, 2 + 1 + len(gts))
    atom_ok = all(bit(runa([x], 1), o2[2]) == 1 and
                  bit(runa([x], 1), o2[0]) != bit(runa([x], 1), o2[1]) for x in (0, 1))
    print(f"    atomic NOT/consistency gate:  b vs NOT b opposite for both b in {{0,1}} : {atom_ok}  ({len(gts)} gates)")

    return all_sep_one and all_eval_ok and all_hamming_max and all_antipodal and atom_ok


def main():
    t0 = time.time()
    print("=" * 78)
    print(" TITAN REASONING CORE (seed) — propositional logic DECIDED as gates, truth PRESERVED")
    print("=" * 78)
    r1 = part1_general()
    r2 = part2_decision()
    r3 = part3_truth_preservation()
    print("\n" + "=" * 78)
    print(f" RESULT: eval byte-exact={r1} · decision/proof correct={r2} · truth-preserving={r3}")
    allok = r1 and r2 and r3
    print(f" {'ALL VERIFIED — reasoning is computed and truth is preserved, not predicted.' if allok else 'FAILURE'}")
    print(f" [done] {time.time()-t0:.2f}s · no numpy · titan.gguf untouched")
    print("=" * 78)
    return allok


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
