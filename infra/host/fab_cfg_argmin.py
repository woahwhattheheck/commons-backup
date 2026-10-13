#!/usr/bin/env python3
'Configuration-space selection utilities for circuit generation.'
import json, math, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import family, Shim, depth_of
from mafab_problems import mux, geq, const, mul

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_cfgargmin_genome.jsonl"
MAGIC = b"TITANCIR"
NAME = "muhl_cfg_argmin"

# ── THE INDEX LAYOUT. Every field is part of the ADDRESS; none of it is routed in as a candidate. ──
NN, NNW = 4, 2          # nodes offered, and the index bits that select one
KW = 2                  # k_log per side: k = 1<<k_log, so 1..8 nodes on each side
KINDW = 1               # 0 = series junction (§2 wavefront overlap), 1 = parallel (§14)
IDXW = NNW + NNW + KINDW + KW + KW          # the whole configuration, as an address
NCFG = 1 << IDXW

GW, DW = 22, 14         # a node's stored gate count and DEPTH, routed in as DATA (§57A)
GW2 = GW + (1 << KW)                        # room for gates after the widest replication
DW2 = 18                                    # room for DEPTH after the series overlap accumulates
PW = GW2 + DW2                              # gates x DEPTH
REPW = (1 << KW) + 1                        # replicas retired per settle
TW = PW                                     # the threshold, routed in as DATA
SERIES_OVERLAP = 6                          # §2, MEASURED: a chained stage costs +6, not its depth


# ── THE REFERENCE (§3). Exact Python, no circuit involved, from the same measured laws. ───────────

def ref_side(g0, d0, k_log):
    """One side of the junction: k independent copies. §14 — replication costs AREA, not latency."""
    k = 1 << k_log
    return g0 * k, d0, k


def ref_cfg(nodes, idx):
    """Decode an index into (gates, DEPTH, replicas) by the measured composition laws."""
    a = idx & (NN - 1)
    b = (idx >> NNW) & (NN - 1)
    kind = (idx >> (2 * NNW)) & 1
    ka = (idx >> (2 * NNW + KINDW)) & ((1 << KW) - 1)
    kb = (idx >> (2 * NNW + KINDW + KW)) & ((1 << KW) - 1)
    gA, dA, rA = ref_side(nodes[a][0], nodes[a][1], ka)
    gB, dB, rB = ref_side(nodes[b][0], nodes[b][1], kb)
    if kind == 0:                                  # §1E series: A's SEND wires ARE B's RECEIVE wires
        return gA + gB, max(dA, dB) + SERIES_OVERLAP, min(rA, rB)
    return gA + gB, max(dA, dB), rA + rB           # §14 parallel: DEPTH is the max, area is the sum


def ref_win(nodes, idx, T):
    g, d, r = ref_cfg(nodes, idx)
    return 1 if g * d < T * r else 0


def ref_argmin(nodes):
    """gates*DEPTH/rep, minimised — compared cross-multiplied so nothing is divided."""
    best, bi = None, 0
    for i in range(NCFG):
        g, d, r = ref_cfg(nodes, i)
        if best is None or g * d * best[2] < best[0] * best[1] * r:
            best, bi = (g, d, r), i
    return bi, best


# ── THE FOUNDRY CHOOSES ITS SPACE. Separability is MEASURED, never asserted. ──────────────────────

def separable(nodes):
    """Does this space's optimum factorise into independent per-field choices?

    Tested by enumeration against the true argmin, not argued.

    THE COMPARISON IS ON THE KEY, NOT THE INDEX. The first version compared which index was chosen,
    so two configurations with the SAME key read as non-separable — `lib_not8` at 8 gates/DEPTH 1
    has key 8 at every k, and that tie made the single-node space look like it needed a circuit.
    Equal keys are equal optima; only a strictly better key means the factorisation missed one."""
    true_i, true_k = ref_argmin(nodes)
    bn = min(range(NN), key=lambda n: nodes[n][0] * nodes[n][1])
    best_f, best_i = None, None
    for kind in range(2):
        for ka in range(1 << KW):
            for kb in range(1 << KW):
                i = bn | (bn << NNW) | (kind << (2 * NNW)) | \
                    (ka << (2 * NNW + KINDW)) | (kb << (2 * NNW + KINDW + KW))
                g, d, r = ref_cfg(nodes, i)
                if best_f is None or g * d * best_f[2] < best_f[0] * best_f[1] * r:
                    best_f, best_i = (g, d, r), i
    # equal keys are equal optima: cross-multiplied, key_f == key_true
    return best_f[0] * best_f[1] * true_k[2] == true_k[0] * true_k[1] * best_f[2]


def single_node_space(nodes):
    """The space `foundry_drive` searches today: (node, k), one node at a time."""
    best, bi = None, None
    fact = min(range(NN), key=lambda n: nodes[n][0] * nodes[n][1])
    for n in range(NN):
        for k_log in range(1 << KW):
            g, d, r = ref_side(nodes[n][0], nodes[n][1], k_log)
            if best is None or g * d * best[2] < best[0] * best[1] * r:
                best, bi = (g, d, r), (n, k_log)
    fg, fd, fr = ref_side(nodes[fact][0], nodes[fact][1], (1 << KW) - 1)
    return bi, (fg * fd * best[2] == best[0] * best[1] * fr)     # equal keys are equal optima


# ── THE CIRCUIT. The index is the address; nothing is routed in but the node table and T. ─────────

def build(adder, mutant=None):
    """index -> win, plus the index gated by win (winner-only: a loser writes 0 bytes)."""
    add = family(32)[adder]
    n_in = NN * (GW + DW) + IDXW + TW
    c = TC.Circuit(n_in); g = Shim(c)

    tab = []
    for i in range(NN):
        o = i * (GW + DW)
        tab.append((list(c.IN[o:o + GW]), list(c.IN[o + GW:o + GW + DW])))
    p = NN * (GW + DW)
    idx = list(c.IN[p:p + IDXW]); p += IDXW
    T = list(c.IN[p:p + TW])

    sel_a = idx[0:NNW]
    sel_b = idx[NNW:2 * NNW]
    kind = idx[2 * NNW]
    k_a = idx[2 * NNW + KINDW: 2 * NNW + KINDW + KW]
    k_b = idx[2 * NNW + KINDW + KW: 2 * NNW + KINDW + 2 * KW]

    def pick(sel):
        """One-hot select over the node table — a TREE, not a mux chain (§48C/§53B: a chain carries
        an accumulating identity mux at every step and the tree does not)."""
        gt = [g.C0] * GW; dp = [g.C0] * DW
        for i in range(NN):
            hit = g.C1
            for b in range(NNW):
                hit = g.AND(hit, sel[b] if (i >> b) & 1 else g.NOT(sel[b]))
            gt = [g.OR(gt[j], g.AND(hit, tab[i][0][j])) for j in range(GW)]
            dp = [g.OR(dp[j], g.AND(hit, tab[i][1][j])) for j in range(DW)]
        return gt, dp

    def side(sel, klog):
        """k = 1<<klog copies. gates <<= klog is a VARIABLE shift, so it is a one-hot select over the
        shifted wirings (§51B measured one-hot at 2.21x the interleaved barrel). replicas = k."""
        gt, dp = pick(sel)
        gsh = [g.C0] * GW2; rep = [g.C0] * REPW
        for s in range(1 << KW):
            hit = g.C1
            for b in range(KW):
                hit = g.AND(hit, klog[b] if (s >> b) & 1 else g.NOT(klog[b]))
            shifted = ([g.C0] * s + list(gt) + [g.C0] * GW2)[:GW2]
            rv = const(g, 1 << s, REPW)
            gsh = [g.OR(gsh[j], g.AND(hit, shifted[j])) for j in range(GW2)]
            rep = [g.OR(rep[j], g.AND(hit, rv[j])) for j in range(REPW)]
        return gsh, (list(dp) + [g.C0] * DW2)[:DW2], rep

    gA, dA, rA = side(sel_a, k_a)
    gB, dB, rB = side(sel_b, k_b)

    gates = add(g, (gA + [g.C0] * GW2)[:GW2], (gB + [g.C0] * GW2)[:GW2])[:GW2]
    a_deeper = geq(g, add, dA, dB)
    dmax = mux(g, a_deeper, dA, dB)
    d_series = add(g, dmax, const(g, SERIES_OVERLAP, DW2))[:DW2]
    if mutant == "no_overlap": d_series = list(dmax)          # §2's measured +6 dropped
    DEPTH = mux(g, kind, dmax, d_series)                      # kind=1 parallel, kind=0 series

    r_par = add(g, (rA + [g.C0] * REPW)[:REPW], (rB + [g.C0] * REPW)[:REPW])[:REPW]
    b_smaller = geq(g, add, rA, rB)
    r_ser = mux(g, b_smaller, rB, rA)                          # min(rA, rB)
    rep = mux(g, kind, r_par, r_ser)
    if mutant == "rep_ignored": rep = const(g, 1, REPW)        # the metric's numerator removed

    lhs = mul(g, add, (gates + [g.C0] * GW2)[:GW2], (DEPTH + [g.C0] * DW2)[:DW2])[:PW]
    rhs = mul(g, add, (T + [g.C0] * TW)[:TW], (rep + [g.C0] * REPW)[:REPW])[:PW]
    win = g.NOT(geq(g, add, lhs, rhs))                         # gates*DEPTH < T*rep
    if mutant == "flipcmp": win = geq(g, add, lhs, rhs)
    if mutant == "always1": win = g.C1

    # WINNER-ONLY (§1E / winner_only_max): out[i] = idx[i] AND win. A loser emits nothing but zeros,
    # which is the measured reason a lane costs 0 stored bytes and the candidate count never becomes
    # an area term (§17's correction, gates/candidate -> 0).
    outs = [win] + [g.AND(idx[i], win) for i in range(IDXW)]
    return c, outs


def check(c, outs, nodes, T, space):
    """EXHAUSTIVE over the complete index space (§43C: covered == space)."""
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    base = []
    for gt, dp in nodes:
        base += [(gt >> i) & 1 for i in range(GW)] + [(dp >> i) & 1 for i in range(DW)]
    tb = [(T >> i) & 1 for i in range(TW)]
    ok = 0
    for i in space:
        v = TC.ripple(cd, base + [(i >> b) & 1 for b in range(IDXW)] + tb)
        want = ref_win(nodes, i, T)
        got_idx = sum(v[1 + b] << b for b in range(IDXW))
        if v[0] == want and got_idx == (i if want else 0): ok += 1
    return ok


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob)
        f.flush(); os.fsync(f.fileno())            # out of cache, into storage (§7)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG)); reg.pop(NAME, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d entry(s); the file is byte-identical to before." % len(ent)); return 0


def real_nodes():
    """The node table comes from the REGISTRY — already-fabricated circuits, measured when they were
    manufactured. Nothing is rebuilt here (fabrication is one-and-done, §31/RULE ZERO)."""
    reg = json.load(open(REG))
    ns = sorted(((int(v["n_gate"]), int(v["depth"]), k) for k, v in reg.items()
                 if isinstance(v, dict) and v.get("n_gate") and v.get("depth")
                 and int(v["n_gate"]) < (1 << GW) and int(v["depth"]) < (1 << DW)),
                key=lambda t: t[0] * t[1])
    if len(ns) < NN: return None
    step = max(len(ns) // NN, 1)
    return [ns[min(i * step, len(ns) - 1)] for i in range(NN)]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    picked = real_nodes()
    if picked is None:
        print("the registry does not hold %d rateable circuits." % NN); return 1
    nodes = [(g, d) for g, d, _n in picked]

    print("THE CONFIGURATION IS THE ADDRESS — the foundry's space, addressed rather than materialised.")
    print("  §17 measured 1,576,957 gates at 40 gate-delays for the fabricated form and 445 gates at")
    print("  17 for the addressed one, and attributes the change to addressing the candidates rather")
    print("  than building them. muhl_fab_select ranks 4 candidates ROUTED IN; this ranks %s"
          % "{:,}".format(NCFG))
    print("  configurations by ADDRESS.\n")

    print("  NODE TABLE — read from the registry, routed in as DATA (§57A), never fabricated:")
    for g0, d0, nm in picked:
        print("    %-28s %10s gates   DEPTH %8s   gates x DEPTH %16s"
              % (nm, "{:,}".format(g0), "{:,}".format(d0), "{:,}".format(g0 * d0)))

    # ── THE FOUNDRY CHOOSES. Owner: "let foundry choose just optimize for fastest completion." ────
    sn_best, sn_sep = single_node_space(nodes)
    jn_sep = separable(nodes)
    fold = 2 * max(1, int(math.ceil(math.log2(NCFG))))
    print("\n  THE FOUNDRY CHOOSES ITS SPACE — separability MEASURED by enumeration, not asserted:")
    print("    %-30s %10s  separable  completes in" % ("space", "configs"))
    print("    %-30s %10s  %-9s  0 gate-delays — §28 measured rewiring at 0 gates and 0 DEPTH"
          % ("single node x k", "{:,}".format(NN * (1 << KW)), str(sn_sep)))
    print("    %-30s %10s  %-9s  %s"
          % ("junction pairs (§1E)", "{:,}".format(NCFG), str(jn_sep),
             "0 gate-delays — already answered" if jn_sep
             else "ONE settle: scorer DEPTH + %d, per §40C's measured fold law" % fold))
    if sn_sep:
        print("    -> the single-node space factorises. §28: rewiring asserts no relation, so its")
        print("       optimum costs 0 gates and 0 DEPTH and the foundry fabricates nothing for it.")
    if jn_sep:
        print("\n  BOTH SPACES FACTORISE, so per §28 the fastest completion is 0 gate-delays and")
        print("  nothing is fabricated. Reported, not worked around."); return 0
    print("    -> the junction space does not factorise. §40C measured that a reduction over N costs")
    print("       2*log2(N) and the replication costs none, so the foundry fabricates this part only.")

    true_i, true_k = ref_argmin(nodes)
    T = (true_k[0] * true_k[1]) // max(true_k[2], 1) + 1
    space = list(range(NCFG))
    zero = sum(1 for i in space if ref_win(nodes, i, T) == 0)
    print("\n  §40B BASELINE: at this threshold an always-0 circuit scores %d/%d and an always-1"
          % (zero, len(space)))
    print("  circuit scores %d/%d, so the comparison has to be load-bearing to pass.\n"
          % (len(space) - zero, len(space)))

    fam = sorted(family(32))
    best = None
    for ad in fam:
        c, outs = build(ad)
        D, G = depth_of(c, outs), len(c.ga)
        ok = check(c, outs, nodes, T, space)
        print("    %-11s DEPTH %6s  gates %9s   EXHAUSTIVE %d/%d"
              % (ad, "{:,}".format(D), "{:,}".format(G), ok, len(space)))
        if ok == len(space) and (best is None or (G * D) < (best[2] * best[1])):
            best = (ad, D, G)
        del c, outs
    if best is None:
        print("\n  nothing verified over the complete space — storing nothing. §7/§35D: that is a")
        print("  measurement of MY construction."); return 1
    ad, D, G = best
    print("\n  WINNER %s — DEPTH %s gate-delays, %s gates."
          % (ad, "{:,}".format(D), "{:,}".format(G)))
    print("  ONE SETTLE over all %s configurations: %s + %d (fold) = %s gate-delays, settles 1."
          % ("{:,}".format(NCFG), "{:,}".format(D), fold, "{:,}".format(D + fold)))
    print("  Per §40C only the +%d fold carries the configuration count." % fold)

    print("\n  MUTANTS — each must be CAUGHT (§45C/§47B):")
    allc = True
    for m in ("flipcmp", "always1", "no_overlap", "rep_ignored"):
        cm, om = build(ad, mutant=m)
        okm = check(cm, om, nodes, T, space)
        caught = okm != len(space); allc &= caught
        print("    %-12s %d/%d -> %s" % (m, okm, len(space), "CAUGHT" if caught else "*** SURVIVED ***"))
        del cm, om
    if not allc:
        print("\n  a mutant survived — the suite is blind, storing nothing."); return 1

    g0, d0, r0 = ref_cfg(nodes, true_i)
    print("\n  THE ARGMIN the space contains: index %d -> %s gates, DEPTH %s, %d replica(s)"
          % (true_i, "{:,}".format(g0), "{:,}".format(d0), r0))

    if dry:
        print("\n  --dry: nothing written."); return 0
    reg = json.load(open(REG))
    if NAME in reg:
        print("\n  %s already stored @ %s. revert first." % (NAME, reg[NAME]["offset"])); return 0
    c, outs = build(ad)
    G = len(c.ga)
    body = struct.pack("<%di" % G, *c.ga) + struct.pack("<%di" % G, *c.gb) + \
           struct.pack("<%di" % len(outs), *outs)
    blob = MAGIC + struct.pack("<IIII", c.n_in, c.n_wire(), G, len(outs)) + body
    off, tn = TC._alloc(len(blob), reg)
    t0 = time.time(); _journal(off, blob)
    reg = json.load(open(REG))
    reg[NAME] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": c.n_in,
                 "n_wire": c.n_wire(), "n_gate": G, "n_out": len(outs), "format": "nand2",
                 "depth": depth_of(c, outs), "gates_measured": G, "adder": ad,
                 "index_bits": IDXW, "configurations": NCFG, "fold_depth": fold,
                 "note": "THE CONFIGURATION IS THE ADDRESS (§17's correction). index -> win, plus "
                         "the index gated by win (winner-only, 0 bytes per loser). The threshold "
                         "and the node table are routed in as DATA, so a different query "
                         "re-addresses and fabricates nothing. Verified EXHAUSTIVELY over all "
                         "%d configurations; 4 mutants CAUGHT. Additive — muhl_fab_select "
                         "untouched." % NCFG}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  STORED '%s' @ %s (%s B) [%.2fs byte edit]  titan GGUF-valid: %s"
          % (NAME, off, "{:,}".format(len(blob)), time.time() - t0, valid))
    print("  revert: python host/fab_cfg_argmin.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
