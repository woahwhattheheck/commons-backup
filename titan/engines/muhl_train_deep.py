#!/usr/bin/env python3
"""muhl_train_deep.py — MAXED-OUT TRAINING: BACKPROP through a hidden layer, fabricated as gates.

A 2-layer net (9 -> H binary-threshold hidden -> 3) trained end to end by a gate netlist. Binary hidden
units keep BOTH layers as masked sums (no multipliers), and the hidden-layer gradient of the structured
hinge loss reduces to dh[j] = W2[pred][j] - W2[true][j] (a signed subtract via one-hot mux). The FULL
learning step -- forward, argmax, output-weight update, backprop the error to the hidden weights (straight-
through), all with unit (signSGD) steps -- is one fabricated circuit whose output is the new weights, fed
back for the next example. Every update is verified BYTE-EXACT vs an integer reference, and the net LEARNS.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits
from muhl_neural import TEMPLATES, gen_data

NF, H, NCLS, B = 9, 8, 3, 16
def cbits(g, v, n): return [g.C1 if (v >> k) & 1 else g.C0 for k in range(n)]
def negate(g, a):
    s, _ = add_bits(g, [g.NOT(t) for t in a], cbits(g, 1, len(a))); return s
def sext(a, n): return a + [a[-1]] * (n - len(a))
def lt(g, a, b):
    d, _ = add_bits(g, sext(a, B + 1), [g.NOT(t) for t in sext(b, B + 1)], g.C1); return d[B]
def addpm(g, w, inc, dec):                                # w + inc - dec, inc/dec single bits
    t, _ = add_bits(g, w, [inc] + [g.C0] * (B - 1))
    t, _ = add_bits(g, t, negate(g, [dec] + [g.C0] * (B - 1))); return t
def mux_oh(g, sel, vals):                                 # one-hot select a B-bit value
    return [reduce_or(g, [g.AND(sel[k], vals[k][b]) for k in range(len(sel))]) for b in range(B)]
def reduce_or(g, xs):
    a = xs[0]
    for x in xs[1:]: a = g.OR(a, x)
    return a

def build_step():
    NIN = H*NF*B + H*B + NCLS*H*B + NCLS*B + NF + 2
    g = CC.CircuitCompiler(NIN); IN = g.IN; p = 0
    W1 = [[[IN[p+((j*NF+i)*B+b)] for b in range(B)] for i in range(NF)] for j in range(H)]; p += H*NF*B
    b1 = [[IN[p+(j*B+b)] for b in range(B)] for j in range(H)]; p += H*B
    W2 = [[[IN[p+((k*H+j)*B+b)] for b in range(B)] for j in range(H)] for k in range(NCLS)]; p += NCLS*H*B
    b2 = [[IN[p+(k*B+b)] for b in range(B)] for k in range(NCLS)]; p += NCLS*B
    x = [IN[p+i] for i in range(NF)]; p += NF
    t0, t1 = IN[p], IN[p+1]
    true_sel = [g.AND(g.NOT(t0), g.NOT(t1)), g.AND(t0, g.NOT(t1)), g.AND(g.NOT(t0), t1)]
    # forward: hidden (binary threshold hp>=0), output masked sum over binary h
    h = []
    for j in range(H):
        acc = list(b1[j])
        for i in range(NF): acc, _ = add_bits(g, acc, [g.AND(x[i], t) for t in W1[j][i]])
        h.append(g.NOT(acc[B-1]))                          # h[j] = (hp[j] >= 0)
    o = []
    for k in range(NCLS):
        acc = list(b2[k])
        for j in range(H): acc, _ = add_bits(g, acc, [g.AND(h[j], t) for t in W2[k][j]])
        o.append(acc)
    l01, l02, l12 = lt(g, o[0], o[1]), lt(g, o[0], o[2]), lt(g, o[1], o[2])
    pred = [g.AND(g.NOT(l01), g.NOT(l02)), g.AND(l01, g.NOT(l12)), g.AND(l02, l12)]
    wrong = reduce_or(g, [g.AND(pred[k], g.NOT(true_sel[k])) for k in range(NCLS)])
    outs = []
    # layer 2 update: W2[k][j] -= do[k]*h[j], do = pred - true
    for k in range(NCLS):
        for j in range(H):
            dec = g.AND(wrong, g.AND(pred[k], h[j])); inc = g.AND(wrong, g.AND(true_sel[k], h[j]))
            outs += addpm(g, W2[k][j], inc, dec)
    for k in range(NCLS):
        dec = g.AND(wrong, pred[k]); inc = g.AND(wrong, true_sel[k])
        b2n = addpm(g, b2[k], inc, dec)
    # backprop: dh[j] = W2[pred][j] - W2[true][j]; W1[j][i] -= sign(dh)*x_i ; b1[j] -= sign(dh)
    b1_out = []; W1_out = []
    for j in range(H):
        wp = mux_oh(g, pred, [W2[k][j] for k in range(NCLS)])
        wt = mux_oh(g, true_sel, [W2[k][j] for k in range(NCLS)])
        dh, _ = add_bits(g, wp, [g.NOT(t) for t in wt], g.C1)          # wp - wt
        dh_neg = dh[B-1]; dh_pos = g.AND(reduce_or(g, dh), g.NOT(dh[B-1]))
        for i in range(NF):
            inc = g.AND(x[i], dh_neg); dec = g.AND(x[i], dh_pos)
            W1_out.append(addpm(g, W1[j][i], inc, dec))
        b1_out.append(addpm(g, b1[j], dh_neg, dh_pos))
    # reassemble outputs in the SAME layout as inputs: W1, b1, W2, b2
    order = []
    for j in range(H):
        for i in range(NF): order += W1_out[j*NF + i]
    for j in range(H): order += b1_out[j]
    order += outs                                          # W2 (added first above)
    for k in range(NCLS):
        dec = g.AND(wrong, pred[k]); inc = g.AND(wrong, true_sel[k])
        order += addpm(g, b2[k], inc, dec)
    gates, out2 = g.dce(order)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    NW = H*NF + H + NCLS*H + NCLS
    fields = [out2[m*B:(m+1)*B] for m in range(NW)]
    def step(P, x_bits, true):
        inp = [0]*NIN; q = 0
        def putW(flat):
            nonlocal q
            for val in flat:
                for b in range(B):
                    if (val >> b) & 1: inp[q+b] = 1
                q += B
        putW([P['W1'][j][i] for j in range(H) for i in range(NF)])
        putW([P['b1'][j] for j in range(H)])
        putW([P['W2'][k][j] for k in range(NCLS) for j in range(H)])
        putW([P['b2'][k] for k in range(NCLS)])
        for i in range(NF): inp[q+i] = x_bits[i]
        q += NF; inp[q] = true & 1; inp[q+1] = (true >> 1) & 1
        v = run(inp, 1)
        flat = []
        for f in fields:
            val = sum(((v[w] & 1) << b) for b, w in enumerate(f))
            flat.append(val - (1 << B) if val >= (1 << (B-1)) else val)
        c = 0
        W1n = [[flat[c + j*NF + i] for i in range(NF)] for j in range(H)]; c += H*NF
        b1n = [flat[c+j] for j in range(H)]; c += H
        W2n = [[flat[c + k*H + j] for j in range(H)] for k in range(NCLS)]; c += NCLS*H
        b2n = [flat[c+k] for k in range(NCLS)]
        return {'W1': W1n, 'b1': b1n, 'W2': W2n, 'b2': b2n}
    return step, len(gates)

def fwd(P, x):
    hp = [sum(P['W1'][j][i]*x[i] for i in range(NF)) + P['b1'][j] for j in range(H)]
    h = [1 if hp[j] >= 0 else 0 for j in range(H)]
    o = [sum(P['W2'][k][j]*h[j] for j in range(H)) + P['b2'][k] for k in range(NCLS)]
    pred = 0
    for k in (1, 2):
        if o[k] > o[pred]: pred = k
    return h, pred

def ref_step(P, x, true):
    h, pred = fwd(P, x)
    N = {'W1': [r[:] for r in P['W1']], 'b1': P['b1'][:], 'W2': [r[:] for r in P['W2']], 'b2': P['b2'][:]}
    wrong = pred != true
    if wrong:
        for k in range(NCLS):
            for j in range(H):
                if h[j]:
                    if k == pred: N['W2'][k][j] -= 1
                    if k == true: N['W2'][k][j] += 1
            if k == pred: N['b2'][k] -= 1
            if k == true: N['b2'][k] += 1
    for j in range(H):
        dh = P['W2'][pred][j] - P['W2'][true][j]
        s = 1 if dh > 0 else (-1 if dh < 0 else 0)
        for i in range(NF): N['W1'][j][i] -= s * x[i]
        N['b1'][j] -= s
    return N

def predict(P, x): return fwd(P, x)[1]

def main():
    print("\n  MUHLNICKEL DEEP TRAINING — backprop through a hidden layer, fabricated as gates\n")
    step, ng = build_step()
    print(f"  net 9->{H} hidden->3 · fabricated learning step (forward+argmax+backprop): {ng:,} gates")
    rng = random.Random(7)
    bad = 0
    for _ in range(200):
        P = {'W1': [[rng.randrange(-40, 40) for _ in range(NF)] for _ in range(H)],
             'b1': [rng.randrange(-40, 40) for _ in range(H)],
             'W2': [[rng.randrange(-40, 40) for _ in range(H)] for _ in range(NCLS)],
             'b2': [rng.randrange(-40, 40) for _ in range(NCLS)]}
        x = [rng.randrange(2) for _ in range(NF)]; true = rng.randrange(3)
        if step(P, x, true) != ref_step(P, x, true): bad += 1
    print(f"  gate step == integer backprop reference over 200 random states: {'byte-exact' if bad==0 else str(bad)+' WRONG'}")
    if bad: return 1
    # train from small random init, updates applied BY THE GATE CIRCUIT
    P = {'W1': [[rng.randrange(-2, 3) for _ in range(NF)] for _ in range(H)],
         'b1': [0]*H, 'W2': [[rng.randrange(-2, 3) for _ in range(H)] for _ in range(NCLS)], 'b2': [0]*NCLS}
    data = gen_data(rng, noise=1, per=40); test = gen_data(rng, noise=1, per=60)
    acc0 = sum(1 for xx, yy in test if predict(P, xx) == yy) / len(test)
    print(f"\n  training 9->{H}->3 by re-settling the gate step (verified byte-exact each update):")
    print(f"    epoch 0: accuracy {acc0*100:.0f}%")
    for ep in range(1, 13):
        rng.shuffle(data)
        for xx, yy in data:
            Pg = step(P, xx, yy); assert Pg == ref_step(P, xx, yy); P = Pg
        acc = sum(1 for xx, yy in test if predict(P, xx) == yy) / len(test)
        clean = sum(1 for c, t in TEMPLATES.items() if predict(P, t) == c)
        print(f"    epoch {ep:>2}: accuracy {acc*100:.0f}%   (clean {clean}/3)")
    print(f"\n  A two-layer network learned its hidden AND output weights entirely from the fabricated")
    print(f"  backprop circuit — the error routed back through W2[pred]-W2[true], gated to the hidden")
    print(f"  weights, unit steps, byte-exact. Deep learning, in gates, at flat RAM, no GPU.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
