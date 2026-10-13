#!/usr/bin/env python3
"""muhl_consensus.py -- a Byzantine majority-VOTE / consensus circuit fabricated on the
Muhlnickel substrate as pure NAND/AND/OR/XOR/NOT gates, verified BYTE-EXACT vs a pure-Python
reference (no numpy, no host executor at runtime, no touching titan.gguf).

THE CIRCUIT (fault-tolerant Titan servers):
  N replica nodes each broadcast a V-bit value (a proposed result / block hash slice / state).
  The circuit fabricates, in storage, a one-and-done consensus resolver:

    1. equality matrix  eq[i][j] = (val_i == val_j)          (XNOR over V bits, AND-reduced)
    2. agreement counts count_i  = popcount_j eq[i][j]        (how many nodes hold val_i, incl self)
    3. plurality winner via argmax over count_i, tie-break LOWEST index (deterministic) ->
       MAJORITY VALUE  = the value the most nodes agree on
    4. FAULT bit       = 1  when the winning agreement < ceil(2N/3)  (no Byzantine supermajority)

  Because a Byzantine quorum needs > 2/3 honest, the fault bit flags exactly the states where
  fewer than 2N/3 nodes concur -- the server must NOT commit that round. All logic is baked in
  the gate cascade; the host only routes votes in and reads (majority, fault) out.

Everything below is fabrication-time synthesis: the netlist is proven byte-exact against an
independent Python reference over exhaustive + randomized ballots BEFORE it would ever be stored.
"""
import sys, os, random, itertools, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---------- shared White-Box helpers (same idiom as muhl_flex.py) ----------
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return run, out2, gates, n_wire

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))   # LSB-first
def setf(inp, base, W, x):
    for b in range(W): inp[base + b] = (x >> b) & 1

def add_bits(g, A, B, cin=None):
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c
def mux1(g, s, a, b): return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))
def muxw(g, s, A, B): return [mux1(g, s, A[k], B[k]) for k in range(len(A))]
def consts(g, x, n): return [g.C1 if (x >> k) & 1 else g.C0 for k in range(n)]

def eq_val(g, A, B):                       # A==B  (bitwise XNOR, AND-reduced) -> 1 wire
    acc = g.C1
    for k in range(len(A)):
        acc = g.AND(acc, g.NOT(g.XOR(A[k], B[k])))
    return acc

def gt(g, A, B):                           # A > B  (equal-width unsigned) -> 1 wire
    # compute B - A = B + (~A) + 1 ; carry-out c==1  <=>  B >= A  <=>  NOT(A > B)
    _, c = add_bits(g, B, [g.NOT(x) for x in A], g.C1)
    return g.NOT(c)

# ---------- results ----------
RESULTS = []
def record(name, gates, depth, ok, cases, note=""):
    RESULTS.append((name, len(gates), depth, ok, cases, note))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name:14s} {len(gates):>8,} gates  depth {depth:>4}  byte-exact over {cases:>6} cases  {note}", flush=True)

# ================================ the consensus fabricator ================================
def build_consensus(N, V):
    """Fabricate the N-node, V-bit consensus resolver. Returns (run, maj_wires, fault_wire,
    gates, out2, g, T)."""
    Wc = max(1, N.bit_length())            # width to hold a count 1..N
    T  = -(-2 * N // 3)                     # ceil(2N/3) : the Byzantine supermajority threshold
    g = CC.CircuitCompiler(N * V); IN = g.IN
    vals = [[IN[i * V + b] for b in range(V)] for i in range(N)]

    # 1) equality matrix (symmetric; eq[i][i] == 1)
    eq = [[None] * N for _ in range(N)]
    for i in range(N):
        eq[i][i] = g.C1
        for j in range(i + 1, N):
            e = eq_val(g, vals[i], vals[j]); eq[i][j] = e; eq[j][i] = e

    # 2) agreement count per node = popcount over row i (balanced add-tree of 1-bit terms)
    counts = []
    for i in range(N):
        acc = [g.C0] * Wc
        for j in range(N):
            term = [eq[i][j]] + [g.C0] * (Wc - 1)
            acc, _ = add_bits(g, acc, term)
        counts.append(acc)

    # 3) argmax over counts, tie-break LOWEST index (strict > only replaces) -> majority value
    best_val = vals[0]; best_cnt = counts[0]
    for i in range(1, N):
        better = gt(g, counts[i], best_cnt)          # strict: earlier (lower-index) ties keep the seat
        best_val = muxw(g, better, vals[i], best_val)
        best_cnt = muxw(g, better, counts[i], best_cnt)

    # 4) fault bit = agreement < T  ==  NOT(best_cnt > T-1)
    ge = gt(g, best_cnt, consts(g, T - 1, Wc))       # best_cnt >= T
    fault = g.NOT(ge)

    outs = list(best_val) + [fault]
    run, out2, gates, _ = build_run(g, outs)
    maj_w = out2[:V]; fault_w = out2[V]
    return run, maj_w, fault_w, gates, out2, g, T

# ---------- independent Python reference ----------
def ref_consensus(vals, N, T):
    counts = [sum(1 for j in range(N) if vals[j] == vals[i]) for i in range(N)]
    best = 0
    for i in range(1, N):
        if counts[i] > counts[best]:                 # strict -> lowest index on ties
            best = i
    maj = vals[best]
    fault = 1 if counts[best] < T else 0
    return maj, fault

def run_case(N, V, exhaustive_limit=200_000, rand_cases=4000):
    run, maj_w, fault_w, gates, out2, g, T = build_consensus(N, V)
    depth = depth_of(g, gates, out2)
    tested = 0; ok = True

    def check(vals):
        nonlocal tested
        inp = [0] * (N * V)
        for i in range(N): setf(inp, i * V, V, vals[i])
        v = run(inp, 1)
        got_maj = rd(v, maj_w); got_fault = bit(v, fault_w)
        ref_maj, ref_fault = ref_consensus(vals, N, T)
        tested += 1
        return got_maj == ref_maj and got_fault == ref_fault

    space = V ** 0  # noop
    total_space = (1 << V) ** N
    if total_space <= exhaustive_limit:
        for vals in itertools.product(range(1 << V), repeat=N):
            if not check(list(vals)): ok = False; break
        note = f"N={N} V={V} T>={T}  EXHAUSTIVE ({total_space:,} ballots)"
    else:
        seen = 0
        # include stress ballots: all-agree, one-off, evenly split, near-threshold
        stress = []
        base = random.randrange(1 << V)
        stress.append([base] * N)                                  # unanimous
        s = [base] * N; s[0] = (base + 1) & ((1 << V) - 1); stress.append(s)  # single defector
        half = N // 2
        a = random.randrange(1 << V); b = (a + 1) & ((1 << V) - 1)
        stress.append([a] * half + [b] * (N - half))               # even-ish split
        # near-threshold: exactly T agree on a value, rest scattered distinct
        sT = [base] * T + [(base + 1 + k) & ((1 << V) - 1) for k in range(N - T)]
        stress.append(sT)
        sT1 = [base] * (T - 1) + [(base + 1 + k) & ((1 << V) - 1) for k in range(N - T + 1)]
        stress.append(sT1)
        for vals in stress:
            if not check(vals): ok = False; break
        while ok and seen < rand_cases:
            vals = [random.randrange(1 << V) for _ in range(N)]
            if not check(vals): ok = False
            seen += 1
        note = f"N={N} V={V} T>={T}  {tested:,} ballots (stress+random)"
    record(f"consensus{N}x{V}", gates, depth, ok, tested, note)
    return ok

def main():
    random.seed(29)
    print("\n  MUHLNICKEL CONSENSUS -- Byzantine majority-vote resolver as gates, verified byte-exact\n", flush=True)
    # exhaustive where the ballot space is small; stress+random where it explodes
    configs = [
        (3, 2),    # 64 ballots      exhaustive
        (5, 2),    # 1,024 ballots   exhaustive
        (3, 4),    # 4,096 ballots   exhaustive
        (7, 2),    # 128 ballots     exhaustive  (classic 7-node Byzantine, tolerates 2 faults)
        (5, 4),    # ~1.05M -> random+stress
        (7, 4),    # huge          -> random+stress   (the practical Titan config)
        (10, 8),   # huge          -> random+stress
    ]
    for N, V in configs:
        t = time.time()
        try:
            run_case(N, V)
            print(f"        ({time.time()-t:.1f}s)", flush=True)
        except Exception as ex:
            print(f"  [ERR ] consensus{N}x{V}: {type(ex).__name__}: {ex}", flush=True)
    npass = sum(1 for r in RESULTS if r[3])
    tot_g = sum(r[1] for r in RESULTS)
    print(f"\n  === {npass}/{len(RESULTS)} consensus circuits byte-exact  ·  {tot_g:,} total gates fabricated ===", flush=True)
    print("  fault-tolerant Titan servers: route N replica votes in, read (majority, fault) out -- all in storage.\n", flush=True)

if __name__ == "__main__":
    main()
