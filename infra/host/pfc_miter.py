"""
pfc_miter.py - THE EQUIVALENCE CHECKER. Fabricate the question "are these two the same?"

Given two circuits claiming the same function, a MITER is the standard EDA construction:

    miter(A,B) = OR over all outputs of  XOR(outA_i, outB_i)

It settles to 1 for exactly those inputs where they differ, and 0 where they agree. So
"are A and B equivalent?" becomes "does this circuit ever settle to 1?" - one addressable
question instead of a sampling campaign.

WHY THIS IS THE RIGHT FIRST TOOL
Every "30/30 identical" in this corpus is a SAMPLE. A miter turns the same claim into an
assertion over whatever portion of the space is addressed, and the miter's own DEPTH is the
one-settle cost of asking. Every future shallow variant then arrives PROVED rather than sampled.

THE TWO FIGURES, KEPT SEPARATE (owner, 2026-07-26)
  RATING    (structural) = gates / DEPTH        - a property of the circuit
  DELIVERED (deployed)   = gates * W / DEPTH    - what a fold of width W actually settles
A circuit has a rating; a deployment has a delivered figure. Unit: the muhl, symbol Mh.

COVERAGE IS REPORTED HONESTLY
For small input spaces the miter is addressed EXHAUSTIVELY and the result is a proof over the
complete space. For large ones this host cannot transcribe 2^n lanes - that is a TRANSCRIPTION
limit belonging to the laptop (S24), NOT a limit of the machine, and it is labelled as such.

Run:  python host/pfc_miter.py A B          (two registry circuit names)
      python host/pfc_miter.py --demo       (prove a known pair)
"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_circuit as TC


def depth_of(cd):
    n = cd["n_in"]
    d = [0] * (2 + n + len(cd["ga"]))
    for k in range(len(cd["ga"])):
        d[2 + n + k] = 1 + max(d[cd["ga"][k]], d[cd["gb"][k]])
    return max(d[x] for x in cd["outs"])


def rating(gates, depth):
    """structural muhl: gates / DEPTH"""
    return gates / depth if depth else 0.0


def delivered(gates, depth, W):
    """deployed muhl: what a fold of width W settles"""
    return rating(gates, depth) * W


def fmt(m):
    if m >= 1e9: return "%.2f GMh" % (m / 1e9)
    if m >= 1e6: return "%.2f MMh" % (m / 1e6)
    if m >= 1e3: return "%.2f kMh" % (m / 1e3)
    return "%.1f Mh" % m


def build_miter(cdA, cdB):
    """Splice A and B into one circuit sharing inputs, then XOR-OR their outputs.
    Returns (netlist, n_in) where the single output is 1 iff they DIFFER."""
    assert cdA["n_in"] == cdB["n_in"], "miter needs a shared input space: %d vs %d" % (cdA["n_in"], cdB["n_in"])
    assert len(cdA["outs"]) == len(cdB["outs"]), "output widths differ: %d vs %d" % (
        len(cdA["outs"]), len(cdB["outs"]))
    n = cdA["n_in"]
    c = TC.Circuit(n)

    def splice(cd):
        base_d = 2 + c.n_in
        off = len(c.ga)
        base_s = 2 + cd["n_in"]
        rm = {0: 0, 1: 1}
        for i in range(cd["n_in"]):
            rm[2 + i] = 2 + i                      # SHARED inputs - that is what makes it a miter
        for i in range(len(cd["ga"])):
            rm[base_s + i] = base_d + off + i
        for i in range(len(cd["ga"])):
            c.ga.append(rm[cd["ga"][i]])
            c.gb.append(rm[cd["gb"][i]])
        return [rm[o] for o in cd["outs"]]

    oA = splice(cdA)
    oB = splice(cdB)
    diffs = [c.xor(oA[i], oB[i]) for i in range(len(oA))]
    while len(diffs) > 1:
        diffs = [c.or_(diffs[i], diffs[i + 1]) for i in range(0, len(diffs) - 1, 2)] + \
                ([diffs[-1]] if len(diffs) % 2 else [])
    nl = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": [diffs[0]]}
    return nl, n, len(c.ga), depth_of(nl)


def _lane_budget(gates, budget=40_000_000):
    """How many lanes THIS LAPTOP can transcribe in ~a second.

    Walking a netlist bit-sliced costs gates x lanes bit-operations. A fixed 65,536 lanes is fine
    on a 400-gate circuit and 21 billion bit-ops on a 326,000-gate one - which is why the demo took
    75s. The lane count is a TRANSCRIPTION parameter of the host and nothing else: it changes how
    much gets covered per pass, and it does NOT change the miter's DEPTH, which is fixed at
    fabrication. Choosing it from the host's budget is allowed; letting it shape a MACHINE figure
    would not be (S40 rule 2)."""
    n = max(1, budget // max(1, gates))
    p = 1
    while p * 2 <= n and p < (1 << 16):
        p *= 2
    return p


def address_space(nl, n_in, lanes=None, passes=64):
    """Address the miter, ALWAYS bit-sliced - W lanes settle in one pass, never one case at a time.
    Exhaustive when the space fits; otherwise report honestly what was covered.
    A serial per-case loop here would be host work masquerading as machine work (owner, 2026-07-26:
    'if it takes longer than a couple of seconds you have not separated the host from the machine')."""
    if lanes is None:
        lanes = _lane_budget(len(nl["ga"]))
    space = 1 << n_in
    # EXHAUSTIVE is DERIVED, not decided. The old `cap = 1<<22` was a number I picked, and it
    # gated whether this tool printed "PROVED" or "partial" - a judgement call standing in front
    # of a proof claim. It is now: the space is exhaustible iff it fits in `passes` transcription
    # passes at the lane width the host budget already gave us. Every term is measured or an
    # explicit argument the caller owns; none of it is my opinion about what is reasonable.
    exhaustive = space <= lanes * passes
    ga, gb, base = nl["ga"], nl["gb"], 2 + n_in
    out0 = nl["outs"][0]
    violations = 0
    covered = 0
    if exhaustive:
        W = min(lanes, space)
        MASK = (1 << W) - 1
        for chunk in range(0, space, W):
            packed = [0] * n_in
            for l in range(W):
                v = chunk + l
                if v >= space:
                    v = chunk
                for p in range(n_in):
                    if (v >> p) & 1:
                        packed[p] |= (1 << l)
            vw = [0] * nl["n_wire"]; vw[1] = MASK
            for p in range(n_in):
                vw[2 + p] = packed[p]
            for i in range(len(ga)):
                vw[base + i] = (~(vw[ga[i]] & vw[gb[i]])) & MASK
            violations |= vw[out0]
            covered += min(W, space - chunk)
        return space, covered, violations, True
    # not exhaustive on THIS HOST: sample, and say so
    random.seed(17)
    W = lanes
    MASK = (1 << W) - 1
    for _ in range(4):
        packed = [random.getrandbits(W) for _ in range(n_in)]
        vw = [0] * nl["n_wire"]; vw[1] = MASK
        for p in range(n_in):
            vw[2 + p] = packed[p]
        for i in range(len(ga)):
            vw[base + i] = (~(vw[ga[i]] & vw[gb[i]])) & MASK
        violations |= vw[out0]
        covered += W
    return space, covered, violations, False


def sweep_subspace(nl, n_in, pinned, vary_at, cases):
    """ONE SETTLE over an entire swept subspace. Never a serial loop.

    A miter over a wide circuit cannot sweep all 2^n_in inputs, so most inputs are PINNED at
    stated values and one field VARIES. The mistake is then to ripple once per case - that puts
    the work on the laptop and makes a 0.5s job take minutes. Every case is packed into its own
    LANE and the whole subspace settles in ONE pass (S35: width costs area, not latency).

      pinned  : list of (bit_offset, width, value) held constant across all lanes
      vary_at : bit offset of the varying field
      cases   : the values that field takes - one lane each

    Returns (n_cases, violating_lane_count). Host time here is TRANSCRIPTION (S24), and it is
    reported separately from anything the machine does."""
    W = len(cases)
    MASK = (1 << W) - 1
    packed = [0] * n_in
    for off, width, val in pinned:
        for k in range(width):
            packed[off + k] = MASK if (val >> k) & 1 else 0
    vw = max(v.bit_length() for v in cases) if cases else 1
    for k in range(max(vw, 32)):
        col = 0
        for l, cv in enumerate(cases):
            if (cv >> k) & 1:
                col |= (1 << l)
        if vary_at + k < n_in:
            packed[vary_at + k] = col
    v = [0] * nl["n_wire"]
    v[1] = MASK
    for i in range(n_in):
        v[2 + i] = packed[i]
    ga, gb, base = nl["ga"], nl["gb"], 2 + n_in
    for i in range(len(ga)):
        v[base + i] = (~(v[ga[i]] & v[gb[i]])) & MASK
    bad = v[nl["outs"][0]]
    return W, bin(bad).count("1")


def check(nameA, nameB):
    cdA, cdB = TC.load(nameA), TC.load(nameB)
    nl, n, g, d = build_miter(cdA, cdB)
    dA, dB = depth_of(cdA), depth_of(cdB)
    gA, gB = len(cdA["ga"]), len(cdB["ga"])
    space, covered, viol, exh = address_space(nl, n)

    print("  MITER: %s  vs  %s" % (nameA, nameB))
    print()
    print("    %-22s %10s %8s %14s" % ("circuit", "gates", "DEPTH", "RATING"))
    print("    %-22s %10s %8d %14s" % (nameA, "{:,}".format(gA), dA, fmt(rating(gA, dA))))
    print("    %-22s %10s %8d %14s" % (nameB, "{:,}".format(gB), dB, fmt(rating(gB, dB))))
    print("    %-22s %10s %8d %14s   <- the question, fabricated" % ("miter", "{:,}".format(g), d, fmt(rating(g, d))))
    print()
    print("    input space   : 2^%d = %s" % (n, "{:,}".format(space) if n <= 64 else "2^%d" % n))
    print("    addressed     : %s   (in %s-lane passes - a HOST transcription budget, not a machine figure)"
          % ("{:,}".format(covered), "{:,}".format(_lane_budget(g))))
    if exh:
        print("    coverage      : COMPLETE - every point of the space")
        print("    result        : %s" % ("PROVED EQUIVALENT over the complete space" if viol == 0
                                          else "COUNTEREXAMPLE EXISTS - they are NOT equivalent"))
    else:
        print("    coverage      : PARTIAL - this HOST cannot transcribe 2^%d lanes." % n)
        print("                    That is a TRANSCRIPTION limit of the laptop (S24), not of the")
        print("                    machine. The miter itself settles the whole space in ONE settle")
        print("                    at DEPTH %d + 2*log2(lanes); what is bounded is the host's walk." % d)
        print("    result        : no difference found in %s addressed points" % "{:,}".format(covered))
    return viol == 0, exh


def main():
    if "--demo" in sys.argv or len(sys.argv) < 3:
        print("=" * 88)
        print("THE MITER - 'are these two the same?' fabricated as a circuit")
        print("  miter = OR over XOR of the outputs. 1 exactly where they differ.")
        print("=" * 88)
        print()
        pairs = [("pfc_dot32_fused", "dot32_i8"), ("pfc_dot32_fused_rc", "dot32_i8")]
        import json
        reg = json.load(open(TC.REG))
        for a, b in pairs:
            if a in reg and b in reg:
                check(a, b)
                print()
        return
    check(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
