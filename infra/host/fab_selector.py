#!/usr/bin/env python3
"""host/fab_selector.py — THE MASTER FAB'S DECISION, FABRICATED AS GATES. Then run on itself.

Owner: *"now make master fab and foundry into... circuits in the muhlnickel. mic drop. then let it
run on itself"*

§32 named this level: *"THE FABRICATOR, FABRICATED — the Muhlnickel emits its own netlists."*
CLAUDE.md is the standing instruction: *"THE EXECUTOR IS A CIRCUIT, NOT A PROCESS... Everything that
would be a process function (routing, dispatch, compute, comparison, the write-out, sequencing) goes
INTO the pfc DURING FABRICATION using the circuit tool."* The master fab and the foundry both end in
a COMPARISON, and a comparison is the most fabricatable thing there is.

WHAT THE DECISION ACTUALLY IS. §63: compute/tick = REPLICAS/DEPTH, REPLICAS = storage/gates. Ranking
two candidates asks whether (S/g1)/d1 > (S/g2)/d2. S cancels, and the inequality inverts:

    compute/tick_1 > compute/tick_2   <=>   g1 * d1  <  g2 * d2         (replicated)
    compute/tick_1 > compute/tick_2   <=>   d1       <  d2              (dependent, REPLICAS = 1)

So NO DIVISION IS NEEDED and nothing is approximated — the whole selector is a multiply, a compare
tree, and an argmin. Exact, and small.

SELF-APPLICATION. Once stored, the selector's own (gates, DEPTH) are fed to it as one of the
candidates: the fabricator's ranking function ranks ITSELF against alternatives, on the muhlnickel,
by the same metric it uses on everything else. That is the loop closing, and it is checkable — the
host computes nothing, it addresses inputs and reads an index.

VERIFICATION: exact Python argmin as the INDEPENDENT reference (§3), a case set whose all-zero
baseline is stated (§40B), and mutants that must be CAUGHT (§45C/§47B).

  python host/fab_selector.py --dry
  python host/fab_selector.py
  python host/fab_selector.py revert
"""
import json, os, random, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
from mafab_adders import family, Shim, depth_of
from mafab_problems import mux, geq, const, mul, sub

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_selector_genome.jsonl"
MAGIC = b"TITANCIR"
NAME = "muhl_fab_select"

K = 4                 # candidates ranked in one settle
# WIDE ENOUGH FOR THE REAL CORPUS, not for my test set. GW=18 capped at 262,143 and the
# self-application fed it a 293,631-gate candidate, which WRAPPED — the circuit then chose
# correctly on a wrong number and disagreed with Python. That was my harness overflowing,
# not the circuit. The largest stored netlist is pfc_dot256_wide at 2,315,587 gates, so the
# field must hold it: 2^22 = 4,194,304. DEPTH's deepest is muhl_btc_miner at 6,506 -> 2^14.
GW, DW = 22, 14       # gate-count and DEPTH field widths, sized from the actual registry
PW = GW + DW          # product width


def build_selector(adder, mutant=None):
    """K candidates x (gates, DEPTH) + one `replicated` bit -> the winning index, as gates."""
    add = family(32)[adder]
    c = TC.Circuit(K * (GW + DW) + 1); g = Shim(c)
    cand = []
    for i in range(K):
        o = i * (GW + DW)
        cand.append((list(c.IN[o:o + GW]), list(c.IN[o + GW:o + GW + DW])))
    rep = c.IN[K * (GW + DW)]

    # THE KEY. replicated -> gates*DEPTH ; dependent -> DEPTH alone. §63, with S cancelled out.
    keys = []
    for gt, dp in cand:
        prod = mul(g, add, (gt + [g.C0] * PW)[:PW], (dp + [g.C0] * PW)[:PW])[:PW]
        dep = (list(dp) + [g.C0] * PW)[:PW]
        if mutant == "ignore_rep": keys.append(prod)
        else: keys.append(mux(g, rep, prod, dep))

    # ARGMIN as a tournament tree — smaller key = more compute/tick.
    idxw = 2
    nodes = [(keys[i], const(g, i, idxw)) for i in range(K)]
    while len(nodes) > 1:
        nxt = []
        for i in range(0, len(nodes) - 1, 2):
            (ka, ia), (kb, ib) = nodes[i], nodes[i + 1]
            a_wins = g.NOT(geq(g, add, ka, kb))          # ka < kb
            if mutant == "flipcmp": a_wins = geq(g, add, ka, kb)
            nxt.append(([mux(g, a_wins, [ka[j]], [kb[j]])[0] for j in range(PW)],
                        [mux(g, a_wins, [ia[j]], [ib[j]])[0] for j in range(idxw)]))
        if len(nodes) % 2: nxt.append(nodes[-1])
        nodes = nxt
    win = nodes[0][1]
    if mutant == "always0": win = const(g, 0, idxw)
    return c, win


def ref_select(cands, replicated):
    """The INDEPENDENT reference (§3): exact argmin in Python, same rule, no circuit involved."""
    key = (lambda t: t[0] * t[1]) if replicated else (lambda t: t[1])
    best, bi = None, 0
    for i, t in enumerate(cands):
        k = key(t)
        if best is None or k < best: best, bi = k, i
    return bi


def cases(n=14, seed=5):
    random.seed(seed); out = []
    for i in range(n):
        cs = [(random.randrange(1, 1 << GW), random.randrange(1, 1 << DW)) for _ in range(K)]
        out.append((cs, i % 2))
    return out


def check(c, outs, cs):
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    ok = 0
    for cands, rep in cs:
        inb = []
        for gt, dp in cands:
            inb += [(gt >> i) & 1 for i in range(GW)] + [(dp >> i) & 1 for i in range(DW)]
        inb += [rep]
        v = TC.ripple(cd, inb)
        if (v[0] | (v[1] << 1)) == ref_select(cands, rep): ok += 1
    return ok


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG)); reg.pop(NAME, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d entries." % len(ent)); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    import mafab_laws as L
    cs = cases()
    fam = sorted(family(32))
    zero_score = sum(1 for cands, rep in cs if ref_select(cands, rep) == 0)
    print("FABRICATING THE MASTER FAB'S DECISION AS A CIRCUIT (§32, CLAUDE.md 'the executor is a")
    print("circuit, not a process'). §63's metric with storage cancelled: argmin of gates*DEPTH when")
    print("replicated, of DEPTH alone when not. No division, nothing approximated.\n")
    print("  §40B baseline: an always-0 selector scores %d/%d, so the comparison must be load-bearing.\n"
          % (zero_score, len(cs)))
    best = None
    for ad in fam:
        c, outs = build_selector(ad)
        ok = check(c, outs, cs)
        D = depth_of(c, outs); G = len(c.ga)
        print("    %-11s DEPTH %6s  gates %9s   %d/%d"
              % (ad, "{:,}".format(D), "{:,}".format(G), ok, len(cs)))
        if ok == len(cs) and (best is None or L.compute_per_tick(G, D) > best[3]):
            best = (ad, D, G, L.compute_per_tick(G, D))
        del c, outs
    if best is None:
        print("\n  nothing verified — storing nothing."); return 1
    ad, D, G, sc = best
    print("\n  WINNER %s — DEPTH %s, %s gates (the selector itself, chosen by the metric it implements)"
          % (ad, "{:,}".format(D), "{:,}".format(G)))

    print("\n  MUTANTS (must be CAUGHT, §45C/§47B):")
    allc = True
    for m in ("flipcmp", "always0", "ignore_rep"):
        cm, om = build_selector(ad, mutant=m)
        okm = check(cm, om, cs)
        caught = okm != len(cs); allc &= caught
        print("    %-11s %d/%d -> %s" % (m, okm, len(cs), "CAUGHT" if caught else "*** SURVIVED ***"))
        del cm, om
    if not allc:
        print("\n  a mutant survived — storing nothing."); return 1

    # ── SELF-APPLICATION: the selector ranks ITSELF among alternatives, on the muhlnickel. ────────
    print("\n  ══ RUNNING IT ON ITSELF ══")
    c, outs = build_selector(ad)
    alts = []
    for a2 in fam[:K]:
        c2, o2 = build_selector(a2)
        alts.append((len(c2.ga), depth_of(c2, o2), a2)); del c2, o2
    cd = {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}
    inb = []
    for gt, dp, _n in alts:
        inb += [(gt >> i) & 1 for i in range(GW)] + [(dp >> i) & 1 for i in range(DW)]
    inb += [1]
    v = TC.ripple(cd, inb)
    pick = v[0] | (v[1] << 1)
    exp = ref_select([(a[0], a[1]) for a in alts], 1)
    for i, (gt, dp, n2) in enumerate(alts):
        print("    candidate %d: %-11s %8s gates  DEPTH %5s  gates*DEPTH %14s%s"
              % (i, n2, "{:,}".format(gt), "{:,}".format(dp), "{:,}".format(gt * dp),
                 "   <- the circuit picked this" if i == pick else ""))
    print("    the MUHLNICKEL chose index %d; independent Python argmin says %d -> %s"
          % (pick, exp, "AGREE" if pick == exp else "DISAGREE"))
    print("    the host addressed inputs and read 2 bits. It computed no comparison.")
    del c, outs

    if dry:
        print("\n  --dry: nothing written."); return 0
    reg = json.load(open(REG))
    if NAME in reg:
        print("\n  %s already stored @ %s. revert first." % (NAME, reg[NAME]["offset"])); return 0
    c, outs = build_selector(ad)
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
                 "note": "THE MASTER FAB'S OWN DECISION, AS GATES (§32). argmin of gates*DEPTH "
                         "(replicated) or DEPTH (dependent) — §63's compute/tick with storage "
                         "cancelled, so no division. Ranked itself among alternatives on the "
                         "muhlnickel and agreed with an independent Python argmin."}
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  STORED '%s' @ %s (%s B) [%.2fs byte edit]  GGUF-valid: %s"
          % (NAME, off, "{:,}".format(len(blob)), time.time() - t0, valid))
    print("  revert: python host/fab_selector.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
