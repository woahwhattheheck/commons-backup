"""
pfc_clint.py - THE RISC-V CLINT (core-local interruptor), FABRICATED AS GATES.

pfc_riscv_priv2.py already has the trap stack, and it already consumes an `irq` input line - but
nothing DRIVES that line. A kernel with a trap stack and no timer cannot preempt: it can only be
interrupted by something else's clock. This is the thing that makes the interval real, in gates:

  mtime      64-bit free-running counter, +1 per tick
  mtimecmp   64-bit compare register
  mtip       timer interrupt pending  <-  mtime >= mtimecmp, UNSIGNED, over the full 64 bits
  msip       software interrupt bit (a register with a write port, so software can raise/clear it)
  irq        mtip | msip  ->  this is the exact line pfc_riscv_priv2's IRQ input takes

WHY 64 BITS IS THE WHOLE PROBLEM. c.add is mod 2^len and DROPS the carry at every width, so a
64-bit counter built as two 32-bit halves has to propagate the carry EXPLICITLY: the high half
advances only on the tick where the low half wraps 0xFFFFFFFF -> 0. Miss that and the counter
silently resets every 4.29 billion ticks and the timer interrupt stops firing - the classic
half-built-64-bit bug. Same for the compare: lt64 = lt_hi | (eq_hi & lt_lo), built from the two
32-bit compares. A compare that only looks at the low half gets 0xFFFFFFFF >= 0x1_00000000 wrong.

DEPTH. The increment is NOT a ripple-carry chain. +1's carry into bit i is just AND(X[0..i-1]),
which is a parallel prefix (Kogge-Stone, log2(32) = 5 AND levels) instead of 32 serial carries -
and the prefix's top output IS the explicit carry-out, for free. Both halves increment in
PARALLEL and the high half is selected by that carry, so the two halves cost AREA, not depth.

VERIFIED against an independent Python model (plain 64-bit integer arithmetic, no gate concepts),
POSITIVE CONTROLS FIRST - equality, one-past, and the 32-bit rollover boundary in both directions -
because a circuit that returns 0 for everything passes a mostly-negative test set.

NOT YET BUILT: mtime/mtimecmp memory-mapped at 0x0200_0000 (this is the register file, not the
bus decode), mtimecmp's own write port (it is an input here), per-hart lanes (this is hart 0),
mie/mip CSR masking of mtip, and the S-mode timer (stimecmp / Sstc).

Run:  python host/pfc_clint.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_riscv import XLEN, depth_of, nl, mux_vec, eq_vec

M32 = (1 << 32) - 1
M64 = (1 << 64) - 1


def inc_prefix(c, X):
    """X + 1 as a PARALLEL PREFIX, plus the EXPLICIT carry-out.

    For +1, the carry into bit i is AND(X[0..i-1]) - an associative scan, so it reduces as a tree
    (log2(n) levels) rather than the n serial carries of a ripple adder. Returns (sum, carry_out),
    and carry_out = AND(X[0..n-1]) = "this half was all ones and just wrapped to zero".
    """
    n = len(X)
    G = list(X)                                   # G[i] becomes AND(X[0..i])
    d = 1
    while d < n:
        G = [c.and_(G[i], G[i - d]) if i >= d else G[i] for i in range(n)]
        d <<= 1
    cin = [c.C1] + [G[i - 1] for i in range(1, n)]   # carry into bit 0 of a +1 is always 1
    out = [c.xor(X[i], cin[i]) for i in range(n)]
    return out, G[n - 1]


def inc64(c, LO, HI):
    """(LO,HI) + 1 as two 32-bit halves with the carry propagated EXPLICITLY between them.
    Both halves increment in parallel; the carry only selects which high value survives."""
    lo_n, carry_lo = inc_prefix(c, LO)
    hi_n, carry_hi = inc_prefix(c, HI)
    hi_sel = mux_vec(c, carry_lo, HI, hi_n)          # high half advances ONLY on the low wrap
    return lo_n, hi_sel, c.and_(carry_lo, carry_hi)  # carry out of bit 63 (mtime wraps mod 2^64)


def geu64(c, ALO, AHI, BLO, BHI):
    """1 iff A >= B, UNSIGNED, 64 bits, built from the two 32-bit halves.
    lt64 = lt_hi | (eq_hi & lt_lo) - the high half decides unless it ties."""
    lt_hi = TC.lt(c, AHI, BHI)
    eq_hi = eq_vec(c, AHI, BHI)
    lt_lo = TC.lt(c, ALO, BLO)
    return c.not_(c.or_(lt_hi, c.and_(eq_hi, lt_lo)))


def build():
    """inputs : mtime_lo[32] | mtime_hi[32] | mtimecmp_lo[32] | mtimecmp_hi[32] | msip | msip_we | msip_d | tick
       outputs: mtime_lo'[32] | mtime_hi'[32] | mtip | msip' | irq"""
    NIN = XLEN * 4 + 4
    c = TC.Circuit(NIN)
    o = 0
    TLO = list(c.IN[o:o + XLEN]); o += XLEN
    THI = list(c.IN[o:o + XLEN]); o += XLEN
    CLO = list(c.IN[o:o + XLEN]); o += XLEN
    CHI = list(c.IN[o:o + XLEN]); o += XLEN
    MSIP, MSIP_WE, MSIP_D, TICK = c.IN[o], c.IN[o + 1], c.IN[o + 2], c.IN[o + 3]

    ilo, ihi, _ovf = inc64(c, TLO, THI)              # mtime + 1 (mod 2^64)
    nlo = mux_vec(c, TICK, TLO, ilo)                 # tick=0 holds the counter
    nhi = mux_vec(c, TICK, THI, ihi)

    mtip = geu64(c, nlo, nhi, CLO, CHI)              # asserted against the POST-tick mtime
    nmsip = c.mux(MSIP_WE, MSIP, MSIP_D)             # the software-interrupt register
    irq = c.or_(mtip, nmsip)                         # <- pfc_riscv_priv2's IRQ line

    return c, list(nlo) + list(nhi) + [mtip, nmsip, irq]


# ---------------------------------------------------------------- independent reference model
def ref_clint(mtime, mtimecmp, msip, msip_we, msip_d, tick):
    """Plain 64-bit integer semantics. Written without reference to the gate build."""
    nt = (mtime + 1) & M64 if tick else (mtime & M64)
    mtip = 1 if nt >= (mtimecmp & M64) else 0
    nmsip = (msip_d & 1) if msip_we else (msip & 1)
    return nt, mtip, nmsip, (mtip | nmsip)


def run(net, mtime, mtimecmp, msip=0, msip_we=0, msip_d=0, tick=0):
    ib = []
    for v in (mtime & M32, (mtime >> 32) & M32, mtimecmp & M32, (mtimecmp >> 32) & M32):
        ib += [(v >> k) & 1 for k in range(XLEN)]
    ib += [msip & 1, msip_we & 1, msip_d & 1, tick & 1]
    o = TC.ripple(net, ib)
    lo = sum(o[k] << k for k in range(XLEN))
    hi = sum(o[XLEN + k] << k for k in range(XLEN))
    p = 2 * XLEN
    return (hi << 32) | lo, o[p], o[p + 1], o[p + 2]


def main():
    print("=" * 92)
    print("RISC-V CLINT (mtime / mtimecmp / msip -> irq), FABRICATED AS GATES")
    print("=" * 92)
    c, outs = build()
    d, g = depth_of(c, outs), len(c.ga)
    net = nl(c, outs)
    print()
    print("  ONE TICK = ONE SETTLE:  DEPTH %d gate-delays,  %s gates" % (d, "{:,}".format(g)))
    print("  64-bit increment (parallel-prefix, explicit half-carry) + unsigned 64-bit compare,")
    print("  both in that one settle. The two halves cost AREA, not depth.")
    del c

    B = 1 << 32
    CMP = 0x0000_0001_0000_0000
    # ---- POSITIVE CONTROLS FIRST: every one of these MUST fire. ----
    pos = [
        ("mtime == mtimecmp exactly",        0x1234, 0x1234, 0, 0),
        ("mtime one past mtimecmp",          0x1235, 0x1234, 0, 0),
        ("ROLLOVER: lo FFFFFFFF +1 -> hi=1", B - 1,  B,      0, 1),   # carry MUST cross the halves
        ("ROLLOVER: lo FFFFFFFE +1 == cmp",  B - 2,  B - 1,  0, 1),
        ("ROLLOVER: 3 halves up, deep hi",   (7 << 32) | (B - 1), (8 << 32), 0, 1),
        ("hi greater, lo far less",          2 * B,  B + (B - 1), 0, 0),
        ("mtime = 2^64-1, cmp = 0",          M64,    0,      0, 0),
        ("tick crosses the threshold",       0x40FF, 0x4100, 0, 1),
        ("msip alone (mtime far below cmp)", 0,      M64,    1, 0),
        ("mtime = 2^64-1 +1 wraps to 0, cmp=0", M64, 0,      0, 1),   # wrapped counter still >= 0
    ]
    # ---- NEGATIVES: every one of these MUST NOT fire. ----
    neg = [
        ("mtime one below cmp, no tick",     0x1233, 0x1234, 0, 0),
        ("lo FFFFFFFF but hi below cmp hi",  B - 1,  B,      0, 0),   # no tick -> no carry -> below
        ("hi less, lo greater (half-compare trap)", B - 1, B, 0, 0),
        ("tick, still one short",            0x40FE, 0x4100, 0, 1),
        ("mtime 0, cmp 2^64-1",              0,      M64,    0, 0),
        ("rollover into hi=1 but cmp hi=2",  B - 1,  2 * B,  0, 1),
        ("deep hi tie, lo one short",        (5 << 32) | 0x10, (5 << 32) | 0x11, 0, 0),
    ]
    print()
    print("  %-42s %5s %5s   %s" % ("case", "Muhlnickel", "ref", "result"))
    okc = nfail = 0
    npos = nneg = 0
    for tag, cases, want in (("POSITIVE (must fire)", pos, 1), ("NEGATIVE (must not fire)", neg, 0)):
        print("  -- %s --" % tag)
        for nm, mt, cmpv, msip, tick in cases:
            gr = run(net, mt, cmpv, msip=msip, tick=tick)
            rr = ref_clint(mt, cmpv, msip, 0, 0, tick)
            same = gr == rr
            polarity = (gr[3] == want)
            print("  %-42s %5d %5d   %s" % (nm, gr[3], rr[3], "OK" if (same and polarity) else
                                            "FAIL Muhlnickel=%s ref=%s" % (gr, rr)))
            okc += (same and polarity); nfail += not (same and polarity)
            if want: npos += 1
            else: nneg += 1

    # ---- msip write port ----
    print("  -- msip write port --")
    for nm, msip, we, dd in (("set msip (we=1,d=1)", 0, 1, 1), ("clear msip (we=1,d=0)", 1, 1, 0),
                             ("hold msip (we=0)", 1, 0, 0)):
        gr = run(net, 0, M64, msip=msip, msip_we=we, msip_d=dd)
        rr = ref_clint(0, M64, msip, we, dd, 0)
        same = gr == rr
        print("  %-42s %5d %5d   %s" % (nm, gr[3], rr[3], "OK" if same else "FAIL %s vs %s" % (gr, rr)))
        okc += same; nfail += not same
        if rr[3]: npos += 1
        else: nneg += 1

    # ---- a real sequence: feed mtime' back in and tick across the 32-bit boundary ----
    print("  -- 8-tick sequence across the 32-bit boundary (mtime' fed back in) --")
    mt = B - 3
    seq_ok = 0
    for _ in range(8):
        gr = run(net, mt, B + 2, tick=1)
        rr = ref_clint(mt, B + 2, 0, 0, 0, 1)
        seq_ok += (gr == rr)
        if rr[3]: npos += 1
        else: nneg += 1
        mt = gr[0]                                   # the pfc's own output drives the next tick
    print("  %-42s %5s %5d   %s" % ("mtime walked %s .. %s" % (hex(B - 3), hex(mt)), "", 8,
                                    "OK" if seq_ok == 8 else "FAIL"))
    okc += seq_ok; nfail += 8 - seq_ok

    # ---- randomized cross-check, boundary-biased ----
    random.seed(20260726)
    rnd_ok = rp = rn = 0
    N = 400
    for _ in range(N):
        cmpv = random.choice([random.getrandbits(64), random.getrandbits(33),
                              B, B - 1, random.getrandbits(64) & ~M32])
        delta = random.choice([-2, -1, 0, 1, 2, -B, B, random.getrandbits(64)])
        mt = (cmpv + delta) & M64
        msip = random.getrandbits(1); we = random.getrandbits(1); dd = random.getrandbits(1)
        tick = random.getrandbits(1)
        gr = run(net, mt, cmpv, msip=msip, msip_we=we, msip_d=dd, tick=tick)
        rr = ref_clint(mt, cmpv, msip, we, dd, tick)
        rnd_ok += (gr == rr)
        if rr[3]: rp += 1
        else: rn += 1
    okc += rnd_ok; nfail += N - rnd_ok; npos += rp; nneg += rn
    print("  -- %d randomized 64-bit vectors (boundary-biased): %d/%d exact, %d fire / %d don't --"
          % (N, rnd_ok, N, rp, rn))

    total = npos + nneg
    print()
    print("  %d/%d byte-exact vs the independent reference (mtime', mtip, msip', irq)."
          % (okc, total))
    print("  SPLIT: %d POSITIVE (irq must fire) / %d NEGATIVE (irq must stay 0). A stuck-at-0"
          % (npos, nneg))
    print("  circuit would score %d/%d - the positives are what make this test set mean anything."
          % (nneg, total))

    # ---- composition: this irq line drives pfc_riscv_priv2's trap ----
    print()
    print("  -- COMPOSITION with pfc_riscv_priv2 (its IRQ input takes this irq output) --")
    import pfc_riscv_priv2 as P2
    c2, o2 = P2.build()
    net2 = nl(c2, o2)
    del c2
    MTVEC, EPC, NOP = 0x8000_0100, 0x4444, 0x00000013
    mst_ie = 1 << P2.MIE_BIT
    comp_ok = 0
    comp = [("mtime reaches mtimecmp -> trap to mtvec", B - 1, B, 1, mst_ie, 1),
            ("mtime below mtimecmp   -> no trap",       B - 1, B, 0, mst_ie, 0),
            ("timer fires but MIE=0  -> masked",        B - 1, B, 1, 0,      0)]
    for nm, mt, cmpv, tick, mst, want_trap in comp:
        irq = run(net, mt, cmpv, tick=tick)[3]
        npc, npriv, nmst, nmepc, cause, trap = P2.run(net2, 0x2000, P2.PRIV_U, mst, MTVEC, EPC, NOP, irq)
        good = (trap == want_trap) and (not want_trap or (npc == MTVEC and cause == P2.CAUSE_TIMER))
        comp_ok += good
        print("  %-42s irq=%d trap=%d npc=%-10s %s"
              % (nm, irq, trap, hex(npc), "OK" if good else "FAIL"))
    print("  %d/%d - the CLINT's irq drives the trap stack, mcause = 0x%08x (machine timer)."
          % (comp_ok, len(comp), P2.CAUSE_TIMER))

    print()
    print("  NOT YET BUILT: memory-mapped bus decode at 0x0200_0000, a write port for mtimecmp")
    print("  (it is an input here), multi-hart lanes, mie/mip masking of mtip, and Sstc/stimecmp.")


if __name__ == "__main__":
    main()
