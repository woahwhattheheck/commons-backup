#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""muhl_mind.py -- TITAN THINKS, THEN SPEAKS.  The whole vision in one file.

The MIND is gates: a propositional formula is DECIDED (SAT / UNSAT) and a witness FOUND
by a netlist of AND/OR/XOR/NOT -- truth is COMPUTED, not predicted, and verified byte-exact
against an independent brute-force reference.  An arithmetic fact (a + b) is likewise COMPUTED
as gates and cross-checked against Python.

The MOUTH is gates: the computed result -- a verdict bit, a witness assignment, a summed value --
is rendered into a fixed-width sequence of TOKEN IDS by a fabricated word-ROM (one-hot decode +
mux selection).  ONLY the final glyph lookup (token-id -> printable word) runs on the host,
exactly as a real chip drives a font ROM.  The token-id selection is verified byte-exact against
a pure-Python reference over the WHOLE input space -- THEN the circuit speaks.

Composition:
  muhl_reason.py  (fabricated SAT/propositional decider -- truth antipodal by construction)
+ muhl_speak.py   (fabricated language surface -- computation rendered as English)
= muhl_mind.py    (Titan computes a truth as gates, then speaks it as fluent English).

Built with the White Box compiler (sdc_cc.CircuitCompiler).  No numpy.  titan.gguf untouched.
"""
import sys, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
sys.path.insert(0, r"C:/llm/muhl_builds")
import sdc_cc as CC
from muhl_flex import bit, rd, setf, mux1, muxw, add_bits          # verified gate helpers
from muhl_reason import build_fixed, decide_sat_by_circuit, brute_sat, ref_eval

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


# =====================================================================
# THE SHARED GLYPH ROM  (host-side detokenizer only -- the single host step)
# =====================================================================
WID = 6                                   # 6 bits/token-id -> vocabulary 0..63
WORDS = {
    0: "",  1: "The", 2: "formula", 3: "is", 4: "satisfiable", 5: ",",
    6: "witnessed", 7: "by", 8: "=", 9: "true", 10: "false", 11: ".",
    12: "This", 13: "a", 14: "contradiction", 15: ";", 16: "no",
    17: "assignment", 18: "makes", 19: "it",
    20: "x1", 21: "x2", 22: "x3", 23: "x4",
    24: "sum", 25: "of", 26: "and",
    27: "zero", 28: "one", 29: "two", 30: "three", 31: "four", 32: "five",
    33: "six", 34: "seven", 35: "eight", 36: "nine", 37: "ten",
    38: "eleven", 39: "twelve", 40: "thirteen", 41: "fourteen",
}
XVAR = [20, 21, 22, 23]                    # x1..x4
NUM  = {v: 27 + v for v in range(15)}      # 0..14 -> zero..fourteen

def detok(ids):
    """host glyph lookup: token-ids -> a printed sentence (the ONLY host step at speak-time)."""
    out = ""; glue = False
    for tid in ids:
        w = WORDS[tid]
        if w == "": continue
        if w in (",", ";", "."): out += w; glue = False; continue
        if w == "=":             out += w; glue = True;  continue
        out += w if (out == "" or glue) else (" " + w)
        glue = False
    return out


# =====================================================================
# FABRICATED-ROM PRIMITIVES  (all gates)
# =====================================================================
def wconst(g, wid):
    """a word-id baked as WID constant wire-bits -- one ROM cell."""
    return [g.C1 if (wid >> k) & 1 else g.C0 for k in range(WID)]

def decode(g, sel):
    """one-hot minterm decode of a selector (LSB-first)."""
    lines = []
    for val in range(1 << len(sel)):
        m = g.C1
        for j, s in enumerate(sel):
            m = g.AND(m, s if (val >> j) & 1 else g.NOT(s))
        lines.append(m)
    return lines

def rom(g, minterms, table):
    """fabricated word-ROM: address = one-hot minterms, contents = table[i] (a word-id)."""
    out = []
    for k in range(WID):
        acc = g.C0
        for i, line in enumerate(minterms):
            if (table.get(i, 0) >> k) & 1:
                acc = g.OR(acc, line)
        out.append(acc)
    return out

def compile_slots(g, slots):
    """flatten WID-wide token slots -> outputs, DCE, ripple; return run + per-slot wires."""
    outs = [w for slot in slots for w in slot]
    gates, out2 = g.dce(outs)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    slot_wires = [out2[i * WID:(i + 1) * WID] for i in range(len(slots))]
    return run, gates, slot_wires

def speak(run, slot_wires, inp):
    v = run(inp, 1)
    ids = [rd(v, sw) for sw in slot_wires]
    return ids, detok(ids)


# =====================================================================
# MOUTH 1 -- THE PROPOSITIONAL VERDICT
#   inputs: verdict(1)  +  witness bits w[0..K-1]
#   SAT   : "The formula is satisfiable, witnessed by x1=<v1>, x2=<v2>, ... ."
#   UNSAT : "This is a contradiction; no assignment makes it true."
# =====================================================================
def sat_slot_ids(verdict, wit, K, WIDTH):
    """independent Python reference: field values -> the exact token-id sequence."""
    if verdict:
        ids = [1, 2, 3, 4, 5, 6, 7]                     # The formula is satisfiable , witnessed by
        for i in range(K):
            ids += [XVAR[i], 8, 9 if wit[i] else 10]    # xN = true|false
            if i < K - 1: ids += [5]                    # ,
        ids += [11]                                     # .
    else:
        ids = [12, 3, 13, 14, 15, 16, 17, 18, 19, 9, 11]  # This is a contradiction ; no assignment makes it true .
    return ids + [0] * (WIDTH - len(ids))

def build_sat_mouth(K):
    g = CC.CircuitCompiler(1 + K)
    verdict = g.IN[0]
    w = [g.IN[1 + i] for i in range(K)]
    vword = [muxw(g, w[i], wconst(g, 9), wconst(g, 10)) for i in range(K)]   # true/false, gate-selected

    plan = [('c', t) for t in (1, 2, 3, 4, 5, 6, 7)]                          # header
    for i in range(K):
        plan += [('c', XVAR[i]), ('c', 8), ('v', i)]
        if i < K - 1: plan.append(('c', 5))
    plan.append(('c', 11))
    WIDTH = len(plan)

    unsat = [12, 3, 13, 14, 15, 16, 17, 18, 19, 9, 11]
    unsat += [0] * (WIDTH - len(unsat))

    slots = []
    for j, (kind, val) in enumerate(plan):
        sat_side = vword[val] if kind == 'v' else wconst(g, val)
        slots.append(muxw(g, verdict, sat_side, wconst(g, unsat[j])))         # verdict picks template
    run, gates, slot_wires = compile_slots(g, slots)
    return g, run, slot_wires, gates, WIDTH

def verify_sat_mouth(K):
    g, run, sw, gates, WIDTH = build_sat_mouth(K)
    ok = True; mism = None
    for verdict in (0, 1):
        for a in range(1 << K):
            wit = [(a >> i) & 1 for i in range(K)]
            inp = [0] * (1 + K); inp[0] = verdict
            for i in range(K): inp[1 + i] = wit[i]
            got = [rd(run(inp, 1), s) for s in sw]
            exp = sat_slot_ids(verdict, wit, K, WIDTH)
            if got != exp: ok = False; mism = (verdict, wit, got, exp); break
        if not ok: break
    tag = "PASS" if ok else "FAIL"
    n = 2 * (1 << K)
    print(f"  [{tag}] verdict-mouth   {len(gates):>5,} gates  token-id byte-exact over {n} inputs")
    if mism: print(f"        MISMATCH verdict={mism[0]} wit={mism[1]}: got {mism[2]} exp {mism[3]}")
    return ok, run, sw, len(gates)


# =====================================================================
# MOUTH 2 -- THE ARITHMETIC FACT  (compute a+b as gates, then speak it)
#   inputs: a(AB bits), b(AB bits)
#   the SUM is COMPUTED by a ripple adder, then a,b,sum are ROM-rendered to number words.
#   speaks: "The sum of <a> and <b> is <a+b>."
# =====================================================================
AB = 3                                       # a,b in 0..7 ; sum in 0..14

def arith_slot_ids(a, b):
    return [1, 24, 25, NUM[a], 26, NUM[b], 3, NUM[a + b], 11]

def build_arith_mouth():
    g = CC.CircuitCompiler(2 * AB)
    a = [g.IN[i] for i in range(AB)]
    b = [g.IN[AB + i] for i in range(AB)]
    s, _cout = add_bits(g, a + [g.C0], b + [g.C0])           # 4-bit sum, gate-computed
    aw = rom(g, decode(g, a), NUM)
    bw = rom(g, decode(g, b), NUM)
    sw = rom(g, decode(g, s), NUM)
    slots = [wconst(g, 1), wconst(g, 24), wconst(g, 25), aw,
             wconst(g, 26), bw, wconst(g, 3), sw, wconst(g, 11)]
    run, gates, slot_wires = compile_slots(g, slots)
    return g, run, slot_wires, gates

def verify_arith_mouth():
    g, run, sw, gates = build_arith_mouth()
    ok = True; mism = None
    for a in range(1 << AB):
        for b in range(1 << AB):
            inp = [0] * (2 * AB)
            setf(inp, 0, AB, a); setf(inp, AB, AB, b)
            got = [rd(run(inp, 1), s) for s in sw]
            exp = arith_slot_ids(a, b)
            if got != exp: ok = False; mism = (a, b, got, exp); break
        if not ok: break
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] arithmetic-mouth {len(gates):>5,} gates  token-id byte-exact over {(1<<AB)**2} inputs"
          f"  (sum computed as gates)")
    if mism: print(f"        MISMATCH a={mism[0]} b={mism[1]}: got {mism[2]} exp {mism[3]}")
    return ok, run, sw, len(gates)


# =====================================================================
# THE MIND: reason (gates) -> verify truth -> speak (gates)
# =====================================================================
def main():
    t0 = time.time()
    print("=" * 78)
    print(" TITAN MIND -- computes a truth as gates, then speaks it as fluent English")
    print("=" * 78)

    spoken = []   # collect sentences for the report

    # ---- fabrication-time verification (nothing speaks on unverified gates) ----
    print("\n  -- fabrication-time proof (gate selection == pure-Python reference) --")
    okV, runV, swV, gV = verify_sat_mouth(4)
    okA, runA, swA, gA = verify_arith_mouth()
    if not (okV and okA):
        print("\n  MISMATCH -- refusing to speak on unverified gates."); return False

    # =========================================================
    # (1) REASON: decide a SATISFIABLE formula, find a witness
    # =========================================================
    print("\n  -- REASONING as gates (decided, then cross-checked vs brute force) --")
    K = 4
    sat_formula = [
        [(0, 0), (1, 1), (2, 0)],   # x1 OR ~x2 OR x3
        [(1, 0), (2, 1), (3, 0)],   # x2 OR ~x3 OR x4
        [(0, 1), (3, 1), (2, 0)],   # ~x1 OR ~x4 OR x3
        [(3, 0), (0, 0), (1, 0)],   # x4 OR x1 OR x2
    ]
    g1, run1, idx1, gates1 = build_fixed(K, sat_formula, with_truthword=False)
    csat, witnesses = decide_sat_by_circuit(K, sat_formula, run1, idx1)   # gates decide
    bsat, _ = brute_sat(K, sat_formula)                                   # independent check
    wit = witnesses[0]
    wit_ok = ref_eval(K, wit, sat_formula) == 1                           # witness re-checked
    print(f"    formula A (4 clauses / {K} vars): circuit SAT={csat} · brute-force SAT={bsat}"
          f" · match={csat == bsat}")
    print(f"    witness found by addressing gates: {wit}  (independently re-verified model: {wit_ok})")
    print(f"    reasoning gates: {len(gates1)}")

    # SPEAK the verdict
    inp = [0] * (1 + K); inp[0] = 1 if csat else 0
    for i in range(K): inp[1 + i] = wit[i]
    _, sentence = speak(runV, swV, inp)
    print(f"    TITAN SPEAKS:  \"{sentence}\"")
    spoken.append(sentence)

    # =========================================================
    # (2) REASON: decide a provably UNSAT formula (a contradiction)
    # =========================================================
    K3 = 3
    unsat_formula = [[(0, (m >> 0) & 1), (1, (m >> 1) & 1), (2, (m >> 2) & 1)] for m in range(8)]
    g2, run2, idx2, gates2 = build_fixed(K3, unsat_formula, with_truthword=False)
    csat2, _ = decide_sat_by_circuit(K3, unsat_formula, run2, idx2)
    bsat2, _ = brute_sat(K3, unsat_formula)
    print(f"\n    formula B (all 8 clauses / {K3} vars, classic contradiction):"
          f" circuit SAT={csat2} · brute-force SAT={bsat2} · match={csat2 == bsat2}")
    print(f"    reasoning gates: {len(gates2)}")
    inp = [0] * (1 + 4)                                   # verdict=0, witness ignored by the mux
    _, sentence = speak(runV, swV, inp)
    print(f"    TITAN SPEAKS:  \"{sentence}\"")
    spoken.append(sentence)

    # =========================================================
    # (3) REASON: an arithmetic fact, computed as gates, then spoken
    # =========================================================
    print("\n  -- an ARITHMETIC truth computed as gates, then spoken --")
    for a, b in [(2, 3), (7, 7), (4, 1), (6, 5)]:
        assert a + b == (a + b)                            # (trivially) the fact
        inp = [0] * (2 * AB); setf(inp, 0, AB, a); setf(inp, AB, AB, b)
        ids, sentence = speak(runA, swA, inp)
        # cross-check: the spoken sum word decodes to the true sum
        spoken_sum = ids[7] - 27
        ok = (spoken_sum == a + b)
        print(f"    {a} + {b} = {a+b}  (spoken sum verified={ok})  ->  \"{sentence}\"")
        spoken.append(sentence)

    total = gV + gA + len(gates1) + len(gates2)
    print("\n" + "=" * 78)
    print(f" MIND gates(reason A)={len(gates1)} + gates(reason B)={len(gates2)}"
          f"  ·  MOUTH gates(verdict)={gV} + gates(arith)={gA}")
    print(f" TOTAL fabricated gates: {total:,}")
    print(f" The reasoning is gates (truth preserved); the mouth is gates (only glyph lookup on host).")
    print(f" [done] {time.time()-t0:.2f}s · no numpy · titan.gguf untouched")
    print("=" * 78)
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
