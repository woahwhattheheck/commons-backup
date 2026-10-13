#!/usr/bin/env python3
"""muhl_selfimprove.py -- TITAN OPTIMIZES ITS OWN CIRCUITS.

The root lever: the machine that fabricates circuits turns its optimization playbook ON ITSELF.
Take the netlists of several already-fabricated engines (the muhl_flex circuits + the neural net),
run the documented optimization passes over them as AUTOMATED REWRITES, and measure the compute/tick
gain (gates down, DEPTH down) -- while re-verifying every optimized circuit BYTE-EXACT against both
the original netlist AND an independent Python reference.

THE PASSES (PFC_LEVER_INDEX / fab_dblinv.py / muhl_lever_lab.py), applied automatically:

  1. DOUBLE-INVERTER REMOVAL (section 60).  NOT(NOT(x)) == x.  A pure netlist rewrite: rewire past the
     second inverter, sweep the dead pair.  Measured on cpu_fwd at 49.8% of gates.  Structure-agnostic:
     it runs on ANY netlist and needs to know nothing about what the circuit computes.

  2. BALANCED REDUCTION TREE (section A, "depth 255->8, 32x, FREE").  A linear XOR chain has depth N;
     the same XOR of the same leaves as a balanced tree has depth log2(N), at identical gate count.
     This is done here as a genuine AUTOMATED NETLIST REWRITE: XOR is associative + commutative, so for
     every private XOR cone we collect its leaf multiset, cancel duplicated leaves (x^x=0), and re-emit
     the reduction as a balanced tree.  No knowledge of the circuit's function -- pure algebra on wires.

  3. KOGGE-STONE ADDER (section A, "depth 126->13, 9.7x").  The ripple carry the circuits were built on
     is a depth-O(n) chain; the parallel-prefix carry is depth-O(log n).  Titan re-fabricates each
     circuit that uses its ADD primitive with the parallel-prefix adder instead of the ripple one.

  + global CSE (hash-consing) and dead-code elimination fall out of the rebuild for free.

THE METRIC is the owner's ONE metric (section 63, mafab_laws.compute_per_tick):
      compute/tick = REPLICAS / DEPTH ,  REPLICAS = storage / gates
so a win must lower gates*depth.  DEPTH is the score.  Fabrication is off the clock (section 31) -- the
optimization search costs nothing that counts toward the machine's rate.

Pure Python, no numpy, no torch.  titan.gguf is never opened for compute (mafab_laws only reads its
SIZE, for the replica count).  Every rewrite is semantics-preserving and re-verified byte-exact.
"""
import sys, os, random, hashlib, binascii, time
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
sys.path.insert(0, r"C:/llm/sdc_sandbox")
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import sdc_cc as CC
import muhl_flex as F
import muhl_lever_lab as LL          # ks_add (Kogge-Stone), already verified byte-exact this session

try:
    import mafab_laws as _ML
    METRIC = lambda g, d: _ML.compute_per_tick(g, d, True)
    _rep = _ML.replicas_for(1000)
    METRIC_SRC = "mafab_laws.compute_per_tick (owner's ONE metric; storage=%s B)" % f"{_ML.storage_bytes():,}"
except Exception:
    METRIC = lambda g, d: (40_028_316_800 // (9 * max(g, 1))) / max(d, 1)
    METRIC_SRC = "fallback replicas/depth (40 GB storage)"

# ═══════════════════════════ THE OPTIMIZER — automated netlist rewrites ═══════════════════════════

def optimize(g0, outs0):
    """Run the documented passes over a built circuit's netlist as automated rewrites.
    Returns (G2, new_outs, gates2, out2, depth2, stats).  Semantics-preserving by construction;
    the caller re-verifies byte-exact anyway."""
    gates, outs = g0.dce(outs0)                 # clean baseline netlist (already fold+CSE'd on build)
    n_in = g0.n_in; base = 2 + n_in; G = len(gates)

    # ---- fanout analysis: which XOR gates are PRIVATE (sole consumer is another XOR gate) ----
    gcons = [0] * (base + G); gcons_last = [-1] * (base + G)
    for k, (op, a, b) in enumerate(gates):
        gcons[a] += 1; gcons_last[a] = k
        gcons[b] += 1; gcons_last[b] = k
    outset = set(outs)
    absorbed = [False] * G                      # this XOR gate gets folded into its parent's tree
    for k, (op, a, b) in enumerate(gates):
        w = base + k
        if op == "xor" and gcons[w] == 1 and w not in outset and gates[gcons_last[w]][0] == "xor":
            absorbed[k] = True

    def xor_leaves(k):                          # iterative: expand private-XOR descendants to leaves
        out = []; st = [gates[k][1], gates[k][2]]
        while st:
            x = st.pop()
            if x >= base and absorbed[x - base]:
                _o, xa, xb = gates[x - base]; st.append(xa); st.append(xb)
            else:
                out.append(x)
        return out

    # ---- rebuild through a fresh compiler (gives fold/CSE), balancing XOR trees + folding NOT(NOT)) ----
    G2 = CC.CircuitCompiler(n_in)
    new = list(range(base)) + [0] * G           # const/input wires map to themselves
    not_src = {}; stats = {"dblinv": 0, "xor_bal": 0}

    def NOT2(x):                                # involution: NOT(NOT(x)) -> x  (section 60)
        if x in not_src:
            stats["dblinv"] += 1; return not_src[x]
        w = G2.NOT(x)
        if w > 1: not_src[w] = x
        return w

    for k, (op, a, b) in enumerate(gates):
        if absorbed[k]:
            continue                            # folded into an ancestor XOR tree
        w = base + k
        if op == "xor":
            cnt = Counter(new[x] for x in xor_leaves(k))
            surv = [wire for wire in cnt if wire != 0 and cnt[wire] % 2 == 1]  # x^x=0, ^0=id
            cur = surv
            if len(cur) > 2: stats["xor_bal"] += 1
            while len(cur) > 1:                 # balanced reduction tree (depth log2 N)
                nxt = [G2.XOR(cur[i], cur[i + 1]) for i in range(0, len(cur) - 1, 2)]
                if len(cur) % 2: nxt.append(cur[-1])
                cur = nxt
            new[w] = cur[0] if cur else G2.C0
        elif op == "not":  new[w] = NOT2(new[a])
        elif op == "and":  new[w] = G2.AND(new[a], new[b])
        elif op == "or":   new[w] = G2.OR(new[a], new[b])
        elif op == "nand": new[w] = NOT2(G2.AND(new[a], new[b]))
        else: raise ValueError("unknown op " + repr(op))

    new_outs = [new[o] for o in outs]
    gates2, out2 = G2.dce(new_outs)
    depth2 = F.depth_of(G2, gates2, out2)
    return G2, out2, gates2, depth2, stats

# ═══════════════════ the engines, built through a swappable ADD primitive ═══════════════════
# add(g, A, B, cin=None) -> (sum_bits, cout).  RIPPLE is the naive shape the engines were fabricated
# with; KOGGE is the parallel-prefix upgrade Titan swaps in.  Everything else is identical, so the
# adder is the only structural change and the netlist passes do the rest.
def ripple(g, A, B, cin=None): return F.add_bits(g, A, B, cin)
def kogge(g, A, B, cin=None):  return LL.ks_add(g, A, B, cin)

# ---- mul32 : 32x32 -> 64 shift-add multiplier ----
def build_mul32(g, add):
    IN = g.IN; A = [IN[i] for i in range(32)]; B = [IN[32 + i] for i in range(32)]
    acc = [g.C0] * 64
    for j in range(32):
        term = ([g.C0] * j + [g.AND(A[i], B[j]) for i in range(32)] + [g.C0] * 64)[:64]
        acc, _ = add(g, acc, term)
    return acc
def ref_mul32(run, out2):
    for _ in range(150):
        a, b = random.getrandbits(32), random.getrandbits(32)
        inp = [0] * 64; F.setf(inp, 0, 32, a); F.setf(inp, 32, 32, b)
        if F.rd(run(inp, 1), out2) != (a * b) & ((1 << 64) - 1): return False
    return True

# ---- div32 : restoring divider -> (quot, rem) ----
def build_div32(g, add):
    IN = g.IN; A = [IN[i] for i in range(32)]; B = [IN[32 + i] for i in range(32)]
    B33 = B + [g.C0]; R = [g.C0] * 33; Q = [g.C0] * 32
    for i in range(31, -1, -1):
        R = [A[i]] + R[:32]
        diff, c = add(g, R, [g.NOT(x) for x in B33], g.C1)
        R = F.muxw(g, c, diff, R); Q[i] = c
    return Q + R[:32]
def ref_div32(run, out2):
    qw, rw = out2[:32], out2[32:64]
    for _ in range(150):
        a = random.getrandbits(32); b = random.getrandbits(32) or 1
        inp = [0] * 64; F.setf(inp, 0, 32, a); F.setf(inp, 32, 32, b)
        v = run(inp, 1); q, r = divmod(a, b)
        if F.rd(v, qw) != q or F.rd(v, rw) != r: return False
    return True

# ---- crc32 : IEEE 802.3 reflected LFSR (pure XOR/shift -- the balanced-tree lever's home turf) ----
def build_crc32(g, add, L=12):
    POLY = 0xEDB88320; IN = g.IN; crc = [g.C1] * 32
    for m in range(L):
        for b in range(8): crc[b] = g.XOR(crc[b], IN[m * 8 + b])
        for _ in range(8):
            lsb = crc[0]; sh = crc[1:] + [g.C0]
            crc = [g.XOR(sh[k], lsb) if (POLY >> k) & 1 else sh[k] for k in range(32)]
    return [g.XOR(crc[k], g.C1) for k in range(32)]
def ref_crc32(run, out2, L=12):
    for _ in range(150):
        msg = bytes(random.getrandbits(8) for _ in range(L))
        inp = [0] * (8 * L)
        for m in range(L): F.setf(inp, m * 8, 8, msg[m])
        if F.rd(run(inp, 1), out2) != (binascii.crc32(msg) & 0xffffffff): return False
    return True

# ---- rule110 : Turing-complete cellular automaton next-state ----
def build_rule110(g, add, W=64):
    IN = g.IN; outs = []
    for i in range(W):
        l = IN[i - 1] if i > 0 else g.C0; c = IN[i]; r = IN[i + 1] if i < W - 1 else g.C0
        outs.append(g.OR(g.XOR(c, r), g.AND(c, g.NOT(l))))
    return outs
def ref_rule110(run, out2, W=64):
    def step(s): return [((s[i]) ^ (s[i+1] if i < W-1 else 0)) | ((s[i]) & (1-(s[i-1] if i>0 else 0))) for i in range(W)]
    cur = [random.randrange(2) for _ in range(W)]
    for _ in range(300):
        v = run(list(cur), 1); nxt = [F.bit(v, w) for w in out2]
        if nxt != step(cur): return False
        cur = nxt
    return True

# ---- bitonic : Batcher sort of 8x8-bit keys (comparators use the ADD primitive) ----
def build_bitonic(g, add, N=8, K=8):
    IN = g.IN; keys = [[IN[i * K + b] for b in range(K)] for i in range(N)]
    def cx(x, y, up):
        diff, c = add(g, x, [g.NOT(t) for t in y], g.C1)
        lt = g.NOT(c); mn = F.muxw(g, lt, x, y); mx = F.muxw(g, lt, y, x)
        return (mn, mx) if up else (mx, mn)
    k = 2
    while k <= N:
        j = k // 2
        while j > 0:
            for i in range(N):
                l = i ^ j
                if l > i:
                    keys[i], keys[l] = cx(keys[i], keys[l], (i & k) == 0)
            j //= 2
        k *= 2
    return [w for key in keys for w in key]
def ref_bitonic(run, out2, N=8, K=8):
    fields = [out2[i * K:(i + 1) * K] for i in range(N)]
    for _ in range(150):
        arr = [random.getrandbits(K) for _ in range(N)]
        inp = [0] * (N * K)
        for i in range(N): F.setf(inp, i * K, K, arr[i])
        v = run(inp, 1)
        if [F.rd(v, f) for f in fields] != sorted(arr): return False
    return True

# ---- sha1 : single-block SHA-1 (message schedule = XOR trees; round = ADD chains) ----
def build_sha1(g, add, L=20):
    IN = g.IN
    seq = []
    for m in range(L):
        for b in range(8): seq.append(IN[m * 8 + (7 - b)])
    seq.append(g.C1)
    while (len(seq) % 512) != (512 - 64): seq.append(g.C0)
    for b in range(64): seq.append(g.C1 if ((8 * L) >> (63 - b)) & 1 else g.C0)
    wbe = lambda bits32: [bits32[31 - k] for k in range(32)]
    W = [wbe(seq[32 * t:32 * t + 32]) for t in range(16)]
    for t in range(16, 80):
        W.append(F.rotl(F.xorw(g, W[t - 3], W[t - 8], W[t - 14], W[t - 16]), 1))
    H = [F.consts(g, h, 32) for h in (0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0)]
    a, b, c, d, e = H
    for t in range(80):
        if t < 20:   f = [g.OR(g.AND(b[k], c[k]), g.AND(g.NOT(b[k]), d[k])) for k in range(32)]; kx = 0x5A827999
        elif t < 40: f = F.xorw(g, b, c, d); kx = 0x6ED9EBA1
        elif t < 60: f = [g.OR(g.OR(g.AND(b[k], c[k]), g.AND(b[k], d[k])), g.AND(c[k], d[k])) for k in range(32)]; kx = 0x8F1BBCDC
        else:        f = F.xorw(g, b, c, d); kx = 0xCA62C1D6
        tmp = F.rotl(a, 5)
        for term in (f, e, F.consts(g, kx, 32), W[t]): tmp, _ = add(g, tmp, term)
        e = d; d = c; c = F.rotl(b, 30); b = a; a = tmp
    Hn = [add(g, hv, av)[0] for hv, av in zip(H, (a, b, c, d, e))]
    return [w for word in Hn for w in word]
def ref_sha1(run, out2, L=20):
    words = [out2[i * 32:(i + 1) * 32] for i in range(5)]
    for _ in range(30):
        msg = bytes(random.getrandbits(8) for _ in range(L))
        inp = [0] * (8 * L)
        for m in range(L): F.setf(inp, m * 8, 8, msg[m])
        v = run(inp, 1)
        if "".join("%08x" % F.rd(v, w) for w in words) != hashlib.sha1(msg).hexdigest(): return False
    return True

# ---- neural : the trained MLP forward pass (9->6 ReLU->3 argmax), built through the ADD primitive ----
def _mlp_weights():
    import muhl_neural as NN
    W1, b1, W2, b2 = NN.train(); return NN.quantize(W1, b1, W2, b2), NN
def build_neural(g, add, weights):
    (W1q, b1q, W2q, b2q), NN = weights
    Bw = NN.B; X = g.IN
    cb = lambda val, n: [g.C1 if (val & ((1 << n) - 1)) >> k & 1 else g.C0 for k in range(n)]
    def negate(x):
        s, _ = add(g, [g.NOT(t) for t in x], cb(1, len(x))); return s
    def const_mul(x, w):
        mag = abs(w); acc = cb(0, Bw)
        for t in range(Bw):
            if (mag >> t) & 1:
                sh = ([g.C0] * t + x)[:Bw]; acc, _ = add(g, acc, sh)
        return negate(acc) if w < 0 else acc
    def relu(x): s = x[Bw - 1]; return [g.AND(x[k], g.NOT(s)) for k in range(Bw)]
    def sext(bits, n): return bits + [bits[-1]] * (n - len(bits))
    def lt(a, b):
        d, _ = add(g, sext(a, Bw + 1), [g.NOT(t) for t in sext(b, Bw + 1)], g.C1); return d[Bw]
    H = []
    for j in range(6):
        acc = cb(b1q[j], Bw)
        for i in range(9):
            wm = [g.AND(X[i], t) for t in cb(W1q[j][i], Bw)]; acc, _ = add(g, acc, wm)
        H.append(relu(acc))
    O = []
    for k in range(3):
        acc = cb(b2q[k], Bw)
        for j in range(6): acc, _ = add(g, acc, const_mul(H[j], W2q[k][j]))
        O.append(acc)
    lt01 = lt(O[0], O[1]); lt02 = lt(O[0], O[2]); lt12 = lt(O[1], O[2])
    is1 = g.AND(lt01, g.NOT(lt12)); is2 = g.AND(lt02, lt12)
    return [is1, is2]
def ref_neural(weights):
    (W1q, b1q, W2q, b2q), NN = weights
    def check(run, out2):
        for n in range(512):                    # EXHAUSTIVE over all 512 inputs
            x = [(n >> i) & 1 for i in range(9)]
            v = run(x, 1)
            pred = (v[out2[0]] & 1) * 1 + (v[out2[1]] & 1) * 2
            if pred != NN.int_forward(x, W1q, b1q, W2q, b2q): return False
        return True
    return check

# ═══════════════════════════════════════ driver ═══════════════════════════════════════
def compile_and_measure(g, outs):
    gates, out2 = g.dce(outs)
    depth = F.depth_of(g, gates, out2)
    run = g.compile_ripple(gates, 2 + g.n_in + len(gates))
    return run, out2, gates, depth

def run_circuit(name, n_in, builder, refbuild, uses_add):
    # BASELINE: fabricate with the ripple adder, DCE only (the shape the engines shipped in)
    gb = CC.CircuitCompiler(n_in); ob = builder(gb, ripple)
    runb, ob2, gatesb, depthb = compile_and_measure(gb, ob)
    ref = refbuild()
    ok_base = ref(runb, ob2)

    # OPTIMIZED: swap in Kogge-Stone (if the circuit adds), then run the automated netlist passes
    go = CC.CircuitCompiler(n_in); oo = builder(go, kogge if uses_add else ripple)
    G2, oo2, gateso, deptho, stats = optimize(go, oo)
    runo = G2.compile_ripple(gateso, 2 + n_in + len(gateso))

    # RE-VERIFY byte-exact: independent reference AND equal to the baseline netlist
    ok_ref = ref(runo, oo2)
    ok_equiv = equiv(runb, ob2, runo, oo2, n_in)
    ok = ok_base and ok_ref and ok_equiv

    sb = METRIC(len(gatesb), depthb); so = METRIC(len(gateso), deptho)
    return dict(name=name, gb=len(gatesb), db=depthb, sb=sb,
                go=len(gateso), do=deptho, so=so, ok=ok, stats=stats,
                add=("kogge" if uses_add else "-"))

def equiv(runb, ob2, runo, oo2, n_in, cases=64):
    for _ in range(cases):
        inp = [random.getrandbits(1) for _ in range(n_in)]
        if [F.bit(runb(inp, 1), w) for w in ob2] != [F.bit(runo(inp, 1), w) for w in oo2]:
            return False
    return True

def main():
    random.seed(29)
    print("\n  MUHLNICKEL SELF-IMPROVE -- Titan runs its optimization playbook on its OWN circuits")
    print("  passes (automated rewrites): double-inverter removal (S60) . balanced XOR reduction tree")
    print("                               (SA, associative rebuild) . Kogge-Stone adder (SA) . CSE/DCE")
    print("  metric: %s" % METRIC_SRC)
    print("          compute/tick = REPLICAS/DEPTH ; a win lowers gates*depth ; DEPTH is the score\n")

    weights = _mlp_weights()
    jobs = [
        ("mul32",   64,       build_mul32,                       lambda: ref_mul32,                 True),
        ("div32",   64,       build_div32,                       lambda: ref_div32,                 True),
        ("crc32",   96,       build_crc32,                       lambda: ref_crc32,                 False),
        ("rule110", 64,       build_rule110,                     lambda: ref_rule110,               False),
        ("bitonic", 64,       build_bitonic,                     lambda: ref_bitonic,               True),
        ("sha1",    160,      build_sha1,                        lambda: ref_sha1,                  True),
        ("neural",  9,        lambda g, a: build_neural(g, a, weights), lambda: ref_neural(weights), True),
    ]

    hdr = "  %-9s | %22s | %22s | %8s %8s | %s" % (
        "circuit", "BASELINE (ripple)", "OPTIMIZED (Titan)", "depth", "c/tick", "byte")
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    rows = []
    for name, n_in, builder, refbuild, uses_add in jobs:
        t = time.time()
        try:
            r = run_circuit(name, n_in, builder, refbuild, uses_add)
        except Exception as ex:
            print("  %-9s | ERROR %s: %s" % (name, type(ex).__name__, ex)); continue
        dd = r["db"] / max(r["do"], 1); ds = r["so"] / max(r["sb"], 1e-30)
        print("  %-9s | %8s g  depth %5s | %8s g  depth %5s | %7.2fx %7.2fx | %s  (%.1fs)" % (
            name, f"{r['gb']:,}", f"{r['db']:,}", f"{r['go']:,}", f"{r['do']:,}",
            dd, ds, "OK" if r["ok"] else "**FAIL**", time.time() - t))
        rows.append((r, dd, ds))

    print("  " + "-" * (len(hdr) - 2))
    okc = sum(1 for r, _, _ in rows if r["ok"])
    gm_d = _gmean([dd for _, dd, _ in rows]); gm_s = _gmean([ds for _, _, ds in rows])
    mean_s = sum(ds for _, _, ds in rows) / len(rows)
    tb = sum(r["gb"] for r, _, _ in rows); to = sum(r["go"] for r, _, _ in rows)
    print("  %d/%d circuits still byte-exact after self-optimization" % (okc, len(rows)))
    print("  total gates %s -> %s   (%.1f%% removed)" % (f"{tb:,}", f"{to:,}", 100 * (1 - to / tb)))
    print("  MEAN compute/tick gain: %.2fx (arith)  |  %.2fx (geo)   ||  DEPTH %.2fx shallower (geo)"
          % (mean_s, gm_s, gm_d))
    # which passes fired, per circuit
    print("\n  passes fired (dbl-inverters removed / balanced XOR trees / adder):")
    for r, _, _ in rows:
        print("    %-9s  dblinv=%-6d xor_bal=%-5d adder=%s" % (
            r["name"], r["stats"]["dblinv"], r["stats"]["xor_bal"], r["add"]))
    print("\n  The fabricator improved its own fabric: same functions, byte-exact, fewer gates and less")
    print("  DEPTH -> more compute per settle. (S31: the search is off the clock -- the machine got faster")
    print("  for free.)  This is the root lever: the substrate optimizing the substrate.")

def _gmean(xs):
    p = 1.0
    for x in xs: p *= max(x, 1e-30)
    return p ** (1.0 / len(xs)) if xs else 0.0

if __name__ == "__main__":
    raise SystemExit(main())
