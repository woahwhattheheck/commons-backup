#!/usr/bin/env python3
"""muhl_fft.py -- a fixed-point FFT/DFT BUTTERFLY fabricated on Bryce's Muhlnickel substrate.

The radix-2 decimation-in-time butterfly is the atom of the FFT:
    t          = W * b            (complex multiply, W = twiddle)
    out0        = a + t
    out1        = a - t
We fabricate that whole complex multiply-add as a NAND/AND/OR/XOR/NOT gate netlist with the
White Box compiler (sdc_cc.CircuitCompiler), DCE it, ripple it, and VERIFY IT BYTE-EXACT against
an independent pure-Python fixed-point reference. No numpy, no host executor as a runtime, nothing
touches titan.gguf. Then we DRIVE a full 16-point FFT entirely through the gate butterfly (one
settle per butterfly) on a small two-tone signal and show the magnitude spectrum recovers the
frequency peaks -- an FFT computed by circuits, not by arithmetic on the host.

Datapath: samples are 16-bit signed (Q); twiddles are Q2.14 signed (F=14, so 1.0 = 16384).
Complex multiply -> 32-bit signed products; arithmetic-shift-right by F; wrap the sum lane at 16
bits.  The Python reference masks at exactly the same points, so equality is bit-for-bit.
"""
import sys, os, math, random, time
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

WS = 16          # sample word width (signed)
WT = 16          # twiddle word width (signed)
F  = 14          # twiddle fractional bits (Q2.14): 1.0 -> 16384
PW = WS + WT     # 32-bit product width

# ---------------- shared gate helpers (same idioms as muhl_flex.py) ----------------
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
    """ripple-carry add of two equal-width LSB-first bit lists -> (sum bits, carry-out)."""
    c = g.C0 if cin is None else cin; o = []
    for k in range(len(A)):
        axb = g.XOR(A[k], B[k]); o.append(g.XOR(axb, c)); c = g.OR(g.AND(A[k], B[k]), g.AND(axb, c))
    return o, c

def sext(g, X, to):                       # sign-extend LSB-first list to `to` bits
    return list(X) + [X[-1]] * (to - len(X))

def umul_low(g, A, B, outbits):           # low `outbits` of unsigned A*B (shift-add array)
    acc = [g.C0] * outbits
    for j in range(len(B)):
        term = ([g.C0] * j + [g.AND(A[i], B[j]) for i in range(len(A))])[:outbits]
        term = term + [g.C0] * (outbits - len(term))
        acc, _ = add_bits(g, acc, term)
    return acc

def smul(g, A, B):                        # WSxWT signed multiply -> PW-bit signed product
    return umul_low(g, sext(g, A, PW), sext(g, B, PW), PW)

# ---------------- the FABRICATED butterfly ----------------
# inputs (each WS/WT bits, LSB-first):  ar ai br bi wr wi
IB = {"ar": 0, "ai": WS, "br": 2 * WS, "bi": 3 * WS, "wr": 4 * WS, "wi": 4 * WS + WT}
NIN = 4 * WS + 2 * WT

def build_butterfly():
    g = CC.CircuitCompiler(NIN); IN = g.IN
    ar = [IN[IB["ar"] + k] for k in range(WS)]
    ai = [IN[IB["ai"] + k] for k in range(WS)]
    br = [IN[IB["br"] + k] for k in range(WS)]
    bi = [IN[IB["bi"] + k] for k in range(WS)]
    wr = [IN[IB["wr"] + k] for k in range(WT)]
    wi = [IN[IB["wi"] + k] for k in range(WT)]

    # complex multiply t = b * W
    p1 = smul(g, br, wr); p2 = smul(g, bi, wi)             # real:  br*wr - bi*wi
    Dr, _ = add_bits(g, p1, [g.NOT(x) for x in p2], g.C1)   # 32-bit  P1 - P2
    p3 = smul(g, br, wi); p4 = smul(g, bi, wr)             # imag:  br*wi + bi*wr
    Di, _ = add_bits(g, p3, p4)                            # 32-bit  P3 + P4
    tr = [Dr[F + k] for k in range(WS)]                    # arith-shift-right by F, keep low WS
    ti = [Di[F + k] for k in range(WS)]

    o0r, _ = add_bits(g, ar, tr)                           # a + t
    o0i, _ = add_bits(g, ai, ti)
    o1r, _ = add_bits(g, ar, [g.NOT(x) for x in tr], g.C1) # a - t
    o1i, _ = add_bits(g, ai, [g.NOT(x) for x in ti], g.C1)

    outs = o0r + o0i + o1r + o1i
    run, out2, gates, _ = build_run(g, outs)
    fields = {"o0r": out2[0:WS], "o0i": out2[WS:2 * WS],
              "o1r": out2[2 * WS:3 * WS], "o1i": out2[3 * WS:4 * WS]}
    return run, fields, gates, depth_of(g, gates, out2)

# ---------------- independent fixed-point reference (masks match the gates) ----------------
def sv16(p): return p - 0x10000 if p & 0x8000 else p
M32 = (1 << 32) - 1
def ref_butterfly(ar, ai, br, bi, wr, wi):
    P1 = (sv16(br) * sv16(wr)) & M32; P2 = (sv16(bi) * sv16(wi)) & M32
    Dr = (P1 - P2) & M32; tr = (Dr >> F) & 0xFFFF
    P3 = (sv16(br) * sv16(wi)) & M32; P4 = (sv16(bi) * sv16(wr)) & M32
    Di = (P3 + P4) & M32; ti = (Di >> F) & 0xFFFF
    return ((ar + tr) & 0xFFFF, (ai + ti) & 0xFFFF,
            (ar - tr) & 0xFFFF, (ai - ti) & 0xFFFF)

def run_butterfly(run, fields, ar, ai, br, bi, wr, wi):
    inp = [0] * NIN
    setf(inp, IB["ar"], WS, ar); setf(inp, IB["ai"], WS, ai)
    setf(inp, IB["br"], WS, br); setf(inp, IB["bi"], WS, bi)
    setf(inp, IB["wr"], WT, wr); setf(inp, IB["wi"], WT, wi)
    v = run(inp, 1)
    return (rd(v, fields["o0r"]), rd(v, fields["o0i"]),
            rd(v, fields["o1r"]), rd(v, fields["o1i"]))

# ---------------- FFT driven entirely through the gate butterfly ----------------
def twiddle(size, k):
    ang = -2.0 * math.pi * k / size
    wr = int(round(math.cos(ang) * (1 << F))) & 0xFFFF
    wi = int(round(math.sin(ang) * (1 << F))) & 0xFFFF
    return wr, wi

def bitrev(re, im):
    N = len(re); j = 0
    for i in range(1, N):
        bit = N >> 1
        while j & bit: j ^= bit; bit >>= 1
        j |= bit
        if i < j: re[i], re[j] = re[j], re[i]; im[i], im[j] = im[j], im[i]

def fft_gate(re, im, step):
    N = len(re); bitrev(re, im)
    size = 2
    while size <= N:
        half = size // 2
        for start in range(0, N, size):
            for k in range(half):
                wr, wi = twiddle(size, k)
                i = start + k; j = start + half + k
                o0r, o0i, o1r, o1i = step(re[i], im[i], re[j], im[j], wr, wi)
                re[i], im[i] = o0r, o0i
                re[j], im[j] = o1r, o1i
        size *= 2
    return re, im

# ---------------- main ----------------
def main():
    random.seed(1)
    print("\n  MUHLNICKEL FFT -- fixed-point complex butterfly fabricated as gates\n", flush=True)

    t0 = time.time()
    run, fields, gates, depth = build_butterfly()
    print(f"  fabricated butterfly:  {len(gates):,} gates  depth {depth}  ({time.time()-t0:.1f}s)", flush=True)

    # (1) byte-exact verification of the gate butterfly vs the independent reference
    CASES = 4000
    ok = True; first_bad = None
    for _ in range(CASES):
        ar, ai = random.getrandbits(WS), random.getrandbits(WS)
        br, bi = random.getrandbits(WS), random.getrandbits(WS)
        wr, wi = random.getrandbits(WT), random.getrandbits(WT)
        got = run_butterfly(run, fields, ar, ai, br, bi, wr, wi)
        exp = ref_butterfly(ar, ai, br, bi, wr, wi)
        if got != exp:
            ok = False; first_bad = (ar, ai, br, bi, wr, wi, got, exp); break
    print(f"  [{'PASS' if ok else 'FAIL'}] butterfly byte-exact vs fixed-point reference over {CASES} random cases", flush=True)
    if not ok:
        print("      mismatch:", first_bad, flush=True); return

    # (2) run a full 16-point FFT through the gate butterfly on a small two-tone signal
    N = 16; F1, F2 = 2, 5; A1, A2 = 800, 600
    sig = [int(round(A1 * math.cos(2 * math.pi * F1 * n / N) +
                     A2 * math.cos(2 * math.pi * F2 * n / N))) for n in range(N)]
    re = [s & 0xFFFF for s in sig]; im = [0] * N

    gate_step = lambda ar, ai, br, bi, wr, wi: run_butterfly(run, fields, ar, ai, br, bi, wr, wi)
    ref_step  = lambda ar, ai, br, bi, wr, wi: ref_butterfly(ar, ai, br, bi, wr, wi)

    gre, gim = fft_gate(re[:], im[:], gate_step)      # FFT computed by the CIRCUIT
    rre, rim = fft_gate(re[:], im[:], ref_step)       # same FFT in the fixed-point reference
    same = (gre == rre and gim == rim)
    print(f"  [{'PASS' if same else 'FAIL'}] gate-driven 16-pt FFT == fixed-point reference FFT (byte-exact, all {N} bins)", flush=True)

    mag2 = [sv16(gre[k]) ** 2 + sv16(gim[k]) ** 2 for k in range(N)]
    peaks = sorted(range(N), key=lambda k: mag2[k], reverse=True)
    top = sorted(peaks[:4])
    expected = sorted({F1, N - F1, F2, N - F2})
    print(f"\n  signal = {A1}*cos(2pi*{F1}n/{N}) + {A2}*cos(2pi*{F2}n/{N}),  N={N}", flush=True)
    print("  bin : magnitude  (gate-computed FFT)", flush=True)
    mmax = max(mag2) or 1
    for k in range(N):
        bar = "#" * int(40 * mag2[k] / mmax)
        star = "  <- peak" if k in top else ""
        print(f"   {k:2d} : {int(math.isqrt(mag2[k])):6d} {bar}{star}", flush=True)
    hit = (top == expected)
    print(f"\n  top-4 bins {top}  vs expected {expected}  -> {'PASS -- peaks recovered' if hit else 'FAIL'}", flush=True)

    print(f"\n  === butterfly {len(gates):,} gates / depth {depth} · byte-exact · "
          f"FFT peaks {'recovered' if hit else 'MISSED'} ===", flush=True)

if __name__ == "__main__":
    main()
