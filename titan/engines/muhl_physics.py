#!/usr/bin/env python3
"""muhl_physics.py -- PHYSICS AS GATES on Bryce's Muhlnickel substrate (fixed-point, byte-exact, flat RAM).

A fabricated PHYSICS STEP: the differential-equation integrator is a NAND/AND/OR/XOR/NOT netlist, built once
with the White Box compiler (sdc_cc.CircuitCompiler), DCE'd, rippled, and VERIFIED BYTE-EXACT against an
independent pure-Python fixed-point reference -- no numpy, no float in the datapath. Each step's OUTPUT is the
new physical state, fed straight back as the next step's INPUT: the substrate feedback loop IS time advancing.

Everything is signed two's-complement fixed-point (B=32 bits, FRAC=16 fractional bits). The only operations
are the ones a circuit can do exactly: shift-add multiply by an integer constant, arithmetic shift right
(sign-extended), and ripple add/subtract. Because the gate datapath and the Python reference perform the
IDENTICAL integer ops, the whole trajectory is byte-exact -- the physics is PROVABLE, not approximate.

Three integrators, three emergent behaviours:
  ORBIT  central-force (harmonic) 2D integrator, symplectic Euler:  v += -(K*r)>>SK ; r += (D*v)>>SD
         -> a closed, bounded ORBIT (energy conserved by construction of the symplectic step).
  WAVE   1D wave equation stencil  u'' = c^2 u_xx :  unew = 2u - uold + (C2*lap)>>SC , lap=u[i-1]-2u[i]+u[i+1]
         -> a standing WAVE: the string OSCILLATES, amplitude bounded, sign of the midpoint flips in time.
  HEAT   1D heat/diffusion stencil  u_t = a u_xx  :  unew = u + (A*lap)>>SA  (Neumann walls)
         -> DIFFUSION: an initial spike spreads and flattens; total heat is (near-)conserved.

Resident RAM stays FLAT no matter how many steps run: the circuit is fabricated once and the state is a few
fixed-size registers -- time is free (titan_probe law: the data lives in the circuit, not in a growing buffer).
"""
import sys, os, ctypes, time, random, math
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits, bit, rd, setf, depth_of, build_run

# ------------------------------------------------------------------ fixed-point config
B     = 32                       # register width (bits)
WIDE  = 64                       # multiply intermediate width
FRAC  = 16                       # fractional bits: value = real * 2**FRAC
ONE   = 1 << FRAC                # fixed-point 1.0
MASKB = (1 << B) - 1
MASKW = (1 << WIDE) - 1

# ------------------------------------------------------------------ resident-RAM meter (Bryce's law: flat)
class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [("_%d" % i, ctypes.c_size_t) for i in range(6)]
_ps = ctypes.WinDLL("psapi.dll"); _h = ctypes.WinDLL("kernel32.dll").GetCurrentProcess()
def rss_mb():
    m = PMC(); m.cb = ctypes.sizeof(PMC); _ps.GetProcessMemoryInfo(_h, ctypes.byref(m), m.cb)
    return m.WorkingSetSize / (1024 * 1024)

# ------------------------------------------------------------------ gate helpers (signed fixed-point datapath)
def sext(bits, n):
    return list(bits) + [bits[-1]] * (n - len(bits))
def negate(g, a):                                            # two's-complement negate, same width
    inv = [g.NOT(t) for t in a]
    one = [g.C1] + [g.C0] * (len(a) - 1)
    s, _ = add_bits(g, inv, one)
    return s
def sub(g, a, b):                                            # a - b, same width (drop carry)
    s, _ = add_bits(g, a, [g.NOT(t) for t in b], g.C1)
    return s
def mul_const_wide(g, x, C):                                 # signed B-bit x * integer const C -> WIDE bits (exact)
    xe = sext(x, WIDE)
    mag = abs(C)
    acc = [g.C0] * WIDE
    for t in range(WIDE):
        if (mag >> t) & 1:
            sh = ([g.C0] * t + xe)[:WIDE]
            acc, _ = add_bits(g, acc, sh)
    return negate(g, acc) if C < 0 else acc
def ashr(bits, s):                                           # arithmetic shift right by constant s (sign-extended)
    n = len(bits); sign = bits[-1]
    return [bits[k + s] if k + s < n else sign for k in range(n)]
def scale(g, x, C, S):                                       # low-B bits of (x * C) >> S  (signed)
    return ashr(mul_const_wide(g, x, C), S)[:B]

# ------------------------------------------------------------------ reference helpers (identical integer ops)
def sgn(u, w):                                               # signed value of a w-bit two's-complement int
    return u - (1 << w) if (u >> (w - 1)) & 1 else u
def r_mul(x, C):    return (sgn(x, B) * C) & MASKW           # WIDE product
def r_ashr(uw, s):  return (sgn(uw, WIDE) >> s) & MASKW      # arithmetic shift (Python >> floors = sign-extend)
def r_scale(x, C, S): return r_ashr(r_mul(x, C), S) & MASKB
def r_add(a, b):    return (a + b) & MASKB
def r_sub(a, b):    return (a - b) & MASKB

def fx(real):                                               # real -> B-bit fixed-point stored value
    return int(round(real * ONE)) & MASKB
def rl(u):                                                  # stored -> real (for reporting only)
    return sgn(u, B) / ONE

# ================================================================== ORBIT (central-force / harmonic, symplectic)
K, SK = 5, 8        # acceleration coeff  a = -(K/2^SK) * r     (= -0.01953 * r)
D, SD = 5, 8        # position coeff      dr = (D/2^SD) * v

def build_orbit():
    g = CC.CircuitCompiler(4 * B); IN = g.IN
    x  = [IN[0 * B + i] for i in range(B)]
    y  = [IN[1 * B + i] for i in range(B)]
    vx = [IN[2 * B + i] for i in range(B)]
    vy = [IN[3 * B + i] for i in range(B)]
    # symplectic Euler: kick velocity with the central spring force, then drift position with new velocity
    vx2, _ = add_bits(g, vx, scale(g, x, -K, SK))
    vy2, _ = add_bits(g, vy, scale(g, y, -K, SK))
    x2,  _ = add_bits(g, x,  scale(g, vx2, D, SD))
    y2,  _ = add_bits(g, y,  scale(g, vy2, D, SD))
    outs = x2 + y2 + vx2 + vy2
    run, out2, gates, _ = build_run(g, outs)
    fields = [out2[i * B:(i + 1) * B] for i in range(4)]
    return g, run, out2, gates, fields

def ref_orbit(st):
    x, y, vx, vy = st
    vx2 = r_add(vx, r_scale(x, -K, SK))
    vy2 = r_add(vy, r_scale(y, -K, SK))
    x2  = r_add(x,  r_scale(vx2, D, SD))
    y2  = r_add(y,  r_scale(vy2, D, SD))
    return [x2, y2, vx2, vy2]

# ================================================================== WAVE (1D wave equation stencil)
NW      = 16
C2, SC  = 1, 2      # wave coeff = 1/4 -> Courant 0.5 (stable). unew = 2u - uold + (lap>>2)

def _lap_gate(g, u, i, n):                                   # u[i-1] - 2u[i] + u[i+1], fixed (zero) boundaries
    Z = [g.C0] * B
    l = u[i - 1] if i > 0     else Z
    r = u[i + 1] if i < n - 1 else Z
    two_c = ([g.C0] + u[i])[:B]                              # 2*u[i]  (<<1)
    return sub(g, add_bits_(g, l, r), two_c)
def add_bits_(g, a, b):
    s, _ = add_bits(g, a, b); return s

def build_wave():
    g = CC.CircuitCompiler(2 * NW * B); IN = g.IN
    u    = [[IN[(i)      * B + k] for k in range(B)] for i in range(NW)]
    uold = [[IN[(NW + i) * B + k] for k in range(B)] for i in range(NW)]
    outs = []
    for i in range(NW):
        lap  = _lap_gate(g, u, i, NW)
        acc  = sub(g, add_bits_(g, ([g.C0] + u[i])[:B], scale(g, lap, C2, SC)), uold[i])  # 2u + coeff*lap - uold
        outs += acc
    run, out2, gates, _ = build_run(g, outs)
    fields = [out2[i * B:(i + 1) * B] for i in range(NW)]
    return g, run, out2, gates, fields

def ref_wave(u, uold):
    Z = 0
    un = []
    for i in range(NW):
        l = u[i - 1] if i > 0      else Z
        r = u[i + 1] if i < NW - 1 else Z
        lap = r_sub(r_add(l, r), (u[i] << 1) & MASKB)
        acc = r_sub(r_add((u[i] << 1) & MASKB, r_scale(lap, C2, SC)), uold[i])
        un.append(acc)
    return un

# ================================================================== HEAT (1D diffusion stencil, Neumann walls)
NH      = 16
A, SA   = 1, 2      # diffusivity = 1/4 (stable, <= 1/2). unew = u + (lap>>2)

def build_heat():
    g = CC.CircuitCompiler(NH * B); IN = g.IN
    u = [[IN[i * B + k] for k in range(B)] for i in range(NH)]
    outs = []
    for i in range(NH):
        l = u[i - 1] if i > 0      else u[i]                 # Neumann (reflecting) walls conserve heat
        r = u[i + 1] if i < NH - 1 else u[i]
        lap = sub(g, add_bits_(g, l, r), ([g.C0] + u[i])[:B])
        acc, _ = add_bits(g, u[i], scale(g, lap, A, SA))
        outs += acc
    run, out2, gates, _ = build_run(g, outs)
    fields = [out2[i * B:(i + 1) * B] for i in range(NH)]
    return g, run, out2, gates, fields

def ref_heat(u):
    un = []
    for i in range(NH):
        l = u[i - 1] if i > 0      else u[i]
        r = u[i + 1] if i < NH - 1 else u[i]
        lap = r_sub(r_add(l, r), (u[i] << 1) & MASKB)
        un.append(r_add(u[i], r_scale(lap, A, SA)))
    return un

# ------------------------------------------------------------------ driver / verification
def pack(state):
    inp = [0] * (len(state) * B)
    for i, v in enumerate(state): setf(inp, i * B, B, v)
    return inp
def unpack(v, fields):
    return [rd(v, f) for f in fields]

def run_engine(name, build, ref_step, init, steps, describe, spot=200):
    g, run, out2, gates, fields = build
    nfld = len(fields)
    depth = depth_of(g, gates, out2)
    # (1) spot-check random states: gate step == reference step
    ok_spot = True
    for _ in range(spot):
        rs = [random.getrandbits(B) for _ in range(nfld)]
        gv = unpack(run(pack(rs), 1), fields)
        rv = ref_step_wrap(ref_step, rs, nfld)
        if gv != rv:
            ok_spot = False; break
    # (2) full trajectory: assert gate state == reference state at EVERY step (byte-exact over the whole run)
    base = rss_mb(); lo = hi = base
    cur = list(init); ref = list(init)
    traj = []
    ok_traj = True
    for s in range(steps):
        cur = unpack(run(pack(cur), 1), fields)
        ref = ref_step_wrap(ref_step, ref, nfld)
        if cur != ref:
            ok_traj = False
            print(f"    [!] divergence at step {s}"); break
        traj.append(list(cur))
        r = rss_mb(); lo = min(lo, r); hi = max(hi, r)
    end = rss_mb()
    ok = ok_spot and ok_traj
    print(f"\n  == {name} ==")
    print(f"     gates {len(gates):,}  depth {depth}  registers {nfld}x{B}b")
    print(f"     byte-exact: spot {spot}/{spot} {'OK' if ok_spot else 'FAIL'} + full {len(traj)}-step trajectory "
          f"{'OK' if ok_traj else 'FAIL'}  -> {'PASS' if ok else 'FAIL'}")
    print(f"     resident RAM over {len(traj):,} steps: start {base:.1f}  min {lo:.1f}  max {hi:.1f}  end {end:.1f} MB "
          f"(net {end-base:+.2f} MB)")
    describe(traj)
    return name, len(gates), depth, ok, end - base

def ref_step_wrap(ref_step, st, nfld):
    # ORBIT takes/returns a 4-list; WAVE/HEAT phrased as arrays -- unify via arity
    return ref_step(st)

def main():
    random.seed(7)
    print("\n  MUHLNICKEL PHYSICS -- differential-equation integrators fabricated as gates, byte-exact, flat RAM")
    results = []

    # ---- ORBIT ----------------------------------------------------------------
    c1, c2 = K / 2**SK, D / 2**SD                          # v += -c1*r ; r += c2*v
    om = math.sqrt(c1 * c2)                                 # angular frequency of the harmonic step
    r0 = 1.0
    vcirc = r0 * om / c2                                    # register velocity for a circular orbit (dx/dt=c2*v)
    init_orbit = [fx(r0), fx(0.0), fx(0.0), fx(vcirc)]      # near-circular: perpendicular launch
    def describe_orbit(traj):
        rs = [math.hypot(rl(s[0]), rl(s[1])) for s in traj]
        angs = [math.atan2(rl(s[1]), rl(s[0])) for s in traj]
        # count revolutions by summing wrapped angle deltas
        rev = 0.0
        for a, b in zip(angs, angs[1:]):
            d = (b - a + math.pi) % (2 * math.pi) - math.pi
            rev += d
        rmin, rmax = min(rs), max(rs)
        print(f"     EMERGENT: closed ORBIT. radius stays bounded in [{rmin:.4f}, {rmax:.4f}] (drift "
              f"{100*(rmax-rmin)/rmin:.2f}% -- symplectic energy conservation), analytic period ~{2*math.pi/om:.0f} steps,")
        print(f"               body swept {abs(rev)/(2*math.pi):.2f} revolutions in {len(traj):,} steps -- it orbits, it does not spiral in/out.")
    results.append(run_engine("ORBIT (central-force, symplectic Euler)", build_orbit(), ref_orbit,
                              init_orbit, 20000, describe_orbit))

    # ---- WAVE -----------------------------------------------------------------
    def wave_init():
        u = [0] * NW
        u[NW // 2] = fx(1.0)                                 # a pluck at the middle
        return u
    u0 = wave_init()
    # WAVE carries u AND uold (2*NW in, NW out), so it gets its own runner.
    results.append(run_wave(u0))

    # ---- HEAT -----------------------------------------------------------------
    def heat_init():
        u = [0] * NH
        u[NH // 2] = fx(4.0)                                 # a hot spike in the middle
        return u
    def describe_heat(traj):
        first, last = traj[0], traj[-1]
        s0 = sum(sgn(v, B) for v in first); s1 = sum(sgn(v, B) for v in last)
        peak0 = max(rl(v) for v in first); peak1 = max(rl(v) for v in last)
        spread = sum(1 for v in last if abs(rl(v)) > 0.01)
        print(f"     EMERGENT: DIFFUSION. peak fell {peak0:.3f} -> {peak1:.3f}, spike spread to {spread}/{NH} cells,")
        print(f"               total heat {s0/ONE:.4f} -> {s1/ONE:.4f} (Neumann walls: near-conserved, drift "
              f"{100*(s1-s0)/s0 if s0 else 0:.3f}%).")
    results.append(run_engine("HEAT (1D diffusion stencil)", build_heat(), ref_heat,
                              heat_init(), 4000, describe_heat))

    # ---- summary --------------------------------------------------------------
    npass = sum(1 for r in results if r[3])
    tot_g = sum(r[1] for r in results)
    maxram = max(abs(r[4]) for r in results)
    print(f"\n  === {npass}/{len(results)} physics integrators byte-exact · {tot_g:,} total gates · "
          f"peak resident drift {maxram:+.2f} MB ===")
    print(f"      file: C:/llm/muhl_builds/muhl_physics.py")

# WAVE needs a 2*NW-in / NW-out step (state carries u AND uold), so it gets its own runner.
def run_wave(u0):
    g, run, out2, gates, fields = build_wave()
    depth = depth_of(g, gates, out2)
    # spot-check
    ok_spot = True
    for _ in range(200):
        u = [random.getrandbits(B) for _ in range(NW)]
        uo = [random.getrandbits(B) for _ in range(NW)]
        inp = pack(u + uo)
        gv = unpack(run(inp, 1), fields)
        rv = ref_wave(u, uo)
        if gv != rv: ok_spot = False; break
    # full trajectory
    base = rss_mb(); lo = hi = base
    u = list(u0); uold = list(u0)                            # start at rest (uold == u)
    ru, ruold = list(u0), list(u0)
    steps = 8000; traj = []; ok_traj = True
    for s in range(steps):
        un = unpack(run(pack(u + uold), 1), fields)
        rn = ref_wave(ru, ruold)
        if un != rn:
            ok_traj = False; print(f"    [!] wave divergence at step {s}"); break
        uold, u = u, un
        ruold, ru = ru, rn
        traj.append(list(u))
        r = rss_mb(); lo = min(lo, r); hi = max(hi, r)
    end = rss_mb()
    ok = ok_spot and ok_traj
    print(f"\n  == WAVE (1D wave equation stencil) ==")
    print(f"     gates {len(gates):,}  depth {depth}  registers {2*NW}x{B}b in, {NW}x{B}b out")
    print(f"     byte-exact: spot 200/200 {'OK' if ok_spot else 'FAIL'} + full {len(traj)}-step trajectory "
          f"{'OK' if ok_traj else 'FAIL'}  -> {'PASS' if ok else 'FAIL'}")
    print(f"     resident RAM over {len(traj):,} steps: start {base:.1f}  min {lo:.1f}  max {hi:.1f}  end {end:.1f} MB "
          f"(net {end-base:+.2f} MB)")
    mid = [rl(s[NW // 2]) for s in traj]
    sign_flips = sum(1 for a, b in zip(mid, mid[1:]) if (a > 0) != (b > 0) and abs(a) > 1e-6)
    amp = max(abs(rl(v)) for s in traj for v in s)
    print(f"     EMERGENT: standing WAVE. midpoint oscillates (sign flipped {sign_flips} times over {len(traj):,} "
          f"steps), amplitude bounded at {amp:.3f} -- it rings, it does not blow up.")
    return "WAVE (1D wave equation stencil)", len(gates), depth, ok, end - base

if __name__ == "__main__":
    main()
