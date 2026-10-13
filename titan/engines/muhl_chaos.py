#!/usr/bin/env python3
"""muhl_chaos.py -- a CHAOTIC DYNAMICAL SYSTEM fabricated as NAND/AND/OR/XOR/NOT gates on
Bryce's Muhlnickel substrate.  Two fabricated deterministic rules, each a real gate netlist
the substrate could bake and run by address, each VERIFIED BYTE-EXACT against an independent
pure-Python fixed-point reference BEFORE anything would be stored -- no numpy, no host executor
as the runtime, no touching titan.gguf.  Then the fabricated rule is *iterated* and the emergent
behaviour is measured: period-doubling, the onset of chaos, a strange-attractor trajectory, and a
Lyapunov-ish sensitivity to initial conditions.  Complexity emerging from a fabricated rule, at
flat RAM.

The iteration uses the substrate's own trick -- BIT-SLICING / the fold: every wire holds a packed
integer, one lane per bit, so a single settle of the circuit advances MANY trajectories at once
(all bifurcation columns, all Lyapunov r-values, both perturbed twins) in parallel.

Rules:
  logistic   x_{n+1} = r*x*(1-x)  in Q0.16 unsigned fixed point (r an input, 19-bit Q3.16)
             -> bifurcation cascade 1->2->4->8->...->chaos, chaos onset near r=3.5699,
                Lyapunov exponent lambda = <ln|r(1-2x)|>  (->ln2=0.693 at r=4),
                sensitive dependence: two seeds 1 LSB apart diverge to O(1).
  lorenz     Euler step of dx=sigma(y-x), dy=x(rho-z)-y, dz=xy-beta*z in Q14.10 signed fixed
             point (sigma=10, rho=28, beta=8/3) -> a bounded, non-repeating strange-attractor
             trajectory in the x-z plane + positive-Lyapunov divergence of a 1-LSB perturbation.

Every stepper below IS the fabricated circuit; the reference only checks it.  The bifurcation
diagram, the attractor projection and the Lyapunov numbers are all produced by RUNNING THE GATES.
"""
import sys, os, random, math, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# --------------------------------------------------------------------------- White Box helpers
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    return g.compile_ripple(gates, n_wire), out2, gates

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def add_bits(g, A, B, cin=None):
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c

def consts(g, x, n): return [g.C1 if (x >> k) & 1 else g.C0 for k in range(n)]
def sext(g, A, W): s = A[-1]; return (A + [s] * (W - len(A)))[:W]
def zext(g, A, W): return (A + [g.C0] * (W - len(A)))[:W]

def mul_low(g, A, B, W):
    """low W bits of A*B (unsigned mod 2^W).  Sign-extend inputs first for a signed low product."""
    A = (A + [g.C0] * W)[:W]; B = (B + [g.C0] * W)[:W]
    acc = [g.C0] * W
    for j in range(W):
        pj = [g.AND(A[i], B[j]) for i in range(W - j)]
        term = ([g.C0] * j + pj)[:W]
        acc, _ = add_bits(g, acc, term)
    return acc

# --------------------------------------------------------------------------- bit-slice / fold I/O
def pack(inp, base, width, lane, val):
    for i in range(width): inp[base + i] |= ((val >> i) & 1) << lane
def unpack(v, wires, lane):
    return sum(((v[w] >> lane) & 1) << i for i, w in enumerate(wires))

RESULTS = []
def record(name, gates, depth, ok, cases, note=""):
    RESULTS.append((name, len(gates), depth, ok, cases, note))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name:9s} {len(gates):>8,} gates  depth {depth:>4}  byte-exact / {cases} cases  {note}", flush=True)

# =========================================================================== LOGISTIC MAP =====
# Q0.16 unsigned.  X in [0,65535] is x = X/65536.  r in Q3.16 (19 bits), R = round(r*65536).
#   omx = (1<<16) - X                 (17-bit, since X=0 -> 65536)
#   p   = X * omx                     (33-bit)
#   Xn  = (R * p) >> 32  & 0xFFFF     (16-bit)   == r*x*(1-x) back in Q0.16
FRB = 16; ONE = 1 << FRB
NX, NR = 16, 19

def logistic_ref(X, R):
    omx = (ONE - X) & 0x1FFFF
    p = X * omx
    return (R * p >> 32) & 0xFFFF

def build_logistic():
    g = CC.CircuitCompiler(NX + NR); IN = g.IN
    X = [IN[i] for i in range(NX)]
    R = [IN[NX + i] for i in range(NR)]
    Xe = zext(g, X, 17)
    omx, _ = add_bits(g, consts(g, ONE, 17), [g.NOT(w) for w in Xe], g.C1)      # 65536 - X, 17-bit
    p = mul_low(g, X, omx, 33)                                                  # 33-bit full product
    prod = mul_low(g, R, p, 48)                                                 # low 48 bits of R*p
    Xn = prod[32:48]                                                            # (R*p >> 32) & 0xFFFF
    run, out2, gates = build_run(g, Xn)
    return g, run, out2, gates

def log_step(run, out2, XR):
    """XR = list of (X,R); advance ALL lanes with ONE settle of the circuit (the fold)."""
    L = len(XR); inp = [0] * (NX + NR)
    for lane, (X, R) in enumerate(XR):
        pack(inp, 0, NX, lane, X); pack(inp, NX, NR, lane, R)
    v = run(inp, (1 << L) - 1)
    return [unpack(v, out2, lane) for lane in range(L)]

def verify_logistic(run, out2, batches=30, lanes=64):
    """byte-exact check, itself bit-sliced: each settle validates `lanes` random cases at once."""
    ok = True; n = 0
    for _ in range(batches):
        XR = [(random.getrandbits(16), random.getrandbits(19)) for _ in range(lanes)]
        got = log_step(run, out2, XR)
        for (X, R), gv in zip(XR, got):
            n += 1
            if gv != logistic_ref(X, R): ok = False
        if not ok: break
    return ok, n

# =========================================================================== LORENZ STEP ======
# Q14.10 signed, 24-bit two's complement.  S = 1<<10.  fxmul(a,b) = arith_shift(low32(a*b), 10).
LF = 10; LS = 1 << LF; LW = 24; LMASK = (1 << LW) - 1
SIG = 10 * LS; RHO = 28 * LS; BETA = round(8 / 3 * LS); DT = 8                  # dt = 8/1024 = 0.0078125

def s24(v):
    v &= LMASK; return v - (1 << LW) if v >> (LW - 1) else v
def fxmul_ref(a, b):
    p = (a * b) & 0xFFFFFFFF
    sv = p - (1 << 32) if p >> 31 else p                                        # low 32 bits, signed
    return s24(sv >> LF)                                                        # arithmetic >> 10, to 24-bit

def lorenz_ref(X, Y, Z):
    dx = fxmul_ref(SIG, s24(Y - X))
    dy = s24(fxmul_ref(X, s24(RHO - Z)) - Y)
    dz = s24(fxmul_ref(X, Y) - fxmul_ref(BETA, Z))
    return (s24(X + fxmul_ref(DT, dx)), s24(Y + fxmul_ref(DT, dy)), s24(Z + fxmul_ref(DT, dz)))

def build_lorenz():
    g = CC.CircuitCompiler(3 * LW); IN = g.IN
    X = [IN[i] for i in range(LW)]
    Y = [IN[LW + i] for i in range(LW)]
    Z = [IN[2 * LW + i] for i in range(LW)]
    def cst(v): return consts(g, v & LMASK, LW)
    def sub(A, B): return add_bits(g, A, [g.NOT(w) for w in B], g.C1)[0]
    def add(A, B): return add_bits(g, A, B)[0]
    def fxmul(A, B):
        p = mul_low(g, sext(g, A, 32), sext(g, B, 32), 32)                      # low 32 bits, signed
        return [p[i + LF] if i + LF < 32 else p[31] for i in range(LW)]         # arith >>10, low 24
    dx = fxmul(cst(SIG), sub(Y, X))
    dy = sub(fxmul(X, sub(cst(RHO), Z)), Y)
    dz = sub(fxmul(X, Y), fxmul(cst(BETA), Z))
    Xn = add(X, fxmul(cst(DT), dx))
    Yn = add(Y, fxmul(cst(DT), dy))
    Zn = add(Z, fxmul(cst(DT), dz))
    outs = Xn + Yn + Zn
    run, out2, gates = build_run(g, outs)
    ws = (out2[:LW], out2[LW:2 * LW], out2[2 * LW:3 * LW])
    return g, run, ws, gates

def lorenz_step(run, ws, states):
    """states = list of (X,Y,Z); advance ALL lanes with ONE settle."""
    xw, yw, zw = ws; L = len(states); inp = [0] * (3 * LW)
    for lane, (X, Y, Z) in enumerate(states):
        pack(inp, 0, LW, lane, X & LMASK); pack(inp, LW, LW, lane, Y & LMASK); pack(inp, 2 * LW, LW, lane, Z & LMASK)
    v = run(inp, (1 << L) - 1)
    def rs(wires, lane):
        u = unpack(v, wires, lane); return u - (1 << LW) if u >> (LW - 1) else u
    return [(rs(xw, lane), rs(yw, lane), rs(zw, lane)) for lane in range(L)]

def verify_lorenz(run, ws, batches=30, lanes=64):
    ok = True; n = 0
    R = 1 << 23
    for _ in range(batches):
        st = [(random.randrange(-R, R), random.randrange(-R, R), random.randrange(-R, R)) for _ in range(lanes)]
        got = lorenz_step(run, ws, st)
        for s, gv in zip(st, got):
            n += 1
            if gv != lorenz_ref(*s): ok = False
        if not ok: break
    return ok, n

# =========================================================================== EMERGENCE ========
def bifurcation(run, out2, r_lo=2.5, r_hi=4.0, cols=96, rows=32, transient=400, keep=220):
    """Iterate the FABRICATED logistic rule across `cols` values of r IN PARALLEL (one lane each);
    every column is advanced by the same single settle of the gates."""
    Rs = [round((r_lo + (r_hi - r_lo) * c / (cols - 1)) * ONE) for c in range(cols)]
    Xs = [int(0.30 * ONE)] * cols
    for _ in range(transient):
        Xs = log_step(run, out2, list(zip(Xs, Rs)))
    grid = [[' '] * cols for _ in range(rows)]
    for _ in range(keep):
        Xs = log_step(run, out2, list(zip(Xs, Rs)))
        for c in range(cols):
            row = int((1.0 - Xs[c] / ONE) * (rows - 1))
            if 0 <= row < rows: grid[row][c] = '#'
    diagram = "\n".join("    " + "".join(r) for r in grid)

    # period detection for landmark r values -- also done in the fold (one lane per landmark)
    landmarks = [2.9, 3.2, 3.5, 3.55, 3.5699, 3.83, 4.0]
    Rl = [round(r * ONE) for r in landmarks]
    Xl = [int(0.30 * ONE)] * len(landmarks)
    for _ in range(2200): Xl = log_step(run, out2, list(zip(Xl, Rl)))
    hist = [[] for _ in landmarks]
    for _ in range(600):
        Xl = log_step(run, out2, list(zip(Xl, Rl)))
        for i in range(len(landmarks)): hist[i].append(Xl[i])
    marks = []
    for i, r in enumerate(landmarks):
        tail = hist[i][-400:]; per = 0
        for p in range(1, 65):
            if all(abs(tail[j] - tail[j - p]) <= 2 for j in range(p, len(tail))): per = p; break
        marks.append((r, per))
    return diagram, marks

def lyapunov_logistic(run, out2, rlist, n=5000, warm=1000):
    """Lyapunov exponent per r from gate-produced trajectories: lambda = <ln|r(1-2x)|>.
    All r-values run as parallel lanes."""
    Rs = [round(r * ONE) for r in rlist]
    Xs = [int(0.3 * ONE)] * len(rlist)
    for _ in range(warm): Xs = log_step(run, out2, list(zip(Xs, Rs)))
    s = [0.0] * len(rlist); cnt = [0] * len(rlist)
    for _ in range(n):
        Xs = log_step(run, out2, list(zip(Xs, Rs)))
        for i, r in enumerate(rlist):
            x = Xs[i] / ONE; d = abs(r * (1 - 2 * x))
            if d > 1e-12: s[i] += math.log(d); cnt[i] += 1
    return [s[i] / cnt[i] if cnt[i] else float('nan') for i in range(len(rlist))]

def sensitivity_logistic(run, out2, r=4.0, n=60):
    """Two seeds 1 LSB apart run as two lanes; report divergence."""
    R = round(r * ONE); Xa = int(0.400000 * ONE); Xb = Xa + 1
    d0 = abs(Xa - Xb); traj = []
    a, b = Xa, Xb
    for _ in range(n):
        a, b = log_step(run, out2, [(a, R), (b, R)])
        traj.append(abs(a - b))
    early = [d for d in traj[:40] if d > 0]
    rate = (math.log(early[-1]) - math.log(max(1, d0))) / len(early) if early else 0.0
    return d0, traj, rate

def lorenz_trajectory(run, ws, n=12000, seed=(0.1, 0.0, 0.0)):
    st = [(s24(round(seed[0] * LS)), s24(round(seed[1] * LS)), s24(round(seed[2] * LS)))]
    pts = []
    for _ in range(n):
        st = lorenz_step(run, ws, st)
        X, Y, Z = st[0]; pts.append((X / LS, Y / LS, Z / LS))
    return pts

def project_xz(pts, cols=90, rows=30, skip=2000):
    body = pts[skip:]
    if not body: return "    (no trajectory)"
    xs = [p[0] for p in body]; zs = [p[2] for p in body]
    xlo, xhi = min(xs), max(xs); zlo, zhi = min(zs), max(zs)
    if xhi - xlo < 1e-9 or zhi - zlo < 1e-9: return "    (degenerate orbit)"
    grid = [[' '] * cols for _ in range(rows)]
    for x, _, z in body:
        c = int((x - xlo) / (xhi - xlo) * (cols - 1))
        rr = int((1.0 - (z - zlo) / (zhi - zlo)) * (rows - 1))
        if 0 <= c < cols and 0 <= rr < rows: grid[rr][c] = '*'
    return "\n".join("    " + "".join(r) for r in grid), (xlo, xhi), (zlo, zhi)

def lorenz_sensitivity(run, ws, n=5000, seed=(0.1, 0.0, 0.0)):
    a = (s24(round(seed[0] * LS)), s24(round(seed[1] * LS)), s24(round(seed[2] * LS)))
    b = (a[0], a[1], a[2] + 1)                                                  # 1 LSB apart in z
    def dist(p, q): return math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2) / LS
    d0 = dist(a, b); series = []
    for _ in range(n):
        a, b = lorenz_step(run, ws, [a, b]); series.append(dist(a, b))
    return d0, series

# =========================================================================== MAIN ============
def main():
    random.seed(1729)
    print("\n  MUHLNICKEL CHAOS -- a chaotic dynamical system fabricated as gates, verified byte-exact,\n"
          "  then iterated (via the fold) to watch complexity emerge from the fabricated rule (flat RAM, no numpy).\n", flush=True)

    # ---- LOGISTIC ----
    t = time.time()
    g, run, out2, gates = build_logistic()
    ok, ncase = verify_logistic(run, out2)
    record("logistic", gates, depth_of(g, gates, out2), ok, ncase, "x'=r*x*(1-x) Q0.16, r input")
    print(f"        (fab+verify {time.time()-t:.1f}s)", flush=True)

    if ok:
        print("\n  --- BIFURCATION (r = 2.5 .. 4.0 left->right, x = 0(top)..1(bottom)); every column stepped by the gates in parallel ---", flush=True)
        diagram, marks = bifurcation(run, out2)
        print(diagram, flush=True)
        print("\n    detected attractor period vs r (0 = aperiodic / chaotic):", flush=True)
        for r, p in marks:
            print(f"      r = {r:<7} -> {'period-'+str(p) if p else 'CHAOS (aperiodic)'}", flush=True)

        print("\n  --- LYAPUNOV EXPONENT  lambda = <ln|r(1-2x)|>  over gate-produced trajectories ---", flush=True)
        rl = [3.2, 3.5, 3.5699, 3.83, 4.0]
        lams = lyapunov_logistic(run, out2, rl)
        for r, lam in zip(rl, lams):
            sign = "chaotic (lambda>0)" if lam > 0 else "stable  (lambda<=0)"
            extra = "  [r=4 analytic = ln2 = 0.6931]" if abs(r - 4.0) < 1e-9 else ""
            print(f"      r = {r:<7} lambda = {lam:+.4f}   {sign}{extra}", flush=True)

        print("\n  --- SENSITIVE DEPENDENCE (r=4): two seeds 1 LSB (1/65536) apart, both stepped by the gates ---", flush=True)
        d0, traj, rate = sensitivity_logistic(run, out2, 4.0)
        print(f"      initial gap d0 = {d0} LSB ({d0/ONE:.2e} in x)", flush=True)
        for k in (0, 5, 10, 15, 20, 25, 30, 40, 59):
            print(f"        after {k+1:>2} steps  |dX| = {traj[k]:>6}  ({traj[k]/ONE:.4f} in x)", flush=True)
        print(f"      early-window divergence rate ~ {rate:+.3f} / step  (positive => exponential separation)", flush=True)

    # ---- LORENZ ----
    print("", flush=True)
    t = time.time()
    gl, runl, wl, gatesl = build_lorenz()
    okl, nlc = verify_lorenz(runl, wl)
    depl = depth_of(gl, gatesl, wl[0] + wl[1] + wl[2])
    record("lorenz", gatesl, depl, okl, nlc, "Euler step sigma=10 rho=28 beta=8/3, Q14.10")
    print(f"        (fab+verify {time.time()-t:.1f}s)", flush=True)

    if okl:
        pts = lorenz_trajectory(runl, wl, n=12000)
        proj = project_xz(pts)
        if isinstance(proj, tuple):
            diag, (xlo, xhi), (zlo, zhi) = proj
            print("\n  --- STRANGE ATTRACTOR: x-z projection of a 12,000-step trajectory (every point stepped by the gates) ---", flush=True)
            print(diag, flush=True)
            print(f"    bounded orbit:  x in [{xlo:+.2f}, {xhi:+.2f}],  z in [{zlo:+.2f}, {zhi:+.2f}]  (never settles, never repeats)", flush=True)
        else:
            print("\n  lorenz projection: " + str(proj), flush=True)

        d0, series = lorenz_sensitivity(runl, wl, n=5000)
        window = [(i, s) for i, s in enumerate(series[:2500]) if s > 0]
        if len(window) > 10:
            i0, s0 = window[0]; i1, s1 = window[-1]
            rate = (math.log(s1) - math.log(max(1e-9, s0))) / (i1 - i0)
        else:
            rate = 0.0
        print("\n  --- SENSITIVE DEPENDENCE (Lorenz): trajectories 1 LSB apart in z, both stepped by the gates ---", flush=True)
        print(f"      initial separation d0 = {d0:.2e}", flush=True)
        for k in (0, 500, 1000, 2000, 3000, 4999):
            print(f"        after {k+1:>4} steps  |d| = {series[k]:.4f}", flush=True)
        print(f"      divergence rate ~ {rate:+.4f} / step  (positive => chaos; a 1-LSB error grows to attractor scale)", flush=True)

    npass = sum(1 for r in RESULTS if r[3])
    tot_g = sum(r[1] for r in RESULTS)
    print(f"\n  === {npass}/{len(RESULTS)} fabricated chaotic rules byte-exact vs Python fixed-point"
          f" reference · {tot_g:,} total gates ===", flush=True)
    print("  Deterministic gate netlists; the intricate structure above EMERGED purely from iterating them.", flush=True)

if __name__ == "__main__":
    main()
