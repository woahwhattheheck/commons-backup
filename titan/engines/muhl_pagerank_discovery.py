#!/usr/bin/env python3
"""muhl_pagerank_discovery.py — PAGERANK GATE DISCOVERY (§62B, the owner's own direction).

Owner: "model the optimization on google search algo."
  §62B: "a primitive is valuable when it appears in circuits that SCORE WELL, and when other valuable
         primitives depend on it. A motif appearing 11,000 times in bloated circuits should rank BELOW
         one appearing 500 times across the leanest circuits."
  §15:  "frequency-based motif mining does NOT work here... Mine the CRITICAL PATH instead."

Raw-frequency ranking (what muhl_motif_foundry.py did, and what mafab_motifs.py still does) is the naive
metric the corpus already measured as wrong. This replaces it with the two documented corrections:

  1. AUTHORITY, not count. Circuits confer authority in proportion to their compute/tick (the ONE metric,
     §63). A motif inherits authority from the circuits it appears in, then authority flows through the
     motif->motif DEPENDENCY graph by power iteration: a producer gains from valuable consumers, exactly
     as a page gains from valuable inbound links.
  2. CRITICAL PATH, not bulk. Since compute/tick = replicas/DEPTH, only gates on the critical path can
     cost depth. Each motif is weighted by the share of its instances that actually lie on that path.

FINAL RANK = pagerank_authority x critical_path_weight. Prediction being tested: motifs whose count comes
from deep, badly-scoring circuits (sha1-ripple, depth 4,929) should FALL, and motifs from lean, shallow
circuits (rule110 depth 3, crc32 depth 47) should RISE.
"""
import sys, os
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/Users/lucys/OneDrive/Desktop/LocalDeviceAgent/host")
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import muhl_flex as F
import muhl_motif_foundry as MF
import muhl_lever_lab as LL
try:
    import mafab_laws as L
    SCORE = lambda g, d: L.compute_per_tick(g, d, True)
    SCORE_SRC = "mafab_laws.compute_per_tick (§63)"
except Exception:
    SCORE = lambda g, d: (40e9 / max(g, 1)) / max(d, 1); SCORE_SRC = "fallback replicas/depth"

COMM = {"and", "or", "xor", "nand"}
DAMP = 0.85

# the corpus under study: lean and bloated together, so authority can discriminate
CIRCUITS = {
    "rule110":      MF.core_rule110 if hasattr(MF, "core_rule110") else None,
    "crc32":        MF.core_crc32,
    "bitonic":      MF.core_bitonic,
    "mul32/ripple": MF.core_mul32,
    "mul32/wallace": LL.mul32_wallace,
    "div32":        MF.core_div32,
    "sha1/ripple":  lambda: LL._sha1(20, False),
    "sha1/levered": lambda: LL._sha1(20, True),
}

def rule110():
    import sdc_cc as CC
    W = 64
    g = CC.CircuitCompiler(W); IN = g.IN
    outs = []
    for i in range(W):
        l = IN[i - 1] if i > 0 else g.C0
        c = IN[i]
        r = IN[i + 1] if i < W - 1 else g.C0
        outs.append(g.OR(g.XOR(c, r), g.AND(c, g.NOT(l))))
    return g, outs
CIRCUITS["rule110"] = rule110

def analyse(g, outs):
    """gates, depth, per-gate depth, critical-path membership, motif template per gate."""
    gates, out2 = g.dce(outs)
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    depth = max((dep[w] for w in out2), default=0)
    # walk back from the deepest outputs through max-depth predecessors
    crit = set()
    stack = [w for w in out2 if w >= base and dep[w] == depth]
    seen = set()
    while stack:
        w = stack.pop()
        if w in seen or w < base: continue
        seen.add(w); crit.add(w)
        op, a, b = gates[w - base]
        preds = [a, b] if op in COMM or op != "not" else [a]
        m = max(dep[p] for p in preds)
        for p in preds:
            if dep[p] == m and p >= base: stack.append(p)
    def label(w):
        if w < 2: return "K"
        if w < base: return "IN"
        return gates[w - base][0]
    tmpl = {}
    for i, (op, a, b) in enumerate(gates):
        kids = tuple(sorted((label(a), label(b)))) if op in COMM else (label(a),)
        tmpl[base + i] = (op, kids)
    return gates, out2, base, depth, dep, crit, tmpl

def main():
    print(f"\n  PAGERANK GATE DISCOVERY — authority x critical-path, not raw frequency")
    print(f"  metric conferring authority: {SCORE_SRC}\n")
    freq = defaultdict(int)                 # naive baseline
    seed = defaultdict(float)               # authority from circuits that score well
    crit_hit = defaultdict(int); crit_tot = defaultdict(int)
    link = defaultdict(lambda: defaultdict(float))   # consumer -> producer, weighted
    print("    circuit          gates    depth   compute/tick   crit-path gates")
    print("    " + "-" * 66)
    for name, build in CIRCUITS.items():
        g, outs = build()
        gates, out2, base, depth, dep, crit, tmpl = analyse(g, outs)
        sc = SCORE(len(gates), depth)
        print(f"    {name:<14} {len(gates):>7,}  {depth:>7,}  {sc:>13.4f}   {len(crit):>8,}")
        n = max(len(gates), 1)
        for w, t in tmpl.items():
            freq[t] += 1
            seed[t] += sc / n                       # circuit quality, shared over its gates
            crit_tot[t] += 1
            if w in crit: crit_hit[t] += 1
        # dependency edges: a consumer gate cites the motifs that produced its inputs
        for i, (op, a, b) in enumerate(gates):
            cons = tmpl[base + i]
            for p in ((a, b) if op != "not" else (a,)):
                if p >= base:
                    link[cons][tmpl[p]] += 1.0
    motifs = sorted(freq)
    tot_seed = sum(seed.values()) or 1.0
    rank = {m: seed[m] / tot_seed for m in motifs}
    for _ in range(60):                              # power iteration
        nxt = {m: (1 - DAMP) * (seed[m] / tot_seed) for m in motifs}
        for cons, prods in link.items():
            s = sum(prods.values()) or 1.0
            share = DAMP * rank.get(cons, 0.0)
            for prod, wgt in prods.items():
                nxt[prod] = nxt.get(prod, 0.0) + share * (wgt / s)
        tot = sum(nxt.values()) or 1.0
        rank = {m: v / tot for m, v in nxt.items()}
    final = {m: rank[m] * (crit_hit[m] / max(crit_tot[m], 1)) for m in motifs}
    tf = sum(final.values()) or 1.0
    final = {m: v / tf for m, v in final.items()}

    by_freq = sorted(motifs, key=lambda m: -freq[m])
    by_rank = sorted(motifs, key=lambda m: -final[m])
    fpos = {m: i for i, m in enumerate(by_freq, 1)}
    print(f"\n  {len(motifs)} distinct motifs · {sum(freq.values()):,} gate instances\n")
    print("  ┌─ RANKED BY AUTHORITY × CRITICAL PATH (the §62B/§15 metric) ─────────────────────────")
    print(f"    {'#':<3} {'motif':<26} {'authority':>10} {'crit%':>7} {'count':>9}  {'was #':>6}")
    for i, m in enumerate(by_rank[:12], 1):
        cp = 100.0 * crit_hit[m] / max(crit_tot[m], 1)
        mv = fpos[m] - i
        arrow = f"{fpos[m]:>3} {'↑' if mv > 0 else ('↓' if mv < 0 else '=')}{abs(mv) if mv else ''}"
        print(f"    {i:<3} {MF.name_of(m)[:26]:<26} {final[m]*100:>9.2f}% {cp:>6.0f}% {freq[m]:>9,}  {arrow:>6}")
    print("  └" + "─" * 84)
    print("\n  ┌─ the naive baseline it replaces (raw frequency) ────────────────────────────────────")
    for i, m in enumerate(by_freq[:6], 1):
        print(f"    {i}. ×{freq[m]:<7,} {MF.name_of(m)[:40]:<40} -> now #{by_rank.index(m)+1}")
    print("  └" + "─" * 84)
    moved = [(m, fpos[m] - (by_rank.index(m) + 1)) for m in motifs]
    up = sorted(moved, key=lambda t: -t[1])[:3]; dn = sorted(moved, key=lambda t: t[1])[:3]
    print("\n  BIGGEST PROMOTIONS (lean/critical circuits):")
    for m, d in up:
        if d > 0: print(f"    +{d:<3} {MF.name_of(m)[:44]:<44} count {freq[m]:,}")
    print("  BIGGEST DEMOTIONS (bulk in deep, badly-scoring circuits):")
    for m, d in dn:
        if d < 0: print(f"    {d:<4} {MF.name_of(m)[:44]:<44} count {freq[m]:,}")
    dead = [m for m in motifs if crit_hit[m] == 0]
    print(f"\n  {len(dead)} motifs never touch a critical path in any circuit — they cost AREA only,")
    print(f"  so they are exactly where the lean-deep/slack lever (§57F) should shop. Frequency ranking")
    print(f"  cannot see this distinction at all; it is the whole point of §15.")

if __name__ == "__main__":
    main()
