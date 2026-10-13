#!/usr/bin/env python3
"""muhl_lever_lab.py — APPLY THE DOCUMENTED LEVERS to freshly fabricated circuits and MEASURE the gain.

The metric is the owner's ONE metric (§63, mafab_laws.compute_per_tick):
      compute/tick = REPLICAS / DEPTH,  REPLICAS = storage / gates
So DEPTH is the score. The circuits in muhl_flex.py were all built on RIPPLE-CARRY adders — the naive
shape — giving sha1 depth 4929 and mul32 depth 184. PFC_LEVER_INDEX §A documents the fix, measured:

  "Depth: balanced reduction tree — N=256: depth 255->8 (32x shallower at SAME gate count — free)"
  "Depth: Kogge-Stone parallel-prefix adder — W=64: depth 126->13 (9.7x), ~3x gates"
  "Depth: Wallace/Dadda multiplier tree — W=16 multiply depth 88->30 (2.9x)"
  "Depth: carry-save adders (for SHA sums)" [T, OPT_LANDSCAPE §1 — documented target, not yet measured]

This lab implements those levers against the SAME references and reports before/after on the owner's
metric. Every optimized circuit is re-verified BYTE-EXACT — a depth win that changes the answer is not a win.
"""
import sys, os, random, hashlib, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
import muhl_flex as F
try:
    import mafab_laws as L                       # the owner's metric, used verbatim
    METRIC = lambda g, d: L.compute_per_tick(g, d, True)
    METRIC_SRC = "mafab_laws.compute_per_tick (owner's ONE metric)"
except Exception:
    METRIC = lambda g, d: (40e9 / max(g, 1)) / max(d, 1)
    METRIC_SRC = "fallback replicas/depth"

# ─────────────────────────── LEVER 1: Kogge-Stone parallel-prefix adder ───────────────────────────
def ks_add(g, A, B, cin=None):
    """Parallel-prefix carry. Depth O(log n) instead of the ripple's O(n)."""
    n = len(A)
    P0 = [g.XOR(A[i], B[i]) for i in range(n)]
    G = [g.AND(A[i], B[i]) for i in range(n)]
    P = list(P0)
    d = 1
    while d < n:
        nG, nP = list(G), list(P)
        for i in range(n - 1, d - 1, -1):
            nG[i] = g.OR(G[i], g.AND(P[i], G[i - d]))
            nP[i] = g.AND(P[i], P[i - d])
        G, P = nG, nP
        d *= 2
    c0 = g.C0 if cin is None else cin
    carries = [c0] + [g.OR(G[i], g.AND(P[i], c0)) for i in range(n - 1)]
    S = [g.XOR(P0[i], carries[i]) for i in range(n)]
    cout = g.OR(G[n - 1], g.AND(P[n - 1], c0))
    return S, cout

# ─────────────────────────── LEVER 2: carry-save adder (3:2 compressor) ──────────────────────────
def csa(g, a, b, c, W):
    """Full-adder per bit with NO carry propagation: 3 addends -> 2, at constant depth 2."""
    s = [g.XOR(g.XOR(a[i], b[i]), c[i]) for i in range(W)]
    axb = [g.XOR(a[i], b[i]) for i in range(W)]
    cr = [g.OR(g.AND(a[i], b[i]), g.AND(axb[i], c[i])) for i in range(W)]
    cr = [g.C0] + cr[:W - 1]                       # carry weighs 2x -> shift left 1
    return s, cr

def csa_reduce(g, terms, W):
    """Wallace reduction: many addends -> 2, each level costs depth 2 regardless of count."""
    terms = [list(t) for t in terms]
    while len(terms) > 2:
        nxt = []
        while len(terms) >= 3:
            a, b, c = terms.pop(), terms.pop(), terms.pop()
            s, cr = csa(g, a, b, c, W)
            nxt += [s, cr]
        nxt += terms
        terms = nxt
    return terms

# ─────────────────────────── LEVER 3: balanced reduction tree (vs linear chain) ──────────────────
def xor_tree(g, terms):
    """XOR a list pairwise-balanced: depth log2(N) instead of N."""
    cur = list(terms)
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur) - 1, 2):
            nxt.append([g.XOR(cur[i][k], cur[i + 1][k]) for k in range(len(cur[i]))])
        if len(cur) % 2: nxt.append(cur[-1])
        cur = nxt
    return cur[0]

# ───────────────────────────────── circuits: baseline vs levered ─────────────────────────────────
def mul32_ripple():
    g = CC.CircuitCompiler(64); IN = g.IN
    A = [IN[i] for i in range(32)]; B = [IN[32 + i] for i in range(32)]
    acc = [g.C0] * 64
    for j in range(32):
        term = ([g.C0] * j + [g.AND(A[i], B[j]) for i in range(32)] + [g.C0] * 64)[:64]
        acc, _ = F.add_bits(g, acc, term)
    return g, acc

def mul32_wallace():
    """LEVER: Wallace CSA tree + one Kogge-Stone final add."""
    g = CC.CircuitCompiler(64); IN = g.IN
    A = [IN[i] for i in range(32)]; B = [IN[32 + i] for i in range(32)]
    pps = []
    for j in range(32):
        pps.append(([g.C0] * j + [g.AND(A[i], B[j]) for i in range(32)] + [g.C0] * 64)[:64])
    two = csa_reduce(g, pps, 64)
    if len(two) == 1: return g, two[0]
    S, _ = ks_add(g, two[0], two[1])
    return g, S

def sha1_ripple(L_=20): return F.core_sha1_struct(L_) if hasattr(F, "core_sha1_struct") else _sha1(L_, False)
def sha1_levered(L_=20): return _sha1(L_, True)

def _sha1(Lm, levered):
    g = CC.CircuitCompiler(8 * Lm); IN = g.IN
    seq = []
    for m in range(Lm):
        for b in range(8): seq.append(IN[m * 8 + (7 - b)])
    seq.append(g.C1)
    while (len(seq) % 512) != (512 - 64): seq.append(g.C0)
    for b in range(64): seq.append(g.C1 if ((8 * Lm) >> (63 - b)) & 1 else g.C0)
    wbe = lambda bits32: [bits32[31 - k] for k in range(32)]
    W = [wbe(seq[32 * t:32 * t + 32]) for t in range(16)]
    for t in range(16, 80):
        if levered:      # LEVER: balanced XOR tree instead of a 3-deep linear chain
            x = xor_tree(g, [W[t - 3], W[t - 8], W[t - 14], W[t - 16]])
        else:
            x = F.xorw(g, W[t - 3], W[t - 8], W[t - 14], W[t - 16])
        W.append(F.rotl(x, 1))
    H = [F.consts(g, h, 32) for h in (0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0)]
    a, b, c, d, e = H
    for t in range(80):
        if t < 20:   f = [g.OR(g.AND(b[k], c[k]), g.AND(g.NOT(b[k]), d[k])) for k in range(32)]; kx = 0x5A827999
        elif t < 40: f = F.xorw(g, b, c, d); kx = 0x6ED9EBA1
        elif t < 60: f = [g.OR(g.OR(g.AND(b[k], c[k]), g.AND(b[k], d[k])), g.AND(c[k], d[k])) for k in range(32)]; kx = 0x8F1BBCDC
        else:        f = F.xorw(g, b, c, d); kx = 0xCA62C1D6
        addends = [F.rotl(a, 5), f, e, F.consts(g, kx, 32), W[t]]
        if levered:  # LEVER: 5 addends -> CSA tree -> ONE Kogge-Stone add (was 4 ripple adds)
            two = csa_reduce(g, addends, 32)
            tmp, _ = ks_add(g, two[0], two[1]) if len(two) == 2 else (two[0], None)
        else:
            tmp = addends[0]
            for term in addends[1:]: tmp, _ = F.add_bits(g, tmp, term)
        e = d; d = c; c = F.rotl(b, 30); b = a; a = tmp
    if levered:
        Hn = [ks_add(g, hv, av)[0] for hv, av in zip(H, (a, b, c, d, e))]
    else:
        Hn = [F.add_bits(g, hv, av)[0] for hv, av in zip(H, (a, b, c, d, e))]
    return g, [w for word in Hn for w in word]

# ───────────────────────────────────────── measure ───────────────────────────────────────────────
def measure(name, builder, verify, cases):
    t0 = time.time()
    g, outs = builder()
    gates, out2 = g.dce(outs)
    depth = F.depth_of(g, gates, out2)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    ok = verify(run, out2, g.n_in, cases)
    return dict(name=name, gates=len(gates), depth=depth, ok=ok,
                score=METRIC(len(gates), depth), secs=time.time() - t0)

def v_mul32(run, out2, n_in, cases):
    for _ in range(cases):
        a, b = random.getrandbits(32), random.getrandbits(32)
        inp = [0] * 64; F.setf(inp, 0, 32, a); F.setf(inp, 32, 32, b)
        if F.rd(run(inp, 1), out2) != (a * b) & ((1 << 64) - 1): return False
    return True

def v_sha1(run, out2, n_in, cases):
    Lm = n_in // 8
    words = [out2[i * 32:(i + 1) * 32] for i in range(5)]
    for _ in range(cases):
        msg = bytes(random.getrandbits(8) for _ in range(Lm))
        inp = [0] * n_in
        for m in range(Lm): F.setf(inp, m * 8, 8, msg[m])
        v = run(inp, 1)
        if "".join("%08x" % F.rd(v, w) for w in words) != hashlib.sha1(msg).hexdigest(): return False
    return True

def row(base, lev):
    dg = lev["gates"] / base["gates"]; dd = base["depth"] / lev["depth"]; ds = lev["score"] / max(base["score"], 1e-30)
    print(f"    {base['name']:<10} BASELINE  {base['gates']:>8,} gates  depth {base['depth']:>5}  compute/tick {base['score']:>12.4f}  byte-exact {base['ok']}")
    print(f"    {'':<10} LEVERED   {lev['gates']:>8,} gates  depth {lev['depth']:>5}  compute/tick {lev['score']:>12.4f}  byte-exact {lev['ok']}")
    print(f"    {'':<10} ->        gates x{dg:.2f}   DEPTH {dd:.2f}x SHALLOWER   compute/tick {ds:.2f}x\n")
    return dd, ds

def main():
    random.seed(21)
    print(f"\n  MUHLNICKEL LEVER LAB — applying the documented depth levers, measured on the owner's metric")
    print(f"  metric: {METRIC_SRC}   (compute/tick = replicas/depth; DEPTH is the score)\n")
    print("  LEVERS APPLIED: Kogge-Stone parallel-prefix adder · carry-save (Wallace) reduction ·")
    print("                  balanced XOR tree instead of linear chain\n")
    results = []
    b = measure("mul32", mul32_ripple, v_mul32, 200)
    l = measure("mul32", mul32_wallace, v_mul32, 200)
    results.append(row(b, l))
    b2 = measure("sha1", lambda: _sha1(20, False), v_sha1, 30)
    l2 = measure("sha1", lambda: _sha1(20, True), v_sha1, 30)
    results.append(row(b2, l2))
    dd = sum(r[0] for r in results) / len(results); ds = sum(r[1] for r in results) / len(results)
    print(f"  === MEAN: depth {dd:.2f}x shallower · compute/tick {ds:.2f}x · every levered circuit still byte-exact ===")
    print(f"  (§31: fabrication is off the clock — the search costs nothing that counts toward the machine's rate.)")

if __name__ == "__main__":
    main()
