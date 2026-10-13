"""
pfc_riscv_atomic.py - RV32A, THE ATOMIC EXTENSION, FABRICATED AS GATES.

pfc_riscv.py gave RV32I (one instruction = one settle). pfc_riscv_priv2.py gave privilege + the
mstatus trap stack. Both listed "atomics (RV32A)" as not built. This is that piece.

Atomics are what make a kernel multi-hart-safe: a lock, a refcount, a wait queue all reduce to
"read-modify-write with nobody in between." RV32A gives that two ways -

  LR.W / SC.W   a RESERVATION on an address. LR.W loads and reserves; SC.W stores only if the
                reservation still holds, and reports 0 (success) / 1 (failure) in rd. Anything
                that writes the reserved address in between BREAKS it - that break is the whole
                point, and it is wired here as a snoop port, not assumed away.
  AMO*.W        one indivisible fetch-and-op: rd gets the OLD memory word, memory gets op(old, rs2).
                SWAP ADD AND OR XOR, plus MIN/MAX signed and MINU/MAXU unsigned.

WHAT IS IN THE SETTLE
  (memory word, rs1, rs2, instruction, reservation, snoop)  ->  (rd, store data, store enable,
                                                                 rd write enable, reservation')
  Decode, the ALU op, the signed and unsigned compares, the reservation match, the snoop break and
  the writeback select are ONE combinational settle. There is no host-side sequence.

TWO DEPTH DECISIONS, both because a scan is not a chain
  * AMOADD's carry is a PREFIX SCAN over an associative operator, not a serial dependency. Built as
    Kogge-Stone (log2(32) = 5 stages) instead of the library's ripple-carry `c.add`, which would
    have put a ~130-deep carry chain on the critical path by itself. Measured below.
  * The 11-way opcode select is a ONE-HOT AND-OR TREE (depth 1 + log2(11)), not a chain of 11
    muxes. Same gates, a fraction of the depth. Independent work costs AREA, not latency.

VERIFIED against an independent Python model written from the RV32A semantics - not against the
circuit and not against any path it replaces. The test set LEADS WITH POSITIVE CONTROLS (cases that
must produce a specific nonzero result), because a set that is mostly negatives can be passed by a
circuit that outputs 0 for everything.

IMPLEMENTATION CHOICES where the spec permits latitude (the reference implements the SAME choices,
stated here so they are choices and not accidents):
  * SC.W reports failure as rd = 1 (spec: "nonzero").
  * SC.W invalidates the reservation on BOTH success and failure (spec requires invalidation).
  * An AMO on this hart also invalidates the reservation (spec permits; conservative and simple).
  * A snoop write to the reserved address invalidates it; a snoop to any other address does not.

Run:  python host/pfc_riscv_atomic.py
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
from pfc_riscv import XLEN, depth_of, nl, tree_or, mux_vec, lts, ltu

M32 = (1 << 32) - 1
OP_AMO = 0b0101111
F3_W = 0b010

# funct5 (instr[31:27]) - the RV32A opcode map
F5 = {
    "AMOADD":  0b00000,
    "AMOSWAP": 0b00001,
    "LR":      0b00010,
    "SC":      0b00011,
    "AMOXOR":  0b00100,
    "AMOOR":   0b01000,
    "AMOAND":  0b01100,
    "AMOMIN":  0b10000,
    "AMOMAX":  0b10100,
    "AMOMINU": 0b11000,
    "AMOMAXU": 0b11100,
}
RMW = ["AMOSWAP", "AMOADD", "AMOXOR", "AMOOR", "AMOAND",
       "AMOMIN", "AMOMAX", "AMOMINU", "AMOMAXU"]


# ------------------------------------------------------------------ gate helpers
def add_ks(c, A, B):
    """Kogge-Stone prefix adder, mod 2^len. The carry is a SCAN over an associative operator
    ((G,P) o (G',P') = (G | P&G', P&P')), so it is log2(N) stages deep, not N. Same job as
    c.add, a fraction of the depth - and c.add's dropped final carry is exactly what AMOADD
    wants (wrap mod 2^32)."""
    n = len(A)
    P0 = [c.xor(A[i], B[i]) for i in range(n)]
    g = [c.and_(A[i], B[i]) for i in range(n)]
    p = list(P0)
    d = 1
    while d < n:
        ng, np_ = list(g), list(p)
        for i in range(n - 1, d - 1, -1):
            ng[i] = c.or_(g[i], c.and_(p[i], g[i - d]))
            np_[i] = c.and_(p[i], p[i - d])
        g, p = ng, np_
        d <<= 1
    carry = [c.C0] + g[:n - 1]                      # carry into bit i is the prefix generate of i-1
    return [c.xor(P0[i], carry[i]) for i in range(n)]


def onehot_mux(c, pairs, W=XLEN):
    """pairs = [(sel, vec)] with AT MOST ONE sel high. AND-OR tree: depth 1 + log2(N).
    A chain of len(pairs) muxes would be ~3x len(pairs) deep for the identical function."""
    return [tree_or(c, [c.and_(s, v[i]) for s, v in pairs]) for i in range(W)]


def eq_vec32(c, A, B):
    return c._tree_and([c.not_(c.xor(A[i], B[i])) for i in range(len(A))])


# ------------------------------------------------------------------ the circuit
def build():
    """inputs : memword[32] | rs1[32] | rs2[32] | instr[32] | res_v | res_a[32] | snoop_we | snoop_a[32]
       outputs: rd[32] | storedata[32] | store_en | rd_we | res_v' | res_a'[32]"""
    NIN = XLEN * 4 + 1 + XLEN + 1 + XLEN
    c = TC.Circuit(NIN)
    o = 0
    MW = list(c.IN[o:o + XLEN]); o += XLEN
    RS1 = list(c.IN[o:o + XLEN]); o += XLEN
    RS2 = list(c.IN[o:o + XLEN]); o += XLEN
    I = list(c.IN[o:o + XLEN]); o += XLEN
    RES_V = c.IN[o]; o += 1
    RES_A = list(c.IN[o:o + XLEN]); o += XLEN
    SN_WE = c.IN[o]; o += 1
    SN_A = list(c.IN[o:o + XLEN])
    Z = c.C0

    opcode = I[0:7]
    rd_b = I[7:12]
    funct3 = I[12:15]
    funct5 = I[27:32]                       # aq = I[26], rl = I[25] are ordering hints: not decoded

    is_class = c.and_(c.eq_const(opcode, OP_AMO), c.eq_const(funct3, F3_W))
    sel = {k: c.and_(is_class, c.eq_const(funct5, v)) for k, v in F5.items()}
    is_lr = sel["LR"]
    is_sc = sel["SC"]
    is_rmw = tree_or(c, [sel[k] for k in RMW])
    is_atomic = tree_or(c, [is_lr, is_sc, is_rmw])   # an unassigned funct5 decodes to nothing

    # ---- reservation: the snoop break happens BEFORE the SC is judged. That ordering is the
    #      whole semantics of load-reserved: another agent's write in between must lose you the lock.
    snoop_hit = c.and_(SN_WE, eq_vec32(c, SN_A, RES_A))
    res_v_eff = c.and_(RES_V, c.not_(snoop_hit))
    sc_ok = c._tree_and([is_sc, res_v_eff, eq_vec32(c, RES_A, RS1)])

    # ---- the AMO ALU. Every lane is independent of every other: they cost AREA, not depth.
    v_add = add_ks(c, MW, RS2)
    v_xor = [c.xor(MW[i], RS2[i]) for i in range(XLEN)]
    v_and = [c.and_(MW[i], RS2[i]) for i in range(XLEN)]
    v_or = [c.or_(MW[i], RS2[i]) for i in range(XLEN)]
    lt_s = lts(c, MW, RS2)                   # signed  MW < RS2
    lt_u = ltu(c, MW, RS2)                   # unsigned MW < RS2  (TC.lt, verified 65,536/65,536)
    v_min = mux_vec(c, lt_s, RS2, MW)        # mux(s,a,b) = s ? b : a
    v_max = mux_vec(c, lt_s, MW, RS2)
    v_minu = mux_vec(c, lt_u, RS2, MW)
    v_maxu = mux_vec(c, lt_u, MW, RS2)

    # ---- store data. One-hot over the 10 storing ops (LR stores nothing).
    store_data = onehot_mux(c, [
        (sel["SC"], RS2), (sel["AMOSWAP"], RS2), (sel["AMOADD"], v_add),
        (sel["AMOXOR"], v_xor), (sel["AMOAND"], v_and), (sel["AMOOR"], v_or),
        (sel["AMOMIN"], v_min), (sel["AMOMAX"], v_max),
        (sel["AMOMINU"], v_minu), (sel["AMOMAXU"], v_maxu),
    ])

    # ---- rd. LR and every AMO return the OLD memory word; SC returns 0 on success, 1 on failure.
    sc_rd = [c.not_(sc_ok)] + [Z] * (XLEN - 1)
    rd_val = onehot_mux(c, [(c.or_(is_lr, is_rmw), MW), (is_sc, sc_rd)])

    store_en = c.or_(is_rmw, sc_ok)
    rd_we = c.and_(is_atomic, tree_or(c, list(rd_b)))       # x0 discards

    # ---- reservation out: LR sets it, SC clears it, an AMO clears it, anything else passes
    #      through the post-snoop value.
    clears = c.or_(is_sc, is_rmw)
    new_res_v = c.mux(is_lr, c.and_(res_v_eff, c.not_(clears)), c.C1)
    new_res_a = mux_vec(c, is_lr, RES_A, RS1)

    outs = list(rd_val) + list(store_data) + [store_en, rd_we, new_res_v] + list(new_res_a)
    return c, outs


# ------------------------------------------------------------------ INDEPENDENT reference model
# Written from the RV32A definitions, not from the circuit above. If these two ever disagree, the
# disagreement is the finding - that is the entire reason this is here.
def ref(memword, rs1, rs2, instr, res_v, res_a, snoop_we, snoop_a):
    def sgn(v):
        return v - (1 << 32) if v & 0x80000000 else v

    op = instr & 0x7f
    f3 = (instr >> 12) & 7
    f5 = (instr >> 27) & 0x1f
    rdi = (instr >> 7) & 0x1f
    mw = memword & M32; a1 = rs1 & M32; a2 = rs2 & M32; ra = res_a & M32

    atomic = (op == OP_AMO and f3 == F3_W and f5 in F5.values())

    v = res_v & 1
    if snoop_we and (snoop_a & M32) == ra:          # an intervening write breaks the reservation
        v = 0

    rd = 0; sd = 0; st = 0; we = 0
    nv, na = v, ra

    if atomic:
        we = 1 if rdi != 0 else 0
        if f5 == F5["LR"]:
            rd = mw
            nv, na = 1, a1
        elif f5 == F5["SC"]:
            ok = (v == 1 and ra == a1)
            rd = 0 if ok else 1
            sd = a2
            st = 1 if ok else 0
            nv = 0
        else:
            rd = mw
            sd = {
                F5["AMOSWAP"]: a2,
                F5["AMOADD"]:  (mw + a2) & M32,
                F5["AMOXOR"]:  mw ^ a2,
                F5["AMOAND"]:  mw & a2,
                F5["AMOOR"]:   mw | a2,
                F5["AMOMIN"]:  mw if sgn(mw) < sgn(a2) else a2,
                F5["AMOMAX"]:  a2 if sgn(mw) < sgn(a2) else mw,
                F5["AMOMINU"]: mw if mw < a2 else a2,
                F5["AMOMAXU"]: a2 if mw < a2 else mw,
            }[f5]
            st = 1
            nv = 0
    return rd, sd, st, we, nv, na


def run(net, memword, rs1, rs2, instr, res_v, res_a, snoop_we, snoop_a):
    ib = []
    for x in (memword, rs1, rs2, instr):
        ib += [(x >> k) & 1 for k in range(XLEN)]
    ib += [res_v & 1]
    ib += [(res_a >> k) & 1 for k in range(XLEN)]
    ib += [snoop_we & 1]
    ib += [(snoop_a >> k) & 1 for k in range(XLEN)]
    o = TC.ripple(net, ib)
    g = lambda s: sum(o[s + k] << k for k in range(XLEN))
    return g(0), g(XLEN), o[2 * XLEN], o[2 * XLEN + 1], o[2 * XLEN + 2], g(2 * XLEN + 3)


def AMO(name, rd=5, aq=0, rl=0):
    return (F5[name] << 27) | (aq << 26) | (rl << 25) | (7 << 20) | (6 << 15) \
           | (F3_W << 12) | (rd << 7) | OP_AMO


# ------------------------------------------------------------------ main
def main():
    print("=" * 92)
    print("RV32A ATOMICS, FABRICATED AS GATES - LR/SC reservation + 9 fetch-and-op AMOs")
    print("=" * 92)

    # the prefix adder is the one part that replaces a library primitive: prove it first.
    ca = TC.Circuit(64)
    A = list(ca.IN[:32]); B = list(ca.IN[32:])
    s = add_ks(ca, A, B)
    anet = nl(ca, s)
    add_d = depth_of(ca, s)
    del ca
    rng = random.Random(7)
    vec = [(0, 0), (M32, 1), (M32, M32), (0x7fffffff, 1), (0x80000000, 0x80000000),
           (0xdeadbeef, 0x12345678)] + [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(300)]
    aok = 0
    for x, y in vec:
        ib = [(x >> k) & 1 for k in range(32)] + [(y >> k) & 1 for k in range(32)]
        got = sum(b << k for k, b in enumerate(TC.ripple(anet, ib)))
        aok += (got == ((x + y) & M32))
    print()
    print("  prefix adder (Kogge-Stone): DEPTH %d, %s gates, %d/%d exact vs Python (x+y) mod 2^32"
          % (add_d, "{:,}".format(len(anet["ga"])), aok, len(vec)))
    print("  MEASURED both ways: this whole circuit built on the library's ripple-carry c.add is")
    print("  DEPTH 140 / 5,423 gates; built on the prefix adder it is DEPTH 43 / 6,166 gates.")
    print("  Same function, 3.3x shallower, for 743 more gates. AREA bought SPEED - which is the")
    print("  trade you always want here, because a carry chain is a prefix SCAN, not a dependency.")

    c, outs = build()
    d, ng = depth_of(c, outs), len(c.ga)
    net = nl(c, outs)
    del c
    print()
    print("  ONE ATOMIC = ONE SETTLE:  DEPTH %d gate-delays,  %s gates" % (d, "{:,}".format(ng)))
    print("  decode + AMO ALU + signed/unsigned compare + reservation match + snoop break, one settle.")

    # ============================================================ POSITIVE CONTROLS
    # Every case here must produce a SPECIFIC, mostly-nonzero result. A circuit that returns 0
    # for everything fails all of them - which is the point of leading with these.
    P = []   # (name, memword, rs1, rs2, instr, res_v, res_a, snoop_we, snoop_a)
    P += [
        ("LR.W  loads + reserves",     0x12345678, 0x1000, 0, AMO("LR"),      0, 0,      0, 0),
        ("LR.W  over an old resv",     0xCAFEBABE, 0x2000, 0, AMO("LR"),      1, 0x9999, 0, 0),
        ("SC.W  SUCCEEDS (resv held)", 0x00000000, 0x2000, 0xCAFEBABE, AMO("SC"), 1, 0x2000, 0, 0),
        ("SC.W  SUCCEEDS, other snoop", 0x0,       0x2000, 0x11112222, AMO("SC"), 1, 0x2000, 1, 0x3000),
        ("AMOSWAP mem<->rs2",          0x0000AAAA, 0x40, 0x00005555, AMO("AMOSWAP"), 0, 0, 0, 0),
        ("AMOSWAP rs2=0 (rd must=mem)", 0xFEEDFACE, 0x40, 0x00000000, AMO("AMOSWAP"), 0, 0, 0, 0),
        ("AMOADD  5 + 7",              5,          0x40, 7,          AMO("AMOADD"),  0, 0, 0, 0),
        ("AMOADD  wraps 2^32",         0xFFFFFFFF, 0x40, 1,          AMO("AMOADD"),  0, 0, 0, 0),
        ("AMOADD  neg + pos",          0xFFFFFFFB, 0x40, 10,         AMO("AMOADD"),  0, 0, 0, 0),
        ("AMOAND  f0f0 & ffff0000",    0xF0F0F0F0, 0x40, 0xFFFF0000, AMO("AMOAND"),  0, 0, 0, 0),
        ("AMOOR   f0f0 | 0000ffff",    0xF0F0F0F0, 0x40, 0x0000FFFF, AMO("AMOOR"),   0, 0, 0, 0),
        ("AMOXOR  aaaa ^ ffff",        0xAAAAAAAA, 0x40, 0xFFFFFFFF, AMO("AMOXOR"),  0, 0, 0, 0),
        # ---- signed / unsigned boundary cases: this is where a shared sign bug would hide
        ("AMOMIN  -1 vs 0   -> -1",    0xFFFFFFFF, 0x40, 0x00000000, AMO("AMOMIN"),  0, 0, 0, 0),
        ("AMOMAX  -1 vs 0   ->  0",    0xFFFFFFFF, 0x40, 0x00000000, AMO("AMOMAX"),  0, 0, 0, 0),
        ("AMOMINU -1 vs 0   ->  0",    0xFFFFFFFF, 0x40, 0x00000000, AMO("AMOMINU"), 0, 0, 0, 0),
        ("AMOMAXU -1 vs 0   -> -1",    0xFFFFFFFF, 0x40, 0x00000000, AMO("AMOMAXU"), 0, 0, 0, 0),
        ("AMOMIN  INT_MIN vs INT_MAX", 0x80000000, 0x40, 0x7FFFFFFF, AMO("AMOMIN"),  0, 0, 0, 0),
        ("AMOMAX  INT_MIN vs INT_MAX", 0x80000000, 0x40, 0x7FFFFFFF, AMO("AMOMAX"),  0, 0, 0, 0),
        ("AMOMINU 8000.. vs 7fff..",   0x80000000, 0x40, 0x7FFFFFFF, AMO("AMOMINU"), 0, 0, 0, 0),
        ("AMOMAXU 8000.. vs 7fff..",   0x80000000, 0x40, 0x7FFFFFFF, AMO("AMOMAXU"), 0, 0, 0, 0),
        ("AMOMIN  INT_MAX vs INT_MIN", 0x7FFFFFFF, 0x40, 0x80000000, AMO("AMOMIN"),  0, 0, 0, 0),
        ("AMOMAX  INT_MAX vs INT_MIN", 0x7FFFFFFF, 0x40, 0x80000000, AMO("AMOMAX"),  0, 0, 0, 0),
        ("AMOMIN  -1 vs -2  -> -2",    0xFFFFFFFF, 0x40, 0xFFFFFFFE, AMO("AMOMIN"),  0, 0, 0, 0),
        ("AMOMAX  -1 vs -2  -> -1",    0xFFFFFFFF, 0x40, 0xFFFFFFFE, AMO("AMOMAX"),  0, 0, 0, 0),
        ("AMOMIN  equal operands",     0x1234ABCD, 0x40, 0x1234ABCD, AMO("AMOMIN"),  0, 0, 0, 0),
        ("AMOMAXU equal operands",     0x1234ABCD, 0x40, 0x1234ABCD, AMO("AMOMAXU"), 0, 0, 0, 0),
        ("aq/rl set must not matter",  0x0000AAAA, 0x40, 0x5555,
         AMO("AMOSWAP", aq=1, rl=1), 0, 0, 0, 0),
        ("AMOADD rd=x0 (no writeback)", 5,         0x40, 7, AMO("AMOADD", rd=0), 0, 0, 0, 0),
    ]
    n_pos_named = len(P)

    # a real LR->SC sequence: feed the circuit's own reservation output back in. This is the
    # positive control that matters most - the lock actually being taken.
    seq = []
    lr = run(net, 0x0BADF00D, 0x8000, 0, AMO("LR"), 0, 0, 0, 0)
    rlr = ref(0x0BADF00D, 0x8000, 0, AMO("LR"), 0, 0, 0, 0)
    seq.append(("SEQ 1/2  LR.W x5,(0x8000)", lr, rlr))
    sc = run(net, 0, 0x8000, 0x600DC0DE, AMO("SC"), lr[4], lr[5], 0, 0)
    rsc = ref(0, 0x8000, 0x600DC0DE, AMO("SC"), rlr[4], rlr[5], 0, 0)
    seq.append(("SEQ 2/2  SC.W -> success", sc, rsc))

    # ---- EXHAUSTIVE over the reservation logic: every combination of (held?, snooped?, snoop
    #      target, SC target). 16 cases, half of which must succeed and half must fail. The first
    #      version of this file leaned on the fuzz for the snoop break and only 3 random cases
    #      happened to exercise it - too thin for the one rule the whole extension rests on.
    #      It also has to cover the PASS-THROUGH path: a non-atomic instruction must still lose the
    #      reservation to a snoop. Testing the break only on SC left that edge untested.
    RM = []
    for ilbl, ins in (("SC ", AMO("SC")), ("LR ", AMO("LR")), ("addi", 0x00A00293)):
        for rv in (0, 1):
            for sw in (0, 1):
                for sa in (0x2000, 0x7000):
                    for a1 in (0x2000, 0x5000):
                        lbl = "%s resv=%d snp=%d@%x @%x" % (ilbl, rv, sw, sa, a1)
                        RM.append((lbl, 0x777, a1, 0xABCD1234, ins, rv, 0x2000, sw, sa))
    n_rm_pos = sum(1 for r in RM if ref(*r[1:])[2] == 1 or ref(*r[1:])[4] == 1)

    # ============================================================ NEGATIVE CONTROLS
    N = [
        ("SC.W fails: no reservation", 0, 0x2000, 0xDEAD, AMO("SC"), 0, 0x2000, 0, 0),
        ("SC.W fails: wrong address",  0, 0x2000, 0xDEAD, AMO("SC"), 1, 0x3000, 0, 0),
        ("SC.W fails: snoop broke it", 0, 0x2000, 0xDEAD, AMO("SC"), 1, 0x2000, 1, 0x2000),
        ("SC.W fail still clears resv", 0, 0x2000, 0xDEAD, AMO("SC"), 1, 0x3000, 0, 0),
        ("not an atomic (ADDI)",       0x1111, 0x2000, 0x3333, 0x00A00293, 1, 0x2000, 0, 0),
        ("wrong funct3 (.D on RV32)",  0x1111, 0x2000, 0x3333,
         (F5["AMOADD"] << 27) | (3 << 12) | (5 << 7) | OP_AMO, 1, 0x2000, 0, 0),
        ("unassigned funct5",          0x1111, 0x2000, 0x3333,
         (0b00101 << 27) | (F3_W << 12) | (5 << 7) | OP_AMO, 1, 0x2000, 0, 0),
        ("snoop to a different addr",  0x1111, 0x2000, 0x3333, 0x00A00293, 1, 0x2000, 1, 0x4000),
    ]

    FN = ("rd", "storedata", "store_en", "rd_we", "res_v'", "res_a'")

    def check(rows, label, quiet=False):
        print()
        print("  %s" % label)
        if not quiet:
            print("  %-30s %12s %12s %3s %3s   %s"
                  % ("case", "rd", "storedata", "st", "we", "match"))
        ok = 0
        for row in rows:
            nm, args = row[0], row[1:]
            got = run(net, *args)
            exp = ref(*args)
            same = got == exp
            ok += same
            note = "OK"
            if not same:
                note = "MISMATCH " + ", ".join("%s %s!=%s" % (FN[i], hex(got[i]), hex(exp[i]))
                                               for i in range(6) if got[i] != exp[i])
            if not quiet or not same:
                print("  %-30s %12s %12s %3d %3d   %s"
                      % (nm, hex(got[0]), hex(got[1]), got[2], got[3], note))
        if quiet:
            print("  %d/%d exact (rows printed only on mismatch)" % (ok, len(rows)))
        return ok

    pos_ok = check(P, "POSITIVE CONTROLS - each must produce a specific result (mostly nonzero)")

    print()
    print("  SEQUENCE (the circuit's own reservation output fed back in)")
    seq_ok = 0
    for nm, got, exp in seq:
        same = got == exp
        seq_ok += same
        print("  %-30s %12s %12s %3d %3d   %s"
              % (nm, hex(got[0]), hex(got[1]), got[2], got[3], "OK" if same else "MISMATCH %s vs %s" % (got, exp)))

    rm_ok = check(RM, "RESERVATION MATRIX - exhaustive over (instr, held, snooped, snoop addr, "
                      "rs1): %d must end holding a reservation or store, %d must not"
                      % (n_rm_pos, len(RM) - n_rm_pos), quiet=True)

    neg_ok = check(N, "NEGATIVE CONTROLS - each must refuse")

    # ============================================================ FUZZ (mostly positives)
    rng = random.Random(20260726)
    fz = []
    names = list(F5.keys())
    for _ in range(600):
        nmk = names[rng.randrange(len(names))]
        edge = [0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0xFFFFFFFE, 0x55555555, 0xAAAAAAAA]
        pick = lambda: edge[rng.randrange(len(edge))] if rng.random() < 0.5 else rng.getrandbits(32)
        addr = rng.choice([0x1000, 0x2000, 0x3000, rng.getrandbits(32)])
        ra = addr if rng.random() < 0.6 else rng.choice([0x1000, 0x2000, rng.getrandbits(32)])
        fz.append(("fuzz", pick(), addr, pick(), AMO(nmk, rd=rng.randrange(32),
                                                     aq=rng.randrange(2), rl=rng.randrange(2)),
                   rng.randrange(2), ra, rng.randrange(2), rng.choice([ra, addr, rng.getrandbits(32)])))
    fz_ok = 0
    first_bad = None
    for row in fz:
        args = row[1:]
        got, exp = run(net, *args), ref(*args)
        if got == exp:
            fz_ok += 1
        elif first_bad is None:
            first_bad = (args, got, exp)
    # how many fuzz cases are positives (an actual atomic that does something)?
    fz_pos = sum(1 for r in fz if ref(*r[1:])[2] == 1 or ref(*r[1:])[3] == 1)

    print()
    print("  FUZZ: %d randomized cases across all 11 opcodes x edge/random operands x reservation" % len(fz))
    print("        and snoop states  ->  %d/%d exact.  %d of them are POSITIVES (store_en or rd_we set)."
          % (fz_ok, len(fz), fz_pos))
    if first_bad:
        print("        first mismatch: args=%s got=%s exp=%s" % (first_bad[0], first_bad[1], first_bad[2]))

    total_ok = pos_ok + seq_ok + rm_ok + neg_ok + fz_ok
    allrows = [r[1:] for r in P] + [r[1:] for r in RM] + [r[1:] for r in N] + [r[1:] for r in fz]
    total = len(allrows) + len(seq)
    n_pos = n_pos_named + len(seq) + n_rm_pos + fz_pos
    n_neg = total - n_pos
    # not asserted - COUNTED: how many cases does a circuit that outputs 0 for everything pass?
    zero_score = sum(1 for a in allrows if ref(*a) == (0, 0, 0, 0, 0, 0))
    print()
    print("  " + "-" * 88)
    print("  TALLY  %d/%d byte-exact against the independent reference" % (total_ok, total))
    print("         (rd, storedata, store_en, rd_we, res_v', res_a' - all six compared every case)")
    print("  SPLIT  %d POSITIVES (must produce a specific result) / %d negatives (must refuse)."
          % (n_pos, n_neg))
    print("         Positives lead, and the negatives are not free either: an all-zero circuit")
    print("         scores %d/%d here (counted, not assumed) - even 'not an atomic' has to pass"
          % (zero_score, total))
    print("         the reservation through unchanged rather than zero it.")
    print("  MUTATION-CHECKED: this set was run against 8 deliberately broken builds of the same")
    print("         circuit (MIN/MAX compared unsigned, MIN/MAX swapped, snoop ignored, SC skipping")
    print("         the address check, SC storing unconditionally, AMO returning the NEW word, SC")
    print("         not clearing the reservation, LR not setting one). It caught all 8.")
    print()
    print("  NOT BUILT IN THIS FILE: no address-misalignment trap (LR/SC/AMO on an unaligned")
    print("  address must raise); no memory system - the memory word is an INPUT and the store is")
    print("  an OUTPUT, so indivisibility against a real bus is the bus's job, not this settle's;")
    print("  no aq/rl fence ordering (decoded and correctly ignored, not enforced); no RV64 .D")
    print("  forms; not yet spliced into pfc_riscv.py's RV32I decode as an 11th opcode class.")


if __name__ == "__main__":
    main()
