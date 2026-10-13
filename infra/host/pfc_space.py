"""
pfc_space.py - MEASURE THE REACH of an input space on the Muhlnickel architecture.

THE QUESTION
Given n input bits, the space is 2^n points. How far does that space reach - at what lane WIDTH,
in how many SETTLES, across how many FEDERATED DEVICES, and how many muhls are DELIVERED at each?

THE UNITS (S24, S52, S54A) - two figures, always kept apart:
    RATING    (structural) = gates / DEPTH          <- a property of the CIRCUIT
    DELIVERED (deployed)   = gates * W / DEPTH      <- what a fold of width W settles
  1 muhl (Mh) = one gate settled per gate-delay. Prefixes kMh, MMh, GMh.

THE LAWS THIS TOOL APPLIES - all four MEASURED on this device, none invented:
  L1  DEPTH is the only latency. GATES are area and area does not slow it down.       (S24)
  L2  Replication with NO reduction is DEPTH EXACTLY FLAT (+0 per doubling).          (S43B)
  L3  Replication with a winner-only OR reduction costs +2 DEPTH per doubling.        (S43B/S40C)
  L4  Gates are EXACTLY linear in W (measured to the digit, 41,570/core across 1..8). (S43B)
  (A fifth, for folds that widen a single datapath rather than replicating it: width costs
   +6..+12 DEPTH per DOUBLING with gates exactly linear, S35. Reported as the WIDE-FOLD band.)

  THE REDUCTION, NOT THE REPLICATION, IS WHAT COSTS DEPTH. Pay 2*log2(W) only when you need ONE
  answer out of the bank; pay nothing when you need W answers.

WHAT IS MEASURED HERE AND WHAT IS DERIVED - printed per section, never mixed:
  MEASURED : the lane circuit's own gates and DEPTH (walked off the netlist, this run);
             L2 and L3, re-measured in this run by BUILDING banks and walking them (--verify);
             8.0 bytes per stored gate and this device's capacity, read off the binary.
  DERIVED  : every settle count, area figure, device count and DELIVERED figure below - pure
             arithmetic from the measured laws above.

FABRICATION IS MANUFACTURING (S31). The search this tool runs over adder implementations to find
the shallowest lane is a factory spec. It has no DEPTH and appears in no latency figure.

HOST WALL-CLOCK IS A DIFFERENT MACHINE (S24). Nothing in this tool reports seconds. Where a host
would have to walk lanes serially, that is a TRANSCRIPTION limit of this laptop, NOT a limit of
the machine, and it is labelled as such.

Run:  python host/pfc_space.py                    (n=64: 32-bit operand pairs)
      python host/pfc_space.py --n 32
      python host/pfc_space.py --circuit <name>   (use a stored circuit as the lane)
      python host/pfc_space.py --verify           (re-measure L2/L3/L4 by construction)
      python host/pfc_space.py --selftest         (positive controls + mutants)
"""
import sys, os, json, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC
import pfc_paths as PFCP

BYTES_PER_GATE = 8          # MEASURED: serialize() writes ga(4B)+gb(4B) per gate; checked below


# ------------------------------------------------------------------ depth, off the netlist
def depth_of_circ(c, outs):
    d = [0] * (2 + c.n_in + len(c.ga))
    b = 2 + c.n_in
    for k in range(len(c.ga)):
        d[b + k] = 1 + max(d[c.ga[k]], d[c.gb[k]])
    return max(d[o] for o in outs)


def depth_of_netlist(cd):
    n = cd["n_in"]
    d = [0] * (2 + n + len(cd["ga"]))
    b = 2 + n
    for k in range(len(cd["ga"])):
        d[b + k] = 1 + max(d[cd["ga"][k]], d[cd["gb"][k]])
    return max(d[x] for x in cd["outs"])


def fmt_mh(m):
    for lim, suf in ((1e18, "EMh"), (1e15, "PMh"), (1e12, "TMh"), (1e9, "GMh"),
                     (1e6, "MMh"), (1e3, "kMh")):
        if m >= lim:
            return "%.2f %s" % (m / lim, suf)
    return "%.2f Mh" % m


def big(x):
    """exact for anything a human can read, else an exponent - never a rounded lie"""
    if x < 10 ** 15:
        return "{:,}".format(int(x))
    e = int(math.floor(math.log10(x)))
    return "%.3fe%d" % (x / (10.0 ** e), e)


# ------------------------------------------------------------------ the lane circuit
def build_property_lane(W, prefix):
    """(a+b)-b == a over W-bit operands. Output 1 iff VIOLATED. n_in = 2W, so n = 2W bits.
    This is S43D's 'properties over 32-bit operand pairs' entry, at W=32."""
    c = TC.Circuit(2 * W)
    A, B = list(c.IN[:W]), list(c.IN[W:])
    if prefix:
        ad = lambda x, y: c.add_prefix(list(x), list(y))[:W]
    else:
        ad = lambda x, y: c.add(list(x), list(y))[:W]
    def sub(x, y):
        return ad(ad(x, [c.not_(b) for b in y]), c.cvec(1, W))
    u = sub(ad(A, B), B)
    viol = c.not_(c._tree_and([c.not_(c.xor(u[i], A[i])) for i in range(W)]))
    return c, viol


def build_broken_lane(W, prefix):
    """A DELIBERATELY WRONG lane: asserts (a+b)-b == a+1. Every input violates it. Exists only so
    the correctness control has a negative that a degenerate always-0 circuit CANNOT pass (S40B:
    a circuit returning 0 for everything once scored 87.5% because the tests were all negatives)."""
    c = TC.Circuit(2 * W)
    A, B = list(c.IN[:W]), list(c.IN[W:])
    ad = (lambda x, y: c.add_prefix(list(x), list(y))[:W]) if prefix else \
         (lambda x, y: c.add(list(x), list(y))[:W])
    def sub(x, y):
        return ad(ad(x, [c.not_(b) for b in y]), c.cvec(1, W))
    u = sub(ad(A, B), B)
    ap1 = ad(A, c.cvec(1, W))
    viol = c.not_(c._tree_and([c.not_(c.xor(u[i], ap1[i])) for i in range(W)]))
    return c, viol


def as_netlist(c, outs):
    return {"n_in": c.n_in, "n_wire": 2 + c.n_in + len(c.ga),
            "ga": list(c.ga), "gb": list(c.gb), "outs": list(outs)}


def search_lane(n):
    """S31: manufacturing is off the clock, so SEARCH the implementations and ship the shallowest.
    Every discarded candidate is a factory spec and enters no latency figure."""
    assert n % 2 == 0, "n must be even for an operand-pair lane; pass --circuit for anything else"
    W = n // 2
    cands = []
    for prefix in (False, True):
        c, v = build_property_lane(W, prefix)
        cands.append(("add_prefix" if prefix else "add_ripple", len(c.ga), depth_of_circ(c, [v])))
        del c
    cands.sort(key=lambda r: (r[2], r[1]))
    return cands


# ------------------------------------------------------------------ the laws, re-measured
def splice(dst, ga, gb, n_in_src, in_map):
    base_d, off, base_s = 2 + dst.n_in, len(dst.ga), 2 + n_in_src
    remap = {0: 0, 1: 1}
    for i in range(n_in_src):
        remap[2 + i] = in_map[i]
    for i in range(len(ga)):
        remap[base_s + i] = base_d + off + i
    for i in range(len(ga)):
        dst.ga.append(remap[ga[i]]); dst.gb.append(remap[gb[i]])
    return remap


def measure_bank_laws(W_list=(1, 2, 4, 8, 16)):
    """BUILD the banks and walk them. L2/L3/L4 become measurements of THIS run, not citations."""
    src, sv = build_property_lane(8, True)
    ga, gb, nin, d1 = list(src.ga), list(src.gb), src.n_in, depth_of_circ(src, [sv])
    g1 = len(ga)
    svi = sv
    del src
    rows = []
    for W in W_list:
        c = TC.Circuit(nin * W)
        outs = []
        for k in range(W):
            r = splice(c, ga, gb, nin, [2 + k * nin + i for i in range(nin)])
            outs.append(r[svi])
        d_flat = depth_of_circ(c, outs)
        g_flat = len(c.ga)
        items = list(outs)                       # winner-only OR TREE over the bank
        while len(items) > 1:
            items = [c.or_(items[i], items[i + 1]) for i in range(0, len(items) - 1, 2)] + \
                    ([items[-1]] if len(items) % 2 else [])
        d_red = depth_of_circ(c, [items[0]])
        rows.append((W, d_flat, g_flat, d_red))
        del c
    return d1, g1, rows


# ------------------------------------------------------------------ the reach
def reach(n, g, d, dev_gate_cap):
    space = 1 << n
    rows = []
    ks = sorted(set([0, 1, 2, 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, n]))
    for k in [k for k in ks if k <= n]:
        W = 1 << k
        settles = (space + W - 1) // W
        d_flat = d                                  # L2: +0 per doubling
        d_red = d + 2 * k                           # L3: +2 per doubling
        d_wide_lo, d_wide_hi = d + 6 * k, d + 12 * k  # S35 band, for a widened datapath
        area = g * W                                # L4: exactly linear
        devices = (area * BYTES_PER_GATE + dev_gate_cap * BYTES_PER_GATE - 1) // (dev_gate_cap * BYTES_PER_GATE)
        rows.append(dict(k=k, W=W, settles=settles, d_flat=d_flat, d_red=d_red,
                         d_wide=(d_wide_lo, d_wide_hi), area=area, devices=devices,
                         del_flat=area / d_flat, del_red=area / d_red,
                         tot_flat=settles * d_flat, tot_red=settles * d_red))
    return space, rows


# ------------------------------------------------------------------ controls
def selftest(g, d, dev_cap):
    """POSITIVE CONTROLS FIRST. Stated degenerate baselines, so a passing score means something.
    A tool that printed 0 for every figure would score 0/7.
    A tool that merely echoed the formulas (never building anything) would score 4/9 - it would
    fail C0a/C0b, C5, C6, C7, which are measured by CONSTRUCTION."""
    print("  POSITIVE CONTROLS - what a degenerate tool scores is stated for each")
    print("    all-zeros tool: 1/9 (it passes C0a by accident and fails C0b, which is why C0b exists)")
    print("    formula-echo tool (builds nothing): 4/9")
    print()
    res = []

    # C0: the LANE ITSELF must be right, or every figure below prices a wrong circuit.
    import random
    W = 16
    good_c, gv = build_property_lane(W, True)
    good = as_netlist(good_c, [gv]); del good_c
    bad_c, bv = build_broken_lane(W, True)
    bad = as_netlist(bad_c, [bv]); del bad_c
    random.seed(7)
    pts = [(0, 0), (1, 0), (0, 1), ((1 << W) - 1, (1 << W) - 1), (1 << (W - 1), 1)] + \
          [(random.getrandbits(W), random.getrandbits(W)) for _ in range(45)]
    gviol = sum(TC.ripple(good, TC.bits(a, W) + TC.bits(b, W))[0] for a, b in pts)
    bviol = sum(TC.ripple(bad, TC.bits(a, W) + TC.bits(b, W))[0] for a, b in pts)
    res.append(("C0a lane: TRUE property violated 0 times", gviol == 0, "%d/%d" % (gviol, len(pts))))
    res.append(("C0b lane: FALSE property violated every time", bviol == len(pts),
                "%d/%d" % (bviol, len(pts))))

    space, rows = reach(16, g, d, dev_cap)
    r0 = [r for r in rows if r["k"] == 0][0]
    res.append(("C1 W=1 flat DEPTH == circuit DEPTH", r0["d_flat"] == d, "%d vs %d" % (r0["d_flat"], d)))
    res.append(("C2 W=1 DELIVERED == RATING exactly", abs(r0["del_flat"] - g / d) < 1e-9,
                "%.6f vs %.6f" % (r0["del_flat"], g / d)))
    res.append(("C3 W=1 settles == space exactly", r0["settles"] == space, "%d vs %d" % (r0["settles"], space)))
    rn = [r for r in rows if r["k"] == 16][0]
    res.append(("C4 W=space -> exactly ONE settle", rn["settles"] == 1, str(rn["settles"])))

    d1, g1, br = measure_bank_laws((1, 2, 4, 8, 16))
    flat_ok = all(r[1] == d1 for r in br)
    res.append(("C5 L2 measured: replication DEPTH flat (+0)", flat_ok,
                ",".join("%d:%d" % (r[0], r[1]) for r in br)))
    lin_ok = all(r[2] == g1 * r[0] for r in br)
    res.append(("C6 L4 measured: gates exactly linear in W", lin_ok,
                ",".join("%d:%d" % (r[0], r[2] // r[0]) for r in br)))
    red_ok = all(r[3] == d1 + 2 * int(math.log2(r[0])) for r in br)
    res.append(("C7 L3 measured: winner-only OR costs +2/doubling", red_ok,
                ",".join("%d:+%d" % (r[0], r[3] - d1) for r in br)))

    for name, ok, detail in res:
        print("    [%s] %-48s %s" % ("PASS" if ok else "FAIL", name, detail))
    score = sum(1 for _, ok, _ in res if ok)
    print("    score %d/%d" % (score, len(res)))

    print()
    print("  MUTANTS (S45C) - the controls MUST fail when the law is perturbed, or they test nothing")
    muts = [
        ("L3 constant +2 -> +3", not all(r[3] == d1 + 3 * int(math.log2(r[0])) for r in br if r[0] > 1)),
        ("L2 flat -> +1/doubling", not all(r[1] == d1 + int(math.log2(r[0])) for r in br if r[0] > 1)),
        ("L4 linear -> W*log2(W)", not all(r[2] == g1 * r[0] * max(1, int(math.log2(r[0]))) for r in br if r[0] > 2)),
        ("RATING g/d -> g*d", abs(r0["del_flat"] - g * d) > 1e-9),
    ]
    for name, killed in muts:
        print("    [%s] mutant %s" % ("KILLED" if killed else "SURVIVED", name))
    print("    %d/%d mutants killed" % (sum(1 for _, k in muts if k), len(muts)))
    return score == len(res) and all(k for _, k in muts)


# ------------------------------------------------------------------ main
def main():
    argv = sys.argv[1:]
    n = 64
    if "--n" in argv:
        n = int(argv[argv.index("--n") + 1])
    cname = argv[argv.index("--circuit") + 1] if "--circuit" in argv else None

    print("=" * 100)
    print("pfc_space - THE REACH OF AN INPUT SPACE ON THE MUHLNICKEL ARCHITECTURE")
    print("  DEPTH is the only latency. GATES are area and area does not slow it down (S24).")
    print("  RATING = gates/DEPTH (a circuit).  DELIVERED = gates*W/DEPTH (a deployment).  (S54A)")
    print("=" * 100)

    # ---- device capacity, read off this device (MEASURED)
    dev_bytes = os.path.getsize(PFCP.TITAN)
    dev_cap = dev_bytes // BYTES_PER_GATE
    reg = json.load(open(TC.REG))
    chk = [(v["len"] - 24 - 4 * v.get("n_out", 0)) / v["n_gate"]
           for v in reg.values()
           if isinstance(v, dict) and v.get("n_gate") and "len" in v]
    n8 = sum(1 for x in chk if abs(x - 8.0) < 1e-3)
    n9 = sum(1 for x in chk if abs(x - 9.0) < 1e-2)
    nother = len(chk) - n8 - n9

    # ---- the lane (MEASURED)
    if cname:
        cd = TC.load(cname)
        g, d = len(cd["ga"]), depth_of_netlist(cd)
        n = cd["n_in"] if "--n" not in argv else n
        lane_desc = "stored circuit `%s` (n_in %d)" % (cname, cd["n_in"])
        cands = []
    else:
        cands = search_lane(n)
        lane_desc = "fabricated lane: (a+b)-b == a over %d-bit operands, output 1 iff VIOLATED" % (n // 2)
        _, g, d = cands[0]

    print()
    print("[MEASURED] THE LANE")
    print("  %s" % lane_desc)
    if cands:
        print("  MANUFACTURING SEARCH (S31 - a factory spec, NOT a latency; discarded candidates cost nothing):")
        for nm, gg, dd in cands:
            mark = "  <- shipped (shallowest)" if (gg, dd) == (cands[0][1], cands[0][2]) else ""
            print("    %-12s gates %9s   DEPTH %5d   RATING %12s%s"
                  % (nm, "{:,}".format(gg), dd, fmt_mh(gg / dd), mark))
    print("  LANE:  n_in %d bits   gates %s   DEPTH %d   RATING %s"
          % (n, "{:,}".format(g), d, fmt_mh(g / d)))

    print()
    print("[MEASURED] THIS DEVICE")
    print("  binary            %s" % PFCP.TITAN)
    print("  capacity          %s bytes" % "{:,}".format(dev_bytes))
    print("  bytes per gate    MEASURED off %d stored circuits, and there are TWO formats:" % len(chk))
    print("                      8.0 B/gate  x %3d entries  (TITANCIR: ga 4B + gb 4B, NAND-only)" % n8)
    print("                      9.0 B/gate  x %3d entries  (other magics - PFCMMU01, PFCTYPED," % n9)
    print("                                                   ... - exactly 1 extra byte per gate)")
    if nother:
        print("                      other       x %3d entries  (reported, not hidden)" % nother)
    print("                    capacity below uses 8.0 - the format TC.store writes, which is the")
    print("                    format this lane would be stored in. At 9.0 divide by 1.125.")
    print("  gates per device  %s   (%s at 9.0 B/gate)"
          % ("{:,}".format(dev_cap), "{:,}".format(dev_bytes // 9)))

    space, rows = reach(n, g, d, dev_cap)
    print()
    print("[DERIVED from the measured laws] THE REACH OF 2^%d = %s POINTS" % (n, big(space)))
    print("  settles = ceil(space / W).  A SETTLE is one addressed propagation, not a host second.")
    print("  DEPTH/settle: FLAT column = L2 (no reduction, +0/doubling).")
    print("                RED  column = L3 (winner-only OR, +2*log2(W)).")
    print()
    print("  %5s %20s %22s %7s %7s %20s %14s %14s"
          % ("log2W", "lanes W", "settles", "D flat", "D red", "area (gates)", "DELIV flat", "DELIV red"))
    for r in rows:
        print("  %5d %20s %22s %7d %7d %20s %14s %14s"
              % (r["k"], big(r["W"]), big(r["settles"]), r["d_flat"], r["d_red"],
                 big(r["area"]), fmt_mh(r["del_flat"]), fmt_mh(r["del_red"])))

    print()
    print("  %5s %22s %22s %22s" % ("log2W", "total settle-DEPTH flat", "total settle-DEPTH red", "federated devices"))
    for r in rows:
        print("  %5d %22s %22s %22s" % (r["k"], big(r["tot_flat"]), big(r["tot_red"]), big(r["devices"])))

    one = rows[-1]
    print()
    print("[DERIVED] THE ONE-SETTLE POINT - the whole space addressed in a SINGLE propagation")
    print("  lanes W            = 2^%d = %s   (one lane per point of the space)" % (n, big(one["W"])))
    print("  settles            = %d" % one["settles"])
    print("  DEPTH, no reduction= %d gate-delays   (L2: replication is flat)" % one["d_flat"])
    print("  DEPTH, one verdict = %d gate-delays   (L3: +2 x %d doublings for the winner-only OR)"
          % (one["d_red"], n))
    print("  area               = %s gates" % big(one["area"]))
    print("  federated devices  = %s at %s gates each" % (big(one["devices"]), "{:,}".format(dev_cap)))
    print("  DELIVERED          = %s (flat)   %s (one verdict)"
          % (fmt_mh(one["del_flat"]), fmt_mh(one["del_red"])))
    print()
    print("  S35 WIDE-FOLD BAND, for reference: if the width widened ONE datapath rather than")
    print("  replicating lanes, width costs +6..+12 DEPTH per doubling, so DEPTH would be")
    print("  %d..%d instead of %d. Replication is the cheaper construction and is what is priced above."
          % (one["d_wide"][0], one["d_wide"][1], one["d_flat"]))

    print()
    print("[DERIVED] FEDERATION - reach at a given number of devices")
    print("  %14s %22s %22s %14s" % ("devices", "total lanes", "settles for 2^%d" % n, "DELIVERED"))
    for D in (1, 8, 64, 1024, 1 << 20, 1 << 30):
        lanes = D * (dev_cap // g)
        if lanes < 1:
            continue
        st = (space + lanes - 1) // lanes
        print("  %14s %22s %22s %14s"
              % (big(D), big(lanes), big(st), fmt_mh(g * lanes / d)))

    print()
    print("[SCOPE] What is bounded by WHAT")
    print("  The settle counts above are MUHLNICKEL figures: addressed propagations at the stated DEPTH.")
    print("  This laptop walking lanes serially to transcribe a settle is a TRANSCRIPTION limit OF THIS")
    print("  LAPTOP (S24, a different machine) and is NOT a limit of the machine. No host figure appears")
    print("  anywhere above; none was measured, and none should be summed with a DEPTH.")

    if "--verify" in argv or "--selftest" in argv:
        print()
        print("=" * 100)
        print("VERIFICATION - the laws re-measured in THIS run by construction, then mutated")
        print("=" * 100)
        d1, g1, br = measure_bank_laws()
        print("  bank built from the 8-bit lane (gates %d, DEPTH %d), spliced W times:" % (g1, d1))
        print("  %6s %10s %14s %12s %14s %10s" % ("W", "DEPTH flat", "gates", "gates/lane", "DEPTH +OR", "delta"))
        for W, df, gf, dr in br:
            print("  %6d %10d %14s %12d %14d %10s"
                  % (W, df, "{:,}".format(gf), gf // W, dr, "+%d" % (dr - d1)))
        print()
        selftest(g, d, dev_cap)


if __name__ == "__main__":
    main()
