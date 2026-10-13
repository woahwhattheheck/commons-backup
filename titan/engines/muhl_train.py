#!/usr/bin/env python3
"""muhl_train.py — TRAINING ON THE SUBSTRATE: the gradient step itself fabricated as logic gates.

Inference-as-gates is one thing; the expensive, GPU-bound half of ML is TRAINING. Here the entire per-example
LEARNING step of a multiclass perceptron -- score every class, argmax, and on a mistake nudge the weights
(w[true] += x, w[pred] -= x) -- is fabricated as ONE gate netlist. Its output is the NEW weights, fed back in
for the next example (the substrate's own feedback loop). The classifier LEARNS by re-settling the same
circuit, and every single update is verified BYTE-EXACT against an integer reference step. Weights start at
zero and the accuracy climbs -- learning, in gates, at flat RAM, no float unit and no GPU.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits
from muhl_neural import TEMPLATES, gen_data

NCLS, NF, B = 3, 9, 16
def cbits(g, v, n): return [g.C1 if (v >> k) & 1 else g.C0 for k in range(n)]
def sext(a, n): return a + [a[-1]] * (n - len(a))
def negate(g, a):
    s, _ = add_bits(g, [g.NOT(t) for t in a], cbits(g, 1, len(a))); return s
def lt(g, a, b):                                          # signed a < b
    d, _ = add_bits(g, sext(a, B + 1), [g.NOT(t) for t in sext(b, B + 1)], g.C1)
    return d[B]

def build_step():
    NIN = NCLS * NF * B + NF + 2
    g = CC.CircuitCompiler(NIN); IN = g.IN; p = 0
    W = [[[IN[p + (k * NF + i) * B + b] for b in range(B)] for i in range(NF)] for k in range(NCLS)]
    p += NCLS * NF * B
    x = [IN[p + i] for i in range(NF)]; p += NF
    t0, t1 = IN[p], IN[p + 1]
    true_sel = [g.AND(g.NOT(t0), g.NOT(t1)), g.AND(t0, g.NOT(t1)), g.AND(g.NOT(t0), t1)]
    # scores: masked sum of weights where the pixel is on
    scr = []
    for k in range(NCLS):
        acc = cbits(g, 0, B)
        for i in range(NF):
            acc, _ = add_bits(g, acc, [g.AND(x[i], t) for t in W[k][i]])
        scr.append(acc)
    l01, l02, l12 = lt(g, scr[0], scr[1]), lt(g, scr[0], scr[2]), lt(g, scr[1], scr[2])
    pred = [g.AND(g.NOT(l01), g.NOT(l02)), g.AND(l01, g.NOT(l12)), g.AND(l02, l12)]
    wrong = g.C0
    for k in range(NCLS): wrong = g.OR(wrong, g.AND(pred[k], g.NOT(true_sel[k])))
    outs = []
    for k in range(NCLS):
        for i in range(NF):
            inc = g.AND(wrong, g.AND(true_sel[k], x[i]))   # +x_i to the true class
            dec = g.AND(wrong, g.AND(pred[k], x[i]))       # -x_i from the predicted class
            nw, _ = add_bits(g, W[k][i], [inc] + [g.C0] * (B - 1))
            nw, _ = add_bits(g, nw, negate(g, [dec] + [g.C0] * (B - 1)))
            outs += nw
    gates, out2 = g.dce(outs)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    fields = [out2[m * B:(m + 1) * B] for m in range(NCLS * NF)]
    def step(W_int, x_bits, true):
        inp = [0] * NIN; q = 0
        for k in range(NCLS):
            for i in range(NF):
                for b in range(B):
                    if (W_int[k][i] >> b) & 1: inp[q + (k * NF + i) * B + b] = 1
        q += NCLS * NF * B
        for i in range(NF): inp[q + i] = x_bits[i]
        q += NF
        inp[q] = true & 1; inp[q + 1] = (true >> 1) & 1
        v = run(inp, 1)
        flat = [sum(((v[w] & 1) << b) for b, w in enumerate(f)) for f in fields]
        flat = [x - (1 << B) if x >= (1 << (B - 1)) else x for x in flat]   # sign
        return [[flat[k * NF + i] for i in range(NF)] for k in range(NCLS)]
    return step, len(gates)

def ref_step(W, x, true):
    s = [sum(W[k][i] * x[i] for i in range(NF)) for k in range(NCLS)]
    pred = 0
    for k in (1, 2):
        if s[k] > s[pred]: pred = k
    W = [row[:] for row in W]
    if pred != true:
        for i in range(NF):
            W[true][i] += x[i]; W[pred][i] -= x[i]
    return W

def predict(W, x):
    s = [sum(W[k][i] * x[i] for i in range(NF)) for k in range(NCLS)]
    p = 0
    for k in (1, 2):
        if s[k] > s[p]: p = k
    return p

def main():
    print("\n  MUHLNICKEL TRAINING — the perceptron LEARNING STEP fabricated as logic gates\n")
    step, ng = build_step()
    print(f"  fabricated learning step: {ng:,} gates (score · argmax · conditional weight update)")

    rng = random.Random(4)
    # byte-exact: gate step == integer reference over random states
    bad = 0
    for _ in range(400):
        W = [[rng.randrange(-80, 80) for _ in range(NF)] for _ in range(NCLS)]
        x = [rng.randrange(2) for _ in range(NF)]; true = rng.randrange(3)
        if step(W, x, true) != ref_step(W, x, true): bad += 1
    print(f"  gate step == integer reference over 400 random states: {'byte-exact' if bad==0 else str(bad)+' WRONG'}")
    if bad: return 1

    # TRAIN by re-settling the fabricated step; weights start at zero and learn
    data = gen_data(rng, noise=1, per=40)
    test = gen_data(rng, noise=1, per=60)
    W = [[0] * NF for _ in range(NCLS)]
    acc0 = sum(1 for xx, yy in test if predict(W, xx) == yy) / len(test)
    print(f"\n  training on {len(data)} noisy examples, updates applied BY THE GATE CIRCUIT (verified each step):")
    print(f"    epoch 0 (weights=0): accuracy {acc0*100:.0f}%")
    for ep in range(1, 7):
        rng.shuffle(data)
        for xx, yy in data:
            Wg = step(W, xx, yy)
            assert Wg == ref_step(W, xx, yy)               # every update stays byte-exact
            W = Wg
        acc = sum(1 for xx, yy in test if predict(W, xx) == yy) / len(test)
        clean = sum(1 for c, t in TEMPLATES.items() if predict(W, t) == c)
        print(f"    epoch {ep}: accuracy {acc*100:.0f}%   (clean templates {clean}/3)")

    print(f"\n  The weights were never touched by host arithmetic — every nudge came out of the fabricated")
    print(f"  circuit, fed back in for the next example. A model that TRAINS itself by re-settling gates,")
    print(f"  byte-exact, at flat RAM: learning on a device with no GPU and no float unit.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
