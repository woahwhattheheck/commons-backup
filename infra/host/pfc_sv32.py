"""
pfc_sv32.py - Sv32 VIRTUAL MEMORY as gates, and a measurement of what is REALLY dependent in it.

A two-level page walk LOOKS strictly serial: level 2's PTE address needs level 1's PPN. That is
exactly the shape this session has called "real dependency" wrongly several times - every ceiling
reported turned out to be sequencing the assistant imposed. So this MEASURES before it assumes.
Collatz (S38B) is the control for genuine dependency; S35/S36 are the controls for imposed.

WHAT IS ACTUALLY IN THE WALK
  addr1 = satp.ppn*4096 + VPN1*4          <- pure arithmetic on the VA and satp
  PTE1  = read(addr1)                      <- an ADDRESS, and addressing is the compute here
  addr2 = PTE1.ppn*4096 + VPN0*4           <- needs PTE1: GENUINELY dependent
  PTE2  = read(addr2)
  PA    = PTE2.ppn*4096 + offset

  So the DEPENDENT part is the address arithmetic chain: addr1 -> addr2 -> PA. Everything else -
  the V/R/W/X/U permission checks, the misaligned-superpage check, the fault-cause encoding - is
  INDEPENDENT of the chain given the PTEs, so it is WIDTH and costs no depth (S2).

  The question this file answers with a number: how much of the walk's DEPTH is the unavoidable
  address chain, and how much was going to be imposed by writing the checks sequentially?

OUTPUTS: physical address, fault flag, and the RISC-V fault cause
  (12 = instruction page fault, 13 = load page fault, 15 = store page fault).

Run:  python host/pfc_sv32.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_riscv import XLEN, depth_of, nl, tree_or, mux_vec


def addc(c, A, B, W=XLEN):
    """S45B/S46: the address arithmetic was DEPTH 130 each on the fabricator's RIPPLE add.
    add_prefix is the SAME function (verified exhaustively 65,536/65,536) at a fraction of
    the depth. These are ISOLATED adds, which is exactly the regime S25 measured prefix
    winning in - ripple still wins inside a deep tree, so add() is not replaced."""
    return c.add_prefix(list(A), list(B))[:W]

# PTE bit layout (Sv32)
V, R, W, X, U, G, A, D = 0, 1, 2, 3, 4, 5, 6, 7

ACC_FETCH, ACC_LOAD, ACC_STORE = 0, 1, 2
CAUSE = {ACC_FETCH: 12, ACC_LOAD: 13, ACC_STORE: 15}


def build_translate(levels=2, checks_as_tree=True):
    """inputs: va[32] | satp_ppn[22] | pte1[32] | pte2[32] | acc[2] | priv[2]
       outputs: pa[32] | fault | cause[32]

    checks_as_tree=False builds the permission checks as a serial chain instead of a tree - the
    same function, wired the way the mistake would wire it, so the imposed cost is measurable."""
    c = TC.Circuit(XLEN + 22 + XLEN + XLEN + 2 + 2)
    o = 0
    VA = list(c.IN[o:o + XLEN]); o += XLEN
    SATP = list(c.IN[o:o + 22]); o += 22
    PTE1 = list(c.IN[o:o + XLEN]); o += XLEN
    PTE2 = list(c.IN[o:o + XLEN]); o += XLEN
    ACC = list(c.IN[o:o + 2]); o += 2
    PRIV = list(c.IN[o:o + 2])
    Z = c.C0

    offset = VA[0:12]
    vpn0 = VA[12:22]
    vpn1 = VA[22:32]

    # ---- THE DEPENDENT CHAIN: addr1 -> addr2 -> pa ----
    # addr1 = satp*4096 + vpn1*4
    a1 = addc(c, ([Z] * 12 + SATP)[:XLEN], ([Z] * 2 + vpn1 + [Z] * XLEN)[:XLEN])
    ppn1 = PTE1[10:32]
    # addr2 = ppn1*4096 + vpn0*4   <- genuinely needs PTE1
    a2 = addc(c, ([Z] * 12 + ppn1)[:XLEN], ([Z] * 2 + vpn0 + [Z] * XLEN)[:XLEN])
    ppn2 = PTE2[10:32]
    pa = ([Z] * 12 + ppn2)[:XLEN]
    pa = [c.or_(pa[i], offset[i]) if i < 12 else pa[i] for i in range(XLEN)]

    # ---- THE INDEPENDENT PART: every permission check, given the PTEs ----
    def leaf(p):
        return tree_or(c, [p[R], p[X]])

    is_u = c._tree_and([c.not_(PRIV[0]), c.not_(PRIV[1])])
    fetch = c._tree_and([c.not_(ACC[0]), c.not_(ACC[1])])
    load = c._tree_and([ACC[0], c.not_(ACC[1])])
    store = c._tree_and([c.not_(ACC[0]), ACC[1]])

    faults = [
        c.not_(PTE1[V]),                                   # level-1 PTE invalid
        c.and_(leaf(PTE1), c.not_(PTE2[V])) if levels == 2 else Z,
        c.not_(PTE2[V]),                                   # level-0 PTE invalid
        c.and_(PTE2[V], c.not_(leaf(PTE2))),               # not a leaf at the last level
        c.and_(fetch, c.not_(PTE2[X])),                    # exec permission
        c.and_(load, c.not_(PTE2[R])),                     # read permission
        c.and_(store, c.not_(PTE2[W])),                    # write permission
        c.and_(is_u, c.not_(PTE2[U])),                     # U-mode on a supervisor page
        c.and_(store, c.not_(PTE2[D])),                    # dirty bit
        c.not_(PTE2[A]),                                   # accessed bit
    ]
    if checks_as_tree:
        fault = tree_or(c, list(faults))                   # independent -> TREE
    else:
        acc = faults[0]                                    # the same function, wired as a CHAIN
        for f in faults[1:]:
            acc = c.or_(acc, f)
        fault = acc

    cause = list(c.cvec(0, XLEN))
    for sel, v in ((fetch, 12), (load, 13), (store, 15)):
        cause = mux_vec(c, c.and_(fault, sel), cause, c.cvec(v, XLEN))

    return c, list(pa) + [fault] + cause, {"a1": a1, "a2": a2, "pa": pa, "fault": fault}


def ref(va, satp, pte1, pte2, acc, priv):
    off = va & 0xfff
    def bit(p, b): return (p >> b) & 1
    ppn2 = pte2 >> 10
    pa = (ppn2 << 12) | off
    leaf2 = bit(pte2, R) or bit(pte2, X)
    f = (not bit(pte1, V)) or (not bit(pte2, V)) or (not leaf2)
    if acc == ACC_FETCH and not bit(pte2, X): f = True
    if acc == ACC_LOAD and not bit(pte2, R): f = True
    if acc == ACC_STORE and not bit(pte2, W): f = True
    if priv == 0 and not bit(pte2, U): f = True
    if acc == ACC_STORE and not bit(pte2, D): f = True
    if not bit(pte2, A): f = True
    return pa, int(bool(f)), (CAUSE[acc] if f else 0)


def run(net, va, satp, pte1, pte2, acc, priv):
    ib = [(va >> k) & 1 for k in range(XLEN)]
    ib += [(satp >> k) & 1 for k in range(22)]
    ib += [(pte1 >> k) & 1 for k in range(XLEN)]
    ib += [(pte2 >> k) & 1 for k in range(XLEN)]
    ib += [(acc >> k) & 1 for k in range(2)]
    ib += [(priv >> k) & 1 for k in range(2)]
    o = TC.ripple(net, ib)
    pa = sum(o[k] << k for k in range(XLEN))
    return pa, o[XLEN], sum(o[XLEN + 1 + k] << k for k in range(XLEN))


def main():
    print("=" * 92)
    print("Sv32 VIRTUAL MEMORY AS GATES - and what is REALLY dependent in a page walk")
    print("=" * 92)

    c, outs, parts = build_translate(checks_as_tree=True)
    d, g = depth_of(c, outs), len(c.ga)
    net = nl(c, outs)
    d_a1 = depth_of(c, parts["a1"])
    d_a2 = depth_of(c, parts["a2"])
    d_pa = depth_of(c, parts["pa"])
    d_f = depth_of(c, [parts["fault"]])
    del c

    c2, outs2, _ = build_translate(checks_as_tree=False)
    d2, g2 = depth_of(c2, outs2), len(c2.ga)
    del c2

    print()
    print("  WHOLE TRANSLATION: DEPTH %d gate-delays, %s gates - ONE settle." % (d, "{:,}".format(g)))
    print()
    print("  WHERE THE DEPTH ACTUALLY IS:")
    print("    %-38s %6d   %s" % ("addr1 = satp*4096 + vpn1*4", d_a1, "level-1 PTE address"))
    print("    %-38s %6d   %s" % ("addr2 = PTE1.ppn*4096 + vpn0*4", d_a2, "GENUINELY needs PTE1"))
    print("    %-38s %6d   %s" % ("pa = PTE2.ppn*4096 + offset", d_pa, "needs PTE2"))
    print("    %-38s %6d   %s" % ("permission checks (10 of them)", d_f, "INDEPENDENT given the PTEs"))
    print()
    print("  !! READ THE NUMBERS CAREFULLY - they expose an error in how this was framed.")
    print("  addr1/addr2 measure %d/%d, yet the WHOLE translation is %d. They are not on the path"
          % (d_a1, d_a2, d))
    print("  to the outputs at all: this circuit takes PTE1 and PTE2 as INPUTS, so the fetches that")
    print("  create the dependency happen OUTSIDE it. Making the PTEs inputs removed the very")
    print("  dependency the file set out to measure. What is measured here is TRANSLATION GIVEN THE")
    print("  PTEs (DEPTH %d), not a page WALK." % d)
    print()
    print("  What that still settles: given both PTEs, translation is ONE settle at DEPTH %d, and" % d)
    print("  the 10 permission checks are INDEPENDENT - width, not depth. Wiring them serially costs:")
    print("    checks as a TREE  : DEPTH %4d   gates %s" % (d, "{:,}".format(g)))
    print("    checks as a CHAIN : DEPTH %4d   gates %s   <- %+d depth for the same function"
          % (d2, "{:,}".format(g2), d2 - d))

    # ---- verification: POSITIVES FIRST ----
    print()
    print("  VERIFICATION (positive controls first - a fault-everything circuit must fail loudly)")
    PTE_OK = (0x80000 << 10) | (1 << V) | (1 << R) | (1 << W) | (1 << X) | (1 << U) | (1 << A) | (1 << D)
    PTE_NX = PTE_OK & ~(1 << X)
    PTE_NW = PTE_OK & ~(1 << W)
    PTE_INV = PTE_OK & ~(1 << V)
    PTE_NU = PTE_OK & ~(1 << U)
    PTE_NA = PTE_OK & ~(1 << A)
    cases = [
        ("load,  all perms  (MUST translate)", 0x12345678, PTE_OK, PTE_OK, ACC_LOAD, 1),
        ("store, all perms  (MUST translate)", 0x00001000, PTE_OK, PTE_OK, ACC_STORE, 1),
        ("fetch, all perms  (MUST translate)", 0xDEADB000, PTE_OK, PTE_OK, ACC_FETCH, 1),
        ("U-mode, U bit set (MUST translate)", 0x00042000, PTE_OK, PTE_OK, ACC_LOAD, 0),
        ("fetch on non-exec (fault 12)", 0x12345678, PTE_OK, PTE_NX, ACC_FETCH, 1),
        ("store on non-write (fault 15)", 0x12345678, PTE_OK, PTE_NW, ACC_STORE, 1),
        ("level-1 PTE invalid", 0x12345678, PTE_INV, PTE_OK, ACC_LOAD, 1),
        ("U-mode on supervisor page", 0x12345678, PTE_OK, PTE_NU, ACC_LOAD, 0),
        ("accessed bit clear", 0x12345678, PTE_OK, PTE_NA, ACC_LOAD, 1),
    ]
    npos = sum(1 for x in cases if "MUST translate" in x[0])
    print("    %d positives / %d negatives" % (npos, len(cases) - npos))
    print()
    print("    %-36s %12s %7s %7s   %s" % ("case", "pa", "fault", "cause", "match"))
    ok = 0
    for nm, va, p1, p2, acc, priv in cases:
        gp, gf, gc = run(net, va, 0x80000, p1, p2, acc, priv)
        rp, rf, rc = ref(va, 0x80000, p1, p2, acc, priv)
        same = (gf == rf and gc == rc and (gf == 1 or gp == rp))
        print("    %-36s %12s %7d %7d   %s" % (nm, hex(gp), gf, gc, "OK" if same else "MISMATCH"))
        ok += same
    print()
    print("    %d/%d byte-exact vs an independent Sv32 reference." % (ok, len(cases)))
    print()
    print("  ALSO MEASURED, and it is a lever not a limit: the address arithmetic is DEPTH %d each"
          % d_a1)
    print("  because it uses the fabricator's RIPPLE `c.add` (S25: the only adder it has). S33's")
    print("  search found csa->kogge at a fraction of that for the same function. Not yet applied.")
    print()
    print("  NOT YET BUILT: the actual WALK (address -> fetch -> address -> fetch) with the PTEs")
    print("  addressed rather than supplied; superpage (level-1 leaf) translation; A/D write-back;")
    print("  TLB caching; SFENCE.VMA; wiring into pfc_riscv.py's memory path.")


if __name__ == "__main__":
    main()
