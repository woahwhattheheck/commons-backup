#!/usr/bin/env python3
"""muhl_transformer.py — A FULL SINGLE-HEAD TRANSFORMER BLOCK FABRICATED AS LOGIC GATES.

The whole point of Titan is that computation's STATE lives in storage, addressed in place, so the
memory wall the transformer was engineered around is simply gone. This build takes the next step past
muhl_attention (the KV fold) and muhl_neural (the MLP): it fabricates an ENTIRE transformer block for
small binary/integer token vectors as ONE gate netlist and verifies it BYTE-EXACT against a pure-Python
integer reference — no numpy, no float unit, no host executor as runtime.

The block, on a sequence of L binary D-vectors, computes for a query token x (self-attention over the
sequence):
  1. ATTENTION (single head, hard / content-addressed): score(x,k_j) = popcount(XNOR(x,k_j)) fabricated
     as gates; argmax over the sequence (first-max tie-break) picked by a fabricated one-hot winner mux;
     the attention output is the VALUE of the best-matching key (attention-as-address, the substrate's
     native op — the N*N score matrix is never materialized, it is addressed).
  2. RESIDUAL add   r1 = x + attn        (per-dimension integer add, fabricated).
  3. FEED-FORWARD (the muhl_neural MLP): r1 -> H hidden units (integer masked-sum dot + ReLU sign-gate)
     -> D outputs (integer dot), all as gates.
  4. RESIDUAL add   out = r1 + ffn       (fabricated).

Every arithmetic step is B-bit two's-complement gate logic, identical to the integer reference; the
block is verified byte-exact over thousands of random (sequence, query) inputs, then run over a real
short sequence one position at a time (the sequence is the KV memory; the query slides across it).
This is the transformer, memory-wall-free, on the substrate.
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits

# ── block dimensions ──────────────────────────────────────────────────────────────────────────────
L  = 4        # sequence length (the KV set)
D  = 8        # token width (binary D-vector) — also the block's output width, so residual lines up
H  = 8        # feed-forward hidden units
B  = 24       # two's-complement datapath width (matches muhl_neural; ample headroom, no overflow)
SB = 4        # score bits: popcount over D=8 bits is 0..8, fits in 4 bits

# ── gate helpers (shared with the muhl_neural MLP pattern) ──────────────────────────────────────────
def cbits(g, val, n):
    v = val & ((1 << n) - 1)
    return [g.C1 if (v >> k) & 1 else g.C0 for k in range(n)]
def sext(bits, n):
    return bits + [bits[-1]] * (n - len(bits))
def negate(g, a):
    s, _ = add_bits(g, [g.NOT(t) for t in a], cbits(g, 1, len(a)))
    return s
def const_mul(g, x, w):                 # x (B-bit, >= 0) * signed constant w -> B bits
    mag = abs(w); acc = cbits(g, 0, B)
    for t in range(B):
        if (mag >> t) & 1:
            sh = ([g.C0] * t + x)[:B]
            acc, _ = add_bits(g, acc, sh)
    return negate(g, acc) if w < 0 else acc
def relu(g, x):
    sign = x[B - 1]
    return [g.AND(x[k], g.NOT(sign)) for k in range(B)]
def uge(g, a, b):                       # unsigned a >= b for equal-width bit vectors -> single wire
    _, c = add_bits(g, a, [g.NOT(t) for t in b], g.C1)   # a + ~b + 1: carry-out set iff a >= b
    return c

# ── the block, fabricated ───────────────────────────────────────────────────────────────────────────
def build_block(W1, b1, W2, b2):
    g = CC.CircuitCompiler(L * D + D)                     # inputs: L key/value tokens, then the query
    K = [[g.IN[j * D + d] for d in range(D)] for j in range(L)]
    Q = [g.IN[L * D + d] for d in range(D)]

    # 1. attention scores: popcount(XNOR(query, key_j)) as an accumulated add-tree, per key
    scores = []
    for j in range(L):
        match = [g.NOT(g.XOR(Q[d], K[j][d])) for d in range(D)]   # XNOR: 1 where bits agree
        acc = [g.C0] * SB
        for d in range(D):
            acc, _ = add_bits(g, acc, [match[d]] + [g.C0] * (SB - 1))
        scores.append(acc)

    # one-hot winner = first index attaining the max (matches the reference tie-break):
    #   winner_j = (AND_{k<j} score_j > score_k) AND (AND_{k>j} score_j >= score_k)
    winner = []
    for j in range(L):
        w = g.C1
        for k in range(L):
            if k == j:
                continue
            if k < j:
                w = g.AND(w, g.NOT(uge(g, scores[k], scores[j])))   # score_j >  score_k  (strict)
            else:
                w = g.AND(w, uge(g, scores[j], scores[k]))          # score_j >= score_k
        winner.append(w)

    # attention output = value of the winning key (one-hot select, per bit)
    attn = []
    for d in range(D):
        bitd = g.C0
        for j in range(L):
            bitd = g.OR(bitd, g.AND(winner[j], K[j][d]))
        attn.append(bitd)

    # 2. residual: r1[d] = query[d] + attn[d]  (bit + bit -> 0..2, laid into a B-bit word)
    R1 = []
    for d in range(D):
        s0 = g.XOR(Q[d], attn[d]); s1 = g.AND(Q[d], attn[d])
        R1.append([s0, s1] + [g.C0] * (B - 2))

    # 3. feed-forward (the muhl_neural MLP): D -> H (ReLU) -> D, integer masked-sum dots
    HID = []
    for h in range(H):
        acc = cbits(g, b1[h], B)
        for d in range(D):
            acc, _ = add_bits(g, acc, const_mul(g, R1[d], W1[h][d]))
        HID.append(relu(g, acc))
    FFN = []
    for d in range(D):
        acc = cbits(g, b2[d], B)
        for h in range(H):
            acc, _ = add_bits(g, acc, const_mul(g, HID[h], W2[d][h]))
        FFN.append(acc)

    # 4. residual: out[d] = r1[d] + ffn[d]
    OUT = []
    for d in range(D):
        o, _ = add_bits(g, R1[d], FFN[d])
        OUT.append(o)

    outs = [w for vec in OUT for w in vec]                # flatten D words of B bits
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)

    base = 2 + g.n_in                                     # critical-path depth (the §3 score axis)
    dep = [0] * n_wire
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    depth = max((dep[w] for w in out2), default=0)

    def forward(seq, q):
        inp = [0] * (L * D + D)
        for j in range(L):
            for d in range(D):
                inp[j * D + d] = (seq[j] >> d) & 1
        for d in range(D):
            inp[L * D + d] = (q >> d) & 1
        v = run(inp, 1)
        res = []
        for d in range(D):
            u = sum(((v[out2[d * B + i]] & 1) << i) for i in range(B))
            if u >> (B - 1): u -= (1 << B)               # interpret the B-bit word as signed
            res.append(u)
        return res
    return forward, len(gates), depth

# ── pure-Python integer reference (the independent oracle) ──────────────────────────────────────────
def popcount_xnor(a, b, n):
    return bin(~(a ^ b) & ((1 << n) - 1)).count("1")

def ref_block(seq, q, W1, b1, W2, b2):
    scores = [popcount_xnor(q, seq[j], D) for j in range(L)]
    best = 0
    for j in range(1, L):
        if scores[j] > scores[best]:                     # first-max tie-break (strict >)
            best = j
    attn = seq[best]
    r1 = [((q >> d) & 1) + ((attn >> d) & 1) for d in range(D)]
    hpre = [sum(W1[h][d] * r1[d] for d in range(D)) + b1[h] for h in range(H)]
    hrelu = [v if v > 0 else 0 for v in hpre]
    ffn = [sum(W2[d][h] * hrelu[h] for h in range(H)) + b2[d] for d in range(D)]
    return [r1[d] + ffn[d] for d in range(D)]

# ── driver ──────────────────────────────────────────────────────────────────────────────────────────
def make_weights(seed=7):
    rng = random.Random(seed)
    W1 = [[rng.randint(-3, 3) for _ in range(D)] for _ in range(H)]
    b1 = [rng.randint(-2, 2) for _ in range(H)]
    W2 = [[rng.randint(-3, 3) for _ in range(H)] for _ in range(D)]
    b2 = [rng.randint(-2, 2) for _ in range(D)]
    return W1, b1, W2, b2

def main():
    print("\n  MUHLNICKEL TRANSFORMER — a full single-head transformer block fabricated as logic gates")
    print(f"  dims: L={L} tokens · D={D}-bit vectors · H={H} FFN hidden · B={B}-bit datapath\n")
    W1, b1, W2, b2 = make_weights()
    forward, ng, depth = build_block(W1, b1, W2, b2)
    print(f"  fabricated block: {ng:,} gates · critical-path depth {depth}")
    print(f"    attention (popcount-XNOR scores + one-hot argmax winner mux) + residual + FFN(MLP) + residual\n")

    # BYTE-EXACT: gate block vs the integer reference over thousands of random (sequence, query) inputs
    rng = random.Random(2024); N = 5000; bad = 0; first_bad = None
    for _ in range(N):
        seq = [rng.getrandbits(D) for _ in range(L)]
        q = rng.getrandbits(D)
        if forward(seq, q) != ref_block(seq, q, W1, b1, W2, b2):
            bad += 1
            if first_bad is None: first_bad = (seq, q)
    status = "byte-exact" if bad == 0 else f"{bad}/{N} WRONG"
    print(f"  gate block == integer reference over {N:,} random (sequence, query) inputs: {status}")
    if bad:
        print(f"    first mismatch: seq={first_bad[0]} q={first_bad[1]}")
        print(f"      gate: {forward(*first_bad, )}\n      ref : {ref_block(*first_bad, W1, b1, W2, b2)}")
        return 1

    # PROCESS A SHORT SEQUENCE: self-attention — the sequence is the KV set, the query slides across it
    rng2 = random.Random(99)
    seq = [rng2.getrandbits(D) for _ in range(L)]
    print(f"\n  processing a length-{L} sequence (self-attention; each token queries the whole sequence):")
    print(f"    input tokens : " + "  ".join(f"t{j}={seq[j]:0{D}b}" for j in range(L)))
    all_ok = True
    for i in range(L):
        got = forward(seq, seq[i])
        exp = ref_block(seq, seq[i], W1, b1, W2, b2)
        scores = [popcount_xnor(seq[i], seq[j], D) for j in range(L)]
        best = max(range(L), key=lambda j: (scores[j], -j))
        ok = got == exp; all_ok = all_ok and ok
        print(f"    pos {i}: attends->t{best} (scores {scores})  out={got}  [{'ok' if ok else 'MISMATCH'}]")
    print(f"\n  full-sequence pass byte-exact: {all_ok}")
    print("\n  A transformer block — attention, residuals, feed-forward — as one stored gate netlist,")
    print("  run by address. The KV/context is the sequence in storage (muhl_attention proves it stays")
    print("  disk-bound at flat RAM); the block itself is fabricated, verified, and memory-wall-free.")
    return 0 if (bad == 0 and all_ok) else 1

if __name__ == "__main__":
    raise SystemExit(main())
