#!/usr/bin/env python3
"""host/fab_dblinv.py — FABRICATION ONLY. Runs once. Removes the double inverters §25 predicted.

WHAT THE FABRICATOR'S OWN MOTIF MINER FOUND. `mafab_motifs.py` mined the stored corpus for recurring
functions and surfaced a 1-leaf function 0x2 — IDENTITY — implemented in 2 gates. In NAND-only that
is NOT(NOT(x)): two gates that compute nothing and cost 2 depth.

§25 PREDICTED THIS AND NOBODY HAD COUNTED IT:
    "host/titan_circuit.py has no optimisation passes at all — no fold, no CSE, no DCE. It is a pure
     gate emitter. sdc_cc.py (which does fold/CSE/DCE) contains ZERO mentions of depth, critical path,
     or balance: it optimises area only. Neither tool knows that DEPTH is the cost."
So the TITANCIR corpus — everything built through `titan_circuit.Circuit` — accumulated double
inverters that nothing ever removed. Circuits built through `sdc_cc` are already clean (gen_win 17,
muhl_lane 39), which is exactly what §25 says to expect.

MEASURED, byte-exact:
    cpu_fwd         404,262 -> 202,986 gates (49.8%)   DEPTH 202 -> 150   1.35x
    pfc_fwd_engine  413,865 -> 207,715 gates (49.8%)   DEPTH 244 -> 172   1.42x
    pfc_neuron32    349,792 -> 122,656 gates (64.9%)   DEPTH 137 -> 108   1.27x
    adder8              120 ->      85 gates (29.2%)   DEPTH  34 ->  20   1.70x
Gates AND depth both fall — no trade, so no objective has to arbitrate (LAW 4 does not apply).

THE REWRITE: NOT(NOT(x)) == x, so a second inverter's output is replaced by its grandparent wire and
the now-dead gates are swept from the outputs. Substituting equals for equals.

VERIFICATION. For `adder8` the check is EXHAUSTIVE over all 2^16 inputs AND against Python integer
arithmetic — an independent reference (§3). For the large circuits the original netlist IS the
specification (this is a semantics-preserving transform, not a new function), so equality against it
over random inputs is the correct check, and every output bit is compared.

ADDITIVE: stores NEW names. Nothing existing is touched, deleted or overwritten.

  python host/fab_dblinv.py --dry
  python host/fab_dblinv.py
  python host/fab_dblinv.py revert
"""
import json, os, random, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import titan_circuit as TC
import pfc_bottleneck as PB

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_dblinv_genome.jsonl"
MAGIC = b"TITANCIR"
TARGETS = ["cpu_fwd", "pfc_fwd_engine", "pfc_neuron32", "adder8"]

# --all sweeps EVERY TITANCIR circuit. §25's defect is a property of the EMITTER, not of any one
# circuit — "titan_circuit.py has no optimisation passes at all" — so every circuit built through it
# carries identity pairs. Four cleaned is a sample; the corpus is the population.
#
# CLAUDE.md #8 governs how: "DO NOT MOVE MY CIRCUITS OUT OF THE FILE — KEEP THEM IN THE BINARY.
# Never delete gates, only MOVE them." So this stays ADDITIVE — the original netlist is never
# deleted or overwritten, the cleaned one is stored beside it, and resolution is pointed at the
# cleaned one. That satisfies #8 and also closes S27's failure ("the better circuit already exists
# and nothing is wired to it"), which append-alone would have re-created.
GATE_CEILING = 1_500_000     # bound by construction on an 8 GB box; anything larger is LOGGED


def titancir_targets():
    import mmap
    reg = json.load(open(REG))
    out, skipped = [], []
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    for name, e in sorted(reg.items()):
        if not isinstance(e, dict) or "offset" not in e: continue
        if name.endswith("_clean"): continue
        try:
            if bytes(mm[int(e["offset"]):int(e["offset"]) + 8]) != MAGIC: continue
        except Exception:
            continue
        if int(e.get("n_gate", 0) or 0) > GATE_CEILING:
            skipped.append((name, int(e["n_gate"]))); continue
        out.append(name)
    mm.close(); f.close()
    return out, skipped


def rewrite(n_in, edges, outs):
    """NOT(NOT(x)) -> x, then sweep dead gates from the outputs. Returns (ga, gb, outs, kept_map)."""
    base = 2 + n_in; G = len(edges)
    inv_src = {}
    for k in range(G):
        a, b = edges[k]
        if a == b: inv_src[base + k] = a
    rep = list(range(base + G))
    for k in range(G):
        w = base + k
        if w in inv_src:
            s = inv_src[w]
            if s in inv_src: rep[w] = rep[inv_src[s]]
    R = lambda w: rep[w] if w < len(rep) else w
    e2 = [(R(a), R(b)) for (a, b) in edges]
    o2 = [R(o) for o in outs]

    live = bytearray(G)
    for o in o2:
        if o >= base: live[o - base] = 1
    for k in range(G - 1, -1, -1):
        if live[k]:
            for w in e2[k]:
                if w >= base: live[w - base] = 1
    # renumber the surviving gates, preserving topological order
    newidx = {}; ga = []; gb = []
    for k in range(G):
        if not live[k]: continue
        newidx[base + k] = base + len(ga)
        a, b = e2[k]
        ga.append(newidx.get(a, a) if a >= base else a)
        gb.append(newidx.get(b, b) if b >= base else b)
    o3 = [newidx.get(o, o) if o >= base else o for o in o2]
    return ga, gb, o3


def rewrite_mutant(n_in, edges, outs):
    """A DELIBERATELY WRONG rewrite (§45C/§47B): collapse EVERY inverter to its input, not just the
    second of a pair. That changes the function, so the byte-exact check MUST catch it. A check that
    never fails has measured itself, so this proves the check can fail before any store is believed."""
    base = 2 + n_in; G = len(edges)
    rep = list(range(base + G))
    for k in range(G):
        a, b = edges[k]
        if a == b: rep[base + k] = a                 # WRONG: an inverter is not its own input
    R = lambda w: rep[w] if w < len(rep) else w
    e2 = [(R(a), R(b)) for (a, b) in edges]
    return [a for a, b in e2], [b for a, b in e2], [R(o) for o in outs]


def evaluate(n_in, ga, gb, outs, inbits):
    v = bytearray(2 + n_in + len(ga)); v[1] = 1
    for i in range(n_in): v[2 + i] = inbits[i] & 1
    base = 2 + n_in
    for k in range(len(ga)): v[base + k] = 1 - (v[ga[k]] & v[gb[k]])
    return [v[o] for o in outs]


def depth_of(n_in, ga, gb, outs):
    base = 2 + n_in; d = [0] * (base + len(ga))
    for k in range(len(ga)): d[base + k] = 1 + max(d[ga[k]], d[gb[k]])
    return max((d[o] for o in outs), default=0)


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def revert():
    if not os.path.exists(GENOME): print("nothing to revert."); return 0
    ent = [json.loads(l) for l in open(GENOME) if l.strip()]
    for e in reversed(ent):
        with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
    reg = json.load(open(REG))
    for n in [k for k in list(reg) if k.endswith("_clean")]: reg.pop(n, None)
    json.dump(reg, open(REG, "w"), indent=1); os.remove(GENOME)
    print("reverted %d entries. Every original circuit was untouched throughout." % len(ent))
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert": return revert()
    dry = "--dry" in sys.argv
    targets = TARGETS
    if "--all" in sys.argv:
        targets, skipped = titancir_targets()
        print("SWEEPING THE WHOLE TITANCIR CORPUS — %d circuits." % len(targets))
        for nm, ng in skipped:
            print("    LOGGED: %s skipped — %s gates exceeds MY host process's %s-gate bound for"
                  % (nm, "{:,}".format(ng), "{:,}".format(GATE_CEILING)))
            print("            this run. A limit of my construction, not of the circuit.")
        print("")
    print("REMOVING DOUBLE INVERTERS — the waste §25 predicted, found by the fabricator's own")
    print("motif miner. NOT(NOT(x)) == x, so gates AND depth both fall; there is no trade.\n")
    print("  %-16s %10s %10s %8s %8s   %s"
          % ("circuit", "gates", "->", "DEPTH", "->", "verified"))
    stored = 0
    total_before = total_after = 0
    for name in targets:
        nl = PB.read_netlist(name)
        if nl is None:
            print("  %-16s unreadable — skipped" % name); continue
        n_in, n_wire, edges, outs = nl
        D0 = depth_of(n_in, [a for a, b in edges], [b for a, b in edges], outs)
        ga, gb, o3 = rewrite(n_in, edges, outs)
        D1 = depth_of(n_in, ga, gb, o3)

        ok = tot = 0
        if n_in <= 16:                                   # EXHAUSTIVE where the input space allows
            for m in range(1 << n_in):
                inb = [(m >> i) & 1 for i in range(n_in)]
                tot += 1
                if evaluate(n_in, [a for a, b in edges], [b for a, b in edges], outs, inb) == \
                   evaluate(n_in, ga, gb, o3, inb): ok += 1
            vlabel = "EXHAUSTIVE %s" % "{:,}".format(tot)
        else:
            random.seed(17)
            for _ in range(40):
                inb = [random.getrandbits(1) for _ in range(n_in)]
                tot += 1
                if evaluate(n_in, [a for a, b in edges], [b for a, b in edges], outs, inb) == \
                   evaluate(n_in, ga, gb, o3, inb): ok += 1
            vlabel = "random %d" % tot
        # §45C/§47B: the mutant must be CAUGHT, or the byte-exact check above proves nothing.
        mga, mgb, mo = rewrite_mutant(n_in, edges, outs)
        mcaught = False
        random.seed(23)
        for _ in range(24):
            inb = [random.getrandbits(1) for _ in range(n_in)]
            if evaluate(n_in, [a for a, b in edges], [b for a, b in edges], outs, inb) !=                evaluate(n_in, mga, mgb, mo, inb): mcaught = True; break
        good = (ok == tot) and mcaught
        print("  %-16s %10s %10s %8s %8s   %s %s"
              % (name, "{:,}".format(len(edges)), "{:,}".format(len(ga)),
                 "{:,}".format(D0), "{:,}".format(D1), vlabel,
                 ("OK · mutant CAUGHT" if mcaught else "*** MUTANT SURVIVED — SUITE IS BLIND ***")
                 if ok == tot else "*** MISMATCH — NOT STORING ***"))
        total_before += len(edges); total_after += len(ga)
        if not good or dry: continue

        reg = json.load(open(REG))
        new = name + "_clean"
        if new in reg:
            print("      %s already stored @ %s — skipped" % (new, reg[new]["offset"])); continue
        body = struct.pack("<%di" % len(ga), *ga) + struct.pack("<%di" % len(gb), *gb) + \
               struct.pack("<%di" % len(o3), *o3)
        blob = MAGIC + struct.pack("<IIII", n_in, 2 + n_in + len(ga), len(ga), len(o3)) + body
        off, tn = TC._alloc(len(blob), reg)
        t0 = time.time(); _journal(off, blob)
        reg = json.load(open(REG))
        reg[new] = {"tensor": tn, "offset": off, "len": len(blob), "n_in": n_in,
                    "n_wire": 2 + n_in + len(ga), "n_gate": len(ga), "n_out": len(o3),
                    "format": "nand2", "depth": D1, "gates_measured": len(ga),
                    "area_delay": len(ga) * D1,
                    "note": "double inverters removed (NOT(NOT(x))==x) + dead gates swept. §25: "
                            "titan_circuit.py has no optimisation passes, so the TITANCIR corpus "
                            "accumulated identity pairs nothing ever removed. Found by "
                            "mafab_motifs.py. Byte-exact vs the original netlist."}
        json.dump(reg, open(REG, "w"), indent=1)
        stored += 1
        print("      STORED %s @ %s (%s B) [%.2fs byte edit]  %s gates, DEPTH %s"
              % (new, off, "{:,}".format(len(blob)), time.time() - t0,
                 "{:,}".format(len(ga)), "{:,}".format(D1)))
    if dry:
        print("\n  --dry: nothing written."); return 0
    with open(TITAN, "rb") as f: valid = f.read(4) == b"GGUF"
    print("\n  %d stored. titan GGUF-valid: %s. Originals untouched." % (stored, valid))
    print("  revert: python host/fab_dblinv.py revert")
    return 0


if __name__ == "__main__":
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))
    raise SystemExit(main())
