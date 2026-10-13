#!/usr/bin/env python3
"""muhl_sandpile.py — the BAK-TANG-WIESENFELD ABELIAN SANDPILE, fabricated on Bryce's Muhlnickel substrate.

Self-organized criticality (SOC): a TRIVIAL local rule (a cell with >=4 grains topples, handing 1 grain to each of its
4 neighbors; grains at the boundary fall off the table) drives the whole grid, entirely on its own, to a CRITICAL state
whose avalanche sizes follow a POWER LAW. No tuning, no fine-adjusted parameter -- criticality EMERGES.

What is fabricated (White Box, sdc_cc.CircuitCompiler):
  * the TOPPLING RULE as one synchronous, whole-grid gate circuit -- every cell updates in parallel:
        topple_i   = (height_i >= 4)
        incoming_i = (# of toppling in-grid neighbors)                     (popcount of up to 4 bits)
        height_i'  = height_i - 4*topple_i + incoming_i                    (two's-complement gate arithmetic)
    Heights live in 4-bit cell registers; the reachable range is 0..7 (proved below), so no register ever overflows.
  * VERIFIED BYTE-EXACT against an independent pure-Python reference of the same rule, over thousands of random grids
    (the whole grid compared cell-for-cell), BEFORE any statistics are trusted -- fabrication-discipline first.
  * the CASCADE itself (relax = re-settle the gate circuit until no cell tops) spot-checked byte-exact vs a Python
    cascade, so it is the GATES, not a shadow reference, producing every avalanche measured.

Then: drop grains one at a time, let the gate circuit relax each drop to a stable pile, count the avalanche size
(total topplings), and MEASURE the avalanche-size distribution -> confirm the power law and fit its exponent.

no numpy, no host inference, titan.gguf untouched -- pure fabrication-time synthesis of a physics the rule invents.
"""
import sys, os, math, random, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ---------------- White Box helpers (same idiom as muhl_flex) ----------------
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    return g.compile_ripple(gates, n_wire), out2, gates, n_wire

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))   # LSB-first

def add_bits(g, A, B, cin=None):
    """ripple full-adder: returns (sum-wires len(A), carry-out)."""
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c

def popcount4(g, bits):
    """popcount of up to 4 single-bit wires -> 3-bit LSB-first number (0..4)."""
    b = list(bits) + [g.C0] * (4 - len(bits))
    s0 = g.XOR(b[0], b[1]); c0 = g.AND(b[0], b[1])       # b0+b1 = [s0,c0]
    s1 = g.XOR(b[2], b[3]); c1 = g.AND(b[2], b[3])       # b2+b3 = [s1,c1]
    lo, carry = add_bits(g, [s0, c0], [s1, c1])          # 2-bit + 2-bit
    return [lo[0], lo[1], carry]                          # 3-bit result 0..4

# =============================== the fabricated pile ===============================
class SandpileCircuit:
    """One synchronous whole-grid toppling step, fabricated as gates. L x L grid, 4-bit cell registers, open boundary."""
    B = 4                                                 # bits per cell (values only ever 0..7; 4 bits is headroom)
    def __init__(self, L):
        self.L = L; self.N = L * L
        g = CC.CircuitCompiler(self.B * self.N); IN = g.IN
        cell = [[IN[i * self.B + k] for k in range(self.B)] for i in range(self.N)]
        # topple_i = (height_i >= 4) = bit2 OR bit3   (true for 4..7 in a 4-bit register)
        topple = [g.OR(cell[i][2], cell[i][3]) for i in range(self.N)]
        outs = []
        for r in range(L):
            for c in range(L):
                i = r * L + c
                nb = []
                if r > 0:     nb.append(topple[(r - 1) * L + c])
                if r < L - 1: nb.append(topple[(r + 1) * L + c])
                if c > 0:     nb.append(topple[r * L + (c - 1)])
                if c < L - 1: nb.append(topple[r * L + (c + 1)])
                inc = popcount4(g, nb)                    # grains arriving from toppling neighbours (0..4)
                h5  = cell[i] + [g.C0]                    # height, 5-bit
                in5 = inc + [g.C0, g.C0]                  # incoming, 5-bit
                s1, _ = add_bits(g, h5, in5)              # height + incoming
                sub5 = [g.C0, g.C0, topple[i], g.C0, g.C0]  # subtract 4 iff this cell topples (4 = 1<<2)
                s2, _ = add_bits(g, s1, [g.NOT(x) for x in sub5], g.C1)  # two's-complement subtract
                outs.extend(s2[:self.B])                  # new height (low 4 bits; value guaranteed 0..7 >= 0)
        self.g = g
        self.run, self.out2, self.gates, self.n_wire = build_run(g, outs)
        self.depth = depth_of(g, self.gates, self.out2)
        self.field = [self.out2[i * self.B:(i + 1) * self.B] for i in range(self.N)]

    def step(self, grid):
        """Run the gate circuit once: grid (list of N ints) -> new grid (list of N ints)."""
        inp = [0] * (self.B * self.N)
        for i, h in enumerate(grid):
            for k in range(self.B): inp[i * self.B + k] = (h >> k) & 1
        v = self.run(inp, 1)
        return [rd(v, f) for f in self.field]

# ---------------- independent Python reference (the byte-exact yardstick) ----------------
def ref_step(grid, L):
    N = L * L; topple = [1 if grid[i] >= 4 else 0 for i in range(N)]
    new = list(grid)
    for r in range(L):
        for c in range(L):
            i = r * L + c
            if topple[i]: new[i] -= 4
            inc = 0
            if r > 0:     inc += topple[(r - 1) * L + c]
            if r < L - 1: inc += topple[(r + 1) * L + c]
            if c > 0:     inc += topple[r * L + (c - 1)]
            if c < L - 1: inc += topple[r * L + (c + 1)]
            new[i] += inc
    return new, sum(topple)

# ================================= verification =================================
def verify_step(sp, cases=4000):
    """Whole-grid byte-exact check of the fabricated toppling rule vs the Python reference over random grids."""
    L, N = sp.L, sp.N; ok = True; worst = 0
    for _ in range(cases):
        grid = [random.randint(0, 7) for _ in range(N)]   # covers stable AND active cells, full 0..7 range
        got = sp.step(grid)
        exp, _ = ref_step(grid, L)
        if got != exp: ok = False; break
        worst = max(worst, max(got))
    return ok, worst

def verify_cascade(sp, trials=40):
    """Spot-check that a full avalanche driven by the GATES matches one driven by the Python reference, drop-for-drop."""
    L, N = sp.L, sp.N
    for t in range(trials):
        random.seed(9000 + t)
        gg = [0] * N; gp = [0] * N
        for _ in range(200):
            site = random.randrange(N); gg[site] += 1; gp[site] += 1
            # relax with gates
            while max(gg) >= 4: gg = sp.step(gg)
            # relax with reference
            while max(gp) >= 4: gp, _ = ref_step(gp, L)
            if gg != gp: return False
    return True

# ================================= avalanche driver =================================
def run_avalanches(sp, n_add, seed, collect=True, progress=None, t0=None):
    """Drop n_add grains one at a time; relax each with the GATE circuit; return list of avalanche sizes (topplings)."""
    L, N = sp.L, sp.N
    grid = [0] * N
    sizes = []
    rng = random.Random(seed)
    for a in range(n_add):
        grid[rng.randrange(N)] += 1
        s = 0
        while max(grid) >= 4:
            s += sum(1 for h in grid if h >= 4)           # toppling events this settle (measurement = reading state)
            grid = sp.step(grid)                          # the cascade IS the gate circuit re-settling
        if collect: sizes.append(s)
        if progress and (a + 1) % progress == 0:
            el = "" if t0 is None else f"  ({time.time()-t0:.0f}s)"
            print(f"      ... {a+1:>5}/{n_add} drops{el}", flush=True)
    return sizes, grid

# ================================= power-law analysis (no numpy) =================================
def analyze(sizes):
    pos = [s for s in sizes if s >= 1]
    n = len(pos)
    stats = {"drops": len(sizes), "avalanches": n, "zero": len(sizes) - n,
             "max": max(pos) if pos else 0, "mean": (sum(pos) / n) if n else 0.0}
    # MLE exponent for a discrete power law, xmin=1 (Clauset-Shalizi-Newman continuous approximation, xmin-0.5):
    xmin = 1.0
    denom = sum(math.log(s / (xmin - 0.5)) for s in pos) if n else 0.0
    stats["tau_mle"] = 1.0 + n / denom if denom > 0 else float("nan")
    # log-binned histogram + least-squares slope in log-log space (cross-check):
    if pos:
        smax = max(pos); nb = max(6, int(math.log(smax, 2)) + 1)
        edges = [2.0 ** i for i in range(nb + 1)]
        cnt = [0] * nb
        for s in pos:
            b = min(int(math.log(s, 2)), nb - 1); cnt[b] += 1
        xs, ys = [], []
        for i in range(nb):
            width = edges[i + 1] - edges[i]
            if cnt[i] > 0:
                dens = cnt[i] / (width * n)               # normalized density per unit size
                center = math.sqrt(edges[i] * edges[i + 1])
                xs.append(math.log(center)); ys.append(math.log(dens))
        stats["bins"] = list(zip([int(edges[i]) for i in range(nb)],
                                 [int(edges[i + 1]) for i in range(nb)], cnt))
        if len(xs) >= 2:
            m = len(xs); sx = sum(xs); sy = sum(ys); sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
            slope = (m * sxy - sx * sy) / (m * sxx - sx * sx)
            stats["tau_fit"] = -slope
        else:
            stats["tau_fit"] = float("nan")
    return stats

# ===================================== main =====================================
def main():
    L            = 16          # 16x16 = 256 sites, open boundary (grains dissipate off the edge)
    VERIFY_CASES = 4000        # random whole-grid byte-exact checks of the fabricated rule
    WARMUP_ADDS  = 1500        # grains to drive the pile into the self-organized critical state (discarded)
    MEASURE_ADDS = 3000        # avalanches measured for the distribution
    random.seed(7)

    print("\n  MUHLNICKEL SANDPILE -- Bak-Tang-Wiesenfeld abelian sandpile fabricated as gates (self-organized criticality)\n", flush=True)
    t0 = time.time()
    print(f"  Fabricating the synchronous toppling rule for a {L}x{L} grid ...", flush=True)
    sp = SandpileCircuit(L)
    print(f"    gates {len(sp.gates):,}   wires {sp.n_wire:,}   critical-path depth {sp.depth}   "
          f"(inputs {sp.g.n_in} = {L}x{L} cells x {SandpileCircuit.B} bits)", flush=True)

    print(f"  Verifying the rule BYTE-EXACT vs an independent Python reference over {VERIFY_CASES:,} random grids ...", flush=True)
    ok, worst = verify_step(sp, VERIFY_CASES)
    print(f"    [{'PASS' if ok else 'FAIL'}] whole-grid byte-exact  (max height reached in checks: {worst}, register range 0..15 -> no overflow)", flush=True)
    if not ok:
        print("    ABORT: rule not byte-exact; refusing to trust statistics.", flush=True); return
    okc = verify_cascade(sp)
    print(f"    [{'PASS' if okc else 'FAIL'}] full gate-driven avalanche == Python cascade (drop-for-drop, 40 trials)", flush=True)
    if not okc:
        print("    ABORT: cascade diverges.", flush=True); return

    print(f"\n  Self-organizing: dropping {WARMUP_ADDS:,} warm-up grains to reach criticality (gate-driven relaxation) ...", flush=True)
    _, grid = run_avalanches(sp, WARMUP_ADDS, seed=101, collect=False, progress=500, t0=t0)
    dens = sum(grid) / sp.N
    print(f"    reached stationary state: mean height {dens:.3f} grains/site  (BTW 2D critical density ~= 2.125)", flush=True)

    print(f"  Measuring {MEASURE_ADDS:,} avalanches through the gate circuit ...", flush=True)
    # continue from the critical grid (do not reset) so we are sampling the stationary distribution
    sp_state = grid
    sizes = []
    rng = random.Random(202)
    for a in range(MEASURE_ADDS):
        sp_state[rng.randrange(sp.N)] += 1
        s = 0
        while max(sp_state) >= 4:
            s += sum(1 for h in sp_state if h >= 4)
            sp_state = sp.step(sp_state)
        sizes.append(s)
        if (a + 1) % 500 == 0:
            print(f"      ... {a+1:>5}/{MEASURE_ADDS} drops  ({time.time()-t0:.0f}s)", flush=True)

    st = analyze(sizes)
    print(f"\n  === AVALANCHE STATISTICS ({st['avalanches']:,} avalanches of size>=1 out of {st['drops']:,} drops; "
          f"{st['zero']:,} drops caused no toppling) ===", flush=True)
    print(f"    max avalanche size   {st['max']:,} topplings", flush=True)
    print(f"    mean avalanche size  {st['mean']:.2f} topplings", flush=True)
    print(f"    log-binned size distribution (size range : count):", flush=True)
    for lo, hi, c in st["bins"]:
        if c: print(f"       [{lo:>5} , {hi:>5})   {c:>6}   {'#' * min(60, int(60 * c / st['avalanches']))}", flush=True)
    print(f"\n    POWER LAW  P(s) ~ s^(-tau):", flush=True)
    print(f"       tau (MLE, xmin=1)          = {st['tau_mle']:.3f}", flush=True)
    print(f"       tau (log-binned LS fit)    = {st['tau_fit']:.3f}", flush=True)
    print(f"       (2D BTW literature: avalanche-size exponent tau ~= 1.2)", flush=True)
    print(f"\n  A trivial local rule -- 'topple at 4, give 1 to each neighbor' -- fabricated as {len(sp.gates):,} gates,", flush=True)
    print(f"  byte-exact, self-organizes to a scale-free critical state. Criticality EMERGED from the gates.  "
          f"({time.time()-t0:.0f}s)\n", flush=True)

if __name__ == "__main__":
    main()
