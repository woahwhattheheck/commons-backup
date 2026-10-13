#!/usr/bin/env python3
"""muhl_primitives.py -- a ZOO of small arithmetic primitives fabricated on the Muhlnickel substrate.

Every primitive is built as NAND/AND/OR/XOR/NOT gates with the White Box compiler
(sdc_cc.CircuitCompiler), dead-code-eliminated, rippled, and VERIFIED BYTE-EXACT against an
INDEPENDENT pure-Python reference -- exhaustively where the input space allows (<=65,536), on a
large random sample otherwise. Fabrication-time synthesis: prove the logic byte-exact BEFORE it
would ever be baked into titan.gguf. No numpy, no host executor as a runtime, no touching titan.

The zoo:
  isqrt16    integer sqrt (bit-by-bit / restoring) of a 32-bit x -> 16-bit floor(sqrt)   == math.isqrt
  cordic     fixed-point rotation-mode CORDIC sin/cos, B-bit two's complement            == integer-CORDIC ref
  popcount16 population count of a 16-bit word -> 5-bit count                             == bin(x).count('1')
  gray_enc   binary -> reflected Gray code (16-bit)                                       == x ^ (x>>1)
  gray_dec   reflected Gray code -> binary (16-bit)                                       == prefix-xor inverse
  priority16 priority encoder: index (+valid) of the HIGHEST set bit of a 16-bit word     == bit_length-1
  barrel16   barrel shifter: logical left shift of 16-bit data by a 4-bit amount          == (d<<a)&0xffff
  bcd_add    BCD adder: two decimal digits + carry-in -> decimal digit + carry-out        == decimal add
  clz16      leading-zero count of a 16-bit word -> 5-bit count                           == 16-bit_length
  ctz16      trailing-zero count of a 16-bit word -> 5-bit count                          == (x&-x) index
  satadd8    unsigned saturating adder: min(a+b, 0xFF) over 8-bit lanes                    == min(a+b,255)
  minmax8    min/max tree over 8 x 8-bit keys -> (min, max)                                == min()/max()
"""
import sys, os, math, random, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ------------------------------------------------------------------ shared helpers
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return run, out2, gates

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))     # LSB-first
def setf(inp, base, W, x):
    for b in range(W): inp[base + b] = (x >> b) & 1

def addc(g, A, B, cin=None):
    """ripple add of two equal-length wire vectors; returns (sum_list, carry_out)."""
    c = g.C0 if cin is None else cin
    o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c

def addfull(g, A, B):
    """add vectors of possibly-different length; returns sum with carry appended (len=max+1)."""
    n = max(len(A), len(B))
    A = A + [g.C0] * (n - len(A)); B = B + [g.C0] * (n - len(B))
    s, c = addc(g, A, B)
    return s + [c]

def mux1(g, s, a, b): return g.OR(g.AND(s, a), g.AND(g.NOT(s), b))            # s ? a : b
def muxw(g, s, A, B): return [mux1(g, s, A[k], B[k]) for k in range(len(A))]
def consts(g, x, n): return [g.C1 if (x >> k) & 1 else g.C0 for k in range(n)]
def notw(g, A): return [g.NOT(a) for a in A]

def cmp_ge(g, A, B):
    """unsigned A >= B -> wire (A,B equal length). carry-out of A-B == no borrow == A>=B."""
    _, c = addc(g, A, notw(g, B), g.C1)
    return c

RESULTS = []
def record(name, gates, depth, ok, cases, note=""):
    RESULTS.append((name, len(gates), depth, ok, cases))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name:10s} {len(gates):>7,} gates  depth {depth:>4}  byte-exact over {cases:>6} cases  {note}", flush=True)

# ================================================================ isqrt16 (bit-by-bit)
def prim_isqrt16():
    NBIT = 32; M = 34                                         # res transiently reaches ~2**30
    g = CC.CircuitCompiler(NBIT); IN = g.IN
    num = list(IN) + [g.C0] * (M - NBIT)                     # working remainder, zero-extended
    res = [g.C0] * M                                          # result accumulator (wide)
    for i in range(15, -1, -1):                              # bit = 1 << (2i), i = 15..0
        bitc = consts(g, 1 << (2 * i), M)
        t, _ = addc(g, res, bitc)                            # t = res + bit
        ge = cmp_ge(g, num, t)                               # num >= t ?
        diff, _ = addc(g, num, notw(g, t), g.C1)             # num - t
        num = muxw(g, ge, diff, num)
        rsh = res[1:] + [g.C0]                                # res >> 1
        addbit = muxw(g, ge, bitc, [g.C0] * M)               # + bit only when ge
        res, _ = addc(g, rsh, addbit)
    outs = res[:16]
    run, out2, gates = build_run(g, outs)
    ok = True; cases = 0
    tests = [0, 1, 2, 3, 4, 0xFFFFFFFF, (1 << 31), (1 << 31) + 1]
    tests += [k * k for k in (0, 1, 255, 256, 65535)] + [k * k - 1 for k in (1, 2, 256, 65535)]
    tests += [random.getrandbits(32) for _ in range(4000)]
    for x in tests:
        inp = [0] * NBIT; setf(inp, 0, NBIT, x)
        if rd(run(inp, 1), out2) != math.isqrt(x): ok = False; break
        cases += 1
    record("isqrt16", gates, depth_of(g, gates, out2), ok, cases, "32b -> 16b floor(sqrt) == math.isqrt")

# ================================================================ CORDIC sin/cos (fixed-point)
def prim_cordic():
    B = 24; N = 16
    scale = 1 << (B - 2)                                      # 1.0 in fixed point
    mask = (1 << B) - 1
    atan = [round(math.atan(2.0 ** -i) * scale) for i in range(N)]
    gain = 1.0
    for i in range(N): gain *= math.sqrt(1 + 4.0 ** -i)
    K = round(scale / gain)                                   # gain-compensated seed for x

    # ---- independent Python reference (integer CORDIC, two's complement B bits) ----
    def asr_ref(val, i):
        sign = (val >> (B - 1)) & 1; res = 0
        for k in range(B):
            src = k + i
            b = (val >> src) & 1 if src < B else sign
            res |= b << k
        return res
    def add_ref(a, b, cin): return (a + b + cin) & mask
    def cordic_ref(theta):
        x, y, z = K, 0, theta & mask
        for i in range(N):
            sign = (z >> (B - 1)) & 1                        # z < 0 ?
            xsh = asr_ref(x, i); ysh = asr_ref(y, i)
            if sign:                                          # z<0: x+=ysh, y-=xsh, z+=atan
                x = add_ref(x, ysh, 0); y = add_ref(y, (~xsh) & mask, 1); z = add_ref(z, atan[i], 0)
            else:                                             # z>=0: x-=ysh, y+=xsh, z-=atan
                x = add_ref(x, (~ysh) & mask, 1); y = add_ref(y, xsh, 0); z = add_ref(z, (~atan[i]) & mask, 1)
        return x, y, z

    # ---- gate build ----
    g = CC.CircuitCompiler(B); IN = g.IN
    def asr_g(v, i):                                          # arithmetic shift right by i (static)
        return [v[k + i] if k + i < B else v[B - 1] for k in range(B)]
    x = consts(g, K, B); y = [g.C0] * B; z = list(IN)
    for i in range(N):
        sign = z[B - 1]; nsign = g.NOT(sign)
        xsh = asr_g(x, i); ysh = asr_g(y, i)
        xterm = [g.XOR(ysh[k], nsign) for k in range(B)]     # sign? ysh : ~ysh
        x, _ = addc(g, x, xterm, nsign)                      # sign? x+ysh : x-ysh
        yterm = [g.XOR(xsh[k], sign) for k in range(B)]      # sign? ~xsh : xsh
        y, _ = addc(g, y, yterm, sign)                       # sign? y-xsh : y+xsh
        acon = consts(g, atan[i], B)
        zterm = [g.XOR(acon[k], nsign) for k in range(B)]    # sign? atan : ~atan
        z, _ = addc(g, z, zterm, nsign)                      # sign? z+atan : z-atan
    outs = x + y + z
    run, out2, gates = build_run(g, outs)
    xw, yw, zw = out2[:B], out2[B:2 * B], out2[2 * B:3 * B]
    ok = True; cases = 0
    thetas = list(range(-scale, scale + 1, max(1, (2 * scale) // 4000)))     # ~ +-1.0 rad, converges
    thetas += [0, scale, -scale, scale // 2, -scale // 2, round(0.7853 * scale)]
    for th in thetas:
        thm = th & mask
        inp = [0] * B; setf(inp, 0, B, thm)
        v = run(inp, 1)
        if (rd(v, xw), rd(v, yw), rd(v, zw)) != cordic_ref(thm): ok = False; break
        cases += 1
    record("cordic", gates, depth_of(g, gates, out2), ok, cases, f"B={B} N={N} sin/cos == integer-CORDIC ref")

# ================================================================ popcount / tree reducers
def popcount_tree(g, bits):
    nums = [[b] for b in bits]
    while len(nums) > 1:
        nxt = []
        for i in range(0, len(nums) - 1, 2):
            nxt.append(addfull(g, nums[i], nums[i + 1]))
        if len(nums) % 2: nxt.append(nums[-1])
        nums = nxt
    return nums[0]

def prim_popcount16():
    W = 16
    g = CC.CircuitCompiler(W); IN = g.IN
    outs = popcount_tree(g, list(IN))[:5]
    run, out2, gates = build_run(g, outs)
    ok = True
    for x in range(1 << W):
        inp = [0] * W; setf(inp, 0, W, x)
        if rd(run(inp, 1), out2) != bin(x).count("1"): ok = False; break
    record("popcount16", gates, depth_of(g, gates, out2), ok, 1 << W, "exhaustive == bin().count('1')")

# ================================================================ Gray encode / decode
def prim_gray_enc():
    W = 16
    g = CC.CircuitCompiler(W); IN = g.IN
    outs = [g.XOR(IN[k], IN[k + 1]) if k + 1 < W else IN[k] for k in range(W)]
    run, out2, gates = build_run(g, outs)
    ok = True
    for x in range(1 << W):
        inp = [0] * W; setf(inp, 0, W, x)
        if rd(run(inp, 1), out2) != (x ^ (x >> 1)): ok = False; break
    record("gray_enc", gates, depth_of(g, gates, out2), ok, 1 << W, "exhaustive == x ^ (x>>1)")

def prim_gray_dec():
    W = 16
    g = CC.CircuitCompiler(W); IN = g.IN
    outs = []; acc = g.C0
    for k in range(W - 1, -1, -1):                            # binary[k] = XOR of gray[k..MSB]
        acc = g.XOR(acc, IN[k]); outs.append((k, acc))
    outs = [w for _, w in sorted(outs)]
    run, out2, gates = build_run(g, outs)
    def gray_dec_ref(gc):
        b = 0
        while gc: b ^= gc; gc >>= 1
        return b
    ok = True
    for x in range(1 << W):
        inp = [0] * W; setf(inp, 0, W, x)
        if rd(run(inp, 1), out2) != gray_dec_ref(x): ok = False; break
    record("gray_dec", gates, depth_of(g, gates, out2), ok, 1 << W, "exhaustive == inverse Gray")

# ================================================================ priority encoder (highest set bit)
def prim_priority16():
    W = 16; IDX = 4
    g = CC.CircuitCompiler(W); IN = g.IN
    above = g.C0                                              # OR of all bits strictly higher than k
    onehot = [None] * W
    for k in range(W - 1, -1, -1):
        onehot[k] = g.AND(IN[k], g.NOT(above))               # highest set bit
        above = g.OR(above, IN[k])
    idx = []
    for b in range(IDX):
        acc = g.C0
        for k in range(W):
            if (k >> b) & 1: acc = g.OR(acc, onehot[k])
        idx.append(acc)
    valid = g.C0
    for k in range(W): valid = g.OR(valid, IN[k])
    outs = idx + [valid]
    run, out2, gates = build_run(g, outs)
    iw, vw = out2[:IDX], out2[IDX]
    ok = True
    for x in range(1 << W):
        inp = [0] * W; setf(inp, 0, W, x)
        v = run(inp, 1)
        exp_idx = x.bit_length() - 1 if x else 0
        exp_val = 1 if x else 0
        if rd(v, iw) != exp_idx or bit(v, vw) != exp_val: ok = False; break
    record("priority16", gates, depth_of(g, gates, out2), ok, 1 << W, "exhaustive: highest-set-bit index+valid")

# ================================================================ barrel shifter (logical left)
def prim_barrel16():
    W = 16; SB = 4
    g = CC.CircuitCompiler(W + SB); IN = g.IN
    data = list(IN[:W]); amt = IN[W:W + SB]
    cur = list(data)
    for s in range(SB):                                      # conditional shift by 2**s
        sh = 1 << s
        shifted = [g.C0] * sh + cur[:W - sh]
        cur = muxw(g, amt[s], shifted, cur)
    run, out2, gates = build_run(g, cur)
    ok = True; cases = 0
    trials = [(d, a) for a in range(16) for d in (0, 1, 0xFFFF, 0x8001, 0xAAAA)]
    trials += [(random.getrandbits(W), random.getrandbits(SB)) for _ in range(5000)]
    for d, a in trials:
        inp = [0] * (W + SB); setf(inp, 0, W, d); setf(inp, W, SB, a)
        if rd(run(inp, 1), out2) != ((d << a) & 0xFFFF): ok = False; break
        cases += 1
    record("barrel16", gates, depth_of(g, gates, out2), ok, cases, "logical left shift == (d<<a)&0xffff")

# ================================================================ BCD adder (one decimal digit)
def prim_bcd_add():
    g = CC.CircuitCompiler(9); IN = g.IN                     # a[4], b[4], cin[1]
    A = list(IN[0:4]); Bd = list(IN[4:8]); cin = IN[8]
    b, _ = addc(g, A + [g.C0], Bd + [g.C0], cin)             # 5-bit binary sum 0..19
    gt9 = g.OR(b[4], g.AND(b[3], g.OR(b[2], b[1])))          # >=16, or >=8 and (>=12 or >=10)
    six = [g.C0, gt9, gt9, g.C0]                             # add 0b0110 when the digit exceeds 9
    corr, _ = addc(g, b[:4], six)                            # corrected low nibble
    outs = corr + [gt9]
    run, out2, gates = build_run(g, outs)
    dw, cw = out2[:4], out2[4]
    ok = True; cases = 0
    for a in range(10):
        for bb in range(10):
            for ci in range(2):
                inp = [0] * 9; setf(inp, 0, 4, a); setf(inp, 4, 4, bb); inp[8] = ci
                v = run(inp, 1)
                tot = a + bb + ci
                if rd(v, dw) != tot % 10 or bit(v, cw) != tot // 10: ok = False
                cases += 1
    record("bcd_add", gates, depth_of(g, gates, out2), ok, cases, "exhaustive decimal digit + carry")

# ================================================================ leading / trailing zero count
def prim_clz16():
    W = 16
    g = CC.CircuitCompiler(W); IN = g.IN
    incl = g.C0; nz = []                                      # NOT(prefix-or from MSB)
    for k in range(W - 1, -1, -1):
        incl = g.OR(incl, IN[k]); nz.append(g.NOT(incl))
    outs = popcount_tree(g, nz)[:5]
    run, out2, gates = build_run(g, outs)
    ok = True
    for x in range(1 << W):
        inp = [0] * W; setf(inp, 0, W, x)
        if rd(run(inp, 1), out2) != (W - x.bit_length()): ok = False; break
    record("clz16", gates, depth_of(g, gates, out2), ok, 1 << W, "exhaustive leading-zero count")

def prim_ctz16():
    W = 16
    g = CC.CircuitCompiler(W); IN = g.IN
    incl = g.C0; nz = []                                      # NOT(prefix-or from LSB)
    for k in range(W):
        incl = g.OR(incl, IN[k]); nz.append(g.NOT(incl))
    outs = popcount_tree(g, nz)[:5]
    run, out2, gates = build_run(g, outs)
    def ctz_ref(x): return W if x == 0 else (x & -x).bit_length() - 1
    ok = True
    for x in range(1 << W):
        inp = [0] * W; setf(inp, 0, W, x)
        if rd(run(inp, 1), out2) != ctz_ref(x): ok = False; break
    record("ctz16", gates, depth_of(g, gates, out2), ok, 1 << W, "exhaustive trailing-zero count")

# ================================================================ saturating adder (unsigned)
def prim_satadd8():
    W = 8
    g = CC.CircuitCompiler(2 * W); IN = g.IN
    A = list(IN[:W]); Bd = list(IN[W:2 * W])
    s, c = addc(g, A, Bd)
    outs = [g.OR(s[k], c) for k in range(W)]                  # carry -> force 0xFF
    run, out2, gates = build_run(g, outs)
    ok = True
    for a in range(1 << W):
        for b in range(1 << W):
            inp = [0] * (2 * W); setf(inp, 0, W, a); setf(inp, W, W, b)
            if rd(run(inp, 1), out2) != min(a + b, 0xFF): ok = False; break
        if not ok: break
    record("satadd8", gates, depth_of(g, gates, out2), ok, 1 << (2 * W), "exhaustive min(a+b,255)")

# ================================================================ min/max tree
def prim_minmax8():
    N = 8; W = 8
    g = CC.CircuitCompiler(N * W); IN = g.IN
    keys = [[IN[i * W + b] for b in range(W)] for i in range(N)]
    def mn(a, b):
        ge = cmp_ge(g, a, b); return muxw(g, ge, b, a)       # a>=b ? b : a
    def mx(a, b):
        ge = cmp_ge(g, a, b); return muxw(g, ge, a, b)
    def tree(vals, fn):
        while len(vals) > 1:
            nxt = [fn(vals[i], vals[i + 1]) for i in range(0, len(vals) - 1, 2)]
            if len(vals) % 2: nxt.append(vals[-1])
            vals = nxt
        return vals[0]
    outs = tree(list(keys), mn) + tree(list(keys), mx)
    run, out2, gates = build_run(g, outs)
    minw, maxw = out2[:W], out2[W:2 * W]
    ok = True; cases = 0
    for _ in range(6000):
        arr = [random.getrandbits(W) for _ in range(N)]
        inp = [0] * (N * W)
        for i in range(N): setf(inp, i * W, W, arr[i])
        v = run(inp, 1)
        if rd(v, minw) != min(arr) or rd(v, maxw) != max(arr): ok = False; break
        cases += 1
    record("minmax8", gates, depth_of(g, gates, out2), ok, cases, "8x8-bit == min()/max()")

def main():
    random.seed(42)
    print("\n  MUHLNICKEL PRIMITIVES ZOO -- small arithmetic circuits, each verified byte-exact vs an independent reference\n", flush=True)
    prims = [prim_isqrt16, prim_cordic, prim_popcount16, prim_gray_enc, prim_gray_dec,
             prim_priority16, prim_barrel16, prim_bcd_add, prim_clz16, prim_ctz16,
             prim_satadd8, prim_minmax8]
    for fn in prims:
        t = time.time()
        try:
            fn()
        except Exception as ex:
            import traceback
            print(f"  [ERR ] {fn.__name__}: {type(ex).__name__}: {ex}", flush=True)
            traceback.print_exc()
    npass = sum(1 for r in RESULTS if r[3])
    tot_g = sum(r[1] for r in RESULTS)
    print(f"\n  === {npass}/{len(RESULTS)} primitives byte-exact  .  {tot_g:,} total gates fabricated ===", flush=True)

if __name__ == "__main__":
    main()
