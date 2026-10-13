#!/usr/bin/env python3
"""muhl_engineered.py — ENGINEERED TENSORS, NO BLIND HOPE: a model whose weights are CONSTRUCTED, proven exact.

Training exists because conventional hardware can't compute the right weights directly -- you descend a gradient
and HOPE. On a substrate that fabricates exact logic and verifies byte-exact, you ENGINEER the tensors and PROVE
the model correct by construction. This is a substrate-native architecture: an associative / content-addressable
classifier whose "weight tensor" IS the set of class prototypes, set directly (no SGD). Inference = match the
input against every prototype (popcount-XNOR, the substrate's native addressing) and take the argmax class.
Result: 100% correct on every prototype BY CONSTRUCTION (not hoped), nearest-match generalization from the fold,
and a new class is added by writing one prototype -- no retraining. Fabricated as gates, byte-exact end to end.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits

D, SB = 16, 5                                             # input width, score bits (0..16)
# ENGINEERED weight tensor: class -> list of prototype codes (chosen for separation; no training)
PROTOTYPES = {
    0: [0x0000, 0xFF00],   # class 0
    1: [0xFFFF, 0x00FF],   # class 1
    2: [0xAAAA, 0x5555],   # class 2  (checkerboards)
    3: [0xF0F0, 0x0F0F],   # class 3
}
K = len(PROTOTYPES)

def cbits(g, v, n): return [g.C1 if (v >> k) & 1 else g.C0 for k in range(n)]
def score(g, x, proto):                                  # popcount(XNOR(x, proto)) -- proto is a constant (engineered)
    acc = [g.C0] * SB
    for i in range(D):
        agree = x[i] if (proto >> i) & 1 else g.NOT(x[i])  # XNOR with a constant bit folds to x or NOT x
        acc, _ = add_bits(g, acc, [agree] + [g.C0] * (SB - 1))
    return acc
def lt(g, a, b):
    d, _ = add_bits(g, a + [g.C0], [g.NOT(t) for t in (b + [g.C0])], g.C1)
    return d[SB]
def maxw(g, a, b): return [g.OR(g.AND(lt(g, a, b), b[k]), g.AND(g.NOT(lt(g, a, b)), a[k])) for k in range(SB)]

def build():
    g = CC.CircuitCompiler(D); x = g.IN
    cls_score = []
    for c in range(K):
        s = None
        for p in PROTOTYPES[c]:
            sp = score(g, x, p); s = sp if s is None else maxw(g, s, sp)
        cls_score.append(s)
    # argmax over K classes, lowest index on tie -> onehot
    sel = []
    for c in range(K):
        is_max = g.C1
        for d2 in range(K):
            if d2 == c: continue
            if d2 < c: is_max = g.AND(is_max, lt(g, cls_score[d2], cls_score[c]))           # c > d2 (earlier ties win)
            else:      is_max = g.AND(is_max, g.NOT(lt(g, cls_score[c], cls_score[d2])))    # c >= d2
        sel.append(is_max)
    kb = max(1, (K - 1).bit_length())
    outs = []
    for b in range(kb):
        acc = g.C0
        for c in range(K):
            if (c >> b) & 1: acc = g.OR(acc, sel[c])
        outs.append(acc)
    gates, out2 = g.dce(outs)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    def predict(v):
        inp = [(v >> i) & 1 for i in range(D)]
        r = run(inp, 1)
        return sum(((r[w] & 1) << b) for b, w in enumerate(out2))
    return predict, len(gates)

def ref_predict(v):
    best_c, best_s = 0, -1
    for c in range(K):
        s = max(bin(~(v ^ p) & ((1 << D) - 1)).count("1") for p in PROTOTYPES[c])
        if s > best_s: best_s, best_c = s, c
    return best_c

def main():
    predict, ng = build()
    print(f"\n  MUHLNICKEL ENGINEERED — an associative classifier, weights SET not trained, fabricated as {ng:,} gates\n")
    print(f"  weight tensor = {sum(len(v) for v in PROTOTYPES.values())} engineered prototypes across {K} classes (no SGD)")

    # PROVEN BY CONSTRUCTION: every prototype classifies to its own class
    proof = all(predict(p) == c for c in range(K) for p in PROTOTYPES[c])
    print(f"\n  proof-by-construction: every prototype -> its own class: {proof}  (100%, not hoped)")

    # byte-exact vs the reference, EXHAUSTIVE over all 65,536 inputs
    bad = sum(1 for v in range(1 << D) if predict(v) != ref_predict(v))
    print(f"  gate model == reference over ALL {1<<D:,} inputs: {'byte-exact' if bad==0 else str(bad)+' WRONG'}")
    if bad: return 1

    # nearest-match generalization on corrupted prototypes
    rng = random.Random(2); ok = tot = 0
    for c in range(K):
        for p in PROTOTYPES[c]:
            for _ in range(200):
                v = p
                for _ in range(rng.randrange(4)): v ^= 1 << rng.randrange(D)   # up to 3-bit corruption
                tot += 1; ok += (predict(v) == c)
    print(f"  nearest-match generalization (<=3-bit corruption): {100*ok/tot:.0f}%")

    print(f"\n  No gradient, no epochs, no hope: the decision rule is FULLY SPECIFIED (nearest prototype) and the")
    print(f"  model is exact by construction. Add a class = write one prototype constant + re-fabricate; nothing")
    print(f"  is retrained. Engineered tensors on a substrate that lets you PROVE the model, not pray over it.")
    return 0 if (proof and bad == 0) else 1

if __name__ == "__main__":
    raise SystemExit(main())
