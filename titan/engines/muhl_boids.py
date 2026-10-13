#!/usr/bin/env python3
"""muhl_boids.py -- REYNOLDS FLOCKING (boids) fabricated as fixed-point NAND/AND/OR/XOR gates.

A full-field boids step for N agents is built as ONE gate netlist with the White Box compiler
(sdc_cc.CircuitCompiler): every agent's SEPARATION / ALIGNMENT / COHESION steer is computed from its
local neighbours, entirely in fixed-point two's-complement integer logic -- no float, no numpy, no
division, no sqrt in the dynamics. The gate step is verified BYTE-EXACT against an independent pure-Python
integer reference at every tick of a real trajectory, then the circuit's output is fed back into its own
input (the substrate feedback loop, exactly like a stored circuit run by address) for many ticks.

The point is EMERGENCE FROM LOCAL RULES: agents start with random headings (low order parameter) and,
purely through the three local Reynolds rules baked into the gates, self-organise into a coherent flock --
the velocity-alignment ORDER PARAMETER phi = |mean unit-velocity| rises from ~random toward ~1.

Toroidal world is FREE: fixed-width two's-complement subtraction of two positions IS the minimum-image
displacement (mod 2^POS), so wrap-around costs zero gates. Neighbourhood test is Manhattan distance
(abs + add + unsigned compare) to stay division/sqrt-free. Steering blends shifted (arithmetic-shift =
divide-by-power-of-two) sums of the local displacements and neighbour velocities, then clamps speed.

Measurement (the order parameter) uses host math -- that is analysis of the output, NOT the fabricated
dynamics; every state transition is produced by the gate circuit and checked byte-exact.
"""
import sys, os, math, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ===================== simulation constants (shared by gates AND reference) =====================
N     = 16          # number of boids
POS   = 16          # position/velocity word width (two's complement); world wraps mod 2^POS = toroidal
WACC  = 24          # accumulator width (two's complement)
R     = 4500        # neighbour radius (Manhattan, fixed-point units)
RSEP  = 1600        # separation radius (Manhattan)
VMAX  = 60          # per-component speed clamp
CSH   = 13          # cohesion   steer = (sum neighbour displacement) >> CSH
SSH   = 9           # separation steer = (sum away-displacement)      >> SSH
ASH   = 8           # alignment  steer = (sum neighbour velocity)     >> ASH
M16   = (1 << POS) - 1

# ============================== gate helpers (over the White Box IR) ==============================
def cbits(g, val, W):
    v = val & ((1 << W) - 1)
    return [g.C1 if (v >> b) & 1 else g.C0 for b in range(W)]

def add(g, A, B, cin=None):                 # ripple add, equal-width; returns (sum, carry_out)
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c

def sub(g, A, B):                           # A - B; carry_out==1 means A>=B (no borrow)
    return add(g, A, [g.NOT(x) for x in B], g.C1)

def negate(g, X):
    d, _ = add(g, [g.NOT(x) for x in X], [g.C0] * len(X), g.C1); return d

def sext(g, X, W2):                          # sign-extend X to width W2
    W = len(X); s = X[-1]
    return [X[i] if i < W else s for i in range(W2)]

def ashr(g, X, k):                           # arithmetic right shift by k, width preserved
    W = len(X); s = X[-1]
    return [X[i + k] if i + k < W else s for i in range(W)]

def mux1(g, s, a, b): return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))          # s? a : b
def muxw(g, s, A, B): return [mux1(g, s, A[k], B[k]) for k in range(len(A))]

def abs_(g, X):
    s = X[-1]; return muxw(g, s, negate(g, X), X)

def ule(g, A, B):                            # unsigned A <= B  (equal width)
    _, c = sub(g, B, A); return c            # B>=A  <=>  A<=B

def slt(g, A, B):                            # signed A < B (equal width)
    ae = sext(g, A, len(A) + 1); be = sext(g, B, len(B) + 1)
    d, _ = sub(g, ae, be); return d[-1]      # sign bit of (A-B)

def add_masked(g, acc, val, mask):           # acc += (mask ? val : 0)
    s, _ = add(g, acc, [g.AND(v, mask) for v in val]); return s

# ============================== the boids step as a gate netlist ==============================
def build_step():
    g = CC.CircuitCompiler(N * 4 * POS); IN = g.IN
    def field(a, f): return [IN[(a * 4 + f) * POS + b] for b in range(POS)]   # f: 0=px 1=py 2=vx 3=vy

    R17   = cbits(g, R, 17)
    RS17  = cbits(g, RSEP, 17)
    VP    = cbits(g, VMAX, WACC)
    VN    = cbits(g, -VMAX, WACC)

    outs = []
    for i in range(N):
        pix, piy, vix, viy = field(i, 0), field(i, 1), field(i, 2), field(i, 3)
        cohx = cohy = alix = aliy = sepx = sepy = [g.C0] * WACC
        for j in range(N):
            if j == i: continue
            pjx, pjy, vjx, vjy = field(j, 0), field(j, 1), field(j, 2), field(j, 3)
            dx, _ = sub(g, pjx, pix)                       # minimum-image displacement (toroidal, free)
            dy, _ = sub(g, pjy, piy)
            adx, ady = abs_(g, dx), abs_(g, dy)
            dist, _ = add(g, sext(g, adx, 17), sext(g, ady, 17))   # Manhattan distance (>=0)
            near    = ule(g, dist, R17)
            nearsep = ule(g, dist, RS17)
            dxe, dye = sext(g, dx, WACC), sext(g, dy, WACC)
            cohx = add_masked(g, cohx, dxe, near)          # cohesion: steer toward neighbours
            cohy = add_masked(g, cohy, dye, near)
            alix = add_masked(g, alix, sext(g, vjx, WACC), near)   # alignment: match neighbour heading
            aliy = add_masked(g, aliy, sext(g, vjy, WACC), near)
            sepx = add_masked(g, sepx, negate(g, dxe), nearsep)    # separation: push away when too close
            sepy = add_masked(g, sepy, negate(g, dye), nearsep)

        def combine(vi, coh, sep, ali):
            s, _ = add(g, sext(g, vi, WACC), ashr(g, coh, CSH))
            s, _ = add(g, s, ashr(g, sep, SSH))
            s, _ = add(g, s, ashr(g, ali, ASH))
            s = muxw(g, slt(g, VP, s), VP, s)              # clamp high
            s = muxw(g, slt(g, s, VN), VN, s)              # clamp low
            return s
        nvx = combine(vix, cohx, sepx, alix)
        nvy = combine(viy, cohy, sepy, aliy)
        nvx16, nvy16 = nvx[:POS], nvy[:POS]                # exact: |v|<=VMAX < 2^(POS-1)
        npx, _ = add(g, pix, nvx16)                        # position update, wraps mod 2^POS
        npy, _ = add(g, piy, nvy16)
        outs += npx + npy + nvx16 + nvy16

    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return g, run, gates, out2

# ============================== independent Python integer reference ==============================
def tos(x, W):
    x &= (1 << W) - 1; return x - (1 << W) if (x >> (W - 1)) & 1 else x

def ref_step(state):                                       # state: list of (px,py,vx,vy) unsigned POS-bit
    new = []
    for i in range(N):
        pix, piy, vix, viy = state[i]
        cohx = cohy = alix = aliy = sepx = sepy = 0
        for j in range(N):
            if j == i: continue
            pjx, pjy, vjx, vjy = state[j]
            dx = tos(pjx - pix, POS); dy = tos(pjy - piy, POS)   # minimum-image displacement
            dist = abs(dx) + abs(dy)
            if dist <= R:
                cohx += dx; cohy += dy
                alix += tos(vjx, POS); aliy += tos(vjy, POS)
            if dist <= RSEP:
                sepx -= dx; sepy -= dy
        def combine(vi, coh, sep, ali):
            s = tos(vi, POS) + (coh >> CSH) + (sep >> SSH) + (ali >> ASH)   # >> on ints = arithmetic shift
            if s > VMAX: s = VMAX
            elif s < -VMAX: s = -VMAX
            return s
        nvx = combine(vix, cohx, sepx, alix); nvy = combine(viy, cohy, sepy, aliy)
        npx = (pix + nvx) & M16; npy = (piy + nvy) & M16
        new.append((npx, npy, nvx & M16, nvy & M16))
    return new

# ============================== packing + order parameter ==============================
def pack(state):
    inp = [0] * (N * 4 * POS)
    for i in range(N):
        for f, val in enumerate(state[i]):
            for b in range(POS): inp[(i * 4 + f) * POS + b] = (val >> b) & 1
    return inp

def unpack(v, out2):
    st = []
    for i in range(N):
        fields = []
        for f in range(4):
            base = (i * 4 + f) * POS
            fields.append(sum(((0 if w == 0 else 1 if w == 1 else v[w] & 1) << b)
                              for b, w in enumerate(out2[base:base + POS])))
        st.append(tuple(fields))
    return st

def order_param(state):                                    # phi = |mean unit velocity|  in [0,1]
    sx = sy = 0.0
    for (_, _, vx, vy) in state:
        vx, vy = tos(vx, POS), tos(vy, POS); m = math.hypot(vx, vy)
        if m > 0: sx += vx / m; sy += vy / m
    return math.hypot(sx, sy) / N

def mean_speed(state):
    return sum(math.hypot(tos(vx, POS), tos(vy, POS)) for (_, _, vx, vy) in state) / N

def rand_state(rng, box=2500, vspan=30):
    return [((rng.randint(-box, box) & M16), (rng.randint(-box, box) & M16),
             (rng.randint(-vspan, vspan) & M16), (rng.randint(-vspan, vspan) & M16)) for _ in range(N)]

# ============================== depth ==============================
def depth_of(g, gates, out2):
    base = 2 + g.n_in; d = [0] * (base + len(gates))
    for k, (op, a, b) in enumerate(gates): d[base + k] = 1 + max(d[a], d[b])
    return max((d[w] for w in out2), default=0)

# ============================== main ==============================
def main():
    t0 = time.time()
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    print("\n  MUHL_BOIDS -- Reynolds flocking (separation/alignment/cohesion) as fixed-point gates\n", flush=True)

    tb = time.time(); g, run, gates, out2 = build_step()
    depth = depth_of(g, gates, out2)
    print(f"  fabricated boids step : N={N} agents, {len(gates):,} gates, depth {depth}, "
          f"{g.n_in} input bits  (built {time.time()-tb:.1f}s)", flush=True)

    STEPS = 300
    rng = random.Random(1234)
    state = rand_state(rng)
    ref = list(state)

    byte_exact = True; first_mismatch = None
    traj = []                                              # (step, phi, mean_speed)
    traj.append((0, order_param(state), mean_speed(state)))
    for step in range(1, STEPS + 1):
        v = run(pack(state), 1)
        gate_next = unpack(v, out2)
        ref = ref_step(ref)
        if gate_next != ref:
            byte_exact = False; first_mismatch = step; break
        state = gate_next
        traj.append((step, order_param(state), mean_speed(state)))

    print(f"  byte-exact vs Python  : {byte_exact}  "
          f"({'all %d ticks matched' % STEPS if byte_exact else 'MISMATCH at tick %d' % first_mismatch})",
          flush=True)

    phi0 = traj[0][1]; phiN = traj[-1][1]
    print(f"\n  EMERGENT FLOCK COHERENCE (alignment order parameter phi in [0,1], from random start):", flush=True)
    print(f"  {'tick':>5}  {'phi':>6}  {'mean|v|':>8}   flock alignment", flush=True)
    marks = [t for t in range(0, len(traj), max(1, len(traj) // 20))]
    if (len(traj) - 1) not in marks: marks.append(len(traj) - 1)
    for idx in marks:
        s, phi, ms = traj[idx]
        bar = "#" * int(round(phi * 40))
        print(f"  {s:>5}  {phi:>6.3f}  {ms:>8.2f}   {bar}", flush=True)

    print(f"\n  phi: {phi0:.3f} (random) -> {phiN:.3f} (flocked)   rise = {phiN - phi0:+.3f}", flush=True)
    print(f"  EMERGENCE: local separation/alignment/cohesion rules -> global velocity coherence.", flush=True)
    print(f"\n[done] {time.time()-t0:.1f}s · no numpy · no float in the dynamics · titan.gguf not opened.", flush=True)

if __name__ == "__main__":
    main()
