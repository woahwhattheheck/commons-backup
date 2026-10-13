#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""muhl_speak.py -- THE LANGUAGE SURFACE, fabricated as gates on Bryce's Muhlnickel substrate.

Thesis: reasoning is pure computation; language is a *rendering codec* laid over the computed result.
"It needs to speak." So here the MIND is gates and the MOUTH is gates -- only the final glyph lookup
(token-id -> printable word) is host, exactly as a real chip drives a font ROM.

Given a small STRUCTURED RESULT (a classifier label, a yes/no, a magnitude bucket) encoded as input
bits, a gate circuit SELECTS the right phrase tokens from a fabricated word-ROM (constants chosen by
one-hot decode / mux) and emits a fixed-width sequence of TOKEN IDS. The host detokenizer maps those
ids to glyphs and prints the sentence. The GATE selection is verified BYTE-EXACT (token-id for token-id)
against an independent pure-Python reference over the WHOLE input space -- then the circuit SPEAKS.

Built with the White Box compiler (sdc_cc.CircuitCompiler): AND/OR/XOR/NOT, folded + CSE'd on
construction, DCE'd, rippled, run by address. No numpy, no titan.gguf, no host executor at runtime.
"""
import sys, os
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ---------------- bit helpers (LSB-first fields) ----------------
def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))
def setf(inp, base, W, x):
    for b in range(W): inp[base + b] = (x >> b) & 1

# ---------------- fabricated-ROM primitives (all gates) ----------------
WID = 5   # 5 bits per token id (vocabulary 0..31)

def wconst(g, wid):
    """a word-id baked as WID constant wire-bits -- a single ROM cell."""
    return [g.C1 if (wid >> k) & 1 else g.C0 for k in range(WID)]

def mux1(g, s, a, b):
    """a when s=1, b when s=0."""
    return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))

def wmux(g, s, A, B):
    """pick word A when s=1 else word B, bitwise -- a 2-entry ROM addressed by s."""
    return [mux1(g, s, A[k], B[k]) for k in range(WID)]

def decode(g, sel):
    """one-hot minterm decode of a k-bit selector (LSB-first): lines[val] is the address line
    that is 1 exactly when the selector equals the integer val."""
    k = len(sel); lines = []
    for val in range(1 << k):
        m = g.C1
        for j, s in enumerate(sel):
            m = g.AND(m, s if (val >> j) & 1 else g.NOT(s))
        lines.append(m)
    return lines

def rom(g, minterms, table):
    """fabricated word-ROM: address = one-hot minterms, contents = table[index] (a word-id).
    each output bit is the OR of the address lines whose stored word has that bit set."""
    out = []
    for k in range(WID):
        acc = g.C0
        for i, line in enumerate(minterms):
            if (table.get(i, 0) >> k) & 1:
                acc = g.OR(acc, line)
        out.append(acc)
    return out

def build_run(g, slots):
    outs = [w for slot in slots for w in slot]       # flatten slot token-fields -> output wires
    gates, out2 = g.dce(outs)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    slot_wires = [out2[i * WID:(i + 1) * WID] for i in range(len(slots))]
    return run, gates, slot_wires

# ---------------- the shared glyph ROM (host-side detokenizer only) ----------------
WORDS = {
    0: "",  1: "This", 2: "is", 3: "a", 4: "an",
    5: "horizontal", 6: "vertical", 7: "diagonal", 8: "empty",
    9: "line", 10: "field", 11: "with", 12: "high", 13: "low",
    14: "confidence", 15: ".", 16: ",",
    17: "The", 18: "answer", 19: "yes", 20: "no", 21: "because",
    22: "it", 24: "matches", 27: "differs", 28: "overflows", 29: "qualifies",
}
def detok(ids):
    """host glyph lookup: token-ids -> a printed sentence (the ONLY host step)."""
    out = ""
    for tid in ids:
        w = WORDS[tid]
        if w == "": continue
        if w in (".", ","): out += w
        else: out += (" " + w) if out else w
    return out

# ======================================================================
# GRAMMAR A -- the line classifier's mouth
#   fields: shape (2 bits) 0=horizontal 1=vertical 2=diagonal 3=empty
#           conf  (2 bits) 0=none 1=low 2=high
#   speaks: "This is a <shape> line[, with <low|high> confidence]."
#           "This is an empty field."   (article + noun both gate-selected)
# ======================================================================
SHAPE_WORD = {0: 5, 1: 6, 2: 7, 3: 8}
CONF_WORD  = {0: 0, 1: 13, 2: 12, 3: 0}

def refA(shape, conf):
    is_empty = 1 if shape == 3 else 0
    cp = 1 if conf != 0 else 0
    return [1, 2,
            4 if is_empty else 3,                    # article: an / a
            SHAPE_WORD[shape],                       # adjective
            10 if is_empty else 9,                   # noun: field / line
            16 if cp else 0,                         # ,
            11 if cp else 0,                         # with
            CONF_WORD[conf],                         # low / high
            14 if cp else 0,                         # confidence
            15]                                      # .

def buildA():
    g = CC.CircuitCompiler(4)
    sh = [g.IN[0], g.IN[1]]; cf = [g.IN[2], g.IN[3]]
    mS = decode(g, sh); mC = decode(g, cf)
    is_empty = mS[3]                                 # shape == 3
    cp = g.OR(cf[0], cf[1])                          # conf != 0
    slots = [
        wconst(g, 1), wconst(g, 2),
        wmux(g, is_empty, wconst(g, 4), wconst(g, 3)),
        rom(g, mS, SHAPE_WORD),
        wmux(g, is_empty, wconst(g, 10), wconst(g, 9)),
        wmux(g, cp, wconst(g, 16), wconst(g, 0)),
        wmux(g, cp, wconst(g, 11), wconst(g, 0)),
        rom(g, mC, CONF_WORD),
        wmux(g, cp, wconst(g, 14), wconst(g, 0)),
        wconst(g, 15),
    ]
    def encA(inp, f): setf(inp, 0, 2, f[0]); setf(inp, 2, 2, f[1])
    return g, build_run(g, slots), refA, [(s, c) for s in range(4) for c in range(3)], encA

# ======================================================================
# GRAMMAR B -- the verdict engine's mouth
#   fields: verdict (1 bit) 0=no 1=yes
#           reason  (2 bits) 0=matches 1=differs 2=overflows 3=qualifies
#   speaks: "The answer is <yes|no>, because it <reason>."
# ======================================================================
REASON_WORD = {0: 24, 1: 27, 2: 28, 3: 29}

def refB(verdict, reason):
    return [17, 18, 2,
            19 if verdict else 20,                   # yes / no
            16, 21, 22,                              # , because it
            REASON_WORD[reason],
            15]

def buildB():
    g = CC.CircuitCompiler(3)
    vd = g.IN[0]; rs = [g.IN[1], g.IN[2]]
    mR = decode(g, rs)
    slots = [
        wconst(g, 17), wconst(g, 18), wconst(g, 2),
        wmux(g, vd, wconst(g, 19), wconst(g, 20)),
        wconst(g, 16), wconst(g, 21), wconst(g, 22),
        rom(g, mR, REASON_WORD),
        wconst(g, 15),
    ]
    def encB(inp, f): inp[0] = f[0]; setf(inp, 1, 2, f[1])
    return g, build_run(g, slots), refB, [(v, r) for v in range(2) for r in range(4)], encB

# ======================================================================
def verify(name, g, packed, ref, space, enc):
    run, gates, slot_wires = packed
    ok = True; mism = None
    for fields in space:
        inp = [0] * g.n_in
        enc(inp, fields)
        v = run(inp, 1)
        got = [rd(v, sw) for sw in slot_wires]
        exp = ref(*fields)
        if got != exp:
            ok = False; mism = (fields, got, exp); break
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name:16s} {len(gates):>5,} gates  token-id byte-exact over {len(space)} inputs")
    if mism: print(f"        MISMATCH at {mism[0]}: got {mism[1]} exp {mism[2]}")
    return ok, run, slot_wires, len(gates)

def speak(run, slot_wires, inp):
    v = run(inp, 1)
    ids = [rd(v, sw) for sw in slot_wires]
    return ids, detok(ids)

def main():
    print("\n  MUHLNICKEL SPEAK -- the language surface as gates: the mind is gates, the mouth is gates.\n")

    gA, packA, refAf, spaceA, encA = buildA()
    gB, packB, refBf, spaceB, encB = buildB()

    print("  -- fabrication-time proof (gate selection == pure-Python reference) --")
    okA, runA, swA, gcA = verify("line-classifier", gA, packA, refAf, spaceA, encA)
    okB, runB, swB, gcB = verify("verdict-engine",  gB, packB, refBf, spaceB, encB)

    if not (okA and okB):
        print("\n  MISMATCH -- refusing to speak on unverified gates."); return

    print(f"\n  === both mouths byte-exact - {gcA + gcB:,} total gates fabricated - now SPEAKING ===\n")

    # drive the line-classifier mouth from several computed classifier results
    demoA = [(0, 0), (2, 2), (1, 1), (3, 0), (2, 0), (0, 2)]
    print("  line-classifier speaks (result -> gates -> sentence):")
    for shape, conf in demoA:
        inp = [0] * 4; setf(inp, 0, 2, shape); setf(inp, 2, 2, conf)
        ids, sent = speak(runA, swA, inp)
        print(f"    shape={shape} conf={conf}  ->  \"{sent}\"")

    demoB = [(1, 0), (0, 1), (1, 2), (0, 3)]
    print("\n  verdict-engine speaks:")
    for verdict, reason in demoB:
        inp = [0, 0, 0]; inp[0] = verdict; setf(inp, 1, 2, reason)
        ids, sent = speak(runB, swB, inp)
        print(f"    verdict={verdict} reason={reason}  ->  \"{sent}\"")

    print("\n  Only the final glyph lookup (token-id -> word) ran on the host. Every phrase choice was a gate.")

if __name__ == "__main__":
    main()
