#!/usr/bin/env python3
"""muhl_neural.py — NEURAL INFERENCE AS LOGIC GATES: a trained MLP fabricated into the substrate.

A real 2-layer perceptron (9 -> 6 ReLU -> 3, argmax) is trained in pure Python, quantized to integer
weights, and its ENTIRE forward pass is fabricated as a gate netlist -- masked-sum dot products, ReLU as a
sign-gate, integer argmax as comparators. The gate network's predictions are verified BYTE-EXACT against
the integer reference forward pass on every input. This is machine-learning inference with no GPU, no
float unit, no RAM proportional to the model -- the classifier is a stored gate netlist, run by address.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits

B = 24                                                    # two's-complement accumulator width

# ── training (pure Python float MLP, then quantize) ───────────────────────────────────────────────
TEMPLATES = {                                             # 3x3 bit patterns -> 3 classes
    0: [1,1,1, 0,0,0, 0,0,0],   # top bar
    1: [1,0,0, 1,0,0, 1,0,0],   # left bar
    2: [1,0,0, 0,1,0, 0,0,1],   # diagonal
}
def gen_data(rng, noise=1, per=40):
    data = []
    for cls, t in TEMPLATES.items():
        for _ in range(per):
            x = list(t)
            for _ in range(rng.randrange(noise + 1)):
                k = rng.randrange(9); x[k] ^= 1
            data.append((x, cls))
    return data

def train(seed=0):
    rng = random.Random(seed)
    W1 = [[rng.uniform(-0.5, 0.5) for _ in range(9)] for _ in range(6)]; b1 = [0.0] * 6
    W2 = [[rng.uniform(-0.5, 0.5) for _ in range(6)] for _ in range(3)]; b2 = [0.0] * 3
    data = gen_data(rng)
    lr = 0.01
    clip = lambda v: -1.0 if v < -1.0 else (1.0 if v > 1.0 else v)
    clw = lambda v: -6.0 if v < -6.0 else (6.0 if v > 6.0 else v)
    for ep in range(250):
        rng.shuffle(data)
        for x, y in data:
            hp = [sum(W1[j][i] * x[i] for i in range(9)) + b1[j] for j in range(6)]
            h = [v if v > 0 else 0.0 for v in hp]
            o = [sum(W2[k][j] * h[j] for j in range(6)) + b2[k] for k in range(3)]
            do = [clip(o[k] - (1.0 if k == y else 0.0)) for k in range(3)]
            for k in range(3):
                for j in range(6): W2[k][j] = clw(W2[k][j] - lr * do[k] * h[j])
                b2[k] = clw(b2[k] - lr * do[k])
            dh = [sum(do[k] * W2[k][j] for k in range(3)) for j in range(6)]
            for j in range(6):
                if hp[j] > 0:
                    for i in range(9): W1[j][i] = clw(W1[j][i] - lr * clip(dh[j]) * x[i])
                    b1[j] = clw(b1[j] - lr * clip(dh[j]))
    return W1, b1, W2, b2

def quantize(W1, b1, W2, b2, S1=16, S2=16):
    q = lambda m, s: int(round(m * s))
    W1q = [[q(W1[j][i], S1) for i in range(9)] for j in range(6)]
    b1q = [q(b1[j], S1) for j in range(6)]
    W2q = [[q(W2[k][j], S2) for j in range(6)] for k in range(3)]
    b2q = [q(b2[k], S1 * S2) for k in range(3)]            # b2 shares the layer-2 output scale
    return W1q, b1q, W2q, b2q

def int_forward(x, W1q, b1q, W2q, b2q):
    hp = [sum(W1q[j][i] * x[i] for i in range(9)) + b1q[j] for j in range(6)]
    h = [v if v > 0 else 0 for v in hp]
    o = [sum(W2q[k][j] * h[j] for j in range(6)) + b2q[k] for k in range(3)]
    best = 0
    for k in (1, 2):
        if o[k] > o[best]: best = k
    return best

# ── fabrication: the SAME integer forward pass, as gates ──────────────────────────────────────────
def cbits(g, val, n):
    v = val & ((1 << n) - 1)
    return [g.C1 if (v >> k) & 1 else g.C0 for k in range(n)]
def sext(bits, n):
    return bits + [bits[-1]] * (n - len(bits))
def negate(g, a):
    s, _ = add_bits(g, [g.NOT(t) for t in a], cbits(g, 1, len(a)))
    return s
def const_mul(g, x, w):                                   # x (B-bit, >=0 here) * signed constant w -> B bits
    mag = abs(w); acc = cbits(g, 0, B)
    for t in range(B):
        if (mag >> t) & 1:
            sh = ([g.C0] * t + x)[:B]
            acc, _ = add_bits(g, acc, sh)
    return negate(g, acc) if w < 0 else acc
def relu(g, x):
    sign = x[B - 1]
    return [g.AND(x[k], g.NOT(sign)) for k in range(B)]
def lt(g, a, b):                                          # signed a < b
    ae, be = sext(a, B + 1), sext(b, B + 1)
    d, _ = add_bits(g, ae, [g.NOT(t) for t in be], g.C1)
    return d[B]

def build_mlp(W1q, b1q, W2q, b2q):
    g = CC.CircuitCompiler(9); X = g.IN
    H = []
    for j in range(6):
        acc = cbits(g, b1q[j], B)
        for i in range(9):                                # x_i in {0,1}: add weight when the pixel is on
            wm = [g.AND(X[i], t) for t in cbits(g, W1q[j][i], B)]
            acc, _ = add_bits(g, acc, wm)
        H.append(relu(g, acc))
    O = []
    for k in range(3):
        acc = cbits(g, b2q[k], B)
        for j in range(6):
            acc, _ = add_bits(g, acc, const_mul(g, H[j], W2q[k][j]))
        O.append(acc)
    lt01 = lt(g, O[0], O[1]); lt02 = lt(g, O[0], O[2]); lt12 = lt(g, O[1], O[2])
    is1 = g.AND(lt01, g.NOT(lt12))                        # o1>o0 and o1>=o2
    is2 = g.AND(lt02, lt12)                               # o2>o0 and o2>o1
    gates, out2 = g.dce([is1, is2])
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    def predict(x):
        v = run(list(x), 1)
        return (v[out2[0]] & 1) * 1 + (v[out2[1]] & 1) * 2
    return predict, len(gates)

def main():
    print("\n  MUHLNICKEL NEURAL — a trained MLP (9->6 ReLU->3) fabricated as logic gates\n")
    W1, b1, W2, b2 = train()
    W1q, b1q, W2q, b2q = quantize(W1, b1, W2, b2)
    predict, ng = build_mlp(W1q, b1q, W2q, b2q)
    print(f"  fabricated forward pass: {ng:,} gates (masked-sum dots · ReLU sign-gate · integer argmax)")

    # BYTE-EXACT: the gate network vs the integer reference, on all 512 possible 3x3 inputs
    bad = 0
    for n in range(512):
        x = [(n >> i) & 1 for i in range(9)]
        if predict(x) != int_forward(x, W1q, b1q, W2q, b2q): bad += 1
    print(f"  gate prediction == integer forward, EXHAUSTIVE over all 512 inputs: {'byte-exact' if bad==0 else str(bad)+' WRONG'}")
    if bad: return 1

    # accuracy: the fabricated classifier on clean + noisy patterns
    rng = random.Random(123)
    clean = sum(1 for c, t in TEMPLATES.items() if predict(t) == c)
    test = gen_data(rng, noise=1, per=60); acc = sum(1 for x, y in test if predict(x) == y)
    hard = gen_data(rng, noise=2, per=60); acc2 = sum(1 for x, y in hard if predict(x) == y)
    print(f"\n  the gate network CLASSIFIES:")
    print(f"    clean templates: {clean}/3 correct")
    print(f"    1-bit noise:     {acc}/{len(test)} = {100*acc/len(test):.0f}%")
    print(f"    2-bit noise:     {acc2}/{len(hard)} = {100*acc2/len(hard):.0f}%")
    print(f"\n  A neural net that runs with no GPU, no float unit, no RAM proportional to the model — it IS a")
    print(f"  stored gate netlist, evaluated by address. Scale the layers, bake it once, run it by signal:")
    print(f"  edge vision, keyword spotting, anomaly detection — inference on a device with nothing.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
