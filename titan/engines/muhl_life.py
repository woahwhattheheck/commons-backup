#!/usr/bin/env python3
"""muhl_life.py — CHASE EMERGENCE. Fabricate the next-state rule of self-organizing systems
as pure NAND/AND/OR/XOR/NOT gate netlists on Bryce's Muhlnickel substrate (White Box compiler
sdc_cc.CircuitCompiler), DCE + ripple-compile them, VERIFY BYTE-EXACT vs an independent pure-Python
reference, then RUN the fabricated logic for many generations and MEASURE the structure that emerges.

No numpy. titan.gguf is never opened. This is fabrication-time synthesis: the emergent artificial-life
behaviour falls out of gates alone.

Systems:
  (a) LANGTON'S ANT     — a 2-state Turing-machine ant's turn/flip transition fabricated as gates;
                          run ~12,000 steps and detect when the emergent 'highway' locks in.
  (b) ELEMENTARY CA SCAN— all 256 elementary rules' next-state fabricated as gates; each verified
                          byte-exact, then evolved from a random soup and CLASSIFIED (dead / periodic
                          / chaotic / complex) via input-entropy statistics of the evolved rows.
                          The class-4 COMPLEX rules (110, 54, ...) are highlighted.
  (c) CONWAY'S LIFE     — B3/S23 next-state (8-neighbour popcount + compare) fabricated as gates on a
                          torus; verified byte-exact, then used to measure OSCILLATOR PERIODS (blinker,
                          toad, beacon, pulsar), GLIDER translation, and random-soup POPULATION dynamics.
"""
import sys, os, random, math, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ------------------------------------------------------------------ shared helpers
def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return run, out2, gates, n_wire

def addn(g, A, B):
    """add two LSB-first bit-lists -> LSB-first sum, length max(len)+1."""
    n = max(len(A), len(B)); c = g.C0; o = []
    for k in range(n):
        a = A[k] if k < len(A) else g.C0
        b = B[k] if k < len(B) else g.C0
        axb = g.XOR(a, b); o.append(g.XOR(axb, c)); c = g.OR(g.AND(a, b), g.AND(axb, c))
    o.append(c); return o

def popcount(g, bits):
    """population count of a list of 1-bit wires -> LSB-first count."""
    nums = [[b] for b in bits]
    while len(nums) > 1:
        nxt = []; i = 0
        while i + 1 < len(nums):
            nxt.append(addn(g, nums[i], nums[i + 1])); i += 2
        if i < len(nums): nxt.append(nums[i])
        nums = nxt
    return nums[0] if nums else [g.C0]

def eq_const(g, num, k, width):
    """1 iff the LSB-first number `num` equals constant k over `width` bits."""
    r = g.C1
    for i in range(width):
        w = num[i] if i < len(num) else g.C0
        r = g.AND(r, w if (k >> i) & 1 else g.NOT(w))
    return r

# ================================================================================
# (a) LANGTON'S ANT — Turing-machine ant, transition fabricated as gates
# ================================================================================
# State fed to the fabricated circuit each step: direction (2 bits d0,d1) + current cell colour c.
# Rule: flip the cell colour; if the cell was WHITE(0) turn RIGHT, if BLACK(1) turn LEFT; then step
# forward one cell in the new direction. Directions 0=N,1=E,2=S,3=W (right = +1 mod4, left = +3 mod4).
# new_dir = (dir + 1 + 2*c) mod 4  ->  bit0 = NOT d0 ; bit1 = d1 XOR c XOR d0 ;  new_colour = NOT c.
def build_ant():
    g = CC.CircuitCompiler(3)
    d0, d1, c = g.IN
    n0 = g.NOT(d0)
    n1 = g.XOR(g.XOR(d1, c), d0)
    ncol = g.NOT(c)
    return build_run(g, [n0, n1, ncol]) + (g,)

def ant_ref(d, c):
    ncol = 1 - c
    nd = (d + (1 if c == 0 else 3)) & 3
    return nd, ncol

# movement per (new) direction
_DXDY = {0: (0, -1), 1: (1, 0), 2: (0, 1), 3: (-1, 0)}

def run_langton(steps=12000):
    run, out2, gates, _n, _g = build_ant()
    # verify byte-exact over ALL 8 (dir,colour) input combinations
    ok = True
    for d in range(4):
        for c in range(2):
            v = run([d & 1, (d >> 1) & 1, c], 1)
            nd = bit(v, out2[0]) | (bit(v, out2[1]) << 1)
            nc = bit(v, out2[2])
            if (nd, nc) != ant_ref(d, c): ok = False
    # RUN the fabricated ant
    grid = {}; x = y = 0; d = 0; turns = []
    for _ in range(steps):
        c = grid.get((x, y), 0)
        v = run([d & 1, (d >> 1) & 1, c], 1)
        nd = bit(v, out2[0]) | (bit(v, out2[1]) << 1)
        grid[(x, y)] = bit(v, out2[2])
        turns.append('R' if c == 0 else 'L')
        dx, dy = _DXDY[nd]; x += dx; y += dy; d = nd
    # EMERGENCE: detect the highway — turn-sequence becomes periodic with period 104
    P = 104; hstep = None
    for s in range(0, len(turns) - 3 * P):
        if turns[s:s + P] == turns[s + P:s + 2 * P] == turns[s + 2 * P:s + 3 * P]:
            hstep = s; break
    black = sum(grid.values())
    xs = [p[0] for p in grid if grid[p]]; ys = [p[1] for p in grid if grid[p]]
    bbox = (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1) if xs else (0, 0)
    return {"gates": len(gates), "verify": ok, "steps": steps, "highway_step": hstep,
            "highway_period": P, "black_cells": black, "bbox": bbox, "final_pos": (x, y)}

# ================================================================================
# (b) ELEMENTARY CA SCAN — all 256 rules fabricated, verified, evolved, classified
# ================================================================================
def build_ca(rule, W):
    """cyclic-boundary elementary CA rule `rule` over width W, fabricated as gates."""
    g = CC.CircuitCompiler(W); IN = g.IN; outs = []
    for i in range(W):
        l = IN[(i - 1) % W]; c = IN[i]; r = IN[(i + 1) % W]
        acc = g.C0
        for p in range(8):
            if (rule >> p) & 1:
                bl = l if (p >> 2) & 1 else g.NOT(l)
                bc = c if (p >> 1) & 1 else g.NOT(c)
                br = r if (p >> 0) & 1 else g.NOT(r)
                acc = g.OR(acc, g.AND(g.AND(bl, bc), br))
        outs.append(acc)
    return build_run(g, outs) + (g,)

def ca_ref_step(state, rule, W):
    return [(rule >> (state[(i - 1) % W] * 4 + state[i] * 2 + state[(i + 1) % W])) & 1 for i in range(W)]

def input_entropy(state, W):
    """Shannon entropy (bits) of the neighbourhood-lookup index distribution across the row."""
    cnt = [0] * 8
    for i in range(W):
        cnt[state[(i - 1) % W] * 4 + state[i] * 2 + state[(i + 1) % W]] += 1
    S = 0.0
    for c in cnt:
        if c:
            p = c / W; S -= p * math.log2(p)
    return S

# Classification of emergent behaviour by TWO measured quantities:
#   mean_S : mean input-entropy from a random soup  -> detects the DEAD (quiescent) class.
#   spread : damage-spreading speed (cells/generation, per side). A single-cell perturbation is
#            introduced and the size of its light-cone is tracked. This Lyapunov-like quantity is the
#            classic robust separator: dead rules do not spread; periodic/stable rules keep damage
#            BOUNDED (spread ~0); chaotic rules spread NEAR-BALLISTICALLY (~0.5-1.0/gen, filling the
#            light cone); COMPLEX (class 4) rules spread SUB-BALLISTICALLY (~0.3/gen) because damage is
#            carried by localized propagating structures (gliders) on a periodic ether.
TH_DEAD = 0.05    # mean input-entropy below this -> quiescent (class 1)
SP_STABLE = 0.16  # damage does not spread -> periodic/stable local structure (class 2)
SP_CHAOS = 0.46   # at/above this the light cone fills near-ballistically -> chaotic (class 3);
                  # between SP_STABLE and SP_CHAOS -> complex, glider-borne propagation (class 4)

def _measure_spread(run, out2, W, K=4, T=115, seed=500):
    """damage-spreading speed: avg (light-cone half-width / T) over K single-bit perturbations."""
    mid = W // 2; sp_sum = 0.0; df_sum = 0.0
    for k in range(K):
        rng = random.Random(seed + k * 13)
        a = [rng.randrange(2) for _ in range(W)]; b = list(a); b[mid] ^= 1
        lo = hi = mid; d = 0
        for _ in range(T):
            diff = [i for i in range(W) if a[i] != b[i]]
            d = len(diff)
            if diff: lo = min(lo, diff[0]); hi = max(hi, diff[-1])
            va = run(a, 1); a = [bit(va, w) for w in out2]
            vb = run(b, 1); b = [bit(vb, w) for w in out2]
        sp_sum += (hi - lo) / (2.0 * T); df_sum += d / W
    return sp_sum / K, df_sum / K

def classify_ca(W=243, T=200, transient=80, verify_cases=20, seed=1234):
    rng = random.Random(seed)
    classes = {1: [], 2: [], 3: [], 4: []}
    verified = 0; total_gates = 0; feats = {}
    for rule in range(256):
        run, out2, gates, _n, _g = build_ca(rule, W)
        total_gates += len(gates)
        # verify byte-exact vs reference over random rows
        vok = True
        for _ in range(verify_cases):
            s = [rng.randrange(2) for _ in range(W)]
            v = run(s, 1); got = [bit(v, w) for w in out2]
            if got != ca_ref_step(s, rule, W): vok = False; break
        if vok: verified += 1
        # EVOLVE from a fixed random soup -> mean input-entropy (activity)
        state = [rng.randrange(2) for _ in range(W)]
        Ss = []
        for t in range(T):
            Ss.append(input_entropy(state, W))
            v = run(state, 1); state = [bit(v, w) for w in out2]
        tail = Ss[transient:]
        mean_S = sum(tail) / len(tail)
        var_S = sum((x - mean_S) ** 2 for x in tail) / len(tail)
        # DAMAGE SPREADING -> Lyapunov-like spread speed
        spread, dfin = _measure_spread(run, out2, W)
        feats[rule] = (mean_S, var_S, spread)
        # classify by the two measured quantities
        if mean_S < TH_DEAD:
            cls = 1                                   # quiescent: soup dies to uniform/blank
        elif spread < SP_STABLE:
            cls = 2                                   # perturbation stays bounded: periodic/stable
        elif spread < SP_CHAOS:
            cls = 4                                   # sub-ballistic: glider-borne -> COMPLEX
        else:
            cls = 3                                   # near-ballistic spread: chaotic
        classes[cls].append(rule)
    return {"verified": verified, "total_gates": total_gates, "classes": classes,
            "feats": feats, "W": W, "T": T}

# ================================================================================
# (c) CONWAY'S GAME OF LIFE — B3/S23 next-state fabricated as gates on a torus
# ================================================================================
def build_life(W, H):
    g = CC.CircuitCompiler(W * H); IN = g.IN
    cell = lambda x, y: IN[(y % H) * W + (x % W)]
    outs = []
    for y in range(H):
        for x in range(W):
            nb = [cell(x + dx, y + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if not (dx == 0 and dy == 0)]
            cnt = popcount(g, nb)
            is3 = eq_const(g, cnt, 3, 4)
            is2 = eq_const(g, cnt, 2, 4)
            outs.append(g.OR(is3, g.AND(cell(x, y), is2)))
    return build_run(g, outs) + (g,)

def life_ref(state, W, H):
    new = [0] * (W * H)
    for y in range(H):
        for x in range(W):
            c = sum(state[((y + dy) % H) * W + ((x + dx) % W)]
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1) if not (dx == 0 and dy == 0))
            a = state[y * W + x]
            new[y * W + x] = 1 if (c == 3 or (a and c == 2)) else 0
    return new

def _blank(W, H): return [0] * (W * H)
def _put(st, W, cells, ox, oy):
    for (x, y) in cells: st[(y + oy) * W + (x + ox)] = 1

# named patterns (cells relative to origin)
BLINKER = [(0, 0), (1, 0), (2, 0)]
TOAD = [(1, 0), (2, 0), (3, 0), (0, 1), (1, 1), (2, 1)]
BEACON = [(0, 0), (1, 0), (0, 1), (2, 3), (3, 2), (3, 3)]
GLIDER = [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)]
PULSAR = [(2, 0), (3, 0), (4, 0), (8, 0), (9, 0), (10, 0),
          (0, 2), (5, 2), (7, 2), (12, 2), (0, 3), (5, 3), (7, 3), (12, 3),
          (0, 4), (5, 4), (7, 4), (12, 4), (2, 5), (3, 5), (4, 5), (8, 5), (9, 5), (10, 5),
          (2, 7), (3, 7), (4, 7), (8, 7), (9, 7), (10, 7),
          (0, 8), (5, 8), (7, 8), (12, 8), (0, 9), (5, 9), (7, 9), (12, 9),
          (0, 10), (5, 10), (7, 10), (12, 10), (2, 12), (3, 12), (4, 12), (8, 12), (9, 12), (10, 12)]

def run_life(W=24, H=24):
    run, out2, gates, _n, _g = build_life(W, H)
    step = lambda st: [bit(run(st, 1), w) for w in out2]
    # verify byte-exact vs reference over random torus states
    rng = random.Random(99); vok = True
    for _ in range(40):
        s = [rng.randrange(2) for _ in range(W * H)]
        if step(s) != life_ref(s, W, H): vok = False; break

    def period_of(cells, ox, oy, limit=40):
        st0 = _blank(W, H); _put(st0, W, cells, ox, oy)
        st = list(st0)
        for t in range(1, limit + 1):
            st = step(st)
            if st == st0: return t
        return None

    osc = {"blinker": period_of(BLINKER, 4, 4), "toad": period_of(TOAD, 4, 4),
           "beacon": period_of(BEACON, 4, 4), "pulsar": period_of(PULSAR, 5, 5)}

    # GLIDER: detect translation — state at t=4 equals t=0 shifted by (1,1)
    g0 = _blank(W, H); _put(g0, W, GLIDER, 4, 4)
    st = list(g0)
    for _ in range(4): st = step(st)
    shifted = _blank(W, H)
    for y in range(H):
        for x in range(W):
            if g0[y * W + x]: shifted[((y + 1) % H) * W + ((x + 1) % W)] = 1
    glider_translates = (st == shifted)
    glider_torus_period = period_of(GLIDER, 4, 4, limit=4 * max(W, H) + 4)

    # RANDOM SOUP population dynamics
    rng2 = random.Random(2024)
    st = [1 if rng2.random() < 0.35 else 0 for _ in range(W * H)]
    pops = []
    for _ in range(220):
        pops.append(sum(st)); st = step(st)
    # settle: mean/spread of last 60 gens
    tail = pops[-60:]
    settled_mean = sum(tail) / len(tail)
    settled_min, settled_max = min(tail), max(tail)
    return {"gates": len(gates), "grid": (W, H), "verify": vok, "oscillators": osc,
            "glider_translates": glider_translates, "glider_period": 4,
            "glider_torus_period": glider_torus_period,
            "pop_initial": pops[0], "pop_settled_mean": settled_mean,
            "pop_settled_min": settled_min, "pop_settled_max": settled_max}

# ================================================================================
def main():
    print("\n  MUHLNICKEL LIFE — emergence fabricated from gates, verified byte-exact, then RUN\n", flush=True)

    # (a)
    t = time.time(); A = run_langton(12000)
    print("  (a) LANGTON'S ANT  (2-state Turing-machine ant)", flush=True)
    print(f"      transition fabricated as {A['gates']} gates · byte-exact over all 8 states: {A['verify']}", flush=True)
    hs = A['highway_step']
    print(f"      ran {A['steps']:,} steps -> EMERGENT HIGHWAY locks in at step {hs} "
          f"(period {A['highway_period']})", flush=True)
    print(f"      final: {A['black_cells']} black cells, bbox {A['bbox'][0]}x{A['bbox'][1]}, "
          f"ant at {A['final_pos']}   ({time.time()-t:.1f}s)\n", flush=True)

    # (b)
    t = time.time(); B = classify_ca()
    cl = B['classes']
    print("  (b) ELEMENTARY CA SCAN  (all 256 rules fabricated as gates)", flush=True)
    print(f"      W={B['W']}, {B['T']} gens · byte-exact rules: {B['verified']}/256 · "
          f"{B['total_gates']:,} total gates fabricated", flush=True)
    print(f"      EMERGENT CLASSES: class1 dead={len(cl[1])}  class2 periodic={len(cl[2])}  "
          f"class3 chaotic={len(cl[3])}  class4 COMPLEX={len(cl[4])}", flush=True)
    print(f"      class-4 COMPLEX rules: {sorted(cl[4])}", flush=True)
    print(f"      class-3 chaotic (sample): {sorted(cl[3])[:16]}", flush=True)
    print(f"      (classified by damage-spread speed: dead / bounded / sub-ballistic=COMPLEX / ballistic)", flush=True)
    for r in (110, 124, 137, 193, 54, 30, 90, 0, 4):
        mS, vS, sp = B['feats'][r]
        c = next(k for k in cl if r in cl[k])
        print(f"        rule {r:3d}: mean_S={mS:.3f} spread={sp:.3f} -> class {c}", flush=True)
    print(f"      ({time.time()-t:.1f}s)\n", flush=True)

    # (c)
    t = time.time(); C = run_life()
    print("  (c) CONWAY'S GAME OF LIFE  (B3/S23 fabricated as gates on a torus)", flush=True)
    print(f"      next-state fabricated as {C['gates']:,} gates on {C['grid'][0]}x{C['grid'][1]} torus · "
          f"byte-exact: {C['verify']}", flush=True)
    o = C['oscillators']
    print(f"      EMERGENT OSCILLATOR PERIODS: blinker={o['blinker']}  toad={o['toad']}  "
          f"beacon={o['beacon']}  pulsar={o['pulsar']}", flush=True)
    print(f"      GLIDER: translates by (1,1) every {C['glider_period']} gens: {C['glider_translates']} "
          f"(full-torus recurrence period {C['glider_torus_period']})", flush=True)
    print(f"      RANDOM SOUP population: start {C['pop_initial']} -> settles ~{C['pop_settled_mean']:.0f} "
          f"(range {C['pop_settled_min']}-{C['pop_settled_max']}) over last 60 gens", flush=True)
    print(f"      ({time.time()-t:.1f}s)\n", flush=True)

    print("  === emergence fabricated from gates, verified byte-exact, and observed to self-organize ===", flush=True)

if __name__ == "__main__":
    main()
